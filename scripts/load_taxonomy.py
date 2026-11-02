"""Load one Google Product Taxonomy release into taxonomy_nodes, with each full path embedded.

    uv run python scripts/load_taxonomy.py [data/taxonomy/2021-09-21.txt]

Defaults to the release in settings.taxonomy_version. A release that's already loaded is left as it is.
"""

import asyncio
import sys
import time
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from shelfsense_api.db import SessionLocal, TaxonomyNode
from shelfsense_api.embeddings import embed_passages
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import read_release


async def main(path: Path) -> None:
    version, nodes = read_release(path)
    async with SessionLocal() as session:
        loaded = await session.scalar(select(func.count()).where(TaxonomyNode.version == version))
        if loaded == len(nodes):
            print(f"taxonomy {version}: all {loaded} nodes already loaded")
            return

        started = time.perf_counter()
        vectors = embed_passages([n.full_path for n in nodes])
        print(f"embedded {len(nodes)} paths in {time.perf_counter() - started:.1f}s")

        # Parents come before children in the file, so inserting in file order satisfies the parent foreign key.
        rows = [{"version": version, **n.__dict__, "embedding": v} for n, v in zip(nodes, vectors, strict=True)]
        for start in range(0, len(rows), 1000):
            await session.execute(insert(TaxonomyNode).values(rows[start : start + 1000]).on_conflict_do_nothing())
        await session.commit()
        leaves = sum(n.is_leaf for n in nodes)
        print(f"taxonomy {version}: {len(nodes)} nodes ({leaves} leaves), max depth {max(n.depth for n in nodes)}")


if __name__ == "__main__":
    default = Path("data/taxonomy") / f"{settings.taxonomy_version}.txt"
    asyncio.run(main(Path(sys.argv[1]) if len(sys.argv) > 1 else default))
