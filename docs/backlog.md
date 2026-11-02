# Backlog

Improvements found and deliberately not done yet, with the suggested fix and its cost.

- **Candidate recall on short generic leaves** (slice 1). A leaf like *Apparel & Accessories > Shoes* has a
  short path, so a product whose text leans on another word ("Toddler") never gets it as a candidate. Options,
  to compare on the slice 6 golden set: embed `name + parent path + a few synonyms` per leaf; take candidates
  from both a title-only and a full-text query; or cap candidates per top-level branch so one branch can't take
  all 15. Cost: a re-embed of 5.6k paths (~50 s) and an eval run.
- **Embedding the query blocks a thread per request** (slice 1). Fine at one request at a time; the enrichment
  worker in slice 3 should embed in batches instead.
- **Semantic threshold lets in weak matches** (slice 2). At `min_score` 0.80 (cos 0.6), "something to keep drinks
  cold" also returns a laptop sleeve, ranked last by the reranker. Tune `KNN_MIN_SCORE` and `HYBRID_WEIGHTS`
  against nDCG on the slice 6 golden set; consider also dropping head items below a rerank score.
- **Models download on the first request** (slice 2). The first search after a fresh install waits for the
  reranker download (~1.1 GB). Warm both models at API startup, or in the Docker image build (slice 7).
- **Every tail page re-runs the hybrid query** (slice 2). ~10–50 ms per page to recover the head's IDs, the price
  of small cursors (ADR 0006). If deep paging gets hot, cache head IDs per PIT in Redis (slice 3 brings Redis).
- **Multi-select facets** (slice 2). Facet counts are drill-down (after all filters, including the facet's own).
  A storefront usually wants each facet counted without its own filter so other values stay visible; decide with
  the UI in slice 5.
