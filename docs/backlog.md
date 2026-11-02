# Backlog

Improvements found and deliberately not done yet, with the suggested fix and its cost.

- **Candidate recall on short generic leaves** (slice 1). A leaf like *Apparel & Accessories > Shoes* has a
  short path, so a product whose text leans on another word ("Toddler") never gets it as a candidate. Options,
  to compare on the slice 6 golden set: embed `name + parent path + a few synonyms` per leaf; take candidates
  from both a title-only and a full-text query; or cap candidates per top-level branch so one branch can't take
  all 15. Cost: a re-embed of 5.6k paths (~50 s) and an eval run.
- **Embedding the query blocks a thread per request** (slice 1). Fine at one request at a time; the enrichment
  worker in slice 3 should embed in batches instead.
