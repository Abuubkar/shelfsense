# Shelfsense

Marketplace catalog enrichment and search: messy supplier feeds in, classified products out, built in thin slices.

- **How we work:** [HOW_WE_BUILD.md](HOW_WE_BUILD.md). It wins over everything else, including slice prompts.
- **The slice plan:** [03-shelfsense.md](03-shelfsense.md).
- **Where it's heading:** [docs/architecture.md](docs/architecture.md). A destination, not a to-do list.
- **Why things are the way they are:** [docs/adr/](docs/adr/). Add one for every real choice.
- **How schema and taxonomy changes ship:** [docs/migrations.md](docs/migrations.md) (deploy order, rollback).
- **What went wrong before:** [docs/challenges.md](docs/challenges.md). Each slice adds what it hit.
- **Known but parked:** [docs/backlog.md](docs/backlog.md).

## Run it

```bash
docker compose up -d --wait                  # Postgres :5436, OpenSearch :9201, Floci (SQS, S3) :4566, Redis :6380
uv run alembic upgrade head
uv run python scripts/init_aws.py            # feeds bucket, enrich and index queues with DLQs; a rerun is a no-op
make taxonomy                                # only to fetch a new release; 2021-09-21 is committed
uv run python scripts/load_taxonomy.py       # embeds 5,595 taxonomy paths (~1 min on CPU); a rerun is a no-op
ollama pull qwen2.5:7b-instruct              # once; Ollama runs natively on the Mac, not in Docker
ollama pull qwen2.5:3b-instruct              # once; the query-parsing model
uv run uvicorn shelfsense_api.main:app --port 8020
uv run python -m shelfsense_worker_enrich    # one per Ollama; LLM_MAX_CONCURRENCY = OLLAMA_NUM_PARALLEL
uv run python -m shelfsense_worker_index
uv run python scripts/upload_feed.py data/feeds/sample.csv acme-outdoor   # presign, PUT, commit -> queues
curl -X POST "localhost:8020/v1/products/${id}:enrich"   # one product now; braces: in zsh, $id:e is a filename modifier
uv run python scripts/sync_index.py          # full rebuild of the index from Postgres (fresh setup or repair)
curl "localhost:8020/v1/search?q=hiking%20boots&debug=true"
curl -X POST localhost:8020/v1/admin/dlq/enrich/redrive -H 'content-type: application/json' -d '{}'  # dry run
uv run uvicorn shelfsense_supplier_mock:app --port 8030                       # drifting supplier API
uv run python scripts/import_supplier.py ridgeway http://localhost:8030 --verify   # exact import, resumable
uv run python scripts/seed.py --profile small|large [--feed [--commit-feed]] [--reset]  # 5k / 200k from ground truth
uv run python scripts/taxonomy_upgrade.py <release file> [--status|--reindex]  # docs/migrations.md B
uv run python -u scripts/search_loop.py      # keeps reading through the API during a migration; counts errors
uv run python scripts/attributes_report.py --sample 20 [--enqueue]   # extracted attributes, evidence, accuracy
uv run python scripts/query_demo.py [--fresh]  # 10 natural-language queries: parse source, filters, results
make web                                     # the storefront on :3020 (Next.js; needs the API on :8020)
make web-test                                # Jest + typecheck for apps/web
make smoke                                   # 5 searches + deep paging + GraphQL, via the generated client
make test                                    # unit tests, offline
make chaos                                   # slice 3 Done-when: 2,000 products through failing stubs (~3 min)
make test-int                                # service tests on Postgres, OpenSearch and Floci containers (~3 min)
make codegen                                 # after changing contracts, GraphQL types or messages.py (also apps/web's types)
make contract-check                          # oasdiff: the code's spec vs contracts/openapi.yaml
```

## Rules that are easy to break

- Postgres is the source of truth. Search indexes and caches (later slices) are rebuilt from it, never the reverse.
- Every extracted attribute must carry an evidence span: an exact substring of the field it names, located in code
  (`attributes.ground`), with its value normalized from the quote, not taken from the model. One that doesn't
  ground is dropped and counted on the enrichment run (ADR 0015).
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
- OpenSearch is derived data: change or remove a field by adding `products_v2` and moving the alias (slice 6).
  Adding new fields in place is allowed (`search.NEW_FIELDS`, PUT _mapping); existing fields are never redefined.
- Query understanding goes through `query.understand` (rules fast path, Redis cache, small model under
  `QUERY_TIMEOUT_S`, degrade on any failure) and never raises. Page 1's parse travels in the cursor; never
  re-parse on later pages (ADR 0014).
- Embedding and reranking go through `embeddings.py` (bge-small, bge-reranker-base); never load a fastembed model
  elsewhere.
- Feed rejections use spreadsheet row numbers (header = row 1), counted per CSV record, not per line.
- Committing a feed again must change nothing: products upsert only on a changed content hash, rejections are
  unique on (feed, row number), and only products not enriched for their current content are queued. A feed is
  one upload (ADR 0010); the same bytes uploaded twice are two feeds.
- Queue work goes through `queue.consume` (ADR 0009). Handlers decide per product with `plan_followups`: done
  moves on, transient is resubmitted with attempt + 1 (max `MAX_ATTEMPTS`), permanent is dead-lettered one product
  per message through `queue.dead_letter`, which records the reason before sending. Never let one product's
  failure fail its message.
- Workers must be idempotent: enrichment is skipped when the product already has a category for its current
  content hash, taxonomy version and prompt version (`classify.needs_enrichment`), and a category is written in
  the same transaction as its `enrichment_runs` row.
- Queue message bodies are `messages.py` models: consumers ignore unknown fields; a change an old consumer would
  misread bumps `schema_version`. `contracts/messages/` is generated from them.
- SQS and S3 go through `aws.py` (one client setup, endpoint from settings). Queue names can't contain dots;
  DLQs are `<queue>-dlq`.
- Product attributes: raw supplier pairs live in `product_attributes`; the facet columns (`color_base`, `material`,
  `gender`, `size_system`, `size_value`) are derived by `normalize.typed_attributes` in `feeds.upsert_rows`, the one
  write path for products (feeds, supplier APIs, seeds). Never write products another way.
- Schema changes on big tables are expand/contract with batched, resumable backfills outside migrations, and
  `lock_timeout` on DDL (docs/migrations.md). A migration never both adds and removes something code uses.
- Supplier API imports go through `supplier_import.import_supplier`: overlapping pages + reconciliation by the
  supplier's own `updated_at` on v1, snapshot on v2, progress saved per page (ADR 0011).
- Taxonomy releases sit side by side; an upgrade remaps by SQL and reclassifies only split/deleted nodes into the
  new release before `TAXONOMY_VERSION` switches (ADR 0013). `classify_product` takes the release to use.
- apps/web (ADR 0016): the search page's state is its URL; REST goes through `src/lib/api.ts` (openapi-fetch, types
  from `contracts/openapi.yaml`), GraphQL through `src/lib/graphql.ts` with codegen-typed documents. Both are
  generated: `make codegen`, never edit `src/lib/api-types.ts` or `src/gql/`. Money is shown with `formatMoney`
  (BigInt, mirrors `money.py`, fixtures in `contracts/fixtures/money.json`); evidence offsets are code points
  (`src/lib/evidence.ts`). The browser calls `/api/*` on its own origin; Next forwards it to the API.
- Indexing goes through `indexing.bulk_index` (adaptive batch size, per-item retries), from the worker and
  `scripts/sync_index.py` alike.
- The taxonomy file is never fetched at runtime. `data/taxonomy/<version>.txt` and its `.sha256` are committed;
  the loader refuses a file whose checksum doesn't match.
