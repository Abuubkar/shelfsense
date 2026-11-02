---
status: accepted
date: 2026-11-02
---

# Product attributes: typed facet columns plus raw pairs, by expand and contract

**Chosen.** The five facets search filters on become normalized columns on `products`: `color_base` (one of 16
base colours, enforced by a CHECK), `material`, `gender` (men/women/unisex/kids), `size_system` (US/UK/EU/alpha)
and `size_value`. Every raw supplier attribute is kept as given in `product_attributes (product_id, name, value)`.
`normalize.typed_attributes` derives the columns from the raw pairs, whatever each supplier calls its columns
("Colour", "col", "sz"), in the one write path (`feeds.upsert_rows`).

The search index's existing `color` and `size` fields now carry `color_base` and `size_value`, so colour facets
show the base palette ("black", not "blk/gry"). The mapping is unchanged (both are keywords), so no new index
version is needed.

The change shipped as expand (0005), batched backfill, deploy, catch-up, contract (0006); docs/migrations.md.

## Alternatives

- **Keep JSONB with expression indexes**: no migration, but every reader re-implements the normalization, and a
  CHECK on a JSON path is awkward.
- **Typed columns only, drop the raw values**: smaller, but the contract step couldn't be rolled back exactly,
  and slice 5's extraction wants the supplier's own words.
- **One big migration** (add, backfill, drop): locks `products` for the backfill's duration and can't run while
  the old code serves.

## Assumptions

- Five facets cover today's filters. A sixth is another expand/backfill/contract, cheap with this pattern.
- Normalizing in Python (not SQL) is acceptable because all writes go through `feeds.upsert_rows`; a DB trigger
  would duplicate the vocabularies in SQL.
