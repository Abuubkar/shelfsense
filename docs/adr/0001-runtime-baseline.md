---
status: accepted
date: 2026-11-02
---

# Runtime baseline: Python 3.13, Postgres 18 with pgvector 0.8.7, uv workspace from day one

- **Python 3.13** (uv-managed, pinned in `.python-version`), not the 3.12 in the plan. Every slice-1 dependency
  supports it (pydantic-settings and SQLAlchemy 2.1 need ≥ 3.11), and it matches Ledgerline, the sibling project
  on this machine.
- **Postgres 18.6 via `pgvector/pgvector:0.8.7-pg18-trixie`**, not Postgres 16. 18 brings `uuidv7()` for
  time-ordered primary keys; the official pgvector image saves building the extension. The image tag pins both
  the extension and the Postgres major.
- **Port 5436.** 5434 is Ledgerline's Postgres and 5435 Pagerwise's.
- **uv workspace root with one member (`apps/api`).** The target layout adds workers, the importer and the
  supplier mock in slices 3–4; moving the package later would churn every import path.

## Alternatives

- Postgres 16 as planned: works, but no `uuidv7()`, and nothing ties us to 16.
- Plain `postgres` image plus building pgvector: more Dockerfile for the same result.

## Assumptions

- Docker runs locally; port 5436 was free on 2026-11-02.
- Nothing Postgres-18-only is relied on besides `uuidv7()`.
