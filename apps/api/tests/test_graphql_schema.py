from pathlib import Path

from shelfsense_api.graphql import schema

REPO = Path(__file__).resolve().parents[3]


def test_graphql_schema_file_matches_code() -> None:
    """contracts/schema.graphql is what the UI's types are generated from; `make codegen` refreshes it."""
    assert (REPO / "contracts" / "schema.graphql").read_text().strip() == schema.as_str().strip()
