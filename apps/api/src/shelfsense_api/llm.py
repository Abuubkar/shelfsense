"""The one way Shelfsense calls a model: Ollama, JSON-schema-constrained, with token and time accounting."""

import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any

import ollama

from shelfsense_api.settings import settings

# Failures that may go away by themselves: worth retrying later. The rest need a different input or prompt.
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


async def chat_json(system: str, user: str, schema: dict[str, Any],
                    follow_up: list[dict[str, str]] | None = None) -> ModelReply:
    """One constrained chat call. `follow_up` continues the conversation after `user`, e.g. the model's rejected
    reply and the reason it was rejected."""
    client = ollama.AsyncClient(host=settings.ollama_host)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}, *(follow_up or [])]
    try:
        async with asyncio.timeout(settings.llm_timeout_s):
            response = await client.chat(
                model=settings.llm_model,
                messages=messages,
                format=schema,
                logprobs=True,
                options={"temperature": settings.llm_temperature, "num_ctx": settings.llm_num_ctx},
                keep_alive=settings.llm_keep_alive,
            )
    except TimeoutError:
        raise ModelError("model_timeout", f"no reply within {settings.llm_timeout_s:.0f}s") from None
    except ollama.ResponseError as exc:
        # 5xx (Ollama overloaded or crashed) may pass; a 4xx (unknown model, bad request) won't.
        code = "model_unavailable" if exc.status_code >= 500 else "model_request_rejected"
        raise ModelError(code, f"{exc.status_code}: {exc.error}") from exc
    except ConnectionError as exc:
        raise ModelError("model_unavailable", str(exc)) from exc

    prompt_tokens = response.prompt_eval_count or 0
    # Ollama cuts an over-long prompt to num_ctx without an error; a prompt that fills the window was cut.
    if prompt_tokens >= settings.llm_num_ctx:
        raise ModelError("prompt_truncated", f"prompt filled num_ctx {settings.llm_num_ctx}")
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
        model=response.model or settings.llm_model,
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
