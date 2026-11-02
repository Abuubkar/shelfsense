---
status: accepted
date: 2026-11-02
---

# Hybrid search: one defined result set, a reranked head, a PIT-paged tail

**The problem.** Hybrid scores are min-max normalized over whatever each subquery retrieved, so they aren't
stable across pages. A cross-encoder reranker is too slow to run over thousands of results. Yet deep
pagination has to return every result exactly once, even while products are being reindexed.

**Chosen.**

1. **The result set** of a query is every product that matches lexically (BM25 `multi_match`, `cross_fields`,
   75% of terms) **or** semantically: *radial* k-NN with `min_score` 0.80, which is cosine ≥ 0.6. Radial search
   returns everything above a threshold instead of a fixed top-k, so the set has a definite size to page
   through and count. Filters apply to both sides.
2. **The head** is the first 50 products by the hybrid search pipeline (min-max normalization, arithmetic mean,
   weights 0.5/0.5), reranked by `bge-reranker-base` (a *cross-encoder* reads the query and product text
   together and scores their relevance, slower but more accurate than comparing embeddings).
3. **The tail** is the rest of the set, excluding the head's IDs, sorted by `_score` (BM25 + k-NN) with
   `product_id` as tiebreaker, paged with `search_after`.
4. **Every page of one query reads the same point-in-time (PIT) snapshot**, created on the first page and kept
   alive 5 minutes past each request. Updates and deletes after the PIT are invisible to that query.
5. **The cursor doesn't store the head.** Each page re-runs the hybrid query on the PIT to get the head's IDs.
   On one snapshot that query is deterministic. Pages that show head products also rerank; tail pages don't.
   This keeps cursors around 300 bytes, small enough to put one on every GraphQL edge.
6. **Facets** count the whole result set after all filters (drill-down facets), from a `size: 0` aggregation
   on the same PIT.

The service test pages 5,000 matching products (4,900 lexical, 100 semantic-only, 300 non-matching) at 48 per
page while renaming, deleting and adding products between pages, and gets each of the original 5,000 exactly
once. With the head exclusion removed, it fails with 5,050.

## Alternatives

- **Rerank everything**: ~1 s per 50 products on CPU; can't serve thousands.
- **Hybrid `pagination_depth` with from/size**: still offset paging, capped by `max_result_window`, and the
  normalized scores shift as depth changes.
- **Store the head IDs in the cursor**: about 1 KB per cursor, which multiplies across GraphQL edges. Saves one
  hybrid query (~20 ms) per tail page.
- **Top-k k-NN instead of radial**: the set would depend on k, not on similarity.
- **Multi-select facets** (each facet counted without its own filter): more queries per page. Revisit with the UI
  in slice 5.

## Assumptions

- A PIT keep-alive of 5 minutes between pages is enough for people and the smoke test. OpenSearch allows 300 open
  PITs per node by default. The last page deletes its PIT, and abandoned ones expire.
- The 0.80 threshold admits some weak matches (they sink to the bottom after reranking). Slice 6 tunes it, and
  the weights, against nDCG.
