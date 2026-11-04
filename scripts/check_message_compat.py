"""Compare queue message schemas (contracts/messages/) between two checkouts, as CI does against main.

    uv run python scripts/check_message_compat.py <base dir> <head dir>

The rule (shelfsense_api.messages): adding an optional field keeps schema_version; anything an old consumer would
misread bumps it. Exit 0: compatible. Exit 1: breaking but declared (schema_version bumped, or a message removed),
which needs the breaking-change-approved label. Exit 2: an incompatible change without a schema_version bump,
which no label can approve.
"""

import json
import sys
from pathlib import Path
from typing import Any

IGNORED = {"description", "title"}  # wording, not shape


def _shape(schema: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in schema.items() if k not in IGNORED}


def compare(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """What an old consumer could misread: removed or changed fields, newly required ones, new required fields."""
    old_props, new_props = old.get("properties", {}), new.get("properties", {})
    problems = [f"field {name} removed" for name in old_props if name not in new_props]
    problems += [f"field {name} changed" for name in old_props
                 if name in new_props and name != "schema_version" and _shape(old_props[name]) != _shape(new_props[name])]
    problems += [f"field {name} now required" for name in set(new.get("required", [])) - set(old.get("required", []))]
    return problems


def version(schema: dict[str, Any]) -> int:
    return schema.get("properties", {}).get("schema_version", {}).get("default", 0)


def main(base: Path, head: Path) -> int:
    worst = 0
    for path in sorted(base.glob("*.schema.json")):
        name = path.name.removesuffix(".schema.json")
        if not (head / path.name).exists():
            print(f"BREAKING {name}: message removed")
            worst = max(worst, 1)
            continue
        old, new = json.loads(path.read_text()), json.loads((head / path.name).read_text())
        problems = compare(old, new)
        if not problems:
            continue
        if version(new) > version(old):
            print(f"BREAKING {name}: schema_version {version(old)} -> {version(new)}: {'; '.join(problems)}")
            worst = max(worst, 1)
        else:
            print(f"INCOMPATIBLE {name}: {'; '.join(problems)} without a schema_version bump")
            worst = 2
    if worst == 0:
        print("message schemas compatible")
    return worst


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
