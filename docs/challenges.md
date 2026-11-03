# Challenges

What each slice ran into: the problem, what we did, why, and the alternatives.

## Slice 1

### The grammar forced "NONE" when the prompt didn't show the reply shape

- **Problem.** A first probe sent a bare instruction plus a JSON schema whose `category_id` enum held string IDs
  ("187", "5181", …). The logprobs showed the model wanted to write `1` (the start of a bare number 187); the
  grammar only allowed a quoted string, and the sampler ended up at `"NONE"` with token logprobs around −40.
  The JSON key itself came out mangled into odd tokens (`"c`, `ateg`, `o`, `ry`).
- **What we did.** The system prompt spells out the exact reply shape, `{"category_id": "<id>"}`, and says the
  ID is a string. With that, the same probe answered `"187"` with every token at logprob ≈ 0.
- **Why.** Constrained decoding only masks tokens; it doesn't tell the model what's wanted. Ollama's docs also
  recommend putting the schema in the prompt.
- **Alternatives.** An integer enum (`{"category_id": 187}`) also worked once the shape was shown, but would
  need a sentinel number for "none fits".

### The CSV row number isn't the line number

- **Problem.** A quoted description can span lines, so a line counter points a supplier at the wrong row.
- **What we did.** Rejections report spreadsheet row numbers (header = row 1), counted per CSV record.
  `sample.csv` has a three-line description at row 28 so the rejections after it (row 34) prove the count.

### Non-UTF-8 bytes would fail the whole file

- **Problem.** One Latin-1 row in a UTF-8 file makes a strict decode raise and stops the import.
- **What we did.** The file is read with `errors="surrogateescape"`: bad bytes become lone surrogates, and only
  the rows containing them are rejected (`invalid_encoding`); the excerpt shows them as U+FFFD.

### Toddler rain boots: the right category was never a candidate

- **Problem.** In the 10-product check, "Kids Rain Boots Toddler Waterproof Dinosaur" went to
  *Baby Protective Wear* with confidence 0.986. The expected *Apparel & Accessories > Shoes* wasn't among the
  15 candidates: "Toddler" pulled all of them into baby clothing and diapering.
- **What we did.** Recorded it; slice 1 doesn't tune retrieval. See docs/backlog.md.
- **Why it matters.** Logprob confidence can't catch this: the model is sure among the options it got.
  Candidate recall has to be measured separately (slice 6).

## Slice 2

### Hybrid scores aren't stable across pages, and reranking can't cover thousands

- **Problem.** Min-max normalization depends on what each subquery retrieved, and a cross-encoder can't score a
  whole result set, yet pages must return every match exactly once while the index changes.
- **What we did.** A defined result set (lexical OR radial k-NN), a reranked head of 50, a tail paged with
  `search_after`, all on one PIT snapshot (ADR 0006). A service test pages 5,000 products while changing the
  index between pages; removing the head exclusion makes it fail with 5,050.

### A PIT search sorted by `_score` alone returns no sort values

- **Problem.** On OpenSearch 3.9.0 the hits came back with `sort: null`, so there was nothing to pass to
  `search_after`.
- **What we did.** Sort by `_score` then `product_id`. Measured on a scratch index before writing the code.

### Relay wants a cursor on every edge

- **Problem.** The first cursor design carried the head's 50 IDs (~1 KB). One per GraphQL edge would add ~50 KB to
  a 48-item page.
- **What we did.** Each page re-runs the hybrid query on the PIT to recover the head (deterministic on one
  snapshot), so a cursor is `{pit, rank, search_after}`: 323 characters measured.

### oasdiff reported nullable fields as breaking

- **Problem.** The hand-written spec used `type: [string, 'null']`; Pydantic emits `anyOf` with a null branch, and
  oasdiff treats the difference as a widened type (10 false errors).
- **What we did.** The spec uses the `anyOf` form throughout, like Ledgerline's. A deliberately removed field still
  fails the check.

### zsh ate `:enrich`

- **Problem.** `curl .../products/$id:enrich` under zsh returned 404 for every product: `$id:e` is a zsh filename
  modifier, so the URL lost its suffix.
- **What we did.** `${id}:enrich`. The API was fine; the earlier enrichment run used bash.

### The first rerank took five minutes

- **Problem.** fastembed downloads `bge-reranker-base` (~1.1 GB) on first use, inside the first search request.
- **What we did.** Nothing yet; after the download a rerank of up to 50 products takes 75–300 ms. See backlog.

## Slice 3

### LocalStack now needs an account

- **Problem.** The plan names LocalStack, but since 2026.03.0 its image refuses to start without an auth token.
- **What we did.** Floci 2.3.0 (MIT, no account). Before writing code against it we probed what we'd rely on:
  receive counts, redrive after 5 receives, `StartMessageMoveTask` (and its refusal of a second task), presigned
  PUT, `NoSuchKey`. All matched the AWS docs (docs/adr/0008).
- **Alternatives.** LocalStack with a Hobby token per developer and CI runner; ElasticMQ plus an S3 server (no
  move tasks); moto (no move tasks).

### `enrich.dlq` isn't a valid SQS queue name

- **Problem.** The plan's DLQ names contain dots; SQS allows only letters, digits, `-` and `_` (dots only in
  the `.fifo` suffix).
- **What we did.** `aws.dlq_name()` makes `enrich-dlq` and `index-dlq`, the one place the convention lives.

### A late heartbeat could undo the backoff

- **Problem.** The heartbeat extends visibility to the full timeout every third of it. If it fired just after
  the consumer set a short backoff delay on a failed message, the retry would wait a full timeout instead.
- **What we did.** `_process` cancels and awaits the heartbeat before deleting, dead-lettering or delaying the
  message.

### Skipped products must still be indexed

- **Problem.** On redelivery after a crash, products already enriched are skipped. If the crash came after
  enriching but before sending the index message, skipping them would leave them enriched but never searchable.
- **What we did.** Skipped products count as done and go into the index message again. Re-indexing is
  idempotent; losing them isn't.

### Dead-lettering a product twice on redelivery

- **Problem.** A message whose worker dies after dead-lettering a product, but before deleting the message,
  comes back, and the product fails again: a second DLQ message, and a DLQ count that no longer equals the
  failed products.
- **What we did.** The `dead_letters` row is committed before the DLQ send, with a partial unique index on
  (queue, product) for open letters, and `sent_at` set after the send. A redelivery finds the open row and
  doesn't send again. A crash between the send and `sent_at` can still send twice, which is preferred over
  losing the message.

### The chaos script deadlocked on its own API

- **Problem.** `scripts/chaos.py` runs the API in its own event loop and uploads through the generated client,
  which is synchronous: calling it on the loop blocked the server it was waiting for.
- **What we did.** The upload runs in `asyncio.to_thread`.

### Index messages are too small for the adaptive batch size

- **Problem.** The enrich worker sends one index message per enrich message (at most 50 products), so the
  batch sizer halves from 500 toward 50 on rejections but never splits a batch in the worker. Its effect shows
  in `scripts/sync_index.py` (2,000 products per call) and in the unit tests.
- **What we did.** Kept it, and parked batching across messages in docs/backlog.md.

### aiobotocore pins wrapt below 2

- **Problem.** Adding aioboto3 15.5.0 downgraded `wrapt` from 2.5.2 to 1.17.3 (aiobotocore 2.25.1 requires
  `wrapt<2`). Only testcontainers also uses it, and its tests pass on 1.17.
- **What we did.** Accepted the downgrade; revisit when aiobotocore lifts the pin.

### Deleted documents hid live ones from k-NN search

- **Problem.** After two chaos runs had indexed and then deleted 4,000 products, `make smoke`'s paged query
  "outdoor gear for the trail" returned 5 products where an exact scan finds 13. Lucene only marks deleted
  documents; they stay in each segment's HNSW graph until the segment merges. The approximate search fills its
  candidate list (`ef_search`, default 100) with the nearest nodes, deleted ones included, and drops those
  afterwards. The chaos products were near-duplicates of the query ("Trail Hiking Boot …"), so they took the
  slots. Radial search with `ef_search` 200 found 9, with 1,000 all 13.
- **What we did.** `_forcemerge?only_expunge_deletes=true` on the dev index restored all 13 at the default
  `ef_search`, and the chaos script now does the same after its cleanup. An expunge run right after the delete
  left the deleted documents in place (the next smoke run found 2 of 13); one run minutes later removed them.
  Likely cause: OpenSearch retains soft deletes until the global checkpoint advances (synced every 30 s by
  default). So the script retries the expunge until the index reports no deleted documents.
- **What it means beyond the script.** Every update is a delete plus an insert in Lucene, and the index worker
  re-indexes products (on redelivery, on every enrichment). The merge policy keeps deletes to a share of the
  index, but recall drops in the meantime. Parked in docs/backlog.md for the slice 6 eval.

## Slice 4

### Dedupe alone can't fix a drifting offset scan

- **Problem.** The plan's first idea, dedupe by (sku, updated_at), removes the duplicates of a naive scan but not
  its holes: a product updated mid-scan jumps to the front, behind the reader. Against the mock (5,104 products,
  2 inserts and 3 updates per request) a naive scan read 185 twice and missed 185.
- **What we did.** Overlapping pages with anchor SKUs keep unchanged products exact (they can only shift later),
  and reconciliation re-reads from the top everything newer than the scan's first page, by the supplier's clock,
  until one page holds all the changes (ADR 0011). 0 missing, 0 extra, 0 outdated.
- **What made it work.** Taking the watermark from the supplier's own `updated_at`. A watermark from our clock
  needs a skew margin, and with any margin longer than the import, every pass re-reads everything and the loop
  never settles to one page.

### `next_offset` isn't the number of products imported

- **Problem.** The resume test first asserted products-before-failure == saved offset: 400 != 425. The offset
  is a position in a list that grew by 25 at the front during the scan.
- **What we did.** The test asserts saved pages × page size instead; the offset only says where to read next.

### The first migration rehearsal cut over to a process that wasn't listening

- **Problem.** The search loop was pointed at the freshly started old-code API before it accepted connections;
  525 requests failed with `ConnectError` in 10 s, though the migration itself had caused none.
- **What we did.** Discarded the run, added a gate (switch only after 3 × HTTP 200 in a row), and repeated the
  whole rehearsal from the top with one loop: 1,296 requests, 0 errors. The aborted run's logs are kept in
  `build/migration-demo/aborted/`.

### Killing `uv run` doesn't kill the script

- **Problem.** Interrupting the catch-up backfill with `pkill -INT -f "backfill_attributes.py"` hit the `uv`
  wrapper; the Python child ran to the end.
- **What we did.** Signal the interpreter itself (`pkill -f "python.*scripts/backfill_attributes.py"`). With
  SIGKILL after 3 batches, `backfill_state` held 60,000 and the rerun resumed there.

### Feed imports run at ~2,000 rows/s

- **Problem.** Seeding 200k products through the feed import took 92 s; committing the 100k-row feed 67 s.
  Profiling one 4,000-row file: most of the time is SQLAlchemy compiling and executing 500-row multi-VALUES
  statements (products, then product_attributes).
- **What we did.** Kept the one write path; parked COPY into a staging table in docs/backlog.md.

## Slice 5a

### A grounded quote can still carry a made-up value

- **Problem.** For "Packable 2.5L shell" the model returned material "none" with the quote "2.5L shell". The
  quote was really in the description, so a substring check passed, and the first version of the code fell back
  to the model's value and stored material = "none".
- **What we did.** The value is now derived from the quote (normalize.py); the model's value only helps where the
  quote supports it. "2.5L shell" names no material, so it's dropped and counted as unnormalized (ADR 0015).

### Prefix reuse looked broken because the model download was running

- **Problem.** The first enrichment runs showed ~2.3 s of prompt processing per product for a ~2,000-token prompt
  whose 1,600-token system part never changes: as if Ollama recomputed it every time.
- **What we did.** Measured again with nothing else running: 1,640 prompt tokens in ~350 ms on every call after
  the first, so the prefix is reused. The earlier numbers were taken while `ollama pull qwen2.5:3b-instruct` was
  downloading. Generation (~120 tokens of attribute JSON at ~20 tok/s) is the real cost.

### The 3B model's slips

- **Problem.** qwen2.5:3b read "size 8" as a letter size although the prompt says a bare number is US, filled
  `price_min: 0` for "under $120", and sometimes dropped a product word ("waterproof") from the keywords.
- **What we did.** The first two are deterministic, so code fixes them after the call (a numeric "alpha" size is
  US; a minimum of 0 is no minimum). Dropped keywords are left for the slice 6 eval to measure.

### The first query after a start always degraded

- **Problem.** Loading the 3B model takes longer than the 2.5 s limit, so the first parse after Ollama unloads
  it times out.
- **What we did.** The API warms the query model in the background at startup, and the model's keep-alive is
  30 minutes. A cold model still degrades cleanly; it just shouldn't be the normal case.

### Later pages must not re-parse

- **Problem.** If page 2 parsed the query again, a cache expiry or a different model answer would change its
  filters, so the signed cursor (bound to the query and filters) would be rejected, or worse, page through a
  different result set.
- **What we did.** Page 1's parse travels inside the cursor (`carry`), and the cursor is bound to what the client
  sent (q, explicit filters, `parse`). Later pages reuse the parse as is.

## Slice 5b

### The prototypes caught totals that didn't match the results

- **Problem.** A filtered search said "4 results" and showed 7. The total, facet counts and the tail come from
  the result-set query (`search.match_set`), which filtered *after* an approximate radial k-NN search over the
  whole index; the head's hybrid query put the filter *inside* k-NN. The approximate search stops early, so the
  post-filter lost three products whose exact cosine cleared the threshold.
- **What we did.** The filter goes inside the k-NN clause of `match_set` too (OpenSearch's efficient filtering),
  with a unit test. The same query's total went from 303 to 904: the old counts were missing products everywhere a
  filter applied.

### "under $100" became $100–$100

- **Problem.** The 3B query model sometimes writes a one-sided price as a range with equal ends.
- **What we did.** When both ends are equal, code keeps only the bound the query's own words ask for ("under",
  "below", "up to" → maximum; "over", "above", "at least" → minimum).

### `hidden` doesn't hide an element whose CSS sets `display`

- **Problem.** Several prototype "Load more" buttons and a hidden results panel stayed visible: an author style
  like `display:block` beats the `hidden` attribute.
- **What we did.** In the prototypes, `[hidden]{display:none}` or explicit style toggles; in apps/web, elements are
  rendered conditionally instead of hidden.

### MSW 2 in Jest: ESM-only dependencies and a captured fetch

- **Problem.** msw 2.15's dependencies include ES-module-only packages (`.mjs`, and `until-async` with
  `"type": "module"`), which Jest's CommonJS runtime refuses. Then requests escaped MSW: openapi-fetch captured
  `globalThis.fetch` at import, before MSW wrapped it.
- **What we did.** `jest.config.ts` compiles `.mjs` files and the named ESM package; the API client looks fetch up
  per call. (msw 3 is ESM-only throughout, the reason for staying on 2.x with Jest.)

### Versions picked against the docs

- **Problem.** The latest TypeScript (7.0, the Go-native compiler) no longer ships the JavaScript compiler API that
  openapi-typescript and ts-node use (openapi-typescript declares `typescript ^5`); Next.js 16.4.4 was hours old.
- **What we did.** TypeScript 5.9.3 and Next.js 16.4.3. The codegen client preset also needed
  `@graphql-typed-document-node/core` as an explicit dev dependency (approved): its output imports it, and pnpm
  doesn't expose transitive packages.

### Min-max normalization zeroes a pile of BM25 ties

- **Problem.** On "merrell hiking boots", every result but the two Merrells had `bm25_normalized` 0.0, although
  their raw BM25 scores were 8.549 or 7.661. Min-max maps the lowest lexical score in the hybrid pool to 0, and ~40
  near-identical "… HIKING BOOT" titles tie at that minimum, so for those products the hybrid score is meaning
  alone. The ranking section also gave tied products consecutive ranks ("#6 by keyword"), an order BM25 never gave.
- **What we did.** Tied scores now share a rank (1, 2, 2, 4) with "tied with N" beside it, and the footnote says the
  lowest result scores 0. The normalization itself is unchanged; noted in the backlog.

## Slice 6a

### The seed catalog covers 6 of 21 taxonomy branches

- **Problem.** The plan asked for golden products stratified over 25 top-level branches. The 2021-09-21 taxonomy
  has 21, and the seed generator's 18 kinds sit in only 6 of them, so a classifier eval built on the seeds alone
  would test 18 categories over and over.
- **What we did.** The golden builder adds 42 kinds over the other branches (all but Mature) and renders them with
  the seeds' own supplier quirks. Kinds such as coffee or software needed no colour, no material and their own
  adjectives, so `seed.Kind` gained three optional fields. The first 20,000 seed rows still render byte for byte
  as before (checked against `ground_truth.parquet`).

### The golden index searched without extracted attributes

- **Problem.** In production a facet comes from the supplier's column, or else from the attribute enrichment
  extracted (`indexing._facets`). The golden index passed no extracted attributes, so a colour or gender filter
  found nothing for the hard cases that have no columns. "pink phone case", "black headphones under $150" and
  "kids backpack" returned zero results, which read as a search failure.
- **What we did.** The golden index takes the gold attributes as its extracted ones, as it already took gold
  categories (search measured as if enrichment were perfect). Shipped-path nDCG@10 went from 0.791 to 0.815 and
  zero results from 8.8% to 3.8%. The first numbers are kept in `evals/archive/results/`.

### The reranker hides the normalization choice on a small corpus

- **Problem.** The BM25-ties experiment (slice 5b) needed the search eval. With 400 products, most queries match
  fewer than 50, so the head of 50 is the whole match set, and the cross-encoder reorders the same products
  whatever normalization chose them. Every variant scored nDCG@10 0.871 after reranking.
- **What we did.** Reported the variants with and without the reranker. Without it, a BM25 floor of 0 beat min-max
  by a point (0.876 vs 0.866). The pipeline is unchanged, and the decision waits for judgements on the catalog
  (docs/backlog.md).

### A CPU reranker can't meet a 150 ms search

- **Problem.** The plan's p95 gates (150 ms fast path, 180 ms cache hit) assume a fast reranker. On this Mac
  (M1 Pro, CPU) reranking the head of 50 took 0.8–2.0 s per search; embedding plus hybrid retrieval took
  10–170 ms.
- **What we did.** Measured it before the 1,000-search latency run and raised it rather than running into the
  miss. Options: a smaller head, a smaller cross-encoder, a GPU, or a separate gate for reranked searches. The
  decision was to run it as is and report the misses. `make eval-latency` (1,000 searches, 60/30/10 head, torso,
  tail) missed all three gates: p95 2,110 ms on the rules path (gate 150), 1,876 ms on cache hits (gate 180) and
  3,630 ms on model parses (gate 3,000). Reranking costs about 40 ms per product, so a full head of 50 takes
  1.2–2.1 s. Embedding, hybrid retrieval and the tail together took a median 29 ms (max 160 ms).
- **Why the p50s look better than they are.** The golden queries were written for the golden set, not the
  catalog: the catalog's 18 seed kinds leave 17 of the 80 dev queries with no results and 30 with fewer than 50,
  so those searches rerank little or nothing. The rules-path p50 of 170 ms is mostly them. Only the p95s describe
  a search with a full head.

### Replays match the live run exactly

- **Problem.** A replayed eval is only worth having if it reproduces the live numbers, latencies included, and the
  search side rebuilds its index every run (HNSW graphs can differ between builds).
- **What we did.** Model replies are recorded with their wall time and keyed by a hash of the whole request.
  The metrics read model time from the recording. The dev replay matched the live run in every enrichment, parse
  and search metric; OpenSearch returned the same rankings from a fresh index.
