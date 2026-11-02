---
status: accepted
date: 2026-11-02
---

# OpenSearch 3.9, single node, security off locally

**Chosen.** `opensearchproject/opensearch:3.9.0` in docker-compose, one node, one shard, no replicas, on
`127.0.0.1:9201`. The security plugin is disabled (`DISABLE_SECURITY_PLUGIN=true`): no TLS and no users. That's
for local development only. The port binds to localhost so nothing else on the network reaches it. Any
shared or deployed cluster runs with security on.

The client is `opensearch-py` 3.2 with its async (aiohttp) transport.

**Why 3.x, not the 2.x in the plan.** 3.9 is the current release. Everything this design relies on is in both
lines: hybrid queries with a normalization search pipeline (2.10), `search_after` in hybrid queries (2.16),
hybrid score explanation (2.19), radial k-NN (2.14). Starting on 3.x avoids a major upgrade later.

**Measured on 3.9.0** (docs/challenges.md): the k-NN score for `cosinesimil` with faiss is `(1 + cos) / 2`; a
PIT search sorted by `_score` alone returns no sort values, so `search_after` needs an explicit tiebreaker.

## Alternatives

- Elasticsearch: comparable features, but the plan and the hybrid-pipeline design are OpenSearch's.
- pgvector + Postgres full-text search only: one fewer service, but no BM25 scoring and no search pipelines.

## Assumptions

- 1 GB of heap is enough for a local catalog of up to ~100k products.
