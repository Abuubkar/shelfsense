"""Load one Google Product Taxonomy release into taxonomy_nodes, with each full path embedded.

    uv run python scripts/load_taxonomy.py [data/taxonomy/2021-09-21.txt]

Defaults to the release in settings.taxonomy_version. A release that's already loaded is left as it is; releases
load beside each other, so a new one can be prepared while the old one is served.
"""

import asyncio
import sys
import time
from pathlib import Path

from shelfsense_api.db import SessionLocal
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import load_release


async def main(path: Path) -> None:
    started = time.perf_counter()
    async with SessionLocal() as session:
        version, added = await load_release(session, path)
    if added:
        print(f"taxonomy {version}: loaded {added} nodes, paths embedded, in {time.perf_counter() - started:.1f}s")
    else:
        print(f"taxonomy {version}: already loaded")


if __name__ == "__main__":
    default = Path(__file__).resolve().parents[1] / "data" / "taxonomy" / f"{settings.taxonomy_version}.txt"
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default))
