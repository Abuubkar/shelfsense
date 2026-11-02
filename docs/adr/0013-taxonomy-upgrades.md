---
status: accepted
date: 2026-11-02
---

# Taxonomy upgrades: side-by-side releases, SQL remap, reclassify only what changed

**Chosen.** Taxonomy releases live side by side in `taxonomy_nodes` (keyed by version) and products have a
category per release in `product_categories`. An upgrade (`scripts/taxonomy_upgrade.py`):

1. loads the new release beside the served one;
2. diffs them (`taxonomy.diff_releases`) into `taxonomy_remaps`: matching by ID first (Google keeps IDs across
   renames), then by path; a leaf that gained children is **split**; several old nodes landing on one new node
   are **merged**; unmatched ones are **deleted**; anything matched only by path, or not at all, is flagged
   `needs_review`;
3. copies categories in SQL for same, renamed and merged nodes;
4. queues only products in split or deleted nodes for classification, into the new release
   (`EnrichRequest.taxonomy_version`), while the old release is still served;
5. switches `TAXONOMY_VERSION` once no product is waiting, and reindexes only the products whose category changed.

Rehearsed with a synthetic release (5 renames, 2 splits, 1 delete, on populated nodes): 39 products remapped by
SQL, 6 reclassified by the model; split products landed in the new children with confidence 1.0, and products
from the deleted category got a low-confidence pick (0.08) that marks them for review.

The switch is a setting, so it's per process: API and workers restart onto it. Because the new release is
complete before the switch, either version serves consistent data during the rollout.

## Alternatives

- **Reclassify the whole catalog**: simplest, but at ~1,300 products/hour per Ollama, a 200k catalog takes a week.
- **Rewrite categories in place**: no second copy, but no rollback and a window where readers see a mix.
- **Served version in a database row** (one UPDATE switches everyone at once): stricter atomicity than per-process
  settings; worth it once several services read the taxonomy.

## Assumptions

- Google keeps a node's ID when it's renamed or moved, and gives new nodes new IDs.
- Products in "same" nodes don't benefit from reclassification: their candidates didn't change.
