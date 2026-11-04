# Search availability SLO burning

API requests are failing with 5xx often enough to threaten 99.9% (docs/slo.md).

## Look

- *API errors* on **Shelfsense / Search** (by route); Jaeger keeps every error trace.

## Likely causes

- OpenSearch down or rejecting (503 `search_unavailable`).
- Open PIT cap reached (429 inside, 5xx out; docs/backlog.md).
- Postgres connection errors.

## Fix

- `GET _cluster/health` on OpenSearch; restart it if needed (the index is derived from Postgres: `scripts/sync_index.py` rebuilds it).
