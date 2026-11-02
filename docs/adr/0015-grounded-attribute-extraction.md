---
status: accepted
date: 2026-11-02
---

# Attribute extraction: one call with the category, every value grounded in an exact quote

**Chosen.** Enrichment (`classify.classify_product`, prompt `enrich/2`) asks for the category and the attributes
color, material, gender, size and length in one JSON-schema-constrained call. Each attribute names the field it
quotes (title, description, brand or raw_attributes) and the exact words. Then, in code (`attributes.ground`):

- **Located or dropped.** The quote must be an exact substring of the named field, as the model was shown it
  (also tried in Unicode NFC/NFD, so "é" written differently still matches). Offsets are stored in code points.
  A quote that isn't there is dropped and counted as ungrounded on the enrichment run.
- **The value comes from the quote.** It's normalized with slice 4's normalizers from the quoted words, not
  taken from the model: "Color: Navy" is navy even if the model said blue. The model's value only helps where the
  quote supports it (a material named in the quote; a size whose number is in the quote). A quote that states no
  known value is dropped as unnormalized.
- Stored in `product_extracted_attributes`, replaced on every enrichment, kept apart from the supplier's own
  `product_attributes`. Search facets use the supplier's column when it exists, else the extracted value.

The system prompt (glossary of allowed values, 6 worked examples including one with no attributes) is identical
for every product; everything that varies is in the user message, so Ollama reuses the processed prefix:
1,640 prompt tokens take ~350 ms after the first call. Generating the attribute JSON is the cost: ~6.5 s per
product on qwen2.5 7B (about 550/hour, above the 400/hour target), logprobs adding ~25%.

## Alternatives

- **A separate call for attributes**: the attribute prompt could skip the candidates, but every product would pay
  a second prompt and generation.
- **Trust the model's values**: simpler, but the "2.5L shell" → material "none" case (docs/challenges.md) is
  exactly what a quote check catches.
- **Fuzzy matching of quotes**: forgives whitespace slips, but loses the guarantee that the highlight is the text.

## Assumptions

- Five attributes cover the facets today; adding one means a glossary entry, an enum value and a normalizer.
- Offsets in code points are fine for clients; JavaScript indexes `Array.from(text)` (documented in the spec).
