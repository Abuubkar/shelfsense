"""An index version's mapping never changes in place: a changed or removed field needs a new version and a reindex
(docs/adr/0019). The recorded snapshots in contracts/index/ are what deployed indexes were created from."""

import json
from pathlib import Path

import pytest

from shelfsense_api.search import TEMPLATES, template_changes

SNAPSHOTS = Path(__file__).resolve().parents[3] / "contracts" / "index"


@pytest.mark.parametrize("version", sorted(TEMPLATES))
def test_each_index_version_matches_its_recorded_mapping(version: str) -> None:
    path = SNAPSHOTS / f"{version}.json"
    assert path.exists(), f"{version} has no snapshot: run make codegen and commit contracts/index/{version}.json"
    changed, added = template_changes(json.loads(path.read_text()), TEMPLATES[version])
    assert not changed, f"{version} changed in place ({', '.join(changed)}): add a new index version instead"
    assert not added, f"fields added to {version} ({', '.join(added)}): run make codegen to record them"


def test_template_changes_tells_an_allowed_addition_from_a_redefinition() -> None:
    base = {"template": {"settings": {"index": {}}, "mappings": {"dynamic": "strict", "properties": {
        "title": {"type": "text"}}}}}
    added = {"template": {"settings": {"index": {}}, "mappings": {"dynamic": "strict", "properties": {
        "title": {"type": "text"}, "gtin": {"type": "keyword"}}}}}
    redefined = {"template": {"settings": {"index": {}}, "mappings": {"dynamic": "strict", "properties": {
        "title": {"type": "keyword"}}}}}
    assert template_changes(base, added) == ([], ["gtin"])
    assert template_changes(base, redefined) == (["field title"], [])
    assert template_changes(added, base) == (["field gtin"], [])  # a removed field
