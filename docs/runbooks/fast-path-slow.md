# Fast-path search p95 over 150 ms for 10 minutes

First-page searches that need no model call (the rules path) have a p95 over 150 ms.

## Look

- *Latency by parse path* on **Shelfsense / Search**; click an exemplar for a slow search's trace.
- The trace shows each stage: `embed query`, `opensearch hybrid`, `rerank`, `opensearch tail`, `opensearch facets` (ADR 0021 has their usual costs).

## Likely causes

- The reranker on a busy CPU (it dominated on CI's runners).
- OpenSearch merging segments after a bulk load, or short of heap.
- Open point-in-time contexts near their cap (docs/backlog.md): searches start failing with 429 soon after.

## Fix

- Check OpenSearch: `GET _nodes/stats/indices/search` (`point_in_time_current`), `GET _cat/segments/products`.
- Measure the stages: `uv run python scripts/search_timings.py`.
