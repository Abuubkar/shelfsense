## Target architecture (the vision)

This is where the project ends up after slice 8. It is a destination, not a to-do list: slice 1 copies it into `docs/architecture.md`, and each folder, service and dependency appears only when a slice needs it (see HOW_WE_BUILD.md).

> Decided since: Python 3.13 and Postgres 18 instead of 3.12 and 16 (docs/adr/0001); OpenSearch 3.9 instead
> of 2.x (docs/adr/0004); Floci instead of LocalStack, which now needs an account token (docs/adr/0008); Redis
> waits for its first use (slice 5's query cache). Shared code still lives in the apps/api package
> (`shelfsense_api`: db, search, indexing, queue, messages, aws, normalize, supplier_import); the workers in apps/
> import it, and apps/supplier_mock stands alone. It splits into packages/ when a piece needs to be installed
> without the API. The supplier import runs as a script (`scripts/import_supplier.py`), not yet an app.

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

