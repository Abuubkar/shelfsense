# Shelfsense eval report (dev split)

replay run, 2026-11-04 03:14 UTC. Enrichment model `qwen2.5:7b-instruct` (enrich/2), query model `qwen2.5:3b-instruct` (query/1), taxonomy 2021-09-21.

Written by `evals/run.py`; the numbers are in `evals/results/dev.json`.

## Gates

| Metric | Value | Gate | |
|---|---:|---|---|
| enrichment.leaf_accuracy | 0.8357 | >= 0.8 | pass |
| enrichment.hierarchical_f1 | 0.886 | >= 0.9 | **miss** |
| enrichment.candidate_recall | 0.9 | >= 0.97 | **miss** |
| enrichment.attribute_macro_f1 | 0.8933 | >= 0.85 | pass |
| enrichment.ungrounded_rate | 0.0458 | <= 0.05 | pass |
| enrichment.schema_validity | 0.9964 | >= 0.98 | pass |
| enrichment.products_per_hour | 629 | >= 400 | pass |
| parse.exact_match | 0.7625 | >= 0.75 | pass |
| parse.slot_f1 | 0.6567 | >= 0.9 | **miss** |
| search.ndcg10 | 0.8208 | >= 0.72 | pass |
| search.ndcg10_over_bm25 | 0.1085 | >= 0.08 | pass |
| search.zero_result_rate | 0.0375 | <= 0.02 | **miss** |
| latency.rules_p95_ms | 2110 | <= 150 | **miss** |
| latency.llm_p95_ms | 3630 | <= 3000 | **miss** |
| latency.cache_p95_ms | 1876 | <= 180 | **miss** |

Against the baseline: no drop over 1.5 points.

## Enrichment (280 products)

| | |
|---|---:|
| candidate recall | 0.9 |
| leaf accuracy | 0.8357 |
| hierarchical f1 | 0.886 |
| attribute macro f1 | 0.8933 |
| ungrounded rate | 0.0458 |
| unnormalized rate | 0.0646 |
| none rate | 0.0179 |
| error rate | 0.0036 |
| schema validity | 0.9964 |
| seconds per product | 5.72 |
| products per hour | 629 |
| tokens per second | 22.9 |

Seconds per product is model time (the recorded wall time of its model calls).

| Attribute | Precision | Recall | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| color | 0.976 | 0.848 | 0.908 | 162 | 4 | 29 |
| material | 0.988 | 0.898 | 0.941 | 168 | 2 | 19 |
| gender | 1.000 | 0.556 | 0.714 | 10 | 0 | 8 |
| size | 1.000 | 0.935 | 0.967 | 29 | 0 | 2 |
| length | 1.000 | 0.881 | 0.937 | 52 | 0 | 7 |

| Products | Leaf accuracy |
|---|---:|
| absent | 1.000 |
| accessory | 0.714 |
| bundle | 0.700 |
| conflict | 0.875 |
| multi_use | 0.556 |
| non_english | 0.308 |
| rendered | 0.882 |

Depth-2 confusion (gold → predicted, off-diagonal):

| Gold | Predicted | n |
|---|---|---:|
| Apparel & Accessories > Shoes | Sporting Goods > Exercise & Fitness | 2 |
| Arts & Entertainment > Hobbies & Creative Arts | Hardware > Building Consumables | 2 |
| Home & Garden > Kitchen & Dining | Sporting Goods > Outdoor Recreation | 2 |
| Luggage & Bags > Backpacks | NONE | 2 |
| Luggage & Bags > Backpacks | Sporting Goods > Outdoor Recreation | 2 |
| Software > Computer Software | NONE | 2 |
| Apparel & Accessories > Clothing | Apparel & Accessories > Shoes | 1 |
| Apparel & Accessories > Clothing | NONE | 1 |
| Apparel & Accessories > Clothing | Sporting Goods > Exercise & Fitness | 1 |
| Arts & Entertainment > Hobbies & Creative Arts | Hardware > Tools | 1 |
| Arts & Entertainment > Hobbies & Creative Arts | Home & Garden > Fireplace & Wood Stove Accessories | 1 |
| Business & Industrial > Work Safety Protective Gear | Sporting Goods > Outdoor Recreation | 1 |
| Electronics > Audio | Vehicles & Parts > Vehicle Parts & Accessories | 1 |
| Electronics > Communications | Vehicles & Parts > Vehicle Parts & Accessories | 1 |
| Electronics > Video Game Console Accessories | Electronics > Electronics Accessories | 1 |
| Furniture > Office Furniture | Furniture > Chairs | 1 |
| Health & Beauty > Personal Care | NONE | 1 |
| Home & Garden > Lawn & Garden | Furniture > Chairs | 1 |
| Home & Garden > Lighting | Electronics > Electronics Accessories | 1 |
| Luggage & Bags > Backpacks | Apparel & Accessories > Clothing | 1 |
| Software > Computer Software | Furniture > Office Furniture | 1 |

Top confused leaf pairs:

| Gold | Predicted | n |
|---|---|---:|
| Hardware > Tools > Screwdrivers | Hardware > Tools > Tool Sets > Hand Tool Sets | 2 |
| Luggage & Bags > Backpacks | NONE | 2 |
| Software > Computer Software > Business & Productivity Software | NONE | 2 |
| Animals & Pet Supplies > Pet Supplies > Pet Collars & Harnesses | Animals & Pet Supplies > Pet Supplies > Pet Leashes | 1 |
| Apparel & Accessories > Clothing > Outerwear > Coats & Jackets | Apparel & Accessories > Clothing > Outerwear > Chaps | 1 |
| Apparel & Accessories > Clothing > Outerwear > Coats & Jackets | Apparel & Accessories > Clothing > Outerwear > Rain Suits | 1 |
| Apparel & Accessories > Clothing > Outerwear > Coats & Jackets | Apparel & Accessories > Shoes | 1 |
| Apparel & Accessories > Clothing > Outerwear > Coats & Jackets | Sporting Goods > Exercise & Fitness > Weighted Clothing | 1 |
| Apparel & Accessories > Clothing > Shirts & Tops | Apparel & Accessories > Clothing > Uniforms > Contractor Pants & Coveralls | 1 |
| Apparel & Accessories > Clothing > Underwear & Socks > Socks | NONE | 1 |
| Apparel & Accessories > Shoes | Sporting Goods > Exercise & Fitness > Cardio > Cardio Machines > Stair Climbers & Steppers > Stair Climbers | 1 |
| Apparel & Accessories > Shoes | Sporting Goods > Exercise & Fitness > Sport Safety Lights & Reflectors | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Hardware > Building Consumables > Painting Consumables > Paint | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Hardware > Building Consumables > Painting Consumables > Varnishes & Finishes | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Hardware > Tools > Paint Tools > Paint Strainers | 1 |

## Query parsing (80 queries)

Exact match (all filters right) 0.762, slot F1 0.657, keyword F1 0.943. Fast path 52.5%, degraded 0.0% ({'llm': 38, 'rules': 42}). Model time p50 0 ms, p95 1280 ms; on the model path p50 1223 ms, p95 1440 ms.

| Slot | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|
| colors | 0.875 | 7 | 2 | 0 |
| exclude_colors | 0.000 | 0 | 0 | 0 |
| materials | 0.320 | 4 | 2 | 15 |
| exclude_materials | 0.400 | 1 | 1 | 2 |
| price_min | 0.000 | 0 | 0 | 0 |
| price_max | 1.000 | 3 | 0 | 0 |
| gender | 1.000 | 5 | 0 | 0 |
| size | 0.800 | 2 | 1 | 0 |

Wrong parses:

| Query | Source | Got | Wanted |
|---|---|---|---|
| mesh office chair under $200 | llm | price_max=20000 | price_max=20000 materials=mesh |
| stainless steel water bottle | llm | exclude_materials=stainless steel | materials=stainless steel |
| silicone phone case | llm | (none) | materials=silicone |
| wood bookcase | llm | (none) | materials=wood |
| glass coffee table | llm | (none) | materials=glass |
| canvas backpack | llm | (none) | materials=canvas |
| down sleeping bag | llm | (none) | materials=down |
| wooden prayer beads | rules | (none) | materials=wood |
| leather luggage tag | llm | (none) | materials=leather |
| aluminum suitcase | llm | (none) | materials=aluminum |
| rubber yoga mat | llm | (none) | materials=rubber |
| nylon safety gloves | llm | (none) | materials=nylon |
| wood drum sticks | llm | (none) | materials=wood |
| bamboo knitting needles | llm | (none) | materials=bamboo |
| office chair no leather | llm | materials=leather | exclude_materials=leather |
| water bottle not plastic | llm | materials=plastic | exclude_materials=plastic |
| 26 cm cast iron pan | llm | size=US 26 | materials=cast iron |
| red wing boots | llm | colors=red | (none) |
| pink floyd vinyl | llm | colors=pink | (none) |

## Search (80 queries over 400 golden products)

nDCG@10 by tier: {'head': 0.9695, 'torso': 0.8273, 'tail': 0.5681}.

| Configuration | nDCG@10 | MRR | Zero results |
|---|---:|---:|---:|
| BM25 only | 0.7123 | 0.7509 | 18.8% |
| vector only | 0.8572 | 0.8765 | 0.0% |
| hybrid, min-max (shipped) | 0.8690 | 0.8786 | 0.0% |
| hybrid + rerank, min-max (shipped) | 0.8718 | 0.8541 | 0.0% |
| hybrid, min-max, BM25 floor 0 | 0.8783 | 0.8780 | 0.0% |
| hybrid + rerank, min-max, BM25 floor 0 | 0.8774 | 0.8541 | 0.0% |
| hybrid, l2 | 0.8693 | 0.8693 | 0.0% |
| hybrid + rerank, l2 | 0.8719 | 0.8541 | 0.0% |
| hybrid, z-score | 0.8694 | 0.8771 | 0.0% |
| hybrid + rerank, z-score | 0.8756 | 0.8541 | 0.0% |
| hybrid, RRF (rank 60) | 0.8768 | 0.8828 | 0.0% |
| hybrid + rerank, RRF (rank 60) | 0.8764 | 0.8541 | 0.0% |
| hybrid + rerank + parsed filters (shipped) | 0.8208 | 0.8875 | 3.8% |

Lowest nDCG@10 (shipped configuration):

| Query | Tier | nDCG@10 |
|---|---|---:|
| backpak for kids | tail | 0.000 |
| 26 cm cast iron pan | tail | 0.000 |
| red wing boots | tail | 0.000 |
| pink floyd vinyl | tail | 0.000 |
| office chair no leather | tail | 0.076 |
| stainless steel water bottle | torso | 0.087 |
| water bottle not plastic | tail | 0.087 |
| bag to carry a laptop and books | tail | 0.253 |
| mens hiking boots size 10 | torso | 0.471 |
| teliscope | tail | 0.493 |

## Index versions (served: `products_v2`)

| Version | nDCG@10 (shipped path) | MRR | Zero results | BM25 only | Hybrid + rerank | Head / torso / tail |
|---|---:|---:|---:|---:|---:|---|
| `products_v1` | 0.8208 | 0.8875 | 3.8% | 0.7103 | 0.8718 | 0.970 / 0.827 / 0.568 |
| `products_v2` | 0.8208 | 0.8875 | 3.8% | 0.7123 | 0.8718 | 0.970 / 0.827 / 0.568 |

No query's nDCG@10 moved on `products_v1`.

## Search latency (1000 searches on the catalog, live)

| Parse path | Searches | p50 ms | p95 ms |
|---|---:|---:|---:|
| cache | 313 | 510 | 1876 |
| llm | 38 | 2230 | 3630 |
| rules | 649 | 170 | 2110 |
