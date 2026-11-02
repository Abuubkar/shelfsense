import pytest

from shelfsense_api import search
from shelfsense_api.query import ParsedFilters, QueryParse, Size, _from_reply, needs_model, normalize_query
from shelfsense_api.service import _parsed_price_applied, apply_parse


@pytest.mark.parametrize("q", ["hiking boots", "charger for laptop", "yoga mat", "all weather jacket",
                               "headphones", "camp stove"])
def test_plain_product_words_take_the_fast_path(q: str) -> None:
    assert not needs_model(q)


@pytest.mark.parametrize("q", ["boots under $120", "boots under 120", "size 8 boots", "EU 42 shoes", "navy socks",
                               "women's jacket", "mens tee", "wool socks", "not leather", "non-leather wallet",
                               "jacket without hood", "medium tee", "40 dollars headphones"])
def test_filter_words_need_the_model(q: str) -> None:
    assert needs_model(q)


def test_query_keys_ignore_case_spacing_curly_quotes_and_trailing_punctuation() -> None:
    assert normalize_query("  WATERPROOF  Women’s boots!") == normalize_query("waterproof women's boots")
    assert normalize_query("boots under $120") != normalize_query("boots under $12")


def test_model_dollars_become_cents_and_a_bare_size_number_is_us() -> None:
    parse = _from_reply({"keywords": "boots", "category_hint": None, "filters": {
        "price_min": 0, "price_max": 119.99, "colors": ["Navy", "blk"], "exclude_colors": [], "materials": ["Wool"],
        "exclude_materials": [], "gender": "women", "size": {"system": "alpha", "value": "8"}}}, "boots")
    f = parse.filters
    assert (f.price_min, f.price_max) == (None, 11999)
    assert f.colors == ["navy", "black"] and f.materials == ["wool"]
    assert f.size == Size(system="US", value="8")


def parsed(**filters: object) -> QueryParse:
    return QueryParse(source="llm", keywords="boots", filters=ParsedFilters(**filters))  # type: ignore[arg-type]


def test_explicit_filters_win_and_gendered_parses_include_unisex() -> None:
    _, f = apply_parse(parsed(colors=["red"], gender="women", size=Size(system="US", value="8")), "q",
                       search.Filters(color=("blue",)))
    assert f.color == ("blue",)
    assert f.gender == ("women", "unisex")
    assert f.size_eu == 39.5  # US women's 8, compared in EU numbers


def test_a_parsed_price_is_relaxable_only_when_it_was_applied() -> None:
    priced = parsed(price_max=12000)
    assert _parsed_price_applied(priced, search.Filters())
    assert not _parsed_price_applied(priced, search.Filters(price_max=5000))  # an explicit price overrides it
    assert not _parsed_price_applied(parsed(colors=["red"]), search.Filters())
    _, relaxed = apply_parse(priced.model_copy(update={"price_relaxed": True}), "q", search.Filters())
    assert (relaxed.price_min, relaxed.price_max) == (None, None)


def test_a_one_sided_price_written_as_a_range_keeps_only_the_bound_the_query_asked_for() -> None:
    reply = {"keywords": "boots", "category_hint": None, "filters": {
        "price_min": 100, "price_max": 100, "colors": [], "exclude_colors": [], "materials": [],
        "exclude_materials": [], "gender": None, "size": None}}
    under = _from_reply(reply, "boots under $100").filters
    over = _from_reply(reply, "boots over $100").filters
    assert (under.price_min, under.price_max) == (None, 10000)
    assert (over.price_min, over.price_max) == (10000, None)
