"""Fault-injecting stand-ins for scripts/chaos.py: an Ollama /api/chat stub and an OpenSearch proxy.

The workers talk to them through their normal clients (only OLLAMA_HOST and OPENSEARCH_URL change), so every
failure arrives the way a real one would: an HTTP 500, a reply that never comes, a reply that fails validation,
a whole _bulk refused with 429, or single _bulk items rejected with 429.
"""

import asyncio
import hashlib
import json
import random
from collections import Counter
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

MODEL_500_RATE = 0.03
MODEL_TIMEOUT_RATE = 0.02
PERSISTENTLY_INVALID_PERCENT = 1
BULK_REJECT_RATE = 0.10


def persistently_invalid(title: str) -> bool:
    """1% of products, chosen by title so every call for one product (retries included) gets a bad reply."""
    return int(hashlib.sha256(title.encode()).hexdigest(), 16) % 100 < PERSISTENTLY_INVALID_PERCENT


def model_stub(stats: Counter[str], timeout_s: float, seed: int = 3) -> FastAPI:
    app = FastAPI()
    rng = random.Random(seed)

    @app.post("/api/chat")
    async def chat(request: Request) -> Response:
        body = await request.json()
        prompt = next(m["content"] for m in body["messages"] if m["role"] == "user")
        title = prompt.splitlines()[0].removeprefix("Title: ")
        candidates = body["format"]["properties"]["category_id"]["enum"]
        if persistently_invalid(title):
            stats["model_invalid"] += 1
            return _reply("999999")  # not among the candidates: fails validation, and fails it again on retry
        roll = rng.random()
        if roll < MODEL_500_RATE:
            stats["model_500"] += 1
            return JSONResponse({"error": "stub: model runner crashed"}, status_code=500)
        if roll < MODEL_500_RATE + MODEL_TIMEOUT_RATE:
            stats["model_timeout"] += 1
            await asyncio.sleep(timeout_s + 1)  # the worker has given up by now
        stats["model_ok"] += 1
        return _reply(candidates[0])

    return app


def _reply(category_id: str) -> JSONResponse:
    content = json.dumps({"category_id": category_id, "attributes": []})
    logprobs = [{"token": '{"category_id": "', "logprob": 0.0}, {"token": category_id, "logprob": -0.05},
                {"token": '"}', "logprob": 0.0}]
    return JSONResponse({"model": "chaos-stub", "created_at": "2026-11-02T00:00:00Z",
                         "message": {"role": "assistant", "content": content}, "done": True, "done_reason": "stop",
                         "total_duration": 2_000_000, "prompt_eval_count": 300, "prompt_eval_duration": 1_000_000,
                         "eval_count": 8, "eval_duration": 1_000_000, "logprobs": logprobs})


def opensearch_proxy(upstream: str, stats: Counter[str], seed: int = 5) -> FastAPI:
    """Forwards everything to `upstream`, except that 10% of _bulk calls are rejected: half of them whole (HTTP
    429), half item by item (about a third of their items get status 429 and are not indexed)."""
    app = FastAPI()
    rng = random.Random(seed)
    client = httpx.AsyncClient(base_url=upstream, timeout=60)

    @app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "HEAD"])
    async def proxy(path: str, request: Request) -> Response:
        body = await request.body()
        if path.endswith("_bulk") and rng.random() < BULK_REJECT_RATE:
            if rng.random() < 0.5:
                stats["bulk_rejected_whole"] += 1
                error = {"type": "rejected_execution_exception", "reason": "stub: coordinating write queue full"}
                return JSONResponse({"error": {**error, "root_cause": [error]}, "status": 429}, status_code=429)
            return await _reject_some_items(client, path, request, body, rng, stats)
        upstream_response = await client.request(request.method, f"/{path}", params=request.query_params,
                                                 content=body, headers=_content_type(request))
        return Response(upstream_response.content, upstream_response.status_code,
                        media_type=upstream_response.headers.get("content-type"))

    return app


async def _reject_some_items(client: httpx.AsyncClient, path: str, request: Request, body: bytes,
                             rng: random.Random, stats: Counter[str]) -> Response:
    lines = body.decode().splitlines()
    pairs = [(lines[i], lines[i + 1]) for i in range(0, len(lines), 2)]  # (action, document); index actions only
    rejected = set(rng.sample(range(len(pairs)), max(1, len(pairs) // 3)))
    stats["bulk_rejected_items"] += len(rejected)
    kept = [pair for i, pair in enumerate(pairs) if i not in rejected]
    forwarded: list[dict[str, Any]] = []
    if kept:
        response = await client.post(f"/{path}", params=request.query_params, headers=_content_type(request),
                                     content="\n".join(line for pair in kept for line in pair) + "\n")
        forwarded = response.json()["items"]
    items, forwarded_iter = [], iter(forwarded)
    for i, (action, _) in enumerate(pairs):
        if i in rejected:
            items.append({"index": {"_index": "products_v1", "_id": json.loads(action)["index"]["_id"], "status": 429,
                                    "error": {"type": "rejected_execution_exception",
                                              "reason": "stub: write thread pool queue full"}}})
        else:
            items.append(next(forwarded_iter))
    return JSONResponse({"took": 1, "errors": True, "items": items})


def _content_type(request: Request) -> dict[str, str]:
    return {"content-type": request.headers.get("content-type", "application/json")}
