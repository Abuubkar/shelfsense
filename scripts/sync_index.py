"""Rebuild the search index from Postgres: every product, through the same adaptive bulk path as the index worker.
Postgres is the source of truth; the index worker keeps it current after imports, so run this after a fresh
setup or to repair the index.

    uv run python scripts/sync_index.py
"""

import asyncio
import time
from collections import Counter

from sqlalchemy import select

from shelfsense_api.db import Product, SessionLocal
from shelfsense_api.indexing import BatchSizer, bulk_index, product_docs
from shelfsense_api.search import ALIAS, client, ensure_index

CHUNK = 2000  # products embedded and held in memory at once


async def main() -> None:
    os = client()
    try:
        await ensure_index(os)
        started = time.perf_counter()
        sizer, outcomes = BatchSizer(), []
        async with SessionLocal() as session:
            ids = list(await session.scalars(select(Product.id).order_by(Product.id)))
            for start in range(0, len(ids), CHUNK):
                outcomes += await bulk_index(os, await product_docs(session, ids[start:start + CHUNK]), sizer)
        await os.indices.refresh(index=ALIAS)
        counts = Counter(o.status for o in outcomes)
        print(f"indexed {counts['done']} of {len(ids)} products into '{ALIAS}' in {time.perf_counter() - started:.1f}s"
              f" (final batch size {sizer.size})")
        failed = [o for o in outcomes if o.status != "done"]
        for o in failed[:10]:
            print(f"  {o.status} {o.product_id}: {o.error_code} {o.detail[:120]}")
        if failed:
            raise SystemExit(f"{len(failed)} products failed to index")
    finally:
        await os.close()


if __name__ == "__main__":
    asyncio.run(main())
