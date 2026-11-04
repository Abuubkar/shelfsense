"""Where a search's time goes, stage by stage, for the golden queries that take the rules path (no model call).
CI's perf-smoke runs it after k6, so a latency miss comes with its breakdown.

    uv run python scripts/search_timings.py [--rounds 3] [--rerank-threads default,1,2,4] [--close-pits]

Stages are search.search's timings: pit (opening the snapshot, while the query embeds), embed, hybrid (the
head's retrieval), rerank, tail (while the head reranks) and facets (alongside everything after embed). "total"
is the whole service.search_page call, parsing and labels included. --rerank-threads repeats the run once per
onnxruntime thread count for the reranker (settings.rerank_threads; "default" is onnxruntime's choice), with
OpenSearch's queries competing for the CPU as in a real search. Every first page opens a PIT (ADR 0006), so
several runs can reach OpenSearch's cap of 300; --close-pits closes all of them before each run. That also ends
shoppers' open cursors: dev and CI nodes only.
"""

import argparse
import asyncio
import json
import math
import time
from pathlib import Path
from typing import Any

from shelfsense_api import db, embeddings, search, service
from shelfsense_api.settings import settings

QUERIES = Path(__file__).resolve().parents[1] / "evals" / "golden" / "queries.jsonl"


def nearest_rank(values: list[float], pct: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, math.ceil(pct / 100 * len(ordered)) - 1)]


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--rerank-threads", help="comma-separated thread counts to compare, e.g. default,1,2,4")
    parser.add_argument("--close-pits", action="store_true", help="close every open PIT first (dev and CI only)")
    args = parser.parse_args()
    for threads in (args.rerank_threads or "current").split(","):
        if args.close_pits:
            await search.client().transport.perform_request("DELETE", "/_search/point_in_time/_all")
        if threads != "current":
            settings.rerank_threads = None if threads == "default" else int(threads)
            embeddings._reranker.cache_clear()
            print(f"rerank threads: {threads}")
        await run(args.rounds)


async def run(rounds: int) -> None:
    queries = [json.loads(line)["q"] for line in QUERIES.read_text().splitlines() if line.strip()]
    stages: dict[str, list[float]] = {}
    last: dict[str, Any] = {}
    original = search.search

    async def timed(*a: Any, **kw: Any) -> search.SearchPage:
        page = await original(*a, **kw)
        last["timings"] = page.timings_ms
        return page

    search.search = timed  # type: ignore[assignment]
    os = search.client()
    async with db.SessionLocal() as session:
        await service.search_page(session, os, "warm up", search.Filters(), 24, None)
        for _ in range(rounds):
            for q in queries:
                started = time.perf_counter()
                response, _ = await service.search_page(session, os, q, search.Filters(), 24, None)
                total = (time.perf_counter() - started) * 1000
                if response.query_parse and response.query_parse.source == "rules":
                    stages.setdefault("total", []).append(total)
                    for name, ms in last["timings"].items():
                        stages.setdefault(name, []).append(ms)
    await os.close()
    search._client = None  # closed: the next run opens a fresh one
    search.search = original  # type: ignore[assignment]
    print(f"rules-path searches: {len(stages.get('total', []))}")
    for name in ("total", "pit", "embed", "hybrid", "rerank", "tail", "facets"):
        if values := stages.get(name):
            print(f"  {name:7s} median {nearest_rank(values, 50):6.0f} ms   p95 {nearest_rank(values, 95):6.0f} ms")


if __name__ == "__main__":
    asyncio.run(main())
