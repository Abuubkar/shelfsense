import pytest

from shelfsense_api.feeds import FeedRow, Rejection, gtin_is_valid, validate_row

HEADER = ["sku", "title", "description", "brand", "gtin", "price", "currency", "color"]


def row(**overrides: str) -> list[str]:
    values = {"sku": "TRL-1", "title": "Hiking Boot", "description": "", "brand": "Merrell",
              "gtin": "4006381333931", "price": "119.95", "currency": "USD", "color": "blk/gry"}
    return list((values | overrides).values())


@pytest.mark.parametrize("gtin", ["96385074", "036000291452", "4006381333931", "10012345678902"])
def test_valid_gtins_of_every_length_pass(gtin: str) -> None:
    assert gtin_is_valid(gtin)


@pytest.mark.parametrize("gtin", [
    "96385075",  # GTIN-8, wrong check digit
    "036000291453",  # GTIN-12
    "4006381333932",  # GTIN-13
    "10012345678903",  # GTIN-14
    "4006381333",  # 10 digits is no GTIN length
    "4.00638E+12",  # a spreadsheet's scientific notation
])
def test_bad_gtins_fail(gtin: str) -> None:
    assert not gtin_is_valid(gtin)


def test_valid_row_is_normalized() -> None:
    result = validate_row(2, HEADER, row(gtin="4006 381-333931", price="$1,099.00", title="  Hiking   Boot "))
    assert isinstance(result, FeedRow)
    assert (result.gtin, result.price_minor, result.title) == ("4006381333931", 109900, "Hiking Boot")
    assert result.attributes == {"color": "blk/gry"}
    assert result.description is None


@pytest.mark.parametrize(("overrides", "reason"), [
    ({"sku": " "}, "missing_sku"),
    ({"title": ""}, "missing_title"),
    ({"gtin": "4006381333932"}, "invalid_gtin"),
    ({"price": "-9.99"}, "negative_price"),
    ({"price": "call us"}, "invalid_price"),
    ({"price": "9.999"}, "invalid_price"),
    ({"currency": "US$"}, "invalid_currency"),
    ({"description": "cr\udce8me"}, "invalid_encoding"),  # a Latin-1 byte decoded with surrogateescape
])
def test_invalid_rows_are_rejected_with_their_reason(overrides: dict[str, str], reason: str) -> None:
    result = validate_row(7, HEADER, row(**overrides))
    assert isinstance(result, Rejection)
    assert (result.row_number, result.reason_code) == (7, reason)


def test_row_with_missing_fields_is_rejected() -> None:
    result = validate_row(3, HEADER, row()[:5])
    assert isinstance(result, Rejection) and result.reason_code == "wrong_column_count"


def test_undecodable_bytes_show_as_replacement_character_in_excerpt() -> None:
    result = validate_row(3, HEADER, row(description="cr\udce8me"))
    assert isinstance(result, Rejection) and "cr�me" in result.excerpt


def test_blank_currency_defaults_to_usd() -> None:
    result = validate_row(2, HEADER, row(currency=""))
    assert isinstance(result, FeedRow) and result.currency == "USD"
