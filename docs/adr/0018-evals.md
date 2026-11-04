---
status: accepted
date: 2026-11-03
---

# Evals: a fixed golden set, metrics written out, model replies recorded for replay

**Chosen.** `evals/run.py` measures enrichment, query parsing and search ranking over a fixed golden set and exits 1
when a gate is missed (`make eval`; `make eval LIVE=1` against Ollama). Numbers go to `evals/results/<split>.json`
and `evals/REPORT.md`.

- **Golden set** (`evals/golden/`, rebuilt by `make golden`). `products.jsonl` has 300 products rendered with
  the seed generator's supplier quirks (abbreviated colours, inch/cm units, EU sizes, typos), 15 in each of the 20
  top-level taxonomy branches. That is every branch except Mature: the 2021-09-21 release has 21, not 25. The
  other 100 are hand-written hard cases: 20 accessories that name a device ("fits iPhone 15"), 15 bundles,
  15 multi-use products, 15 conflicts and traps ("Red Wing" boots, "Iron Man" figure, a title that says stainless
  steel over a description that says plastic), 20 listings that state almost nothing, and 15 Spanish, French,
  German or Italian ones. Gold is a leaf `node_id` plus the five attributes as the listing states them,
  normalized, or ABSENT. Gold attributes are worked out from the truth and the supplier's quirks, not with
  `normalize.py`, so the eval doesn't grade the code with itself. `queries.jsonl` has 120 queries (40 head,
  50 torso, 30 tail: typos, negations, unit variants, brand names that hold a colour word) with gold parses.
- **Relevance** is graded 0–3 for every query × product from ground truth (`evals/grading.py`, unit-tested). A
  product scores 3 when it is in the category and meets every constraint, 2 when it meets at least half, and 1
  for the category alone or a sibling under a parent below the top level.
- **Splits**: a fixed hash split. 280/120 products and 80/40 queries. `make eval-test` runs the test split.
- **Search is measured apart from classification.** It runs on its own index (`evals-golden-v1`) of all 400
  golden products, with gold categories and gold attributes standing in for the extracted ones (facets use the
  supplier's column first, as in production), and the documents built by `indexing.product_doc`. The
  configurations are
  BM25 only, vector only, hybrid, hybrid + rerank under each score normalization, and the shipped path: the API's
  `service.search_page` with query parsing.
- **Offline replay.** `llm.chat_json` records each reply by a hash of the whole request (model, messages, schema,
  options), timeouts and refusals included, with its wall time. A replay answers from the recording, and the
  metrics read model time from the recorded wall times, so a replay reports exactly the live run's numbers.
  OpenSearch and the reranker run for real in both modes, and both are deterministic. The recording
  (`evals/recordings/<split>.jsonl.gz`) is committed, so CI can replay it without a GPU. So are the embedding
  pre-filter's candidates per product (`<split>-candidates.json.gz`): on CI's x86 runners float differences in
  the embeddings swapped a near-tied candidate, which changed a prompt and missed its reply (slice 7). A live run first copies
  the previous recording to `evals/archive/`.
- **Metrics are written out** (`evals/metrics.py`, about 100 lines with unit tests) rather than taken from a
  library such as ranx or scikit-learn. Each is a few lines, and writing them pins the exact definitions the gates
  depend on:
  - nDCG uses exponential gain, and a query with nothing relevant is skipped.
  - Hierarchical F1 is micro-averaged over ancestor sets, and NONE predicts the empty set.
  - An attribute predicted where the gold is ABSENT counts as a false positive.
  - Parse exact match is on the filters; keywords are free text, scored by token F1.

  The libraries would add a dependency and still leave those choices to configure.

- **Model sweep** (`evals/sweep.py`, `make sweep`): the same enrichment and parse evals per model on the dev
  split, one recording per section, McNemar's exact test against the default, and memory from `ollama ps`. It
  reports; defaults change only by a separate decision.

## Alternatives

- **The catalog's 200k seeded products as the search corpus**: real scale, but most query × product pairs would
  have no judgement, and the 18 seed kinds cover only 6 branches.
- **Search over predicted categories**: closer to production, but a classification miss would read as a ranking
  miss. Enrichment has its own numbers.
- **Mocking the model in the eval**: replay keeps the real replies, so a replayed metric means something.
- **One recording per section**: simpler to reason about, but the search section re-parses the same queries.
  A single recording keyed by request serves both.

## Assumptions

- The golden products are realistic enough. The rendered ones are clean templates with supplier noise, so leaf
  accuracy on them flatters the model, and the hard cases are where it should fall. Report the two apart.
- A 400-product corpus says how ranking orders relevant products, not how it scales. Scale is the latency
  section's job (live, on the catalog).
- Hand-written golds hold judgement calls (a bundle's category is its main item; a "Kids" title over an
  adult-sized description has no gender). Change a gold with a note, never to make a number pass.
