import pytest

from shelfsense_api import cursor
from shelfsense_api.search import Filters, filter_clauses, match_set

SCOPE = {"q": "hiking boots", "filters": {"brand": ["Merrell"]}}


def test_cursor_round_trips() -> None:
    position = {"pit": "abc", "rank": 50, "after": [3.25, "01a19a3e-667f"]}
    assert cursor.decode(cursor.encode(position, SCOPE, "s3cret"), SCOPE, "s3cret") == position


def test_edited_cursor_is_rejected() -> None:
    signature = cursor.encode({"rank": 5}, SCOPE, "s3cret").split(".")[1]
    forged = cursor.encode({"rank": 500}, SCOPE, "other-secret").split(".")[0]
    with pytest.raises(cursor.InvalidCursor, match="signature"):
        cursor.decode(f"{forged}.{signature}", SCOPE, "s3cret")


def test_cursor_signed_with_another_secret_is_rejected() -> None:
    with pytest.raises(cursor.InvalidCursor, match="signature"):
        cursor.decode(cursor.encode({"rank": 5}, SCOPE, "old-secret"), SCOPE, "s3cret")


def test_cursor_from_another_query_is_rejected() -> None:
    token = cursor.encode({"rank": 5}, SCOPE, "s3cret")
    with pytest.raises(cursor.InvalidCursor, match="different query"):
        cursor.decode(token, {**SCOPE, "q": "rain jacket"}, "s3cret")


@pytest.mark.parametrize("token", ["", "no-dot", "a.b.c", "!!!.???"])
def test_malformed_cursor_is_rejected(token: str) -> None:
    with pytest.raises(cursor.InvalidCursor):
        cursor.decode(token, SCOPE, "s3cret")


def test_no_filters_means_no_clauses() -> None:
    assert filter_clauses(Filters()) == []


def test_values_within_a_facet_are_ored_and_facets_anded() -> None:
    clauses = filter_clauses(Filters(brand=("Voltix", "Northpeak", "Voltix"), category_id=(187,)))
    assert clauses == [{"terms": {"brand": ["Northpeak", "Voltix"]}}, {"terms": {"category_id": [187]}}]


@pytest.mark.parametrize(("price_min", "price_max", "expected"), [
    (2500, None, {"gte": 2500}),
    (None, 4999, {"lte": 4999}),
    (0, 4999, {"gte": 0, "lte": 4999}),  # 0 is a real lower bound, not "no filter"
])
def test_price_filter_is_one_range(price_min: int | None, price_max: int | None, expected: dict[str, int]) -> None:
    assert filter_clauses(Filters(price_min=price_min, price_max=price_max)) == [{"range": {"price_minor": expected}}]


def test_result_set_is_lexical_or_semantic_match_after_filters() -> None:
    query = match_set("boots", [0.1, 0.2], Filters(color=("black",)))["bool"]
    assert query["minimum_should_match"] == 1
    assert [next(iter(clause)) for clause in query["should"]] == ["multi_match", "knn"]
    assert query["filter"] == [{"terms": {"color": ["black"]}}]


def test_empty_query_browses_the_filtered_catalog() -> None:
    assert match_set("", None, Filters(brand=("Merrell",))) == {"bool": {"filter": [{"terms": {"brand": ["Merrell"]}}]}}


def test_tail_excludes_the_head() -> None:
    query = match_set("boots", [0.1], Filters(), exclude=["a", "b"])["bool"]
    assert query["must_not"] == [{"ids": {"values": ["a", "b"]}}]
