"""Supplier API imports against the drifting mock, writing to a real Postgres: the cases that would miss or
duplicate products if they broke."""

from collections.abc import AsyncIterator
from decimal import Decimal
from typing import Any

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from shelfsense_api.db import ImportState, Product, Supplier
from shelfsense_api.supplier_import import PAGE_SIZE, SupplierUnavailable, import_supplier
from shelfsense_supplier_mock import app as mock

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

DRIFT = {"seed": 9, "products": 2000, "inserts_per_request": 2, "updates_per_request": 3}


@pytest.fixture
async def session(migrated_postgres_url: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(migrated_postgres_url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


@pytest.fixture
async def http() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=mock), base_url="http://mock") as client:
        yield client


async def imported(session: AsyncSession, supplier: str) -> dict[str, int]:
    rows = await session.execute(select(Product.supplier_sku, Product.price_minor)
                                 .join(Supplier, Supplier.id == Product.supplier_id).where(Supplier.code == supplier))
    return dict(rows.all())


async def truth(http: httpx.AsyncClient) -> dict[str, int]:
    return {i["sku"]: int(Decimal(i["price"]) * 100) for i in (await http.get("/admin/catalog")).json()}


def missing_and_wrong(got: dict[str, int], expected: dict[str, int]) -> tuple[int, int, int]:
    """Products missing, products that shouldn't be there, and products holding an outdated price."""
    stale = sum(1 for sku, price in expected.items() if sku in got and got[sku] != price)
    return len(expected.keys() - got.keys()), len(got.keys() - expected.keys()), stale


async def test_drifting_offset_pages_import_every_product_once_at_its_latest_version(
        session: AsyncSession, http: httpx.AsyncClient) -> None:
    await http.post("/admin/reset", json=DRIFT)

    report = await import_supplier(session, http, "drift-exact", "http://mock", api="v1")

    assert missing_and_wrong(await imported(session, "drift-exact"), await truth(http)) == (0, 0, 0)
    assert report.windows_reread > 0 and report.reconcile_passes >= 2  # the drift really happened


async def test_an_import_that_fails_mid_scan_resumes_where_it_stopped(
        session: AsyncSession, http: httpx.AsyncClient) -> None:
    # Requests 8-10 fail: three 500s in a row make the importer give up partway through the scan.
    await http.post("/admin/reset", json={**DRIFT, "fail_requests": [8, 9, 10]})

    with pytest.raises(SupplierUnavailable):
        await import_supplier(session, http, "drift-resume", "http://mock", api="v1")
    state: Any = await session.scalar(select(ImportState).join(Supplier).where(Supplier.code == "drift-resume"))
    stopped_at, products_before = state.next_offset, len(await imported(session, "drift-resume"))
    assert state.status == "scanning" and state.error and stopped_at > 0
    # Each saved page's products were committed with its progress (the offset also counts products inserted ahead).
    assert products_before == state.pages * PAGE_SIZE

    report = await import_supplier(session, http, "drift-resume", "http://mock", api="v1")

    assert report.resumed
    assert report.items_seen < DRIFT["products"]  # it didn't start over
    assert missing_and_wrong(await imported(session, "drift-resume"), await truth(http)) == (0, 0, 0)
