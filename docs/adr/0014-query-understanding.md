---
status: accepted
date: 2026-11-02
---

# Query understanding: rules first, a small model under a time limit, cache, degrade

**Chosen** (`query.py`, used by `service.search_page`):

1. **Rules fast path.** A query with no price, size, colour, gender, material or negation words ("hiking boots",
   "charger for laptop") is searched as typed. No model call.
2. **Cache.** Redis, 24 h, keyed on the normalized query (NFKC, lowercase, single spaces, no surrounding
   punctuation, curly quotes straightened) plus the prompt version and model, so a prompt change never serves an
   old parse. A cache that's down is only a miss.
3. **Small model.** `qwen2.5:3b-instruct` (settings), JSON-schema output (`QueryParse`: keywords, category hint,
   price range, colours, materials and their exclusions, gender, size), `num_ctx` 2048, within **2.5 s**. The API
   warms it at startup, because a cold load takes longer than the limit.
4. **Degrade.** A timeout or any failure searches the whole query as keywords, with `source: degraded` for the UI
   to say "showing broader results". Degraded parses aren't cached.

The model's answer is normalized like product attributes (colours to the base palette, dollars to integer cents,
a bare size number to US), and a few known 3B slips are corrected in code: "size 8" read as a letter size, a
`price_min` of 0. Parsed filters are hard filters, explicit request filters win per facet, a gendered parse also
matches unisex products, and shoe sizes compare in EU numbers. A **parsed price that matches nothing is dropped**
(`price_relaxed: true`) instead of returning an empty page.

**Paging stays consistent.** Page 1's parse travels inside the signed cursor (`carry`), so later pages search
exactly the same way even after the cache expires or the model answers differently. The cursor is bound to what
the client sent (q, explicit filters, `parse`), not to the parse.

## Alternatives

- **The enrichment model (7B) for queries**: better parses, but ~1 s slower per call and competes with bulk
  enrichment for the same Ollama slots.
- **Rules only**: no latency, but negations, ranges and phrasing ("for men", "between 20 and 50") multiply
  quickly; the slice 6 eval decides how much the model adds.
- **Price as a ranking boost** (the plan): our head is reranked by a cross-encoder, which would undo a boost;
  relaxing an empty price filter keeps the behaviour explainable.
- **Postgres as the cache**: one fewer service, but this is exactly a TTL key-value cache.

## Assumptions

- Most traffic is head queries: the fast path and the cache should absorb it. Slice 6's eval reports the mix.
- `category_hint` is returned but not applied: a hint wrongly applied as a filter would empty the page.
