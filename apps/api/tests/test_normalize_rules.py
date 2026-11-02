from decimal import Decimal

import pytest

from shelfsense_api.normalize import (
    BASE_COLORS,
    length_mm,
    normalize_color,
    normalize_gender,
    normalize_material,
    parse_size,
    shoe_size_eu,
    typed_attributes,
)


@pytest.mark.parametrize(("raw", "base"), [
    ("blk", "black"), ("Blk/Wht", "black"), ("wht/gry", "white"), ("Charcoal Heather", "gray"), ("GREY", "gray"),
    ("nvy", "navy"), ("Olive Drab", "green"), ("teal", "blue"), ("Assorted", "multicolor"), ("tan", "beige"),
    ("burgundy", "red"), ("Heather", None), ("", None), (None, None),
])
def test_colour_abbreviations_map_to_the_base_palette(raw: str | None, base: str | None) -> None:
    assert normalize_color(raw) == base
    assert base is None or base in BASE_COLORS


def test_the_palette_has_16_colours() -> None:
    assert len(BASE_COLORS) == len(set(BASE_COLORS)) == 16


@pytest.mark.parametrize(("raw", "mm"), [
    ("12in", 305), ("30 cm", 300), ('12"', 305), ("12 inches", 305), ("1.5 m", 1500), ("300mm", 300),
    ("2 ft", 610), ("6'", 1829), ("12in / 30cm", 305), ("Length: 25,4 cm", 254), ("0.5in", 13),
    ("12", None), ("large", None), ("5 mins", None),
])
def test_lengths_convert_to_whole_millimetres(raw: str, mm: int | None) -> None:
    assert length_mm(raw) == mm


@pytest.mark.parametrize(("raw", "parsed"), [
    ("US 8", ("US", "8")), ("us8", ("US", "8")), ("42 EU", ("EU", "42")), ("EUR 42", ("EU", "42")),
    ("UK 7,5", ("UK", "7.5")), ("US W 8.5", ("US", "8.5")), ("Medium", ("alpha", "M")), ("XL", ("alpha", "XL")),
    ("2XL", ("alpha", "XXL")), ("8", None), ("size eight", None),
])
def test_sizes_parse_into_system_and_value(raw: str, parsed: tuple[str, str] | None) -> None:
    assert parse_size(raw) == parsed


@pytest.mark.parametrize(("system", "value", "gender", "eu"), [
    ("US", "8", "men", "41"), ("UK", "7", "men", "41"), ("EU", "41", "men", "41"),
    ("US", "9", "men", "42"), ("US", "8", "women", "39.5"), ("UK", "6", "women", "39.5"), ("alpha", "M", None, None),
])
def test_us_uk_and_eu_shoe_sizes_compare_in_eu(system: str, value: str, gender: str | None, eu: str | None) -> None:
    assert shoe_size_eu(system, value, gender) == (Decimal(eu) if eu else None)


@pytest.mark.parametrize(("raw", "gender"), [
    ("Mens", "men"), ("men's", "men"), ("M", "men"), ("Ladies", "women"), ("W", "women"), ("Unisex", "unisex"),
    ("Boys", "kids"), ("toddler", "kids"), ("pets", None),
])
def test_gender_values_map_to_four_groups(raw: str, gender: str | None) -> None:
    assert normalize_gender(raw) == gender


@pytest.mark.parametrize(("raw", "material"), [
    ("SS", "stainless steel"), ("Aluminium", "aluminum"), ("80% cotton / 20% poly", "cotton"),
    ("Merino", "wool"), ("Recycled Nylon Ripstop", "nylon"), ("Mystery Weave", "mystery weave"),
])
def test_materials_use_one_name_each(raw: str, material: str) -> None:
    assert normalize_material(raw) == material


def test_typed_attributes_accept_each_suppliers_column_names() -> None:
    assert typed_attributes({"Colour": "blk/wht", "Fabric": "poly", "Sex": "W", "sz": "EU 39"}) == {
        "color_base": "black", "material": "polyester", "gender": "women", "size_system": "EU", "size_value": "39"}
    assert typed_attributes({"notes": "gift"}) == {
        "color_base": None, "material": None, "gender": None, "size_system": None, "size_value": None}
