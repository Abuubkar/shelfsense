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
- **Models download on the first request** (slice 2; slice 7 kept them out of the images). The first search after a
  fresh start waits for the model downloads (~210 MB) unless `/app/models` is a volume that already has them.
  Options: warm both models at API startup (a slow start instead of a slow first search), or a separate model
  image/volume populated once per release. Since the smaller reranker (ADR 0021), baking them in costs ~210 MB per
  image per architecture per merge: worth reconsidering.
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
- **Min-max normalization and BM25 ties** (slice 5b; measured in 6a). When many lexical hits tie at the pool's
  minimum, min-max gives them all 0 and the hybrid ignores keyword for them. On the golden set, without the
  reranker, a BM25 floor of 0 (`lower_bounds`) scored nDCG@10 0.876 against min-max's 0.866 (RRF 0.875, l2 0.873,
  z-score 0.854), but with the reranker every variant scored 0.871: 400 products are too few for the head of 50 to
  be selective. Deciding needs judgements on the catalog itself (head recall at 8k+ products), not this corpus.
- **Query model misses materials** (slice 6a). qwen2.5:3b left out 15 of 19 materials ("wood bookcase", "canvas
  backpack"), read "stainless steel water bottle" as an exclusion and "no leather" as an inclusion, and turned
  "red wing boots" and "pink floyd vinyl" into colour filters. The prompt's examples show only wool and cotton;
  try material and brand examples (prompt `query/2`), and the 7B model in the 6b sweep.
- **Filters that match nothing dead-end the search** (slice 6a). Only a parsed price is dropped when it zeroes the
  results (`price_relaxed`); a wrong colour or size from the parse returns nothing (3 of 80 dev queries). Relax
  parsed filters one by one before returning an empty page.
- **Candidate recall 0.90 on the golden set** (slice 6a). The embedding pre-filter misses the right leaf for 1 in
  10 products, and the model can't pick what it isn't offered; non-English listings (leaf accuracy 0.31),
  multi-use items (0.56) and bundles (0.70) suffer most. Try more candidates (25) or a multilingual embedding
  model, and measure.
- **`wooden` doesn't wake the query model** (slice 6a). The fast path's material words are the normalized
  vocabulary, so "wooden prayer beads" skips the model and loses its material.
- **Search latency is the CPU reranker** (slice 6a; mostly addressed in slice 7, ADR 0021). Measured with
  bge-reranker-base over a head of 50: p95 2,110 ms on the rules path, 1,876 ms on cache hits, 3,630 ms on model
  parses (gates 150, 180, 3,000). Slice 7 moved to ms-marco-MiniLM-L-6-v2 (int8) over a head of 5 (~10 ms of
  rerank on the M1 Pro; golden nDCG@10 0.8147 -> 0.8235). Still open: `make eval-latency` has to be re-run live once Ollama
  is free (the numbers in evals/results are the old setup's); caching rerank scores per (query, product content
  hash) for repeated head queries; and a latency query set written for the catalog (17 of the 80 golden dev
  queries find nothing in it). Size `RERANK_THREADS` per deployment from `scripts/search_timings.py --rerank-threads`:
  one thread won on a 4-vCPU CI runner, onnxruntime's default on an 8-core Mac (ADR 0021).
- **Model choice: recommendation from the 6b sweep, defaults unchanged** (`evals/SWEEP.md`).
  - *Enrichment: keep qwen2.5:7b.* llama3.1:8b scored 2.1 points more leaf accuracy (0.857 vs 0.836: 9 products
    only it got right, 3 only qwen did, McNemar p = 0.15, so not shown to be better), mostly on accessories,
    bundles and non-English listings. But its ungrounded rate is 7.2% (gate 0.05), its attribute macro F1 is 2.4
    points lower (length 0.82 vs 0.94, gender 0.67 vs 0.71), and it is 5% slower with 0.5 GB more memory. Neither
    model fixes hierarchical F1 or candidate recall: candidate recall is the embedding pre-filter's (0.900 for
    both), so the candidate-recall item above is the bigger lever.
  - *Query parsing: keep qwen2.5:3b under the 2.5 s limit.* The 7B parses better given time (exact match 0.850 vs
    0.762, slot F1 0.814 vs 0.657; 10 queries vs 3, p = 0.09 over 80), but its model-path p50 is 2.6 s and p95
    3.1 s, so under the production limit 41% of its parses time out and it scores far worse (exact match 0.562,
    p < 0.001). It would miss the 3 s model-path gate before search even starts. Try first: prompt `query/2`
    with material and brand examples (item above) on the 3B, then re-run `make sweep`. If the 7B's quality is
    still wanted, it could pre-parse the most frequent queries offline into the Redis cache (31% of the latency
    run's searches were cache hits), keeping the 3B for the live path.
  - *Not run: qwen2.5:14b.* ~9 GB of 4-bit weights against ~7 GB free on this 16 GB Mac with the containers up.
    Worth a run on a 32 GB machine or a GPU host before slice 7 sizes production.
- **Open PITs cap search throughput** (found by slice 7's perf-smoke). Every first-page search that has more pages
  opens a point-in-time and keeps it 5 minutes (ADR 0006); OpenSearch allows 300 open PITs per node by default, so
  past ~300 such searches in 5 minutes on one node, new searches fail with 429 ("Trying to create too many Point
  In Time contexts"). ADR 0006 assumed 300 was enough; a 500-search CI run plus 120 more crossed it. Options:
  open the PIT only when page 2 is asked for, re-running page 1 on it and checking the head matches (keeps the
  snapshot guarantee for page 2 onwards); a shorter keep-alive (1 minute between pages); raising
  `search.max_open_pit_context` with heap to match; or delete PITs of searches nobody pages. Needs a decision on
  ADR 0006's guarantee and a load test.

