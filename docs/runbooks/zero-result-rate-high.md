# Zero-result rate over 4% for 30 minutes

More than 4% of first-page searches found nothing, for 30 minutes.

## Look

- *Searches with no results* and *Parse source mix* on **Shelfsense / Search**.
- Degraded parses are always kept in Jaeger: `uv run python scripts/trace_tree.py --search --path degraded`.

## Likely causes

- The index is missing products (compare `GET products/_count` with `SELECT count(*) FROM products`): a failed reindex or a stalled index worker.
- The query model parsing filters that match nothing (a colour or size from a brand name; docs/backlog.md).

## Fix

- Repair the index with `uv run python scripts/sync_index.py`, or check the reindex state: `uv run python scripts/reindex.py products_v2 --status`.
- If it's the parser, the fix is in prompts or the fast path, checked with `make eval`.
