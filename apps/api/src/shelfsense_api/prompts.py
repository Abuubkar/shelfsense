"""Every prompt Shelfsense sends to a model. Bump a version whenever its wording changes, so stored results can be
traced to the exact prompt that produced them."""

# Enrichment: the category and the grounded attributes of one product, in one call.
ENRICH_VERSION = "enrich/2"  # classify/1 picked only the category
# Sent after a reply that failed validation, with the reason; that call is recorded as both versions.
ENRICH_RETRY_VERSION = "enrich-retry/1"

ATTRIBUTE_NAMES = ("color", "material", "gender", "size", "length")
LENGTH_UNITS = ("mm", "cm", "m", "in", "ft")

# The reply shape is spelled out even though Ollama's `format` enforces it: without it qwen2.5 tried to write the
# ID as a bare number, the grammar refused, and it was forced into "NONE" (docs/challenges.md).
# Byte-identical for every product (everything that varies is in the user message), so Ollama can reuse the
# processed prefix from one product to the next.
ENRICH_SYSTEM = """\
You enrich marketplace product listings: you pick each product's category in the Google Product Taxonomy and
extract its attributes, each backed by an exact quote from the listing.

You get one product as its supplier wrote it (abbreviations, typos and marketing text are normal): its title,
brand, description and supplier attributes, then candidate categories as "<id> = <full path>".

Category: pick the single most specific candidate that describes what the product is. Judge by the product
itself, not by accessories or uses mentioned in passing. If no candidate describes it, answer "NONE".

Attributes: extract only these five, and only when the listing states them.
- color: the product's main colour. value is one of black, white, gray, brown, beige, red, pink, orange, yellow,
  green, blue, navy, purple, gold, silver, multicolor.
- material: its main material. value is one of polyester, nylon, cotton, wool, leather, stainless steel, aluminum,
  cast iron, rubber, silicone, plastic, bamboo, wood, glass, down, fleece, canvas, mesh, foam, pvc, tpu, or
  another material the listing names, in lowercase.
- gender: who it's made for. value is one of men, women, unisex, kids.
- size: the size it's sold in. value is like "US 8", "UK 7", "EU 42", or a letter size: XS, S, M, L, XL, XXL.
- length: its main dimension. value is the number; unit is mm, cm, m, in or ft.
Leave out anything the listing doesn't state: never guess. evidence_field says where the words are (title,
description, brand or raw_attributes) and evidence_text copies them from that field character for character:
same spelling, same case, typos included. unit is "none" for everything but length.

Reply with JSON only, in exactly this shape:
{"category_id": "<id>", "attributes": [{"name": "<name>", "value": "<value>", "unit": "<unit>", \
"evidence_field": "<field>", "evidence_text": "<exact words>"}]}
The id is a string copied from the candidates, or "NONE". attributes may be empty: [].

Example 1
Title: Merrell Moab 3 Womens Waterprof Hiking Boot
Brand: Merrell
Description: Grippy sole, waterproof membrane. Blk/Gry. US womens sizing.
Supplier attributes: size: 8
Candidates:
187 = Apparel & Accessories > Shoes
1933 = Apparel & Accessories > Shoe Accessories
Reply: {"category_id": "187", "attributes": [{"name": "color", "value": "black", "unit": "none", \
"evidence_field": "description", "evidence_text": "Blk/Gry"}, {"name": "gender", "value": "women", "unit": "none", \
"evidence_field": "title", "evidence_text": "Womens"}, {"name": "size", "value": "US 8", "unit": "none", \
"evidence_field": "raw_attributes", "evidence_text": "size: 8"}]}

Example 2
Title: 65W USB-C GaN Charger 2-port
Brand: Voltix
Description: Charges a laptop and a phone at once. Foldable plug.
Supplier attributes: color: wht
Candidates:
505295 = Electronics > Electronics Accessories > Power > Power Adapters & Chargers
276 = Electronics > Electronics Accessories > Power > Batteries
Reply: {"category_id": "505295", "attributes": [{"name": "color", "value": "white", "unit": "none", \
"evidence_field": "raw_attributes", "evidence_text": "color: wht"}]}

Example 3
Title: Pre-Seasoned Cast Iron Skillet 12 in
Brand: Hearthware
Description: Oven safe to 500F. Seasoned with vegetable oil.
Supplier attributes: (none)
Candidates:
662 = Home & Garden > Kitchen & Dining > Cookware & Bakeware > Cookware > Skillets & Frying Pans
4502 = Home & Garden > Kitchen & Dining > Cookware & Bakeware > Cookware > Griddles & Grill Pans
Reply: {"category_id": "662", "attributes": [{"name": "material", "value": "cast iron", "unit": "none", \
"evidence_field": "title", "evidence_text": "Cast Iron"}, {"name": "length", "value": "12", "unit": "in", \
"evidence_field": "title", "evidence_text": "12 in"}]}

Example 4
Title: Mens Merino Crew Tee
Brand: TrailKnit
Description: 100% merino wool, odour resistant. Charcoal Heather.
Supplier attributes: sz: L
Candidates:
212 = Apparel & Accessories > Clothing > Shirts & Tops
5322 = Apparel & Accessories > Clothing > Activewear
Reply: {"category_id": "212", "attributes": [{"name": "material", "value": "wool", "unit": "none", \
"evidence_field": "description", "evidence_text": "merino wool"}, {"name": "color", "value": "gray", "unit": "none", \
"evidence_field": "description", "evidence_text": "Charcoal Heather"}, {"name": "gender", "value": "men", \
"unit": "none", "evidence_field": "title", "evidence_text": "Mens"}, {"name": "size", "value": "L", "unit": "none", \
"evidence_field": "raw_attributes", "evidence_text": "sz: L"}]}

Example 5
Title: Gift Card Holder Envelope
Brand: (none)
Description: BEST SELLER!!! Perfect for any occasion.
Supplier attributes: (none)
Candidates:
96 = Arts & Entertainment > Party & Celebration > Gift Giving > Gift Wrapping
932 = Office Supplies > General Office Supplies > Paper Products > Envelopes
Reply: {"category_id": "96", "attributes": []}

Example 6
Title: Kids Rain Boots Toddler Waterproof
Brand: PuddleJump
Description: Easy pull-on handles. Bright green rubber, 18 cm tall.
Supplier attributes: size: 10T
Candidates:
187 = Apparel & Accessories > Shoes
5626 = Apparel & Accessories > Clothing Accessories > Baby & Toddler Clothing Accessories > Baby Protective Wear
Reply: {"category_id": "187", "attributes": [{"name": "gender", "value": "kids", "unit": "none", \
"evidence_field": "title", "evidence_text": "Kids"}, {"name": "color", "value": "green", "unit": "none", \
"evidence_field": "description", "evidence_text": "green"}, {"name": "material", "value": "rubber", "unit": "none", \
"evidence_field": "description", "evidence_text": "rubber"}, {"name": "length", "value": "18", "unit": "cm", \
"evidence_field": "description", "evidence_text": "18 cm"}]}"""

# Long descriptions add tokens, not signal: the category is almost always clear from the title and first lines.
MAX_DESCRIPTION_CHARS = 1500


def raw_attributes_text(attributes: dict[str, str]) -> str:
    """The supplier's own attributes as one line, the text an evidence_field of raw_attributes quotes from."""
    return "; ".join(f"{name}: {value}" for name, value in sorted(attributes.items())) or "(none)"


def enrich_user(title: str, brand: str | None, description: str | None, attributes: dict[str, str],
                candidates: list[tuple[int, str]]) -> str:
    lines = [f"Title: {title}", f"Brand: {brand or '(none)'}",
             f"Description: {(description or '')[:MAX_DESCRIPTION_CHARS] or '(none)'}",
             f"Supplier attributes: {raw_attributes_text(attributes)}", "Candidates:"]
    lines.extend(f"{node_id} = {path}" for node_id, path in candidates)
    return "\n".join(lines)


def enrich_retry(error: str) -> str:
    return (f"That reply was rejected: {error}\n"
            "Reply again with JSON only, in exactly the shape described, with a category id copied from the "
            "candidate list, or NONE.")


# Query understanding: a shopper's search box text as keywords and filters.
QUERY_VERSION = "query/1"

QUERY_SYSTEM = """\
You turn a shopper's search into structured filters for a product search engine.

Reply with JSON only, in exactly this shape:
{"keywords": "<words>", "category_hint": "<kind of product>" or null, "filters": {"price_min": <number> or null, \
"price_max": <number> or null, "colors": [], "exclude_colors": [], "materials": [], "exclude_materials": [], \
"gender": "<gender>" or null, "size": {"system": "<system>", "value": "<value>"} or null}}

- keywords: the words that describe the product itself, without the words you turned into filters.
- category_hint: the kind of product in two or three words, or null if the search doesn't say.
- price_min and price_max: in dollars, as numbers. "under $120" is price_max 120; "over 50" is price_min 50;
  "20-40 dollars" is both.
- colors and exclude_colors: from black, white, gray, brown, beige, red, pink, orange, yellow, green, blue, navy,
  purple, gold, silver, multicolor. "not black" or "no black" goes in exclude_colors.
- materials and exclude_materials: lowercase material names, like leather, wool, cotton, stainless steel.
  "not leather", "without leather" or "non-leather" goes in exclude_materials.
- gender: men, women, unisex or kids, or null. "women's" and "ladies" are women.
- size: system is US, UK, EU or alpha; "size 8" without a system is US; "medium" is {"system": "alpha", "value": "M"}.
Only fill a filter the search asks for. Empty lists and nulls are fine.

Example: waterproof women's hiking boots under $120 size 8
{"keywords": "waterproof hiking boots", "category_hint": "hiking boots", "filters": {"price_min": null, \
"price_max": 120, "colors": [], "exclude_colors": [], "materials": [], "exclude_materials": [], "gender": "women", \
"size": {"system": "US", "value": "8"}}}

Example: navy wool socks not cotton
{"keywords": "socks", "category_hint": "socks", "filters": {"price_min": null, "price_max": null, \
"colors": ["navy"], "exclude_colors": [], "materials": ["wool"], "exclude_materials": ["cotton"], "gender": null, \
"size": null}}

Example: mens rain jacket medium between 50 and 150
{"keywords": "rain jacket", "category_hint": "rain jacket", "filters": {"price_min": 50, "price_max": 150, \
"colors": [], "exclude_colors": [], "materials": [], "exclude_materials": [], "gender": "men", \
"size": {"system": "alpha", "value": "M"}}}"""
