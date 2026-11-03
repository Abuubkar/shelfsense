"""Writes evals/golden/products.jsonl: 300 products rendered from known ground truth, 15 in each of 20 top-level
taxonomy branches (all but Mature), plus the hand-labelled hard cases in hard_cases.jsonl.

    uv run python evals/golden/build.py

Products are rendered exactly as the seed suppliers write them (scripts/seed.py: abbreviations, units, size
systems, typos), so every messy value has a correct answer. Gold attributes are what the listing states, worked
out here from the truth and the supplier's quirks, not with normalize.py, so the eval doesn't grade the code with
itself. Rerunning writes the same file.
"""

import json
import random
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

import seed  # noqa: E402
from seed import Kind  # noqa: E402

from shelfsense_api.settings import settings  # noqa: E402
from shelfsense_api.taxonomy import read_release  # noqa: E402

HERE = Path(__file__).parent
PER_BRANCH = 15
ABSENT = "ABSENT"
GENERIC = ("Classic", "Premium", "Everyday", "Pro", "Compact", "Heritage", "Deluxe", "Essential")

AP = "Apparel & Accessories"
EXTRA_KINDS = [
    Kind("Dog Bed", "Animals & Pet Supplies > Pet Supplies > Dog Supplies > Dog Beds", ("polyester", "cotton", "fleece"),
         None, False, (60, 110), (25, 120), adjectives=GENERIC),
    Kind("Cat Toy", "Animals & Pet Supplies > Pet Supplies > Cat Supplies > Cat Toys", ("plastic", "wool", "rubber"),
         None, False, None, (4, 20), adjectives=GENERIC),
    Kind("Acrylic Paint Set", "Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Materials "
         "> Craft Paint, Ink & Glaze > Art & Craft Paint", (), None, False, None, (8, 40), colors=False,
         adjectives=GENERIC),
    Kind("Knitting Needles", "Arts & Entertainment > Hobbies & Creative Arts > Arts & Crafts > Art & Crafting Tools > "
         "Needles & Hooks > Knitting Needles", ("bamboo", "aluminum", "wood"), None, False, (20, 40), (5, 30),
         adjectives=GENERIC),
    Kind("Drum Sticks", "Arts & Entertainment > Hobbies & Creative Arts > Musical Instrument & Orchestra Accessories > "
         "Percussion Accessories > Drum Sticks & Brushes", ("wood",), None, False, (38, 42), (8, 25),
         adjectives=GENERIC),
    Kind("Baby Bottle", "Baby & Toddler > Nursing & Feeding > Baby Bottles", ("plastic", "glass", "silicone"), None,
         False, None, (6, 25), adjectives=GENERIC),
    Kind("Baby Bib", "Baby & Toddler > Nursing & Feeding > Bibs", ("cotton", "silicone"), None, False, None, (5, 18),
         adjectives=GENERIC),
    Kind("Baby Stroller", "Baby & Toddler > Baby Transport > Baby Strollers", ("aluminum", "polyester"), None, False,
         None, (90, 400)),
    Kind("Safety Gloves", "Business & Industrial > Work Safety Protective Gear > Safety Gloves",
         ("nylon", "leather", "rubber"), "alpha", False, None, (6, 30), adjectives=GENERIC),
    Kind("Hard Hat", "Business & Industrial > Work Safety Protective Gear > Hardhats", ("plastic",), None, False, None,
         (15, 50), adjectives=GENERIC),
    Kind("Safety Glasses", "Business & Industrial > Work Safety Protective Gear > Protective Eyewear", ("plastic",),
         None, False, None, (5, 30), adjectives=GENERIC),
    Kind("Binoculars", "Cameras & Optics > Optics > Binoculars", ("aluminum", "plastic"), None, False, None, (40, 400)),
    Kind("Camera Tripod", "Cameras & Optics > Camera & Optic Accessories > Tripods & Monopods", ("aluminum",), None,
         False, (100, 180), (25, 200)),
    Kind("Telescope", "Cameras & Optics > Optics > Scopes > Telescopes", ("aluminum",), None, False, None, (90, 600),
         adjectives=GENERIC),
    Kind("Bluetooth Speaker", "Electronics > Audio > Audio Components > Speakers", ("plastic", "aluminum"), None, False,
         None, (25, 250)),
    Kind("Phone Case", "Electronics > Communications > Telephony > Mobile Phone Accessories > Mobile Phone Cases",
         ("silicone", "plastic", "leather", "tpu"), None, False, None, (8, 45)),
    Kind("Ground Coffee", "Food, Beverages & Tobacco > Beverages > Coffee", (), None, False, None, (8, 25),
         colors=False, adjectives=("Dark Roast", "Medium Roast", "Organic", "Single Origin", "Classic", "Premium")),
    Kind("Green Tea", "Food, Beverages & Tobacco > Beverages > Tea & Infusions", (), None, False, None, (5, 20),
         colors=False, adjectives=("Organic", "Loose Leaf", "Premium", "Classic", "Jasmine")),
    Kind("Spaghetti Pasta", "Food, Beverages & Tobacco > Food Items > Pasta & Noodles", (), None, False, None, (2, 9),
         colors=False, adjectives=("Organic", "Whole Wheat", "Classic", "Bronze Cut", "Premium")),
    Kind("Office Chair", "Furniture > Office Furniture > Office Chairs", ("mesh", "leather"), None, False, None,
         (80, 450), adjectives=GENERIC),
    Kind("Bookcase", "Furniture > Shelving > Bookcases & Standing Shelves", ("wood", "bamboo"), None, False, (80, 200),
         (60, 300), adjectives=GENERIC),
    Kind("Coffee Table", "Furniture > Tables > Accent Tables > Coffee Tables", ("wood", "glass"), None, False,
         (90, 130), (70, 400), adjectives=GENERIC),
    Kind("Cordless Drill", "Hardware > Tools > Drills > Handheld Power Drills", ("plastic",), None, False, None,
         (40, 250)),
    Kind("Screwdriver Set", "Hardware > Tools > Screwdrivers", ("stainless steel",), None, False, None, (10, 60)),
    Kind("Tape Measure", "Hardware > Tools > Measuring Tools & Sensors > Tape Measures", ("plastic", "stainless steel"),
         None, False, None, (6, 30)),
    Kind("Toothbrush", "Health & Beauty > Personal Care > Oral Care > Toothbrushes", ("bamboo", "plastic"), None,
         False, None, (3, 15), adjectives=GENERIC),
    Kind("Sunscreen", "Health & Beauty > Personal Care > Cosmetics > Skin Care > Sunscreen", (), None, False, None,
         (6, 25), colors=False, adjectives=("SPF 30", "SPF 50", "Mineral", "Sport", "Daily")),
    Kind("Hair Dryer", "Health & Beauty > Personal Care > Hair Care > Hair Styling Tools > Hair Dryers", ("plastic",),
         None, False, None, (20, 200), adjectives=GENERIC),
    Kind("Coffee Mug", "Home & Garden > Kitchen & Dining > Tableware > Drinkware > Mugs", ("glass", "stainless steel"),
         None, False, None, (8, 30)),
    Kind("Bath Towel", "Home & Garden > Linens & Bedding > Towels > Bath Towels & Washcloths", ("cotton", "bamboo"),
         None, False, (120, 150), (10, 40)),
    Kind("Suitcase", "Luggage & Bags > Suitcases", ("polyester", "aluminum", "plastic"), None, False, (55, 80),
         (60, 400)),
    Kind("Luggage Tag", "Luggage & Bags > Luggage Accessories > Luggage Tags", ("leather", "silicone", "plastic"), None,
         False, None, (5, 20), adjectives=GENERIC),
    Kind("Paperback Novel", "Media > Books > Print Books", (), None, False, None, (8, 25), colors=False,
         adjectives=("Bestselling", "Award-Winning", "Classic", "Illustrated", "Collector's")),
    Kind("Vinyl Record", "Media > Music & Sound Recordings > Records & LPs", (), None, False, None, (18, 45),
         colors=False, adjectives=("Remastered", "Limited Edition", "Classic", "Deluxe", "Live")),
    Kind("Music CD", "Media > Music & Sound Recordings > Music CDs", (), None, False, None, (8, 20), colors=False,
         adjectives=("Remastered", "Greatest Hits", "Classic", "Deluxe", "Live")),
    Kind("Spiral Notebook", "Office Supplies > General Office Supplies > Paper Products > Notebooks & Notepads", (),
         None, False, None, (3, 15), adjectives=GENERIC),
    Kind("Stapler", "Office Supplies > Office Instruments > Staplers", ("plastic", "aluminum"), None, False, None,
         (6, 30), adjectives=GENERIC),
    Kind("Gel Pens", "Office Supplies > Office Instruments > Writing & Drawing Instruments > Pens & Pencils > Pens", (),
         None, False, None, (4, 18), adjectives=GENERIC),
    Kind("Prayer Beads", "Religious & Ceremonial > Religious Items > Prayer Beads", ("wood", "glass"), None, False, None,
         (8, 40), adjectives=GENERIC),
    Kind("Home Altar", "Religious & Ceremonial > Religious Items > Religious Altars", ("wood",), None, False, (60, 120),
         (60, 300), adjectives=GENERIC),
    Kind("Memorial Urn", "Religious & Ceremonial > Memorial Ceremony Supplies > Memorial Urns", ("wood", "aluminum"),
         None, False, None, (40, 250), adjectives=GENERIC),
    Kind("Antivirus Software", "Software > Computer Software > Antivirus & Security Software", (), None, False, None,
         (20, 90), colors=False, adjectives=("1-Year", "3-Device", "Premium", "Total", "Essential")),
    Kind("Video Game", "Software > Video Game Software", (), None, False, None, (20, 70), colors=False,
         adjectives=("Deluxe Edition", "Standard Edition", "Collector's Edition", "Classic")),
    Kind("Office Suite", "Software > Computer Software > Business & Productivity Software", (), None, False, None,
         (40, 150), colors=False, adjectives=("Home & Student", "Professional", "Business", "Essential")),
    Kind("Camping Tent", "Sporting Goods > Outdoor Recreation > Camping & Hiking > Tents", ("nylon", "polyester",
         "canvas"), None, False, None, (60, 500)),
    Kind("Sleeping Bag", "Sporting Goods > Outdoor Recreation > Camping & Hiking > Sleeping Bags", ("down", "polyester"),
         None, False, None, (40, 300)),
    Kind("Bike Helmet", "Sporting Goods > Outdoor Recreation > Cycling > Cycling Apparel & Accessories > Bicycle Helmets",
         ("foam", "plastic"), "alpha", False, None, (30, 150)),
    Kind("Fishing Reel", "Sporting Goods > Outdoor Recreation > Fishing > Fishing Reels", ("aluminum", "plastic"), None,
         False, None, (20, 200)),
    Kind("Jigsaw Puzzle", "Toys & Games > Puzzles > Jigsaw Puzzles", (), None, False, None, (10, 35), colors=False,
         adjectives=("1000-Piece", "500-Piece", "Classic", "Scenic", "Family")),
    Kind("Board Game", "Toys & Games > Games > Board Games", (), None, False, None, (15, 60), colors=False,
         adjectives=("Family", "Strategy", "Classic", "Party", "Deluxe")),
    Kind("Stuffed Animal", "Toys & Games > Toys > Dolls, Playsets & Toy Figures > Stuffed Animals",
         ("polyester", "cotton", "fleece"), None, False, None, (8, 40), adjectives=GENERIC),
    Kind("Toy Car", "Toys & Games > Toys > Play Vehicles > Toy Cars", ("plastic", "aluminum"), None, False, None,
         (5, 30), adjectives=GENERIC),
    Kind("Car Wash Soap", "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Maintenance, Care & Decor > "
         "Vehicle Cleaning > Car Wash Solutions", (), None, False, None, (6, 25), colors=False,
         adjectives=("Concentrated", "pH-Balanced", "Premium", "Foaming", "Classic")),
    Kind("Jump Starter", "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Maintenance, Care & Decor > "
         "Vehicle Repair & Specialty Tools > Vehicle Jump Starters", ("plastic",), None, False, None, (40, 180)),
    Kind("Motorcycle Helmet", "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Safety & Security > "
         "Motorcycle Protective Gear > Motorcycle Helmets", ("plastic",), "alpha", False, None, (80, 500)),
    Kind("Car Air Freshener", "Vehicles & Parts > Vehicle Parts & Accessories > Vehicle Maintenance, Care & Decor > "
         "Vehicle Decor > Vehicle Air Fresheners", (), None, False, None, (2, 10), colors=False,
         adjectives=("Vanilla", "Pine Scent", "Ocean Breeze", "New Car", "Fresh Linen")),
]
KINDS = seed.KINDS + EXTRA_KINDS


def stated_size(truth: dict, q: seed.Quirks) -> str:
    """The size as the listing states it, normalized: a US shoe size written in EU by this supplier is "EU 41"."""
    if truth["size_system"] == "alpha":
        return truth["size_value"]
    if truth["size_system"] == "US":
        if q.size_style == "eu":
            return f"EU {seed._eu(truth['size_value'], truth['gender'])}"
        return f"US {truth['size_value']}"
    return ABSENT


def stated_length(truth: dict, q: seed.Quirks) -> str:
    """The first length the listing states, in whole millimetres (inches rounded as the supplier wrote them)."""
    if not truth["length_mm"]:
        return ABSENT
    cm = truth["length_mm"] // 10
    if q.unit_style == "cm":
        return str(cm * 10)
    inches = round(cm / 2.54)
    return str(int((Decimal(inches) * Decimal("25.4")).quantize(Decimal(1), rounding=ROUND_HALF_UP)))


def rendered(paths: dict[str, int]) -> list[dict]:
    rng = random.Random(6)
    suppliers = seed.make_suppliers(rng)
    branches: dict[str, list[Kind]] = {}
    for kind in KINDS:
        branches.setdefault(kind.path.split(" > ")[0], []).append(kind)
    products = []
    for branch in sorted(branches):
        kinds = branches[branch]
        for i in range(PER_BRANCH):
            kind, q = kinds[i % len(kinds)], rng.choice(suppliers)
            truth = seed.make_truth(rng, kind)
            n = len(products) + 1
            row = seed.render(rng, q, kind, truth, sku=f"G-{n:03d}")
            attributes = {k: v for k, v in row.items()
                          if k not in ("sku", "title", "description", "brand", "gtin", "price", "currency") and v}
            products.append({
                "id": f"g-{n:03d}", "source": "rendered", "supplier": q.code, "title": row["title"],
                "brand": row["brand"], "description": row["description"], "attributes": attributes,
                "price_minor": truth["price_minor"], "currency": "USD",
                "gold": {"node_id": paths[kind.path], "path": kind.path, "attributes": {
                    "color": truth["color_base"] or ABSENT, "material": truth["material"] or ABSENT,
                    "gender": truth["gender"] or ABSENT, "size": stated_size(truth, q),
                    "length": stated_length(truth, q)}},
            })
    return products


def hard_cases(paths: dict[str, int]) -> list[dict]:
    cases = [json.loads(line) for line in (HERE / "hard_cases.jsonl").read_text().splitlines() if line.strip()]
    for case in cases:
        case["gold"]["node_id"] = paths[case["gold"]["path"]]
        case["gold"]["attributes"] = {name: case["gold"]["attributes"].get(name, ABSENT)
                                      for name in ("color", "material", "gender", "size", "length")}
    return cases


def main() -> None:
    _, nodes = read_release(REPO / "data" / "taxonomy" / f"{settings.taxonomy_version}.txt")
    leaves = {n.full_path: n.node_id for n in nodes if n.is_leaf}
    hard = [json.loads(line)["gold"]["path"] for line in (HERE / "hard_cases.jsonl").read_text().splitlines()
            if line.strip()]
    not_leaves = sorted({k.path for k in KINDS} - leaves.keys() | set(hard) - leaves.keys())
    if not_leaves:
        raise SystemExit(f"not leaves of taxonomy {settings.taxonomy_version}: {not_leaves}")
    products = rendered(leaves) + hard_cases(leaves)
    with (HERE / "products.jsonl").open("w") as f:
        f.writelines(json.dumps(p, ensure_ascii=False) + "\n" for p in products)
    branches = {p["gold"]["path"].split(" > ")[0] for p in products}
    print(f"evals/golden/products.jsonl: {len(products)} products ({sum(p['source'] == 'hard' for p in products)} "
          f"hard cases), {len(branches)} top-level branches, {len({p['gold']['node_id'] for p in products})} leaves")


if __name__ == "__main__":
    main()
