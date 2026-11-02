"""Write contracts/messages/*.schema.json from the message models (run by `make codegen`)."""

import json
from pathlib import Path

from shelfsense_api.messages import json_schemas

OUT = Path(__file__).resolve().parents[1] / "contracts" / "messages"

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    for name, schema in json_schemas().items():
        (OUT / name).write_text(json.dumps(schema, indent=2) + "\n")
        print(OUT / name)
