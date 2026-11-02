"""Index every product from Postgres into OpenSearch (alias `products`). Postgres is the source of truth: run this
after imports or enrichment until the indexing worker (slice 3) does it.

    uv run python scripts/sync_index.py
"""

import asyncio
import time

from shelfsense_api.db import SessionLocal
from shelfsense_api.search import ALIAS, client, ensure_index, index_products


async def main() -> None:
    os = client()
    try:
        await ensure_index(os)
        started = time.perf_counter()
        async with SessionLocal() as session:
            indexed, errors = await index_products(os, session)
        print(f"indexed {indexed} products into '{ALIAS}' in {time.perf_counter() - started:.1f}s")
        for error in errors[:10]:
            print("  error:", error)
        if errors:
            raise SystemExit(f"{len(errors)} products failed to index")
    finally:
        await os.close()


if __name__ == "__main__":
    asyncio.run(main())
