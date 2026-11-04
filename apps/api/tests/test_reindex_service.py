"""A zero-downtime reindex into products_v2 on real Postgres and OpenSearch: a write during the build is caught up,
the checks pass, searches through the alias never fail while it moves, and a rollback brings back what changed."""

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any

import pytest
from opensearchpy import AsyncOpenSearch
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shelfsense_api import db, reindex
from shelfsense_api.db import Product, Supplier
from shelfsense_api.feeds import FeedRow, upsert_rows
from shelfsense_api.indexing import BatchSizer, bulk_index, product_docs
from shelfsense_api.search import ALIAS, INDEX, Filters, ensure_index, lexical_query, search

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

TARGET = "products_v2"


def row(n: int, title: str, color: str) -> FeedRow:
    return FeedRow(sku=f"R-{n}", title=title, price=f"{10 + n}.00", attributes={"color": color, "material": "wool"})


@pytest.fixture
async def stack(migrated_postgres_url: str, opensearch_url: str,
                monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncOpenSearch, Any, uuid.UUID]]:
    """Products in Postgres, indexed into products_v1 behind the alias; afterwards the alias is back on v1 and
    this test's documents and products_v2 are gone, so other tests see the index as they left it."""
    engine = create_async_engine(migrated_postgres_url)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "SessionLocal", sessions)
    os = AsyncOpenSearch(hosts=[opensearch_url])
    await ensure_index(os)
    if await os.indices.exists(index=TARGET):
        await os.indices.delete(index=TARGET)
    async with sessions() as session:
        supplier = Supplier(code=f"reindex-{uuid.uuid4().hex[:8]}")
        session.add(supplier)
        await session.flush()
        await upsert_rows(session, supplier.id, [row(n, f"Grey wool hiking sock {n}", "grey") for n in range(10)]
                          + [row(n, f"Insulated rain jacket {n}", "navy") for n in range(10, 30)])
        await session.commit()
        ids = list(await session.scalars(select(Product.id)))
        await bulk_index(os, await product_docs(session, ids), BatchSizer())
        await os.indices.refresh(index=ALIAS)
        yield os, sessions, supplier.id
        if TARGET in await reindex.served_indices(os):
            await os.indices.update_aliases(body={"actions": [{"remove": {"index": TARGET, "alias": ALIAS}},
                                                              {"add": {"index": INDEX, "alias": ALIAS}}]})
        await os.indices.delete(index=TARGET, ignore_unavailable=True)
        await os.delete_by_query(index=INDEX, body={"query": {"ids": {"values": [str(i) for i in ids]}}},
                                 refresh=True)
    await os.close()
    await engine.dispose()


async def total(os: AsyncOpenSearch, index: str, query: dict[str, Any]) -> int:
    return (await os.count(index=index, body={"query": query}))["count"]


async def test_reindex_builds_catches_up_swaps_without_failed_searches_and_rolls_back(stack: Any) -> None:
    os, sessions, supplier_id = stack
    async with sessions() as session:
        state = await reindex.start(os, session, TARGET)
        await reindex.build(os, session, TARGET, state, progress=lambda _: None)
        assert state["phase"] == "built"

        # The worker keeps writing through the alias, so this change reaches v1 only until a catch-up pass.
        await upsert_rows(session, supplier_id, [row(10, "Camping lantern with hook", "navy")])
        await session.commit()
        renamed = await session.scalar(select(Product.id).where(Product.supplier_sku == "R-10",
                                                                Product.supplier_id == supplier_id))
        await bulk_index(os, await product_docs(session, [renamed]), BatchSizer())
        await os.indices.refresh(index=ALIAS)
        assert await reindex.catch_up_target(os, session, TARGET, state) >= 1

        checks = await reindex.check(os, session, TARGET, state)
        assert checks["passed"], checks["parity_mismatches"]
        assert state["phase"] == "checked"

        # What v2 adds: colour synonyms at search time, title prefixes, facets by name.
        assert await total(os, INDEX, lexical_query("gray sock")) == 0
        assert await total(os, TARGET, lexical_query("gray sock")) == 10
        assert await total(os, TARGET, {"match": {"title.autocomplete": "lant"}}) == 1
        assert await total(os, TARGET, {"nested": {"path": "facets", "query": {"bool": {"filter": [
            {"term": {"facets.name": "color"}}, {"term": {"facets.value": "navy"}}]}}}}) == 20

        # Searches through the alias for the whole swap: none may fail, and each sees a complete index.
        stop, failures, totals = asyncio.Event(), [], []

        async def keep_searching() -> None:
            while not stop.is_set():
                try:
                    totals.append((await search(os, "rain jacket", Filters(), 5, None)).total)
                except Exception as exc:  # noqa: BLE001 - counting every failure is the point
                    failures.append(repr(exc))
                await asyncio.sleep(0)

        async def searched(n: int) -> None:
            while len(totals) + len(failures) < n:
                await asyncio.sleep(0.05)

        searcher = asyncio.create_task(keep_searching())
        await searched(3)
        before = len(totals)
        state = await reindex.swap(os, session, TARGET, state)
        await searched(before + 3)
        stop.set()
        await searcher
        assert failures == []
        assert len(set(totals)) == 1  # the same complete result set before, during and after
        assert await reindex.served_indices(os) == [TARGET]
        assert state["previous"] == [INDEX]

        with pytest.raises(reindex.ReindexError, match="kept until"):
            await reindex.drop_previous(os, session, TARGET, state)

        # Changed after the swap: lands in v2 through the alias, and the rollback carries it back to v1.
        await upsert_rows(session, supplier_id, [row(11, "Folding camp stool", "navy")])
        await session.commit()
        stool = await session.scalar(select(Product.id).where(Product.supplier_sku == "R-11",
                                                              Product.supplier_id == supplier_id))
        await bulk_index(os, await product_docs(session, [stool]), BatchSizer())
        await reindex.rollback(os, session, TARGET, state)
        await os.indices.refresh(index=INDEX)
        assert await reindex.served_indices(os) == [INDEX]
        assert (await os.get(index=INDEX, id=str(stool)))["_source"]["title"] == "Folding camp stool"
