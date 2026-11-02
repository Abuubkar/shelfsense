"""Turning supplier attribute values into comparable ones: a 16-colour base palette, millimetres, size systems,
a small gender and material vocabulary. Imports, the attributes backfill and the seeds all use these, so a value
means the same thing wherever it came from.
"""

import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

BASE_COLORS = ("black", "white", "gray", "brown", "beige", "red", "pink", "orange", "yellow", "green", "blue", "navy",
               "purple", "gold", "silver", "multicolor")

_COLOR_WORDS = {
    **{c: c for c in BASE_COLORS},
    "blk": "black", "bk": "black", "jet": "black", "onyx": "black",
    "wht": "white", "wt": "white", "ivory": "white", "cream": "white", "offwhite": "white",
    "grey": "gray", "gry": "gray", "gy": "gray", "charcoal": "gray", "slate": "gray", "graphite": "gray",
    "brn": "brown", "chocolate": "brown", "espresso": "brown", "walnut": "brown",
    "bge": "beige", "tan": "beige", "khaki": "beige", "sand": "beige", "camel": "beige",
    "rd": "red", "maroon": "red", "burgundy": "red", "crimson": "red", "wine": "red",
    "pnk": "pink", "rose": "pink", "blush": "pink", "fuchsia": "pink",
    "org": "orange", "orng": "orange", "rust": "orange", "coral": "orange",
    "ylw": "yellow", "yel": "yellow", "mustard": "yellow", "lemon": "yellow",
    "grn": "green", "olive": "green", "sage": "green", "forest": "green", "lime": "green", "mint": "green",
    "blu": "blue", "bl": "blue", "teal": "blue", "sky": "blue", "royal": "blue", "cobalt": "blue", "turquoise": "blue",
    "nvy": "navy", "nv": "navy", "midnight": "navy",
    "prpl": "purple", "purp": "purple", "violet": "purple", "lavender": "purple", "plum": "purple",
    "gld": "gold", "brass": "gold",
    "slvr": "silver", "slv": "silver", "chrome": "silver", "steel": "silver",
    "multi": "multicolor", "assorted": "multicolor", "rainbow": "multicolor", "print": "multicolor",
}

_MM_PER_UNIT = {"mm": Decimal(1), "cm": Decimal(10), "m": Decimal(1000), "in": Decimal("25.4"),
                "ft": Decimal("304.8")}
_UNIT_WORDS = {"mm": "mm", "millimeter": "mm", "millimeters": "mm", "millimetre": "mm", "millimetres": "mm",
               "cm": "cm", "centimeter": "cm", "centimeters": "cm", "centimetre": "cm", "centimetres": "cm",
               "m": "m", "meter": "m", "meters": "m", "metre": "m", "metres": "m",
               "in": "in", "inch": "in", "inches": "in", '"': "in", "”": "in", "''": "in",
               "ft": "ft", "foot": "ft", "feet": "ft", "'": "ft", "’": "ft"}
_LENGTH = re.compile(r"(\d+(?:[.,]\d+)?)\s*(millimet(?:er|re)s?|centimet(?:er|re)s?|met(?:er|re)s?|inch(?:es)?|"
                     r"feet|foot|mm|cm|in|ft|m|''|\"|”|'|’)(?![a-z])", re.IGNORECASE)

_GENDERS = {"men": "men", "mens": "men", "man": "men", "male": "men", "m": "men", "gents": "men",
            "women": "women", "womens": "women", "woman": "women", "female": "women", "w": "women", "f": "women",
            "ladies": "women", "lady": "women",
            "unisex": "unisex", "u": "unisex", "adult": "unisex", "all": "unisex",
            "kids": "kids", "kid": "kids", "children": "kids", "child": "kids", "youth": "kids", "boys": "kids",
            "girls": "kids", "toddler": "kids", "junior": "kids"}

_MATERIALS = {"poly": "polyester", "polyester": "polyester", "pes": "polyester",
              "nylon": "nylon", "polyamide": "nylon", "pa": "nylon",
              "cotton": "cotton", "cttn": "cotton", "organic cotton": "cotton",
              "wool": "wool", "merino": "wool", "merino wool": "wool",
              "leather": "leather", "lthr": "leather", "leath": "leather", "genuine leather": "leather",
              "ss": "stainless steel", "stainless": "stainless steel", "stainless steel": "stainless steel",
              "alu": "aluminum", "aluminium": "aluminum", "aluminum": "aluminum",
              "cast iron": "cast iron", "iron": "cast iron",
              "rubber": "rubber", "silicone": "silicone", "plastic": "plastic", "abs": "plastic",
              "bamboo": "bamboo", "wood": "wood", "glass": "glass", "down": "down", "fleece": "fleece",
              "canvas": "canvas", "mesh": "mesh", "foam": "foam", "pvc": "pvc", "tpu": "tpu"}

# Vocabularies other modules match against (the query fast path). The canonical material names are what a known
# material normalizes to.
KNOWN_MATERIALS = frozenset(_MATERIALS.values())
COLOR_WORDS = frozenset(_COLOR_WORDS)
GENDER_WORDS = frozenset(_GENDERS)

_ALPHA_SIZES = {"xxs": "XXS", "xs": "XS", "s": "S", "small": "S", "m": "M", "med": "M", "medium": "M", "l": "L",
                "lg": "L", "large": "L", "xl": "XL", "xxl": "XXL", "2xl": "XXL", "xxxl": "XXXL", "3xl": "XXXL",
                "os": "ONE SIZE", "one size": "ONE SIZE", "onesize": "ONE SIZE"}
ALPHA_SIZE_WORDS = frozenset(_ALPHA_SIZES)
_SHOE_SIZE = re.compile(r"^(?:(us|eu|eur|uk)\s*(?:m|w|men'?s|women'?s)?\s*(\d{1,2}(?:[.,]5)?)|"
                        r"(\d{1,2}(?:[.,]5)?)\s*(us|eu|eur|uk))$", re.IGNORECASE)

# Supplier column names for each typed attribute.
ATTRIBUTE_KEYS = {
    "color": ("color", "colour", "col", "clr", "color_name"),
    "material": ("material", "fabric", "mat", "materials"),
    "gender": ("gender", "sex", "dept", "department"),
    "size": ("size", "sz", "shoe_size", "size_label"),
}


def normalize_color(raw: str | None) -> str | None:
    """The base palette colour of a supplier value: "blk/wht" -> black (the first colour named), "Charcoal Heather"
    -> gray. None when no word in it is a known colour."""
    if not raw:
        return None
    for word in re.split(r"[^a-z]+", raw.lower()):  # any non-letter separates: "Colour: orange." -> orange
        if word in _COLOR_WORDS:
            return _COLOR_WORDS[word]
    return None


def length_mm(raw: str | None) -> int | None:
    """The first length in a value, in whole millimetres: "12in" -> 305, "30 cm" -> 300, '12"' -> 305,
    "12in / 30cm" -> 305. Rounded half up; decimal commas are accepted."""
    if not raw:
        return None
    match = _LENGTH.search(raw)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    unit = _UNIT_WORDS[match.group(2).lower()]
    return int((amount * _MM_PER_UNIT[unit]).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def normalize_gender(raw: str | None) -> str | None:
    if not raw:
        return None
    key = re.sub(r"[^a-z ]", "", raw.lower().replace("'s", "s")).strip()
    return _GENDERS.get(key)


def normalize_material(raw: str | None) -> str | None:
    """A material from a small vocabulary ("SS" -> stainless steel, "aluminium" -> aluminum). The first known one in a
    blend ("80% cotton / 20% poly" -> cotton); otherwise the value lowercased."""
    if not raw:
        return None
    value = raw.lower().strip()
    if value in _MATERIALS:
        return _MATERIALS[value]
    for part in re.split(r"[/,;&+]+", value):
        words = re.sub(r"[\d%]+", " ", part).split()
        for n in (2, 1):  # "stainless steel" before "steel"
            for i in range(len(words) - n + 1):
                phrase = " ".join(words[i:i + n])
                if phrase in _MATERIALS:
                    return _MATERIALS[phrase]
    return value or None


def parse_size(raw: str | None) -> tuple[str, str] | None:
    """(system, value) for a size: "US 8" -> ("US", "8"), "42 EU" -> ("EU", "42"), "UK 7,5" -> ("UK", "7.5"),
    "Medium" -> ("alpha", "M"). None for anything else (a bare number is ambiguous)."""
    if not raw:
        return None
    value = raw.strip()
    alpha = _ALPHA_SIZES.get(value.lower())
    if alpha:
        return "alpha", alpha
    match = _SHOE_SIZE.match(value)
    if not match:
        return None
    system = (match.group(1) or match.group(4)).upper()
    number = (match.group(2) or match.group(3)).replace(",", ".")
    return ("EU" if system == "EUR" else system), number.removesuffix(".0")


def shoe_size_eu(system: str, value: str, gender: str | None) -> Decimal | None:
    """A shoe size in EU sizes, to compare sizes given in different systems. UK = US - 1 for men and US - 2 for
    women (and unisex/kids, as US sizes skew women's), EU = 1.27 x UK + 32, to the nearest half size. Brand
    charts differ by about half a size; this is for matching, not for fitting."""
    try:
        number = Decimal(value)
    except InvalidOperation:
        return None
    if system == "EU":
        return number
    if system == "US":
        number -= 1 if gender == "men" else 2
    elif system != "UK":
        return None
    eu = Decimal("1.27") * number + 32
    return (eu * 2).quantize(Decimal(1), rounding=ROUND_HALF_UP) / 2


def typed_attributes(attributes: dict[str, str]) -> dict[str, str | None]:
    """The typed columns for a product's raw supplier attributes, whatever the supplier called them."""
    def first(field: str) -> str | None:
        lowered = {k.lower().strip(): v for k, v in attributes.items()}
        return next((lowered[k] for k in ATTRIBUTE_KEYS[field] if lowered.get(k)), None)

    size = parse_size(first("size"))
    return {
        "color_base": normalize_color(first("color")),
        "material": normalize_material(first("material")),
        "gender": normalize_gender(first("gender")),
        "size_system": size[0] if size else None,
        "size_value": size[1] if size else None,
    }
