"""Grounding the attributes a model extracted: each one must quote the listing exactly, or it's dropped.

A quote is located in the field it names, giving offsets a UI can highlight. Offsets count Unicode code points
(Python string indices), not UTF-16 units or bytes: a JavaScript client converts with Array.from(text).
Values are then normalized with the same functions as supplier columns (normalize.py), preferring the quote over
the model's own value, so what's stored is what the listing says.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from shelfsense_api.normalize import (
    KNOWN_MATERIALS,
    length_mm,
    normalize_color,
    normalize_gender,
    normalize_material,
    parse_size,
)


@dataclass(frozen=True)
class GroundedAttribute:
    name: str
    value: str  # normalized
    unit: str | None
    evidence_field: str
    evidence_start: int
    evidence_end: int
    evidence_text: str  # exactly fields[evidence_field][evidence_start:evidence_end]


@dataclass
class Grounding:
    attributes: list[GroundedAttribute]
    ungrounded: list[dict[str, Any]]  # the quote isn't in the field it names
    unnormalized: list[dict[str, Any]]  # quoted, but neither quote nor value means a known value


def locate(text: str, quote: str) -> tuple[int, int] | None:
    """Where `quote` appears in `text`, exactly. Also tries the quote in NFC and NFD: a model may write "é" as
    one code point where the listing has "e" plus a combining accent, or the other way round. The offsets always
    refer to `text` as stored."""
    if not quote:
        return None
    for form in (quote, unicodedata.normalize("NFC", quote), unicodedata.normalize("NFD", quote)):
        start = text.find(form)
        if start >= 0:
            return start, start + len(form)
    return None


def stated_value(quote: str) -> str:
    """The value part of a quote copied from supplier attributes: "gender: Unisex" states "Unisex"."""
    match = re.fullmatch(r"\s*[A-Za-z_ ]{1,24}:\s*(.+?)\s*", quote)
    return match.group(1) if match else quote


def normalized_value(name: str, quote: str, value: str, unit: str | None) -> tuple[str, str | None] | None:
    """The attribute's normalized value and unit, read from the quote. The model's own value only helps where the
    quote supports it: a material named in the quote, or a size whose number is in the quote ("size: 8" with
    "US 8" when the listing elsewhere says US sizing). Anything else would be the model's word, not the
    listing's."""
    quote = stated_value(quote)
    if name == "color":
        color = normalize_color(quote)
        return (color, None) if color else None
    if name == "gender":
        gender = normalize_gender(quote)
        return (gender, None) if gender else None
    if name == "material":
        material = normalize_material(quote)
        if material in KNOWN_MATERIALS:
            return material, None
        named = value.strip().lower()
        return (normalize_material(named) or named, None) if named and named in quote.lower() else None
    if name == "size":
        size = parse_size(quote)
        if size is None:
            size = parse_size(value)
            if size is None or size[1] not in re.findall(r"\d+(?:\.\d+)?|[A-Za-z]+", quote):
                return None
        system, size_value = size
        return (size_value if system == "alpha" else f"{system} {size_value}"), None
    if name == "length":
        mm = length_mm(quote)
        return (str(mm), "mm") if mm else None
    return None


def ground(extracted: list[dict[str, Any]], fields: dict[str, str]) -> Grounding:
    """Keep the extracted attributes whose evidence is an exact substring of the field they name, with offsets
    and normalized values; at most one per attribute name (the first grounded one)."""
    result = Grounding([], [], [])
    seen: set[str] = set()
    for item in extracted:
        name, field = item.get("name", ""), item.get("evidence_field", "")
        quote = item.get("evidence_text", "")
        span = locate(fields.get(field, ""), quote)
        if span is None:
            result.ungrounded.append(item)
            continue
        normalized = normalized_value(name, quote, str(item.get("value", "")), item.get("unit"))
        if normalized is None:
            result.unnormalized.append(item)
            continue
        if name in seen:
            continue
        seen.add(name)
        start, end = span
        result.attributes.append(GroundedAttribute(name, normalized[0], normalized[1], field, start, end,
                                                   fields[field][start:end]))
    return result

