"""Graded relevance (0-3) of a golden product to a golden query, from ground truth.

A query names a category and constraints: its gold parse's filters, plus a brand or a length range where the words
ask for one. A product is
- 3: in the category (or under it) and meets every constraint,
- 2: in the category and meets at least half of them,
- 1: in the category but meets fewer, or in a related category (a sibling under the same parent, when that parent
  is below the top level: rain jackets and parkas, not jackets and socks),
- 0: otherwise.
A constraint on something the listing doesn't state (gold ABSENT) is not met, except an exclusion: a product with
no stated colour isn't the excluded colour.
"""

from decimal import ROUND_HALF_UP, Decimal
from typing import Any

ABSENT = "ABSENT"


def shoe_size_eu(size: str, gender: str | None) -> Decimal | None:
    """A shoe size ("US 9", "EU 42", "UK 8") in EU numbers: UK = US - 1 for men, US - 2 otherwise; EU = 1.27 x UK +
    32 to the nearest half. Written out here, not imported, so grading doesn't depend on the code it grades."""
    system, _, number = size.partition(" ")
    try:
        value = Decimal(number)
    except ArithmeticError:
        return None
    if system == "EU":
        return value
    if system == "US":
        value -= 1 if gender == "men" else 2
    elif system != "UK":
        return None
    return ((Decimal("1.27") * value + 32) * 2).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 2


def related(category: str, path: str) -> bool:
    query, product = category.split(" > "), path.split(" > ")
    parent = query[:-1]
    return len(parent) >= 2 and product[:len(parent)] == parent


def constraints(query: dict[str, Any], product: dict[str, Any]) -> list[bool]:
    """Whether the product meets each of the query's constraints, in a fixed order."""
    f = query["parse"]["filters"]
    attrs = product["gold"]["attributes"]
    color, material, gender, size = attrs["color"], attrs["material"], attrs["gender"], attrs["size"]
    met = []
    if f["colors"]:
        met.append(color in f["colors"])
    if f["exclude_colors"]:
        met.append(color not in f["exclude_colors"])
    if f["materials"]:
        met.append(material in f["materials"])
    if f["exclude_materials"]:
        met.append(material not in f["exclude_materials"])
    if f["gender"]:
        # A gendered search also wants unisex products (as search filters it).
        wanted = {f["gender"], "unisex"} if f["gender"] in ("men", "women") else {f["gender"]}
        met.append(gender in wanted)
    if f["size"]:
        wanted = f"{f['size']['system']} {f['size']['value']}"
        if f["size"]["system"] == "alpha":
            met.append(size == f["size"]["value"])
        else:
            product_eu = shoe_size_eu(size, gender) if size != ABSENT else None
            met.append(product_eu is not None and product_eu == shoe_size_eu(wanted, f["gender"]))
    if f["price_min"] is not None:
        met.append(product["price_minor"] >= f["price_min"])
    if f["price_max"] is not None:
        met.append(product["price_minor"] <= f["price_max"])
    if query.get("brand"):
        met.append((product.get("brand") or "").lower() == query["brand"].lower())
    if query.get("length_mm"):
        lo, hi = query["length_mm"]
        length = attrs["length"]
        met.append(length != ABSENT and lo <= int(length) <= hi)
    return met


def grade(query: dict[str, Any], product: dict[str, Any]) -> int:
    category, path = query["category"], product["gold"]["path"]
    met = constraints(query, product)
    all_met, most_met = all(met), 2 * sum(met) >= len(met)
    if category is None:
        return 3 if met and all_met else 2 if met and most_met else 0
    if path == category or path.startswith(category + " > "):
        return 3 if all_met else 2 if most_met else 1
    return 1 if related(category, path) else 0
