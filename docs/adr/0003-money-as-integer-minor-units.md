---
status: accepted
date: 2026-11-02
---

# Money as integer minor units plus ISO currency

**Chosen.** Prices are stored as `price_minor BIGINT` (cents for USD) plus `currency CHAR(3)`. Feed prices are
parsed as `Decimal` ("$1,099.00" → 109900); a price with more than two decimals is rejected (`invalid_price`)
instead of rounded.

**Why.** Price filters and boosts in search compare amounts exactly, and a float can't hold 0.10 exactly. Integers
also index and range-filter cheaply in Postgres and OpenSearch alike.

## Alternatives

- `NUMERIC(12,2)`: exact too, but every layer (JSON, OpenSearch, TypeScript) would need to carry it as a string or
  decimal type to stay exact.

## Assumptions

- Every currency we see has two minor-unit digits. A zero-decimal currency (JPY) or a three-decimal one (KWD)
  needs a per-currency exponent before it's accepted.
