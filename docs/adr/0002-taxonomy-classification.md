---
status: accepted
date: 2026-11-02
---

# Taxonomy classification: embedding pre-filter, enum-constrained pick, logprob confidence

**Chosen.** A product is classified in two steps:

1. **Pre-filter.** The product text (title, brand, description) is embedded with `BAAI/bge-small-en-v1.5`
   (fastembed, CPU) as a *query*, and every taxonomy leaf's full path ("Apparel & Accessories > Shoes") as a
   *passage*. The 15 nearest leaves by cosine distance are the candidates. An *embedding* is a vector of numbers
   that places similar texts close together.
2. **Pick.** `qwen2.5:7b-instruct` through Ollama chooses one candidate. The reply is constrained with Ollama's
   `format` JSON schema, whose `category_id` enum is exactly those 15 IDs plus `"NONE"`, built per request. The
   model can't name a category the pre-filter didn't offer, or one that doesn't exist.

**Confidence** is the model's probability of the ID it wrote, from Ollama's token `logprobs` (the product of the
probabilities of the tokens spelling the ID and its closing quote). We don't ask the model to state a confidence:
a number it writes is more text, not a measurement.

**No ANN index on `taxonomy_nodes.embedding`.** One release has 5,595 nodes (4,719 leaves). An exact scan of that
is milliseconds, and an HNSW index with a `WHERE version = … AND is_leaf` filter can return fewer than k rows
(the filter is applied after the index scan). Exact is both simpler and correct.

## Alternatives

- **Send the whole taxonomy to the model.** ~5.6k paths is ~100k tokens: too slow on a local 7B, and over its
  context.
- **Hierarchical descent** (top level, then children, …): one model call per level (up to 7), and an early wrong
  turn can't be recovered.
- **Self-reported confidence** in the schema: cheap, but uncalibrated.

## Assumptions

- The gold leaf is usually among the 15 candidates. Slice 6 measures this (candidate recall, target ≥ 0.97). In
  slice 1's 10-product spot check it wasn't for one product (docs/challenges.md); the logprob confidence can't
  flag that case, because the model is confident among the wrong options it was given.
- The logprobs Ollama returns are the model's before grammar masking (observed on Ollama 0.40.6), so a value the
  grammar forced scores low.
