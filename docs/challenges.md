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
