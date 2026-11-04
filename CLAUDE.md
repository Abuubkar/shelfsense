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
uv run python scripts/reindex.py products_v2 [--swap|--rollback|--status|--drop-previous]  # new index version, zero downtime
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
make eval                                    # evals on the dev split, replaying recorded model replies (no Ollama)
make eval LIVE=1                             # the same against Ollama, re-recording (~45 min); BASELINE=1 compares
make eval-test                               # the test split; run it only to report, never to tune
make eval-latency                            # 1,000 searches on the catalog by parse path (live, ~45 min)
make sweep                                   # enrichment and query models compared on dev (evals/SWEEP.md); LIVE=1 ~80 min
make golden                                  # rebuild evals/golden/products.jsonl (hard cases are hand-written)
make lint                                    # ruff, mypy, eslint, tsc: CI's lint job (actionlint aside)
make test                                    # unit tests, offline (and the eval metric tests)
make migrations-lint                         # squawk on migrations added since origin/main
make perf-smoke [BASE_URL=…]                 # CI's k6 search smoke against a running API (keep OLLAMA_HOST off)
docker build --target api -t shelfsense-api .   # one Dockerfile, targets api|worker-enrich|worker-index|supplier-mock
docker build -f apps/web/Dockerfile -t shelfsense-web .
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
- OpenSearch is derived data: change or remove a field with a new index version in `search.TEMPLATES`, built and
  swapped by `scripts/reindex.py` (ADR 0019). Adding new fields in place is allowed (`search.NEW_FIELDS`, PUT
  _mapping, on every live version); existing fields are never redefined. No template attaches the `products`
  alias; only `ensure_index` (fresh setup) and the reindex move it. A new version keeps answering the previous
  version's queries the same way, since the alias can point at either during a move or rollback.
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
- apps/web look (ADR 0017): colours only as the tokens on `:root` (light and dark); no hue in the chrome, so the
  products' own colours are the only colour on screen. Product pictures go through `ProductArt` (drawn, never a fake
  photo). One typeface, Geist, via `next/font`.
- Evals (ADR 0018): golden data in `evals/golden/` changes only with a reason in the commit, never to make a
  number pass. Metrics live in `evals/metrics.py`, relevance in `evals/grading.py`, both unit-tested. A prompt,
  model or ranking change is followed by `make eval LIVE=1` and a committed recording (with its
  `<split>-candidates.json.gz`, the pre-filter's candidates replays reuse); old recordings and results
  are archived under `evals/archive/`, never deleted.
- CI (ADR 0020): every PR runs `.github/workflows/ci.yml` and merges when it's green. Actions are pinned to a full
  commit SHA with the version in a comment; bump both together. A breaking contract change (OpenAPI, GraphQL, a
  message) needs the `breaking-change-approved` label; a message changed without a `schema_version` bump can't be
  approved. eval-offline fails on regressions against the base branch, never on main's known misses; gates don't
  move. Merges to main publish signed images to `ghcr.io/abuubkar/shelfsense-<service>`.
- A new migration must pass squawk (`make migrations-lint`): `SET LOCAL lock_timeout` before the first statement
  that locks a busy table (a foreign key to `products` locks it too).
- Indexing goes through `indexing.bulk_index` (adaptive batch size, per-item retries), from the worker and
  `scripts/sync_index.py` alike.
- The taxonomy file is never fetched at runtime. `data/taxonomy/<version>.txt` and its `.sha256` are committed;
  the loader refuses a file whose checksum doesn't match.

## Lessons from Ledgerline

Ledgerline (`../ledgerline`) hit these first; the full stories are in `../ledgerline/docs/challenges.md`. Each is a
trap nothing in this repo's config will warn about.

- **An Ollama `format` schema forces the answer into the schema, even when that means null.** A field typed `string`
  while the model writes bare numbers comes back null every time (Ledgerline lost every amount from Qwen this way).
  Type fields the way the model writes them (`string | number`), parse numbers with `json.loads(parse_float=Decimal)`,
  and keep the prompt's wording consistent with the schema.
- **Check the scorer before trusting a low score.** Ledgerline's first real-data line F1 (6%) measured its scoring
  rule, not the model. Reading the per-case failure reasons (not the averages) found that, and found the one gap
  (no currency read) behind most real failures.
- **Models measured on this Mac** (M1 Pro 16 GB, Ledgerline's sweep, `think: false`):
  - gemma4:12b: best quality and tool choice (8.7 GB, ~34 s per page).
  - qwen3.5:9b-q4_K_M: close behind, 1.6× faster, 6.6 GB.
  - qwen2.5:7b: fast and reads well, but weakest at picking a tool action (10 of 15).

  Pin explicit quant tags; a bare tag can pull different builds.
- **OpenTelemetry Python:**
  - The SDK and the contrib instrumentations release in matched pairs (SDK 1.45.0 with 0.66b0); a mismatched pin
    won't resolve.
  - An instrumentation switches itself off silently when a library is newer than it declares (0.66b0's SQLAlchemy
    says < 2.1). Confirm its spans appear; if its hooks still fit, `instrument(skip_dep_check=True)` with a comment.
- **Metrics over OTLP into Prometheus:**
  - A new series' first measurement never counts in `rate()` or `increase()`, because the receiver ignores start
    times: report counters at 0 when a process starts.
  - A stopped process's gauges linger for 5 minutes (no staleness marker): gauge alerts and panels use
    `last_over_time(x[1m])`.
  - A worker process that exits without atexit hooks loses its last export: flush the providers on shutdown.
  - A unit suffix can double: unit `{token}/s` on a metric named `…_per_second` became `…_per_second_per_second`.
- **httpx logs every request at INFO, URL included:** set the `httpx` logger to WARNING. A management URL carrying
  credentials reached Ledgerline's logs that way.
- **Next.js 16:**
  - `next lint` is gone: use the ESLint CLI with a flat config.
  - `rewrites()` are fixed at build time, so the API address a container proxies to is a build argument.
  - `next dev` writes `apps/web/AGENTS.md`: gitignore it.
- **Images and pins:**
  - GHCR packages come out public, linked to the repo; name them `<project>-<service>`.
  - A collector-contrib release can lack its image (0.163.0 did): check the tag exists before pinning.
