"""The one way Shelfsense calls a model: Ollama, JSON-schema-constrained, with token and time accounting."""

import asyncio
import json
import math
from dataclasses import dataclass
from typing import Any

import ollama

from shelfsense_api.settings import settings


class ModelError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


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


async def chat_json(system: str, user: str, schema: dict[str, Any]) -> ModelReply:
    client = ollama.AsyncClient(host=settings.ollama_host)
    try:
        async with asyncio.timeout(settings.llm_timeout_s):
            response = await client.chat(
                model=settings.llm_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                format=schema,
                logprobs=True,
                options={"temperature": settings.llm_temperature, "num_ctx": settings.llm_num_ctx},
                keep_alive=settings.llm_keep_alive,
            )
    except TimeoutError:
        raise ModelError("model_timeout", f"no reply within {settings.llm_timeout_s:.0f}s") from None
    except (ConnectionError, ollama.ResponseError) as exc:
        raise ModelError("model_unavailable", str(exc)) from exc

    prompt_tokens = response.prompt_eval_count or 0
    # Ollama cuts an over-long prompt to num_ctx without an error; a prompt that fills the window was cut.
    if prompt_tokens >= settings.llm_num_ctx:
        raise ModelError("prompt_truncated", f"prompt filled num_ctx {settings.llm_num_ctx}")
    if response.done_reason == "length":
        raise ModelError("output_truncated", "the model hit its output limit")
    try:
        answer = json.loads(response.message.content or "")
    except ValueError as exc:
        raise ModelError("invalid_model_output", str(exc)) from exc

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
