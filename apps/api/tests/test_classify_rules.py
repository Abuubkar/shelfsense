import math

import pytest

from shelfsense_api.classify import category_schema
from shelfsense_api.llm import value_probability


def test_category_enum_is_exactly_the_candidates_plus_none() -> None:
    schema = category_schema([3640, 187, 505295])
    assert schema["properties"]["category_id"]["enum"] == ["3640", "187", "505295", "NONE"]
    assert schema["required"] == ["category_id", "attributes"]


def test_category_enum_keeps_candidate_order_and_drops_duplicates() -> None:
    assert category_schema([187, 100, 187])["properties"]["category_id"]["enum"] == ["187", "100", "NONE"]


def test_no_candidates_leaves_only_none() -> None:
    assert category_schema([])["properties"]["category_id"]["enum"] == ["NONE"]


def test_value_probability_multiplies_the_value_tokens_and_its_closing_quote() -> None:
    tokens = [('{"', 0.0), ("category", 0.0), ("_id", 0.0), ('":', 0.0), (' "', -5.0),
              ("1", -0.1), ("8", -0.2), ("7", -0.3), ('"}', -0.4)]
    # The opening quote token is outside the value and doesn't count.
    assert value_probability(tokens, "187") == pytest.approx(math.exp(-1.0))


def test_value_probability_is_zero_when_the_value_is_absent() -> None:
    assert value_probability([('{"category_id": "NONE"}', 0.0)], "187") == 0.0
