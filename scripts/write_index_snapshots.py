"""Record each index version's template in contracts/index/<version>.json (run by `make codegen`).

A new version gets its snapshot; fields added in place to an existing version (search.NEW_FIELDS) are added to
its snapshot. A field changed or removed, or changed settings, is refused: that needs a new index version and a
reindex (docs/adr/0019). CI checks the same (apps/api/tests/test_index_versions_rules.py).
"""

import json
from pathlib import Path

from shelfsense_api.search import TEMPLATES, template_changes

OUT = Path(__file__).resolve().parents[1] / "contracts" / "index"

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    refused = []
    for version, template in TEMPLATES.items():
        path = OUT / f"{version}.json"
        if path.exists():
            changed, _ = template_changes(json.loads(path.read_text()), template)
            if changed:
                refused.append(f"{version}: {', '.join(changed)}")
                continue
        path.write_text(json.dumps(template, indent=2, sort_keys=True) + "\n")
        print(path)
    if refused:
        raise SystemExit("changed in place, which needs a new index version: " + "; ".join(refused))
