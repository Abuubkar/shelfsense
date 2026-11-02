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
