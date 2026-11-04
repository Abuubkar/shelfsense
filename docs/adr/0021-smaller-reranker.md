---
status: accepted
date: 2026-11-04
---

# A smaller cross-encoder over a head of 5

**Chosen.** Search reranks its top 5 hybrid results (`search.HEAD_SIZE`) with `Xenova/ms-marco-MiniLM-L-6-v2`
(`embeddings.RERANK_MODEL`, ~80 MB). Before, it reranked the top 50 with `BAAI/bge-reranker-base` (~1.1 GB).
The rest of the result set keeps the hybrid order (ADR 0006's tail, unchanged).

Measured on the M1 Pro CPU and the golden set. Rerank time is the median over 20 golden queries' texts; nDCG is
the shipped search path, replayed (evals/run.py):

| Reranker | Head | nDCG@10 | MRR | Rerank time |
|---|---:|---:|---:|---:|
| bge-reranker-base | 50 | 0.8147 | 0.8708 | 2,551 ms |
| bge-reranker-base | 20 | 0.8110 | 0.8708 | 1,019 ms |
| MiniLM-L-6 | 50 | 0.8247 | 0.8875 | 294 ms |
| MiniLM-L-6 | 20 | 0.8215 | 0.8875 | 113 ms |
| MiniLM-L-6 | 10 | 0.8208 | 0.8875 | 54 ms |
| **MiniLM-L-6** | **5** | **0.8223** | **0.8875** | **~27 ms** |

- The fast path's gate is a p95 of 150 ms for the whole search. A head of 10 was the first choice, from M1
  numbers. CI's perf-smoke then missed at 154–187 ms p95. Its stage breakdown (`scripts/search_timings.py`)
  put reranking at a median 77 ms and p95 134 ms for 10 products on a GitHub runner, about 2.3× the Mac, while
  retrieval, tail and facets took under 10 ms each on 5,000 products. Halving the head halves the dominant
  cost, and on the golden set it scores no lower (0.8223 against 0.8208).
- The ranking explainer in the storefront reads the head size from the API (`debug.head_size`) instead of
  hardcoding it.

## Alternatives

- **bge-reranker-base over a smaller head:** 1 s at 20 products, and lower nDCG than MiniLM at any size.
- **MiniLM over 20 or 50:** 0.0007 and 0.0039 more nDCG@10 than 10 for 2× and 5× the rerank time. That's within
  noise on a 400-product golden set, while the latency cost is certain.
- **Shorter rerank text (no description):** about 24% faster, but nDCG@10 falls to 0.792–0.796 at heads of 5–10.
  That's more than the 1.5-point regression tolerance against main, so the description stays.
- **Rerank-score cache per (query, product content hash):** it only helps repeated queries, so a first sighting
  still pays the full cost. Parked (docs/backlog.md).
- **Other fastembed rerankers** (jina tiny/turbo, MiniLM-L-12): not measured. Each is a new download, and
  MiniLM-L-6 already clears the bar.

## Assumptions

- The golden set ranks like the catalog. It's 400 products, so most queries match fewer than 50 and the head-size
  effect is understated. A catalog with judgements would say more.
- CI's runners are in the same speed class as the M1 Pro for onnxruntime. perf-smoke on CI is the check.
- `make eval-latency` must be re-run live once Ollama is free: the latency figures in evals/results are from
  bge-reranker-base over 50.
