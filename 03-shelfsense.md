# Project 3: Shelfsense (Marketplace Catalog Enrichment and Search)

**Pitch:** Shelfsense ingests messy supplier product feeds (CSV/JSON drops and a paginated supplier API) for a multi-seller marketplace. It normalizes them, classifies each product into the **Google Product Taxonomy**, and extracts typed attributes (color, material, size system, gender, dimensions) with evidence spans. All of that powers a faceted hybrid search where natural-language queries ("waterproof women's hiking boots under $120 size 8") are parsed into structured filters.

**Why it isn't a toy:** This is a throughput problem. A local 7B model enriches a few hundred products an hour, and a real catalog has millions, so the design has to spend model time only where it matters (embedding pre-filter, rules first, idempotent reruns) and survive every item-level failure mode of bulk inference and bulk indexing. Search quality is measured with nDCG against a baseline, not judged by eye.

## Real-world concerns, mapped to where they're built

| Concern | Implementation | Slice |
|---|---|---|
| Backpressure | The feed upload API checks SQS `ApproximateNumberOfMessages` and returns `429 + Retry-After` above 200k pending. The enrichment worker caps in-flight LLM calls at `OLLAMA_NUM_PARALLEL` and stops calling `ReceiveMessage` at the cap. OpenSearch bulk requests use adaptive batch sizing that halves on `429 es_rejected_execution_exception` and grows additively on success (AIMD) | 3 |
| Retries | SQS visibility timeout with heartbeat extension for long jobs. App-level retry with exponential backoff + jitter. The SQS redrive policy (`maxReceiveCount=5`) is the backstop | 3 |
| Dead letters | `enrich.dlq` and `index.dlq` SQS queues, a `dead_letters` table, and a redrive endpoint using SQS `StartMessageMoveTask` with a dry-run preview | 3 |
| Pagination | The supplier API mock uses **offset pagination with drift** (items inserted mid-scan cause skips and duplicates). The importer uses the snapshot token where the API offers one, and otherwise dedupes on `(supplier_sku, updated_at)` plus a reconciliation pass. Search deep-pagination uses OpenSearch PIT + `search_after`. GraphQL uses Relay connections | 2, 4 |
| Partial failures | Feed rows: 100k-row file, 0.5% invalid → `feed_rejections` with row number and reason, and the rest proceed. Enrichment: each product in a message succeeds or fails on its own, and only the failures are resubmitted or dead-lettered. Bulk indexing: per-item errors retried individually. Query parsing: LLM timeout (2.5s) → degrade to plain hybrid search with `parse_degraded=true` | 1, 3, 5 |
| Schema migrations | (a) Taxonomy version upgrade with a node remap table, re-classifying only products in changed subtrees. (b) OpenSearch zero-downtime reindex via alias swap (`products_v1` → `products_v2` with a new analyzer and `knn_vector` mapping). (c) Postgres JSONB attributes → typed columns for the 6 hottest facets | 4, 6 |

## AI scope and precise targets

**Enrichment (offline, bulk):** an embedding pre-filter (bge-small over taxonomy path strings) picks the top 15 candidate leaf categories. Each product then goes to `qwen2.5:7b-instruct` through Ollama, with output constrained by Ollama's `format` JSON schema: `{category_id ∈ candidates ∪ {NONE}, attributes[] {name, value, unit, evidence: exact substring of input}}`. Any attribute whose evidence isn't a literal substring of the product text is dropped deterministically.

**Query understanding (online):** a rules fast path handles simple queries (no constraints detected → skip the LLM). Otherwise a smaller local model, `qwen2.5:3b-instruct`, returns structured `QueryParse {keywords, category_hint, filters{price_max, color[], size, gender, material[]}}`, with a 2.5s timeout and a Redis cache keyed on the normalized query (24h TTL). Most traffic should hit the cache or the fast path. The eval reports the actual mix.

**Ranking:** OpenSearch BM25 + kNN (`bge-small`) hybrid via a search pipeline with normalization + combination, then the top 50 reranked by `bge-reranker-base`. LLM-parsed filters are applied as hard filters, except price, which is a soft boost when it would produce zero results.

| Metric | Definition | Target (gate) |
|---|---|---|
| Taxonomy leaf accuracy | Predicted leaf == gold leaf | ≥ 0.80 |
| Taxonomy hierarchical F1 | Set-overlap of ancestor paths (standard hF1) | ≥ 0.90 |
| Candidate recall | Gold leaf in the 15 embedding candidates (an upper bound on accuracy) | ≥ 0.97 |
| Attribute F1 | Per attribute, after normalization (color → base palette of 16, units → SI) | ≥ 0.85 macro |
| Ungrounded attribute rate | Values emitted by the model before the evidence-substring filter that fail it | ≤ 5% (all of them are dropped before persistence) |
| Schema validity | Replies that parse into the schema on the first try | ≥ 98% |
| Query parse exact match | Full filter object equals gold | ≥ 0.75 |
| Query slot F1 | Per-slot F1 over 120 queries | ≥ 0.90 |
| Search nDCG@10 | Graded relevance (0–3) computed deterministically from true product attributes vs query constraints | ≥ 0.72, and ≥ +0.08 over a BM25-only baseline |
| Zero-result rate | Golden queries returning 0 hits | ≤ 2% |
| Enrichment throughput | Products enriched per hour with one local Ollama instance | ≥ 400 / hour (report seconds per product and tokens/sec alongside) |
| Search latency | API server-side, fast path / LLM path / cache hit | p95 ≤ 150ms / ≤ 3s / ≤ 180ms |

**Golden set:** 400 products. 300 are generated by taking known structured items and rendering them into supplier-style messy text (abbreviations "blk/wht", mixed units "12in / 30cm", typos, marketing fluff, attributes buried in descriptions), so gold is correct by construction. The other 100 are adversarial and hand-labelled: bundles, multi-category items, missing attributes where the right answer is "absent", and conflicting title vs description. There are also 120 search queries (40 head, 50 torso, 30 tail including typos and negations like "not leather") with gold parses. Hash split: 280 / 120 products, 80 / 40 queries.

---

## Target architecture (the vision)

This is where the project ends up after slice 8. It is a destination, not a to-do list: slice 1 copies it into `docs/architecture.md`, and each folder, service and dependency appears only when a slice needs it (see HOW_WE_BUILD.md).

**Stack:** Python 3.12, uv workspaces, FastAPI, Pydantic v2, SQLAlchemy 2.0 async + asyncpg, Alembic, Strawberry GraphQL, Postgres 16 (source of truth), OpenSearch 2.x (search, with the k-NN plugin and search pipelines), AWS SQS + S3 via LocalStack (aioboto3 client), Redis 7, fastembed (bge-small-en-v1.5, bge-reranker-base), Next.js 15 + TypeScript storefront search UI, pnpm.

```text
  apps/api/              FastAPI: REST /v1 (feeds, products, search), GraphQL /graphql
  apps/worker_enrich/    SQS consumer: per-product LLM calls through Ollama, applies results
  apps/worker_index/     SQS consumer: Postgres → OpenSearch bulk indexing
  apps/feed_importer/    S3 feed parsing + supplier API pull
  apps/supplier_mock/    mock supplier API: offset pagination WITH drift, 429s, snapshot tokens on v2 endpoint only
  apps/web/              Next.js search UI with facets and "why this result" debug panel
  packages/core/         Product, Attribute, Money, TaxonomyNode, normalization (colors, units, sizes)
  packages/db/           models, Alembic
  packages/taxonomy/     Google Product Taxonomy loader (versioned files in data/taxonomy/), candidate retrieval
  packages/search/       OpenSearch index templates, mapping versions, query builder, alias management
  packages/queue/        SQS consumer framework (heartbeat, backoff, DLQ, graceful shutdown)
  packages/ai/           Ollama client, prompts, schemas, token/latency accounting
  packages/clients/      generated clients
  packages/telemetry/
  contracts/ evals/ infra/ scripts/ data/ .github/workflows/
```

---

## Pairing plan: 8 slices

Each prompt is one vertical slice that runs end to end on real input. Your 8 topics are all covered; each slice leads with one of them and pulls in only the infrastructure, packages and tests it needs.

| Slice | Leads with | Delivers | First appearance of |
|---|---|---|---|
| 1 | Scaffolding | Import one small feed file → validate rows → classify one product into the real Google taxonomy with a local model | uv project, FastAPI, Postgres + pgvector, fastembed, Ollama, pytest |
| 2 | Contracts | Faceted hybrid search with deep pagination behind a spec-first API, typed client, GraphQL search | OpenSearch, OpenAPI spec, Strawberry, testcontainers |
| 3 | Workers | Feeds upload to S3 and enrich/index through queues with per-item failures, DLQs and backpressure | LocalStack (SQS, S3), Redis |
| 4 | Data | Drifting supplier API import, realistic seeds, JSONB → typed columns, taxonomy version upgrade | supplier_mock, quirk-profile seeds |
| 5a | AI (attributes + queries) | Grounded attribute extraction, natural-language query parsing with fast path, cache and fallback | Redis, qwen2.5:3b |
| 5b | UI (prototypes) + Tests (Jest) | 3–4 search-UI concepts prototyped against the real API, then the chosen one built | Next.js, Jest |
| 6 | AI (evals) | Golden set, enrichment/parse/search evals with nDCG, zero-downtime reindex judged by the eval | Eval harness, recorded responses |
| 7 | CI/CD | GitHub Actions incl. a search performance smoke test; image build and push | Workflows, Dockerfiles, GHCR |
| 8 | Instrumentation | One product traced from feed row to searchable; freshness and search SLOs | OpenTelemetry, Jaeger, Prometheus, Grafana |

Every prompt ends with a **Done when** check. Each slice lists what it will ask to add, so you can approve in one go.

### Slice 1. Scaffolding: walking skeleton

```text
Slice 1 of 8 for Shelfsense: walking skeleton. Read HOW_WE_BUILD.md first; it wins over anything in this prompt.

Goal: import one small, messy supplier CSV, reject the bad rows with reasons, and classify each good product into the real Google Product Taxonomy with a local model. Nothing more.

Vision: copy the "Target architecture" section of 03-shelfsense.md into docs/architecture.md as the destination. Do not create folders, services or dependencies from it until a slice needs them.

Build:
- A uv project with one app, apps/api (FastAPI). Settings via pydantic-settings; .env.example lists only the keys used today.
- `make taxonomy` downloads the official Google Product Taxonomy file (with IDs) into data/taxonomy/<version>.txt with a checksum file. Find the current official URL with a web search; never fetch at runtime.
- scripts/load_taxonomy.py: load nodes (version, node_id, parent, full path, depth) and embed each full path with fastembed bge-small-en-v1.5 into pgvector.
- data/feeds/sample.csv: 40 hand-written supplier rows in a realistic mess ("blk/wht", "12in", typos, marketing fluff), 4 of them invalid (bad GTIN checksum, negative price, missing title, broken encoding).
- POST /v1/feeds:import-local {path}: stream the CSV, validate each row with a Pydantic model, write invalid rows to feed_rejections (row number, reason code, excerpt), upsert valid rows on (supplier_id, supplier_sku) only when the content hash changed.
- POST /v1/products/{id}:enrich: embed the product text, take the 15 nearest taxonomy leaves as candidates, and call Ollama (qwen2.5:7b-instruct; model and options from settings; num_ctx set explicitly because the default silently truncates) with format = a JSON schema whose category_id enum is exactly those 15 IDs plus "NONE". Store category, confidence, model, prompt_version, token counts and durations.
- GET /v1/products/{id} with the category's full path.
- Prompts in one module with a version string. docker-compose with Postgres (pgvector image) only; Ollama runs natively on the Mac (no GPU in Docker on macOS) at OLLAMA_HOST.
- Alembic baseline: suppliers, products (attributes_json JSONB for now), feed_rejections, taxonomy_nodes, product_categories.
- CLAUDE.md pointing at HOW_WE_BUILD.md and docs/architecture.md: "Postgres is the source of truth", "every extracted attribute must carry an evidence span".
- Tests (pytest): GTIN checksum validation (GTIN-8/12/13/14), row validation reasons, the per-request category enum builder. Ollama stubbed.

Check current official docs (web search) for the Google Product Taxonomy download, pgvector, fastembed, and the ollama Python client's structured output before using them.
Will ask before adding: fastapi, uvicorn, pydantic-settings, sqlalchemy[asyncio], asyncpg, alembic, pgvector, fastembed, ollama, pytest, pytest-asyncio; the Postgres service; the five tables.
Git: init the repo if needed, branch slice/01-walking-skeleton.

Done when: importing sample.csv gives 36 products and 4 rejections with the right row numbers; re-importing changes nothing; enriching 10 products shows each predicted category path next to what you'd expect, with any wrong ones named. Tests pass. Merge, then report.
```

### Slice 2. Contracts: faceted hybrid search, typed client, GraphQL

```text
Slice 2 of 8 for Shelfsense: contracts and search. Follow HOW_WE_BUILD.md.

Goal: products are searchable through a spec-first API with facets and correct deep pagination, a generated typed client and a GraphQL search connection.

Build:
- OpenSearch in compose (single node; security disabled for local only, documented). An index template products_v1 (BM25 text fields, keyword facets, knn_vector 384) behind the alias `products`. A sync script indexes products from Postgres (Postgres stays the source of truth).
- Hybrid search: BM25 and k-NN combined through an OpenSearch search pipeline with normalization and combination, then the top 50 reranked by bge-reranker-base.
- contracts/openapi.yaml (OpenAPI 3.1), source of truth for:
  - GET /v1/search: q, repeatable facet filters, page_size ≤ 48, deep pagination with a point-in-time (PIT) + search_after cursor (offset paging past 10k is not offered, and the spec says so). Response: items, facets with counts, next cursor, optional debug block with per-stage scores.
  - GET /v1/products with keyset pagination and filters; GET /v1/products/{id}; GET /v1/feeds/{id}/rejections with keyset pagination.
  - RFC 9457 problem+json errors with a code enum.
- `make contract-check` with oasdiff (Docker image), failing on breaking changes.
- Python client via openapi-python-client into packages/clients/python; first user is scripts/smoke.py.
- Strawberry GraphQL: product(id), products(first, after) and search(query, filters, first, after) as Relay connections. The search cursor wraps PIT + search_after, opaque and HMAC-signed. Resolvers call the same service functions as REST. Schema printed to contracts/schema.graphql with a drift test.
- Unit tests: cursor encoding and tamper rejection; facet filter → query DSL builder.
- Service tests (testcontainers OpenSearch + Postgres): PIT + search_after over 5,000 docs returns every doc exactly once while documents are being updated.

Check current official docs (web search) for OpenSearch hybrid search pipelines, k-NN field mapping, point-in-time and search_after, opensearch-py, and Strawberry's Relay support.
Will ask before adding: opensearch-py, strawberry-graphql, openapi-python-client (dev), testcontainers (dev); the OpenSearch service; the public API shape above.
Git: branch slice/02-contracts-search.

Done when: scripts/smoke.py, using only the generated client, runs 5 searches showing facets and per-stage scores, then pages through one result set to the end. A GraphQL search returns the same first page. Show the outputs.
```

### Slice 3. Workers: queued enrichment and indexing with per-item failures

```text
Slice 3 of 8 for Shelfsense: workers. Follow HOW_WE_BUILD.md.

Goal: large feeds upload straight to storage and flow through enrichment and indexing queues where one bad product never fails a batch, nothing is lost when a worker dies, and producers slow down when the system is full.

Build:
- LocalStack (SQS, S3) in compose. An init script creates bucket `feeds` and queues enrich, enrich.dlq, index, index.dlq with redrive policies (maxReceiveCount 5) and visibility timeouts.
- POST /v1/feeds returns a presigned S3 PUT URL; POST /v1/feeds/{id}:commit starts the import. The import streams the file from S3 (never fully in memory), reuses slice 1's row validation, and enqueues EnrichRequest messages of ≤ 50 product IDs. Commit returns 429 with Retry-After when the enrich queue holds more than MAX_ENRICH_BACKLOG messages, with the delay derived from the measured products-per-hour rate.
- contracts/messages/: JSON Schema for EnrichRequest and IndexRequest with a schema_version field.
- One SQS consumer loop used by both workers: long polling, bounded concurrency, a heartbeat that extends visibility every timeout/3 while a handler runs, graceful SIGTERM. TransientError → change visibility to a backoff delay based on ApproximateReceiveCount; PermanentError → dead_letters row, explicit send to the DLQ, delete. Redrive is the backstop for crashes. A should_receive() check stops polling while capacity is exhausted.
- apps/worker_enrich: skip products already enriched for the same (taxonomy_version, prompt_version, content_hash); run model calls concurrently up to LLM_MAX_CONCURRENCY (= OLLAMA_NUM_PARALLEL, since more just queue inside Ollama); write each product's result as soon as it finishes. Connection errors, 5xx and timeouts go into a resubmission message (attempt + 1, max 3); output still invalid after one retry with the validation error appended → that product to enrich.dlq. Enqueue an IndexRequest for the successes.
- apps/worker_index: bulk-index with an adaptive batch size (start 500 docs; halve on 429 or es_rejected_execution, min 50; +50 on success, max 2,000) and retry only the failed items in each bulk response; mapping errors go to index.dlq per item.
- POST /v1/admin/dlq/{queue}/redrive {dry_run} using SQS's message-move task.
- Table: enrichment_runs (product_id, attempt, outcome, error_code, model, prompt_version, token counts, durations), dead_letters.
- Unit tests: resubmission set builder, adaptive batch sizer, message schema compatibility (an old consumer ignores unknown fields).
- Service tests (testcontainers LocalStack + Postgres + OpenSearch, Ollama stubbed): the heartbeat keeps a long handler from being redelivered; a crash after half the products are written doesn't redo them on redelivery; a permanent failure lands in the DLQ and redrive moves it back.

Check current official docs (web search) for SQS visibility timeouts, redrive policies and StartMessageMoveTask, LocalStack's community services, aioboto3, and the OpenSearch _bulk response format.
Will ask before adding: aioboto3; the LocalStack and Redis services; the two tables; the feed upload API change.
Git: branch slice/03-workers.

Done when: scripts/chaos.py uploads a 2,000-product feed while the model stub returns 3% 500s, 2% timeouts and 1% invalid output that also fails its retry, OpenSearch returns 429 on 10% of bulk calls, and one enrich worker is killed. Show: every valid product enriched or in the DLQ with a reason, DLQ count equal to the persistently invalid products, no product enriched twice for the same attempt, indexed count equal to enriched count.
```

### Slice 4. Data: drifting supplier API, seeds, two live migrations

```text
Slice 4 of 8 for Shelfsense: data. Follow HOW_WE_BUILD.md.

Goal: products also arrive from a supplier API whose pagination shifts under you, the catalog has realistic volume, and the schema and taxonomy can change without downtime.

Build:
- apps/supplier_mock: v1 endpoint with offset/limit pagination that drifts (rows are inserted during a scan, so naive paging skips and duplicates), injectable 429s; v2 endpoint that offers a snapshot_token.
- Supplier importer: prefer v2's snapshot token; on v1, scan, dedupe by (sku, updated_at), then re-request the windows where page boundaries shifted (detected by comparing the edge SKUs of adjacent pages). Save progress in import_state after every page.
- Seeds (deterministic --seed, --profile small|large): 50 suppliers, each with a quirk profile (unit style, colour abbreviations, title template, typo rate); 5k products (small) or 200k (large) generated from structured ground truth and rendered through those quirks; ground truth written to evals/ground_truth.parquet. A 100k-row feed file with 0.5% invalid rows uploaded to S3.
- Migration A, JSONB → typed columns (expand/contract): add color_base, material, gender, size_system, size_value and a product_attributes table; resumable batched backfill (20k rows per batch); switch reads; drop attributes_json. Deploy order and rollback in docs/migrations.md.
- Migration B, taxonomy version upgrade: scripts/taxonomy_diff.py compares two taxonomy versions and writes taxonomy_remaps (same, renamed, split, merged, deleted), matching by ID, then path, flagging the rest for review. Load the new version beside the old; remap same/renamed products in SQL; mark products in split or deleted nodes stale and re-enqueue them for classification only. The served taxonomy_version comes from a setting, so the switch is atomic. Test with a synthetic "next" version containing 5 renames, 2 splits and 1 delete.
- Unit tests: normalizers (colour abbreviations to a 16-colour base palette; "12in", "30 cm", '12"' to mm; US/EU/UK shoe sizes), taxonomy diff classification, drift-window detection.
- Service tests: every migration up → down → up; the drifting v1 import ends with 0 missing and 0 duplicate SKUs; the importer resumes after a failure mid-scan.

Check current official docs (web search) for Alembic online-migration guidance, Postgres batched backfills and NOT VALID constraints, and pyarrow/parquet writing.
Will ask before adding: faker (dev), pyarrow; the supplier_mock service; every table and migration above.
Git: branch slice/04-data.

Done when: seeds load (show row counts and rows/sec for the large profile); the drifting import is exact; both migrations run while a background loop keeps searching with 0 errors; the taxonomy upgrade remaps the synthetic changes correctly. Show the outputs.
```

### Slice 5a. AI attributes and query understanding (backend)

Split from the original slice 5 (2026-11-02) so the UI can be prototyped on its own against a working API.

```text
Slice 5a of 8 for Shelfsense: grounded attributes and query parsing. Follow HOW_WE_BUILD.md.

Goal: enrichment also extracts typed attributes that are each backed by an exact quote from the product text,
natural-language queries become filters, and search stays fast and works even when the model is slow.

Build:
- Enrichment schema grows: attributes [{name (enum), value, unit or null, evidence_field (title | description |
  brand | raw_attributes), evidence_text}]. The system prompt carries the attribute glossary with allowed
  normalized values and 6 worked examples, including absent attributes, byte-identical across products so Ollama
  reuses the processed prefix.
- Grounding in code: evidence_text must be an exact substring of the named field (offsets stored); otherwise the
  attribute is dropped and counted as ungrounded. Values normalized with slice 4's normalizers. Stored in
  product_extracted_attributes and indexed as facets.
- Query understanding: a rules fast path skips the model when there are no price, size, colour, gender, material
  or negation signals; otherwise qwen2.5:3b-instruct returns QueryParse {keywords, category_hint, filters} within
  2.5 s. On timeout or error: plain hybrid search with parse_degraded. Parses cached in Redis for 24 h on a
  normalized key. Filters are hard, except price, which is relaxed when it would return nothing. The search
  response reports query_parse.source (cache | rules | llm | degraded).
- Python unit tests: evidence offsets with unicode, the fast-path detector, query-key normalization, the price rule.

Done when: 20 products show extracted attributes with highlighted evidence and the ungrounded count; 10
natural-language queries show their parse source, filters and results, including one forced timeout that
degrades cleanly.
```

### Slice 5b. Search UI: prototype concepts, then build one (with Jest)

```text
Slice 5b of 8 for Shelfsense: the storefront search UI. Follow HOW_WE_BUILD.md.

Goal: pick the search experience by trying real alternatives, then build the chosen one properly.

Build:
- Prototypes first: 3–4 distinct, throwaway search-UI concepts against 5a's real API (for example: classic facet
  sidebar; parsed query as editable filter chips; conversational refine; results with a "why this result" panel).
  Each answers a stated design question; the user compares them in the browser and picks (or combines).
- Then apps/web (Next.js + TypeScript) for the chosen concept: search box, facets, "load more" via the opaque
  cursor, the degraded-parse notice, the debug panel. Generated TS client (openapi-typescript + openapi-fetch);
  GraphQL with @graphql-codegen for the product detail page.
- Jest (next/jest, React Testing Library, MSW): a facet updates the URL and query; "load more" sends the cursor;
  the degraded notice appears; price formatting matches the Python fixtures.

Will ask before adding: next, react, openapi-typescript, openapi-fetch, a GraphQL client, @graphql-codegen/*,
jest, @testing-library/react, msw.

Done when: the prototypes were compared and a choice recorded (ADR); the chosen UI works in the browser; Jest passes.
```

### Slice 6. AI evals: nDCG, golden set, zero-downtime reindex

```text
Slice 6 of 8 for Shelfsense: evals. Follow HOW_WE_BUILD.md.

Goal: classification, attribute extraction, query parsing and search ranking are measured by a script over a fixed golden set with gates, and a new index design ships only if the numbers say so.

Build:
- Golden set (evals/golden/): products.jsonl with 300 products rendered from ground truth across 25 top-level taxonomy branches (stratified) plus 100 hand-labelled hard cases (bundles, multi-use items, conflicting title vs description, "fits iPhone 15" accessories that must not be classified as phones, truly absent attributes, non-English fragments); gold = {leaf node_id, attributes with ABSENT allowed}. queries.jsonl with 120 queries (40 head, 50 torso, 30 tail with typos, negations and unit variants) and gold parses. Graded relevance 0–3 for every query × eval product, computed from ground truth (3 = category and all constraints, 2 = category and most, 1 = related category, 0 = otherwise); the grading function gets its own unit tests. Hash split 280/120 products, 80/40 queries; the test split runs only with `make eval-test`.
- evals/run.py (a plain script, not part of the test suite):
  - Enrichment: candidate recall@15, leaf accuracy, hierarchical F1, per-attribute precision/recall/F1 (a value predicted for an ABSENT gold is a false positive), ungrounded rate, NONE rate, first-try schema validity, seconds per product, products per hour, tokens/sec. Confusion matrix at taxonomy depth 2 and the top 15 confused leaf pairs.
  - Query parsing: exact match, per-slot F1, fast-path rate, degraded rate, p50/p95 latency.
  - Search: nDCG@10, MRR and zero-result rate for BM25 only, vector only, hybrid, hybrid + rerank, and hybrid + rerank + parsed filters (ablation table); p95 per path (fast, LLM, cache hit) over 1,000 replayed queries with a realistic head/tail mix.
  - Gates (exit 1 if missed): leaf accuracy ≥ 0.80, hF1 ≥ 0.90, candidate recall ≥ 0.97, attribute macro F1 ≥ 0.85, ungrounded ≤ 0.05, schema validity ≥ 0.98, parse exact match ≥ 0.75, slot F1 ≥ 0.90, nDCG@10 ≥ 0.72 and ≥ BM25 + 0.08, zero-result ≤ 0.02, throughput ≥ 400 products/hour, search p95 ≤ 150ms fast path / 3s LLM path / 180ms cache hit. After the first baseline run, propose recalibrated gates with reasons; I decide.
  - `--baseline evals/baseline.json` fails on any drop over 1.5 points.
- Offline mode: record live model responses keyed by prompt hash so the eval replays without Ollama.
- evals/sweep.py on the dev split: qwen2.5:7b vs llama3.1:8b vs qwen2.5:14b (if it fits) for enrichment; qwen2.5:3b vs 7b for query parsing. Quality, products per hour, memory. Don't change defaults; write a recommendation for me.
- Zero-downtime reindex: products_v2 adds a synonym graph filter for colours and materials, an edge-ngram autocomplete field and nested facets. A resumable task builds v2 from Postgres, runs a catch-up pass for rows updated since the start, checks doc counts and a query parity sample, then swaps the alias atomically and keeps v1 for 24h. Run the search eval on v1 and v2; swap only if v2's nDCG@10 is at least v1's — my call after seeing the numbers.
- Unit tests for the metric code: nDCG, hF1 and slot F1 on hand-computed examples.

Check current official docs (web search) for OpenSearch synonym graph filters, index aliases and atomic alias actions.
Will ask before adding: the products_v2 index template; any metrics library (or write nDCG and hF1 directly, with a reason).
Git: branch slice/06-evals.

Done when: `make eval LIVE=1` runs the dev split on local Ollama and `make eval` replays it offline with identical metrics. Before the first live run, time 10 products and print the projected wall-clock. Show REPORT.md, the ablation table, the sweep and the v1-vs-v2 comparison; if the swap runs, show 0 failed searches during it.
```

### Slice 7. CI/CD: GitHub Actions with a search performance smoke

```text
Slice 7 of 8 for Shelfsense: CI/CD. Follow HOW_WE_BUILD.md.

Goal: every pull request is checked automatically, including search latency, and every merge to main produces signed images.

Build (only for what exists today):
- Dockerfiles for api, worker_enrich, worker_index, supplier_mock and web if missing (multi-stage, uv sync --frozen, non-root).
- ci.yml on pull requests and main: concurrency cancel-in-progress, least-privilege permissions per job, every action pinned to a commit SHA.
  - lint: ruff, mypy, tsc, eslint, actionlint.
  - contracts: client regeneration diff, oasdiff, graphql-inspector, message-schema compatibility. Breaking changes need the label breaking-change-approved.
  - unit; integration (testcontainers: Postgres, OpenSearch, LocalStack, Redis; raise vm.max_map_count for OpenSearch; cache fastembed models); migrations (up/down/up + squawk); an index-mapping check that fails when a mapping changes without a new index version; web (jest --ci).
  - eval-offline: enrichment and parse evals replay recorded responses; the search ablation runs for real. Sticky PR comment with metrics and deltas against main.
  - perf-smoke, only when search or API code changes (paths filter): load 5k products, replay 500 queries headless with k6 or locust, fail if fast-path p95 > 150ms.
- release.yml on main and v* tags: multi-arch Buildx with gha cache, push to GHCR with sha/branch/semver tags, SBOM + provenance, trivy (fail on CRITICAL), cosign keyless signing. A job renders the Alembic SQL and the index-template diff as artifacts for review; neither is auto-applied.
- No live-eval workflow (no GPU on runners); REPORT.md and baseline.json are committed from local runs.
- From now on, slices merge through PRs (HOW_WE_BUILD.md section 7).

Check current official docs (web search) for every action used and pin current SHAs; check k6 or locust headless usage.
Will ask before: creating the GitHub repo or remote if none exists; any repository settings or branch protection; adding k6 or locust.
Git: branch slice/07-ci-cd, opened as the first PR through the new flow.

Done when: actionlint is clean; the PR's checks pass on GitHub, including perf-smoke; after merge, images are pushed and signed. Show the run summary and the perf-smoke latency output.
```

### Slice 8. Instrumentation: OpenTelemetry from feed row to search

```text
Slice 8 of 8 for Shelfsense: instrumentation. Follow HOW_WE_BUILD.md.

Goal: one product can be followed from its feed row through S3, the queues, its model call and indexing to being searchable; one search can be followed through parsing, OpenSearch and reranking; freshness and search SLOs have metrics and alerts.

Build:
- One telemetry setup function for every Python app: OTLP to an OpenTelemetry Collector, resource attributes, structlog JSON with trace and span IDs shipped to Loki. Auto-instrument FastAPI, SQLAlchemy, Redis, httpx and botocore; wrap opensearch-py with manual spans if no maintained instrumentation exists.
- SQS: traceparent in MessageAttributes on send; the consumer span links to the producer context, with queue name, receive count and message ID. Each product's model call is a child span under the consumer span, so one slow or failing product stands out.
- Model spans `chat <model>` with GenAI semantic-convention attributes (gen_ai.system=ollama, models, token counts) plus tokens_per_second, prompt_version and parse_source.
- No product text or query text in attributes (seller data and shopper queries): hashes only, enforced by a denylist span processor with a unit test.
- Metrics: feed rows by outcome, enrich items by outcome, in-flight model calls, seconds per product, LLM tokens, products enriched per hour, ungrounded attributes, queue and DLQ depth (from GetQueueAttributes), bulk batch size (shows the adaptive sizing at work), bulk rejections, search seconds by path, parse source mix, zero-result count, catalog freshness (source_updated_at → indexed). Exemplars on histograms.
- Collector: tail sampling keeps errors, DLQ sends, degraded parses and searches over 1s, plus 5% of the rest; a spanmetrics connector produces per-route rate/error/duration metrics.
- Grafana "Shelfsense / Pipeline" and "Shelfsense / Search" dashboards. Alerts with runbook links: DLQ depth > 100; enrich queue age > 6h; products per hour < 50% of its 24h average; Ollama unreachable for 2m; ungrounded rate > 6%; zero-result rate > 4% for 30m; fast-path search p95 > 150ms for 10m.
- docs/slo.md: catalog freshness 95% ≤ 2h from feed commit to searchable on the small profile; search availability 99.9%; fast-path latency SLO; multiwindow burn-rate alerts.

Check current official docs (web search) for botocore/SQS trace propagation in OpenTelemetry Python, the GenAI semantic conventions (note the version used), the spanmetrics connector and tail_sampling processor.
Will ask before adding: opentelemetry-* packages, structlog; the collector, Jaeger, Prometheus, Grafana and Loki services.
Git: branch slice/08-instrumentation, merged by PR.

Done when: after a chaos run, the Jaeger API returns one product's trace from SQS receive → model call → index request → bulk index, showing the span links; one LLM-path search prints its span tree with per-stage durations; Prometheus shows products enriched per hour. The denylist test passes.
```
