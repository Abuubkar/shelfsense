---
status: accepted
date: 2026-11-02
---

# Opaque, signed pagination cursors bound to their query

**Chosen.** Every paginated endpoint (REST and GraphQL) takes and returns an opaque cursor:
`base64url(json{position, query digest}) . base64url(HMAC-SHA256(...)[:16])`, keyed by `CURSOR_SECRET`.

- **Products and rejections** use keyset positions (the last product ID, the last row number). Product IDs are
  uuidv7, so ID order is creation order.
- **Search** positions are `{pit, rank, search_after}` (docs/adr/0006).

The query digest (12 bytes of SHA-256 over the query and filters) makes a cursor from one query fail on
another instead of silently skipping or repeating results. The signature stops clients from editing positions,
for example jumping to rank 9,000 or pointing at another client's PIT.

## Alternatives

- Offset paging: drifts when rows are added and gets slower with depth; OpenSearch caps `from + size` at 10,000.
- Unsigned base64 cursors: readable and forgeable.
- Encrypting cursors: hides the PIT ID, which isn't a secret; signing is enough.

## Assumptions

- Rotating `CURSOR_SECRET` invalidates open cursors, which is acceptable: clients restart from the first page.
