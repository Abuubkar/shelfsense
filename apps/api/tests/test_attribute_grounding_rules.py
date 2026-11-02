import unicodedata

from shelfsense_api.attributes import ground, locate


def attr(name: str, value: str, quote: str, field: str = "title", unit: str = "none") -> dict[str, str]:
    return {"name": name, "value": value, "unit": unit, "evidence_field": field, "evidence_text": quote}


def test_offsets_count_code_points_past_emoji() -> None:
    text = "🔥🔥 HOT DEAL 🔥 Blk/Gry trail runner"
    start, end = locate(text, "Blk/Gry")  # type: ignore[misc]
    assert text[start:end] == "Blk/Gry"
    assert start == 14  # each emoji is one code point (in UTF-16 each would be two units: 17)


def test_a_quote_in_the_other_unicode_form_is_found_at_the_stored_texts_offsets() -> None:
    stored = "Café au lait mug, crème finish"  # decomposed: e + combining accent
    quote = unicodedata.normalize("NFC", "Café au lait")  # the model wrote é as one code point
    start, end = locate(stored, quote)  # type: ignore[misc]
    assert (start, end) == (0, 13)
    assert stored[start:end] == "Café au lait"


def test_a_quote_not_in_its_field_is_dropped_as_ungrounded() -> None:
    fields = {"title": "Trail Runner", "description": "Black mesh upper.", "brand": "", "raw_attributes": "(none)"}
    result = ground([attr("color", "black", "black", field="title"),  # wrong field: it's in the description
                     attr("color", "black", "Jet black")], fields)   # not in the listing at all
    assert result.attributes == [] and len(result.ungrounded) == 2


def test_the_value_comes_from_the_quote_not_from_the_model() -> None:
    fields = {"title": "Rain Shell", "description": "Packable 2.5L shell. Color: Navy", "brand": "",
              "raw_attributes": "(none)"}
    result = ground([attr("color", "blue", "Color: Navy", field="description"),
                     attr("material", "none", "2.5L shell", field="description")], fields)
    assert [(a.name, a.value) for a in result.attributes] == [("color", "navy")]  # navy, as quoted
    assert len(result.unnormalized) == 1  # "2.5L shell" names no material, and "none" isn't one


def test_lengths_become_millimetres_and_sizes_need_their_number_in_the_quote() -> None:
    fields = {"title": "Cast Iron Skillet 12 in", "description": "", "brand": "", "raw_attributes": "size: 8"}
    result = ground([attr("length", "12", "12 in", unit="in"),
                     attr("size", "US 8", "size: 8", field="raw_attributes"),
                     attr("size", "US 9", "size: 8", field="raw_attributes")], fields)
    assert [(a.name, a.value, a.unit) for a in result.attributes] == [("length", "305", "mm"), ("size", "US 8", None)]


def test_only_the_first_grounded_attribute_of_a_name_is_kept() -> None:
    fields = {"title": "Black and white sneaker", "description": "", "brand": "", "raw_attributes": "(none)"}
    result = ground([attr("color", "black", "Black"), attr("color", "white", "white")], fields)
    assert [(a.value, a.evidence_start, a.evidence_end) for a in result.attributes] == [("black", 0, 5)]
