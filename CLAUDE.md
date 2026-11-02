# Shelfsense

Marketplace catalog enrichment and search: messy supplier feeds in, classified products out, built in thin slices.

- **How we work:** [HOW_WE_BUILD.md](HOW_WE_BUILD.md). It wins over everything else, including slice prompts.
- **The slice plan:** [03-shelfsense.md](03-shelfsense.md).
- **Where it's heading:** [docs/architecture.md](docs/architecture.md). A destination, not a to-do list.
- **Why things are the way they are:** [docs/adr/](docs/adr/). Add one for every real choice.
- **What went wrong before:** [docs/challenges.md](docs/challenges.md). Each slice adds what it hit.
- **Known but parked:** [docs/backlog.md](docs/backlog.md).

## Run it

```bash
docker compose up -d --wait                  # Postgres 18 + pgvector on :5436, OpenSearch 3.9 on :9201
uv run alembic upgrade head
make taxonomy                                # only to fetch a new release; 2021-09-21 is committed
uv run python scripts/load_taxonomy.py       # embeds 5,595 taxonomy paths (~1 min on CPU); a rerun is a no-op
ollama pull qwen2.5:7b-instruct              # once; Ollama runs natively on the Mac, not in Docker
uv run uvicorn shelfsense_api.main:app --port 8020
curl -X POST localhost:8020/v1/feeds:import-local -H 'content-type: application/json' \
  -d '{"path": "sample.csv", "supplier": "acme-outdoor"}'
curl -X POST "localhost:8020/v1/products/${id}:enrich"   # braces: in zsh, $id:e is a filename modifier
uv run python scripts/sync_index.py          # Postgres -> OpenSearch (alias `products`); rerun after imports/enrichment
curl "localhost:8020/v1/search?q=hiking%20boots&debug=true"
make smoke                                   # 5 searches + deep paging + GraphQL, via the generated client
make test                                    # unit tests, offline
make test-int                                # service tests on Postgres and OpenSearch containers (~2.5 min)
make codegen                                 # after changing contracts/openapi.yaml or GraphQL types
make contract-check                          # oasdiff: the code's spec vs contracts/openapi.yaml
```

## Rules that are easy to break

- Postgres is the source of truth. Search indexes and caches (later slices) are rebuilt from it, never the reverse.
- Every extracted attribute must carry an evidence span: an exact substring of the product text. One that
  doesn't is dropped before it's stored.
- Money is integer minor units + ISO currency (ADR 0003). Never floats, never rounding.
- Model name and options come from settings. Prompts live only in `prompts.py`; any wording change bumps its
  version.
- All model calls go through `llm.chat_json`, which always sends `num_ctx` (Ollama's default silently truncates).
  The `format` schema isn't enough on its own: spell out the reply shape in the prompt too, or qwen fights the
  grammar (docs/challenges.md).
- The category enum is built per request from the candidates (`classify.category_schema`); the model can't
  answer outside it. Confidence comes from token logprobs, never from a number the model states (ADR 0002).
- `contracts/openapi.yaml` is the source of truth: change it first, then the code, then `make codegen` and
  `make contract-check`. Write nullable fields as `anyOf` with a `type: 'null'` branch (what Pydantic emits).
  `packages/clients/python` and `contracts/schema.graphql` are generated; never edit them by hand.
- REST routes and GraphQL resolvers both call `service.py`; business rules never live in a route or resolver.
  Errors are raised as `schemas.ApiProblem` with a code from `ProblemCode` (documented in docs/problems.md).
- Pagination is cursor-only, through `cursor.py` (signed, bound to the query). No offsets anywhere.
- Search (ADR 0006): the result set is lexical OR radial k-NN after filters; the head (50) is hybrid + rerank, the
  tail is `search_after` on the same PIT excluding the head. Every query of one search reads its PIT, and a PIT
  sort always ends with the `product_id` tiebreaker. Don't store the head in the cursor; re-run it on the PIT.
- OpenSearch is derived data: change the mapping by adding `products_v2` and moving the alias (slice 6), never
  by editing `products_v1` in place.
- Embedding and reranking go through `embeddings.py` (bge-small, bge-reranker-base); never load a fastembed model
  elsewhere.
- Feed rejections use spreadsheet row numbers (header = row 1), counted per CSV record, not per line.
- A re-import of the same file must change nothing: products upsert only on a changed content hash, and
  rejections are unique on (file hash, row number).
- The taxonomy file is never fetched at runtime. `data/taxonomy/<version>.txt` and its `.sha256` are committed;
  the loader refuses a file whose checksum doesn't match.
