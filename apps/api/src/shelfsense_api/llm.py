"""The one way Shelfsense calls a model: Ollama, JSON-schema-constrained, with token and time accounting."""

import asyncio
import gzip
import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

import ollama
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode
from opentelemetry.util.types import AttributeValue

from shelfsense_api import metrics
from shelfsense_api.settings import settings

# Failures that may go away by themselves: worth retrying later. The rest need a different input or prompt.
_tracer = trace.get_tracer(__name__)

TRANSIENT_CODES = frozenset({"model_timeout", "model_unavailable"})


class ModelError(Exception):
    def __init__(self, code: str, message: str, content: str | None = None):
        super().__init__(message)
        self.code = code
        # The reply text, when the model did reply (an invalid reply is shown back to it on a retry).
        self.content = content


@dataclass
class ModelReply:
    answer: dict[str, Any]
    # (token, logprob) pairs of the reply, for scoring how sure the model was of a value.
    tokens: list[tuple[str, float]]
    model: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int
    prompt_eval_ms: int
    eval_ms: int


@dataclass(frozen=True)
class ModelConfig:
    """Which model to call and how; every value comes from settings."""

    model: str
    num_ctx: int
    timeout_s: float
    keep_alive: str
    logprobs: bool = True


def enrich_model() -> ModelConfig:
    return ModelConfig(settings.llm_model, settings.llm_num_ctx, settings.llm_timeout_s, settings.llm_keep_alive)


def query_model() -> ModelConfig:
    return ModelConfig(settings.query_model, settings.query_num_ctx, settings.query_timeout_s,
                       settings.query_keep_alive, logprobs=False)


@dataclass
class Cassette:
    """Model replies recorded by prompt hash, so an eval can replay a live run without Ollama (evals/run.py). Off
    unless an eval installs one with use_cassette. `calls` logs each call's key and recorded wall time, so replayed
    latencies equal the live ones."""

    path: Path
    mode: Literal["record", "replay"]
    entries: dict[str, dict[str, Any]] = field(default_factory=dict)
    calls: list[tuple[str, int]] = field(default_factory=list)

    def save(self) -> None:
        with gzip.open(self.path, "wt", encoding="utf-8") as f:
            for key in sorted(self.entries):
                f.write(json.dumps(self.entries[key], sort_keys=True) + "\n")


_cassette: Cassette | None = None


def use_cassette(path: Path, mode: Literal["record", "replay"]) -> Cassette:
    """Record model calls to `path` (gzipped JSON lines), or answer every call from it. Recording starts empty and
    answers a prompt it has already recorded from the recording, so one run asks the model each prompt once."""
    global _cassette
    entries: dict[str, dict[str, Any]] = {}
    if mode == "replay":
        with gzip.open(path, "rt", encoding="utf-8") as f:
            entries = {e["key"]: e for e in map(json.loads, f)}
    _cassette = Cassette(path, mode, entries)
    return _cassette


def stop_cassette() -> None:
    """Back to calling the model directly."""
    global _cassette
    _cassette = None


def _call_key(config: "ModelConfig", messages: list[dict[str, str]], schema: dict[str, Any]) -> str:
    request = {"model": config.model, "messages": messages, "format": schema, "logprobs": config.logprobs,
               "num_ctx": config.num_ctx, "temperature": settings.llm_temperature, "timeout_s": config.timeout_s}
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


async def chat_json(system: str, user: str, schema: dict[str, Any], follow_up: list[dict[str, str]] | None = None,
                    config: ModelConfig | None = None, prompt_version: str | None = None) -> ModelReply:
    """One constrained chat call (the enrichment model unless `config` says otherwise). `follow_up` continues the
    conversation after `user`, e.g. the model's rejected reply and the reason it was rejected."""
    config = config or enrich_model()
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}, *(follow_up or [])]
    if _cassette is None:
        return await _call(config, messages, schema, prompt_version)
    key = _call_key(config, messages, schema)
    entry = _cassette.entries.get(key)
    if entry is None and _cassette.mode == "replay":
        raise LookupError(f"no recorded reply for this prompt in {_cassette.path}; run the eval with LIVE=1")
    if entry is None:
        started = time.perf_counter()
        try:
            entry = {"reply": asdict(await _call(config, messages, schema, prompt_version))}
        except ModelError as exc:
            entry = {"error": {"code": exc.code, "message": str(exc), "content": exc.content}}
        entry |= {"key": key, "model": config.model, "wall_ms": round((time.perf_counter() - started) * 1000)}
        _cassette.entries[key] = entry
    _cassette.calls.append((key, entry["wall_ms"]))
    if "error" in entry:
        raise ModelError(entry["error"]["code"], entry["error"]["message"], entry["error"]["content"])
    reply = entry["reply"]
    return ModelReply(**reply | {"tokens": [tuple(t) for t in reply["tokens"]]})


async def _call(config: ModelConfig, messages: list[dict[str, str]], schema: dict[str, Any],
                prompt_version: str | None = None) -> ModelReply:
    """One Ollama call in a `chat <model>` client span with GenAI semantic-convention attributes (docs/adr/0022).
    No prompt or reply text goes on the span: only models, token counts and speed."""
    attributes: dict[str, AttributeValue] = {
        "gen_ai.operation.name": "chat", "gen_ai.provider.name": "ollama",
        "gen_ai.system": "ollama",  # the attribute's name before semconv moved it to gen_ai.provider.name
        "gen_ai.request.model": config.model, "server.address": settings.ollama_host}
    if prompt_version:
        attributes["shelfsense.prompt_version"] = prompt_version
    labels = {"model": config.model}
    with _tracer.start_as_current_span(f"chat {config.model}", kind=SpanKind.CLIENT, attributes=attributes) as span:
        metrics.llm_inflight.add(1, labels)
        try:
            reply = await _ollama(config, messages, schema)
        except ModelError as exc:
            span.set_status(Status(StatusCode.ERROR))
            span.set_attribute("error.type", exc.code)
            raise
        finally:
            metrics.llm_inflight.add(-1, labels)
        span.set_attributes({
            "gen_ai.response.model": reply.model, "gen_ai.usage.input_tokens": reply.prompt_tokens,
            "gen_ai.usage.output_tokens": reply.output_tokens,
            "shelfsense.tokens_per_second": round(reply.output_tokens / (reply.eval_ms / 1000), 1) if reply.eval_ms else 0.0})
        metrics.llm_tokens.add(reply.prompt_tokens, labels | {"type": "input"})
        metrics.llm_tokens.add(reply.output_tokens, labels | {"type": "output"})
        return reply


async def _ollama(config: ModelConfig, messages: list[dict[str, str]], schema: dict[str, Any]) -> ModelReply:
    client = ollama.AsyncClient(host=settings.ollama_host)
    try:
        async with asyncio.timeout(config.timeout_s):
            response = await client.chat(
                model=config.model,
                messages=messages,
                format=schema,
                logprobs=config.logprobs,
                options={"temperature": settings.llm_temperature, "num_ctx": config.num_ctx},
                keep_alive=config.keep_alive,
            )
    except TimeoutError:
        raise ModelError("model_timeout", f"no reply within {config.timeout_s:g}s") from None
    except ollama.ResponseError as exc:
        # 5xx (Ollama overloaded or crashed) may pass; a 4xx (unknown model, bad request) won't.
        code = "model_unavailable" if exc.status_code >= 500 else "model_request_rejected"
        raise ModelError(code, f"{exc.status_code}: {exc.error}") from exc
    except ConnectionError as exc:
        raise ModelError("model_unavailable", str(exc)) from exc

    prompt_tokens = response.prompt_eval_count or 0
    # Ollama cuts an over-long prompt to num_ctx without an error; a prompt that fills the window was cut.
    if prompt_tokens >= config.num_ctx:
        raise ModelError("prompt_truncated", f"prompt filled num_ctx {config.num_ctx}")
    if response.done_reason == "length":
        raise ModelError("output_truncated", "the model hit its output limit")
    content = response.message.content or ""
    try:
        answer = json.loads(content)
    except ValueError as exc:
        raise ModelError("invalid_model_output", f"reply is not JSON: {exc}", content) from exc

    return ModelReply(
        answer=answer,
        tokens=[(lp.token, lp.logprob) for lp in response.logprobs or []],
        model=response.model or config.model,
        prompt_tokens=prompt_tokens,
        output_tokens=response.eval_count or 0,
        total_ms=(response.total_duration or 0) // 1_000_000,
        prompt_eval_ms=(response.prompt_eval_duration or 0) // 1_000_000,
        eval_ms=(response.eval_duration or 0) // 1_000_000,
    )


def value_probability(tokens: list[tuple[str, float]], value: str) -> float:
    """The model's probability of writing the string `value` in its reply: the product of the probabilities of
    the tokens spelling it, closing quote included (that quote is where "50" and "500" part ways). The logprobs
    are the model's own, before the JSON grammar masks tokens, so a value the grammar forced on it scores low."""
    text = "".join(token for token, _ in tokens)
    needle = f'"{value}"'
    start = text.find(needle)
    if start < 0:
        return 0.0
    span_start, span_end = start + 1, start + len(needle)
    logprob, pos = 0.0, 0
    for token, token_logprob in tokens:
        end = pos + len(token)
        if end > span_start and pos < span_end:
            logprob += token_logprob
        pos = end
    return math.exp(logprob)
