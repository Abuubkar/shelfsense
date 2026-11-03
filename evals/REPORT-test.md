# Shelfsense eval report (test split)

live run, 2026-11-03 10:10 UTC. Enrichment model `qwen2.5:7b-instruct` (enrich/2), query model `qwen2.5:3b-instruct` (query/1), taxonomy 2021-09-21.

Written by `evals/run.py`; the numbers are in `evals/results/test.json`.

## Gates

| Metric | Value | Gate | |
|---|---:|---|---|
| enrichment.leaf_accuracy | 0.8583 | >= 0.8 | pass |
| enrichment.hierarchical_f1 | 0.9109 | >= 0.9 | pass |
| enrichment.candidate_recall | 0.9333 | >= 0.97 | **miss** |
| enrichment.attribute_macro_f1 | 0.8947 | >= 0.85 | pass |
| enrichment.ungrounded_rate | 0.0406 | <= 0.05 | pass |
| enrichment.schema_validity | 1 | >= 0.98 | pass |
| enrichment.products_per_hour | 743 | >= 400 | pass |
| parse.exact_match | 0.65 | >= 0.75 | **miss** |
| parse.slot_f1 | 0.6275 | >= 0.9 | **miss** |
| search.ndcg10 | 0.7609 | >= 0.72 | pass |
| search.ndcg10_over_bm25 | 0.1446 | >= 0.08 | pass |
| search.zero_result_rate | 0.025 | <= 0.02 | **miss** |

## Enrichment (120 products)

| | |
|---|---:|
| candidate recall | 0.9333 |
| leaf accuracy | 0.8583 |
| hierarchical f1 | 0.9109 |
| attribute macro f1 | 0.8947 |
| ungrounded rate | 0.0406 |
| unnormalized rate | 0.0355 |
| none rate | 0.0083 |
| error rate | 0 |
| schema validity | 1 |
| seconds per product | 4.84 |
| products per hour | 743 |
| tokens per second | 24.7 |

Seconds per product is model time (the recorded wall time of its model calls).

| Attribute | Precision | Recall | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| color | 1.000 | 0.940 | 0.969 | 78 | 0 | 5 |
| material | 1.000 | 0.875 | 0.933 | 70 | 0 | 10 |
| gender | 0.800 | 0.571 | 0.667 | 4 | 1 | 3 |
| size | 1.000 | 0.923 | 0.960 | 12 | 0 | 1 |
| length | 1.000 | 0.895 | 0.944 | 17 | 0 | 2 |

| Products | Leaf accuracy |
|---|---:|
| absent | 0.833 |
| accessory | 0.667 |
| bundle | 0.400 |
| conflict | 1.000 |
| multi_use | 0.667 |
| non_english | 0.500 |
| rendered | 0.909 |

Depth-2 confusion (gold → predicted, off-diagonal):

| Gold | Predicted | n |
|---|---|---:|
| Arts & Entertainment > Hobbies & Creative Arts | Hardware > Building Consumables | 1 |
| Electronics > Communications | Apparel & Accessories > Handbags, Wallets & Cases | 1 |
| Electronics > Electronics Accessories | Electronics > Communications | 1 |
| Hardware > Tools | Hardware > Tool Accessories | 1 |
| Home & Garden > Kitchen & Dining | Sporting Goods > Outdoor Recreation | 1 |
| Media > Books | Arts & Entertainment > Party & Celebration | 1 |
| Media > Books | NONE | 1 |
| Software > Computer Software | Office Supplies > General Office Supplies | 1 |
| Software > Video Game Software | Electronics > Video Game Consoles | 1 |

Top confused leaf pairs:

| Gold | Predicted | n |
|---|---|---:|
| Apparel & Accessories > Clothing > Outerwear > Coats & Jackets | Apparel & Accessories > Clothing > Outerwear > Rain Suits | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Ink Pads | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Tools > Color Mixing Tools > Palettes | 1 |
| Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials > Craft Paint, Ink & Glaze > Art & Craft Paint | Hardware > Building Consumables > Painting Consumables > Paint | 1 |
| Electronics > Communications > Telephony > Mobile Phone Accessories > Mobile Phone Cases | Apparel & Accessories > Handbags, Wallets & Cases > Wallets & Money Clips | 1 |
| Electronics > Electronics Accessories > Power > Power Adapters & Chargers | Electronics > Communications > Telephony > Mobile Phone Accessories > Mobile Phone Stands | 1 |
| Hardware > Tools > Drills > Handheld Power Drills | Hardware > Tool Accessories > Power Tool Batteries | 1 |
| Hardware > Tools > Screwdrivers | Hardware > Tools > Tool Sets > Hand Tool Sets | 1 |
| Health & Beauty > Personal Care > Hair Care > Shampoo & Conditioner > Shampoo | Health & Beauty > Personal Care > Hair Care > Shampoo & Conditioner > Shampoo & Conditioner Sets | 1 |
| Home & Garden > Decor > Throw Pillows | Home & Garden > Decor > Artificial Flora | 1 |
| Home & Garden > Household Appliance Accessories > Vacuum Accessories | Home & Garden > Household Appliance Accessories > Air Purifier Accessories > Air Purifier Filters | 1 |
| Home & Garden > Kitchen & Dining > Cookware & Bakeware > Cookware > Skillets & Frying Pans | Home & Garden > Kitchen & Dining > Cookware & Bakeware > Cookware > Cookware Sets | 1 |
| Home & Garden > Kitchen & Dining > Food & Beverage Carriers > Water Bottles | Sporting Goods > Outdoor Recreation > Hydration System Accessories | 1 |
| Media > Books > Print Books | Arts & Entertainment > Party & Celebration > Gift Giving > Greeting & Note Cards | 1 |
| Media > Books > Print Books | NONE | 1 |

## Query parsing (40 queries)

Exact match (all filters right) 0.650, slot F1 0.627, keyword F1 0.905. Fast path 35.0%, degraded 0.0% ({'llm': 26, 'rules': 14}). Model time p50 1214 ms, p95 1322 ms; on the model path p50 1230 ms, p95 1391 ms.

| Slot | F1 | TP | FP | FN |
|---|---:|---:|---:|---:|
| colors | 0.909 | 5 | 1 | 0 |
| exclude_colors | 1.000 | 1 | 0 | 0 |
| materials | 0.400 | 4 | 3 | 9 |
| exclude_materials | 0.000 | 0 | 2 | 3 |
| price_min | 1.000 | 1 | 0 | 0 |
| price_max | 1.000 | 2 | 0 | 0 |
| gender | 0.800 | 2 | 0 | 1 |
| size | 1.000 | 1 | 0 | 0 |

Wrong parses:

| Query | Source | Got | Wanted |
|---|---|---|---|
| bamboo toothbrush | llm | (none) | materials=bamboo |
| aluminum tripod | llm | (none) | materials=aluminum |
| nylon tent | llm | (none) | materials=nylon |
| rubber cat toy | llm | (none) | materials=rubber |
| glass baby bottle | llm | (none) | materials=glass |
| unisex crew neck tee | llm | (none) | gender=unisex |
| leather bifold wallet | llm | exclude_materials=leather | materials=leather |
| black down parka | llm | colors=black | colors=black materials=down |
| mens nylon hiking pants | llm | gender=men | materials=nylon gender=men |
| stainless steel screwdriver set | llm | (none) | materials=stainless steel |
| rain jacket without nylon | llm | materials=nylon | exclude_materials=nylon |
| toothbrush non plastic | llm | materials=plastic exclude_materials=non-plastic | exclude_materials=plastic |
| dog collar not leather | llm | materials=leather | exclude_materials=leather |
| black diamond shoes | llm | colors=black | (none) |

## Search (40 queries over 400 golden products)

nDCG@10 by tier: {'head': 0.949, 'torso': 0.7804, 'tail': 0.5714}.

| Configuration | nDCG@10 | MRR | Zero results |
|---|---:|---:|---:|
| BM25 only | 0.6163 | 0.6613 | 20.0% |
| vector only | 0.8218 | 0.8467 | 0.0% |
| hybrid, min-max (shipped) | 0.8135 | 0.8279 | 0.0% |
| hybrid + rerank, min-max (shipped) | 0.8555 | 0.8621 | 0.0% |
| hybrid, min-max, BM25 floor 0 | 0.8180 | 0.8342 | 0.0% |
| hybrid + rerank, min-max, BM25 floor 0 | 0.8555 | 0.8621 | 0.0% |
| hybrid, l2 | 0.8173 | 0.8321 | 0.0% |
| hybrid + rerank, l2 | 0.8555 | 0.8621 | 0.0% |
| hybrid, z-score | 0.8060 | 0.8321 | 0.0% |
| hybrid + rerank, z-score | 0.8555 | 0.8621 | 0.0% |
| hybrid, RRF (rank 60) | 0.8176 | 0.8342 | 0.0% |
| hybrid + rerank, RRF (rank 60) | 0.8555 | 0.8621 | 0.0% |
| hybrid + rerank + parsed filters (shipped) | 0.7609 | 0.8500 | 2.5% |

Lowest nDCG@10 (shipped configuration):

| Query | Tier | nDCG@10 |
|---|---|---:|
| leather bifold wallet | torso | 0.000 |
| black down parka | torso | 0.000 |
| toothbrush non plastic | tail | 0.047 |
| black diamond shoes | tail | 0.098 |
| rain jacket without nylon | tail | 0.121 |
| dog collar not leather | tail | 0.179 |
| binoculers | tail | 0.315 |
| wool hiking socks | torso | 0.587 |
| polyester running shorts | torso | 0.664 |
| rain jacket | head | 0.704 |
