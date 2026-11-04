---
status: accepted
date: 2026-11-04
---

# Index versions: products_v2, built beside v1 and swapped by an atomic alias move

**Chosen.** Searches and writes go through the `products` alias. A mapping change that redefines a field ships as a
new index version with its own template (`search.TEMPLATES`). `scripts/reindex.py` builds it from Postgres while
v1 keeps serving, and moves the alias in one `_aliases` request. v1 is kept for 24 hours for a rollback.

- **products_v2** keeps every v1 field, with the same names and types, so the same queries and documents work on
  either version. It adds three things:
  - a search-time `synonym_graph` for colour and material words (`search.SYNONYMS`) on title, description and
    category path. Spelling variants are equivalent ("grey, gray", "aluminium, aluminum"). A base colour or
    material also finds its shades and kinds ("red" finds burgundy), but a shade doesn't find the base. The
    analyzer is the built-in english one rebuilt, with the synonyms after the stop filter and before stemming
    (OpenSearch docs: the synonym graph filter is search-time only, and a stop filter after it breaks the graph);
  - `title.autocomplete`, edge n-grams of 2–15 characters, searched as whole words;
  - `facets`, nested (name, value) pairs, so a facet can be aggregated or filtered by name without a field per
    attribute.

  The nested field is the one addition that changes the document's shape. It is also added to v1 in place
  (`NEW_FIELDS`), so one document fits whichever index the alias points at during the move. Both are
  `"dynamic": "strict"`.
- **No template attaches the alias.** A new version must not take searches before it is built and checked.
  `ensure_index` puts the alias on `search.INDEX` only on a fresh setup. Before, v1's template carried the alias,
  so recreating a dropped v1 would have put a second, empty index behind it.
- **The reindex** (`shelfsense_api.reindex`) runs in steps:
  - **Build:** create v2 with refresh off and index every product in ID order. The position is saved after each
    2,000-product chunk in the index's mapping `_meta`, so a stopped run resumes and the state goes away with
    the index.
  - **Catch-up:** reindex every product changed since the last pass: its row, an enrichment run (written in the
    same transaction as its category), extracted attributes or a category row. Each pass looks back 10 minutes
    further than its mark, because a row's timestamp is when its transaction started. Marks come from
    `statement_timestamp()`, not `now()`, which is the reindex session's own transaction start.
  - **Check:** turn refresh back on. The doc count must equal Postgres's product count. A parity sample of 50
    product titles: a title that found itself in v1's top 10 (its product, or one with the identical title)
    must still do so, and no query may match fewer products than on v1.
  - **Swap:** a last catch-up, then `remove` v1 and `add` v2 in one request, which the docs describe as atomic:
    the alias never points at both or neither. Then a catch-up through the alias for what the index worker wrote
    to v1 between that pass and the move.
  - **Rollback:** the alias back to v1 after a catch-up of v1. **Drop:** v1 is deleted only after 24 hours and
    only if nothing serves from it.
- **Open cursors survive the move.** A cursor holds its point-in-time, which pins v1's segments, and v1 isn't
  deleted for 24 hours.

## Alternatives

- **The `_reindex` API from v1 to v2**: copies OpenSearch to OpenSearch, so v2 would inherit whatever v1 got
  wrong. The rule is that the index is rebuilt from Postgres. It also re-embeds nothing, though embeddings
  depend only on the text.
- **Dual writes to v1 and v2 during the build**: no catch-up needed, but the index worker would have to know
  about migrations (a write index per alias, or a second alias). Catch-up passes keep the worker unchanged, and
  the post-swap pass closes the gap.
- **A Postgres table for reindex progress**: a schema change for state that belongs to one index's lifetime.
- **Making search code version-aware** (nested facet aggregations on v2 only): the alias can point at either
  version during a move or rollback, so v2 has to answer v1's queries the same way. Using the nested facets and
  the autocomplete field (an endpoint) comes after the swap, as a public-interface change.

## Assumptions

- The catch-up signals cover every change to a document. A taxonomy upgrade remaps categories by SQL
  (docs/migrations.md B); don't run one during a reindex, or run a catch-up after it.
- Synonyms only widen matches, which is what the parity check assumes. A rule that narrowed them would fail it.
- On the golden set, v2's nDCG@10 equals v1's (0.8147) on the shipped path, and no query moved: the golden
  listings rarely use a shade where a query uses the base colour. The synonyms are kept because they fix real
  misses ("gray" against "grey") without costing a point. Swapped on the dev stack 2026-11-04 with 0 failed requests across the move; `search.INDEX` is products_v2 from then on.
