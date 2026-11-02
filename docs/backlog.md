# Backlog

Improvements found and deliberately not done yet, with the suggested fix and its cost.

- **Candidate recall on short generic leaves** (slice 1). A leaf like *Apparel & Accessories > Shoes* has a
  short path, so a product whose text leans on another word ("Toddler") never gets it as a candidate. Options,
  to compare on the slice 6 golden set: embed `name + parent path + a few synonyms` per leaf; take candidates
  from both a title-only and a full-text query; or cap candidates per top-level branch so one branch can't take
  all 15. Cost: a re-embed of 5.6k paths (~50 s) and an eval run.
- **Embedding the query blocks a thread per request** (slice 1). The enrich worker (slice 3) still embeds one
  product per call, in a thread; at 8 concurrent calls against the stub that was ~37 products/s. Embed a
  message's products in one batch before the model calls if the embedding shows up in profiles (slice 8).
- **Semantic threshold lets in weak matches** (slice 2). At `min_score` 0.80 (cos 0.6), "something to keep drinks
  cold" also returns a laptop sleeve, ranked last by the reranker. Tune `KNN_MIN_SCORE` and `HYBRID_WEIGHTS`
  against nDCG on the slice 6 golden set; consider also dropping head items below a rerank score.
- **Models download on the first request** (slice 2). The first search after a fresh install waits for the
  reranker download (~1.1 GB). Warm both models at API startup, or in the Docker image build (slice 7).
- **Every tail page re-runs the hybrid query** (slice 2). ~10–50 ms per page to recover the head's IDs, the price
  of small cursors (ADR 0006). If deep paging gets hot, cache head IDs per PIT in Redis (slice 5 brings Redis).
- **Multi-select facets** (slice 2). Facet counts are drill-down (after all filters, including the facet's own).
  A storefront usually wants each facet counted without its own filter so other values stay visible; decide with
  the UI in slice 5.
- **Index requests are capped at one enrich message** (slice 3). Each index message holds at most 50 products, so
  the adaptive batch size can't grow past 50 in the worker. Receive up to 10 index messages and index them as one
  bulk call (acking each message by its own items), when indexing throughput matters.
- **Feed commit runs inside the request** (slice 3). 2,000 rows commit in ~0.6 s; 100k rows would take tens of
  seconds and risk client timeouts. Make commit return 202 and run the import from an `import` queue, with
  `GET /v1/feeds/{id}` for status.
- **Admin endpoints have no auth** (slice 3). `POST /v1/admin/dlq/{queue}/redrive` is open, like the rest of the
  local API. Needs an admin role before any shared deployment.
- **A redrive keeps the message's attempt count** (slice 3). SQS's move task doesn't change bodies, so a product
  dead-lettered after 3 transient failures gets one more try when redriven. If redrives should start fresh, redrive
  by receive-and-resend with `attempt` reset instead of the move task.
- **Retry-After without a recent rate** (slice 3). With no enrichments in the last hour (workers down, or a cold
  start) a full backlog answers a fixed 300 s. Report "no workers" separately once slice 8 has worker heartbeats.
- **k-NN recall drops while deleted documents await merging** (slice 3). Measured: 5 of 13 radial matches at the
  default `ef_search` 100 with ~4k deleted near-duplicates in the graphs; 13 of 13 at `ef_search` 1,000 or after
  expunging deletes (docs/challenges.md). Options for slice 6, judged by recall against exact search on the golden
  queries: pass `method_parameters.ef_search` on the radial query, lower `index.merge.policy.deletes_pct_allowed`,
  or skip re-indexing products whose document didn't change.
- **Feed import throughput ~2,000 rows/s** (slice 4). Multi-VALUES statement compilation dominates. COPY each batch
  into a temporary staging table and `INSERT … SELECT … ON CONFLICT` from it; expect 10x. Keep `upsert_rows` as the
  one write path.
- **Supplier deletions aren't detected** (slice 4). A v1 or v2 listing only shows live products. Mark products not
  seen in a complete v2 snapshot (or a full v1 scan) as withdrawn, after a grace period.
- **Served taxonomy version per process** (slice 4). `TAXONOMY_VERSION` switches per process restart. When several
  services read it, move it to a database row read with a short cache so one UPDATE switches everyone.
- **Remapped categories keep old-release candidate IDs** (slice 4). `candidate_ids` copied by the taxonomy remap
  name nodes of the previous release. Map them through `taxonomy_remaps` or mark them as such if they're used for
  more than diagnostics.
- **Seeds aren't enriched or indexed** (slice 4). 300k seed and bulk-feed products sit in Postgres only; search
  covers the 45 enriched ones. Slice 6's eval enriches its golden subset; indexing all of them takes ~15 min of CPU
  embedding (see "Embedding the query blocks a thread").
- **`category_hint` isn't used** (slice 5a). The parse returns it ("hiking boots") but search ignores it, since a
  wrong hard filter would empty the page. Try it as a ranking signal or a suggested facet once slice 6 can measure.
- **No gender or material facets in responses** (slice 5a). They're filterable (and indexed), but adding values to
  the response's facet-name enum is a contract change; do it with the UI in slice 5b if a concept needs them.
- **Enrichment ~6.5 s per product** (slice 5a). Generating the attribute JSON dominates. Shorter keys, dropping
  `unit` for non-lengths, or logprobs only on the category token would cut output and time; measure with the eval.
- **Editable parsed filters** (slice 5b). The storefront shows "From your search" read-only. Removing one needs the
  API to take gender, size, materials and exclusions as explicit parameters (prototype B rebuilt the query text
  instead). Add them to `/v1/search` and the facets if shoppers ask to undo a parse.
- **Search-as-you-type** (slice 5b). Prototype E showed typeahead works without the model (`parse=false`, ~30 ms);
  a `/v1/suggest` endpoint with query suggestions would make it a real feature.
- **Mobile filter tray** (slice 5b). The sidebar stacks above results under 760 px; prototype H's bottom-sheet tray
  with a live result count is the better phone design.
- **GraphQL `Money.amountMinor` is a 32-bit Int** (slice 5b). Amounts above $21,474,836.47 overflow GraphQL's Int.
  Switch to a string or a custom scalar before high-value catalogs.
- **Min-max normalization and BM25 ties** (slice 5b). When many lexical hits tie at the pool's minimum, min-max gives
  them all 0 and the hybrid ignores keyword for them. Try the `l2` or z-score normalization technique (or RRF) and
  compare with the search eval before changing the pipeline.
