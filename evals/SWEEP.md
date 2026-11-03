# Shelfsense model sweep (dev split)

Enrichment replay, query parsing live; written 2026-11-03 19:50 UTC. Prompts enrich/2 and query/1, taxonomy 2021-09-21. Written by `evals/sweep.py`; the numbers are in `evals/results/sweep-dev.json`. (miss) marks a value outside its `make eval` gate.

## Enrichment (280 products)

| Metric | `qwen2.5:7b-instruct` | `llama3.1:8b` |
|---|---:|---:|
| Leaf accuracy | 0.836 | 0.857 |
| Hierarchical F1 | 0.886 (miss) | 0.891 (miss) |
| Candidate recall | 0.900 (miss) | 0.900 (miss) |
| Attribute macro F1 | 0.893 | 0.869 |
| Ungrounded | 4.6% | 7.2% (miss) |
| Schema valid first try | 99.6% | 100.0% |
| Answered NONE | 1.8% | 0.0% |
| Errors | 0.4% | 0.0% |
| Seconds per product | 5.52 | 5.83 |
| Products per hour | 652 | 617 |
| Output tokens/s | 24.1 | 22.6 |
| Memory (GB) | 4.8 | 5.3 |

- `llama3.1:8b` vs `qwen2.5:7b-instruct`, leaf accuracy: 9 items only it got right, 3 only the default did (McNemar exact p = 0.146, over 280 items).

Leaf accuracy by product type:

| Type | `qwen2.5:7b-instruct` | `llama3.1:8b` |
|---|---:|---:|
| absent | 1.000 | 1.000 |
| accessory | 0.714 | 0.786 |
| bundle | 0.700 | 0.800 |
| conflict | 0.875 | 0.875 |
| multi_use | 0.556 | 0.556 |
| non_english | 0.308 | 0.385 |
| rendered | 0.882 | 0.896 |

Attribute F1:

| Attribute | `qwen2.5:7b-instruct` | `llama3.1:8b` |
|---|---:|---:|
| color | 0.908 | 0.948 |
| material | 0.941 | 0.926 |
| gender | 0.714 | 0.667 |
| size | 0.967 | 0.984 |
| length | 0.937 | 0.819 |

## Query parsing (80 queries)

| Metric | `qwen2.5:3b-instruct` | `qwen2.5:7b-instruct` | `qwen2.5:7b-instruct, no time limit` |
|---|---:|---:|---:|
| Exact match | 0.762 | 0.562 (miss) | 0.850 |
| Slot F1 | 0.657 (miss) | 0.095 (miss) | 0.814 (miss) |
| Keyword F1 | 0.943 | 0.862 | 0.915 |
| Degraded (timeout or invalid) | 0.0% | 41.2% | 0.0% |
| Model-path p50 ms | 1,225 | 2,511 | 2,628 |
| Model-path p95 ms | 1,429 | 2,515 | 3,148 |
| Memory (GB) | 2.1 | 4.6 | 4.6 |

- `qwen2.5:7b-instruct` vs `qwen2.5:3b-instruct`, exact match: 2 items only it got right, 18 only the default did (McNemar exact p = 0.000, over 80 items).
- `qwen2.5:7b-instruct, no time limit` vs `qwen2.5:3b-instruct`, exact match: 10 items only it got right, 3 only the default did (McNemar exact p = 0.092, over 80 items).

Rows without a time limit in their name run under production's `QUERY_TIMEOUT_S` (2.5 s); a parse past it degrades to keywords.

## Not run

- `qwen2.5:14b-instruct`: not run: its 4-bit weights are ~9 GB, and on this 16 GB Mac ~7 GB is free with the stack's containers up (Metal's working-set limit is ~10.7 GB), so it would swap and its throughput would measure the swap.
