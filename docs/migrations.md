# Live migrations

How schema and taxonomy changes ship without downtime: deploy order, the checks between steps, and how to roll
back from each. Rehearsed on 299,545 products with a loop reading search, products and GraphQL throughout
(`scripts/search_loop.py`): 1,296 requests, 0 errors (slice 4, docs/challenges.md).

General rules:

- Migrations only add, or only remove what no running code uses. A change that needs both is split in two
  (expand, contract) with a deploy between.
- DDL on hot tables sets `lock_timeout` (5 s): a migration that can't get its lock fails fast instead of
  queueing behind a long transaction while every query queues behind it.
- Constraints on big tables go in `NOT VALID` and are validated later, under a lock that allows reads and writes.
- Backfills run outside migrations, in batches with their own transactions, and resume where they stopped.

## A. Product attributes: JSONB to typed columns (0005, backfill, 0006)

`products.attributes_json` becomes `product_attributes` (raw supplier name/value pairs) plus five typed,
normalized columns: `color_base`, `material`, `gender`, `size_system`, `size_value` (docs/adr/0012).

| Step | Who's running | What | Measured |
|---|---|---|---|
| 1 | old code | `alembic upgrade 0005`: add the columns and `product_attributes`, colour CHECK `NOT VALID` | ~2 s, metadata only |
| 2 | old code | `scripts/backfill_attributes.py`: 20,000 products per transaction, progress in `backfill_state` | 299,545 in 27 s; resumed after SIGKILL at 60,000 |
| 3 | deploy | new code (reads and writes the typed columns and `product_attributes`, never `attributes_json`) | gated cutover |
| 4 | new code | `scripts/backfill_attributes.py --restart`: catch-up for rows the old code wrote during 2–3 | 24 s |
| 5 | new code | `alembic upgrade 0006`: `VALIDATE` the CHECK, drop `attributes_json`; refuses if any product's attributes aren't in `product_attributes` | ~3 s |

Between 3 and 4, a product the old code wrote after the backfill passed it shows empty typed columns until the
catch-up reaches it. With imports paused during the deploy there are none.

**Rollback.**

- Before step 5: deploy the old code. If the new code wrote products, `alembic downgrade 0004` copies their
  `product_attributes` back into `attributes_json` before dropping the new columns.
- After step 5: `alembic downgrade 0005` re-creates `attributes_json` from `product_attributes` exactly (every raw
  attribute is kept there), then deploy the old code, then `downgrade 0004` if wanted. Rehearsed: 0006 to 0005
  under the new code (6.5 s), cutover, 0005 to 0004 under the old code.

## B. Taxonomy release upgrade (no schema change)

The served release is `TAXONOMY_VERSION`; releases load side by side, keyed by version (docs/adr/0013).

| Step | Who's running | What | Measured (45 categorized products) |
|---|---|---|---|
| 1 | current | `scripts/taxonomy_upgrade.py <new release file>`: load the new release (paths embedded), diff into `taxonomy_remaps`, copy categories for same/renamed/merged nodes by SQL, queue products in split/deleted nodes for classification into the new release | 60 s (embedding 5.6k paths) |
| 2 | current + enrich worker | the worker classifies the queued products into the new release | 6 products, ~20 s |
| 3 | current | `--status` until "0 still waiting"; review the remaps flagged `needs_review` and low-confidence picks | |
| 4 | deploy | API and workers with the new `TAXONOMY_VERSION` | gated cutover |
| 5 | new release | `--reindex`: index requests for products whose category changed (not "same") | 16 products |

**Rollback.** Switch `TAXONOMY_VERSION` back and run `--reindex` again: both releases' categories stay in
`product_categories`, and the reindex follows whichever release is served. Rehearsed after the upgrade.

## C. Search index version: products_v1 to products_v2 (no schema change)

A new mapping ships as a new index beside the served one; the `products` alias moves in one atomic request
(docs/adr/0019). `scripts/reindex.py products_v2` runs every step but the swap; each is resumable.

| Step | What | Measured (dev, 299,545 products) |
|---|---|---|
| 1 | `make eval`: the search eval runs on every version (REPORT.md, "Index versions") | v1 and v2 nDCG@10 0.8147, no query moved |
| 2 | build v2 from Postgres, refresh off, position saved per 2,000 products | 2,020 s (~8,900 products/min, embedding-bound) |
| 3 | catch-up: products changed since the build started, minus 10 min | 0 (no writes during the run) |
| 4 | checks: doc count = Postgres, 50-title parity sample against the served index | 299,545 = 299,545; 50 of 50 |
| 5 | `--swap`: last catch-up, alias moved (remove v1 + add v2, one request), catch-up through the alias | integration test: 0 failed searches |
| 6 | `--drop-previous` after 24 h (refused before, or while v1 serves) | |

**Rollback.** `--rollback` catches v1 up on everything changed since the swap, moves the alias back, and catches
up again for writes during the move. Don't run a taxonomy upgrade (B) during a reindex: its remaps aren't among
the catch-up signals.

## Gated cutover

A deploy switches traffic only after the new process answers health requests (3 × HTTP 200 in a row). The first
rehearsal switched to a process that wasn't listening yet and failed 525 requests in 10 s; that run was
discarded and repeated with the gate (docs/challenges.md).
