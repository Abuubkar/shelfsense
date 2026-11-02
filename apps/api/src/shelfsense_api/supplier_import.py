"""Importing a supplier's product API exactly, even when its pagination drifts (docs/adr/0011).

v2 offers a snapshot token: every page of the scan reads one frozen copy, so a plain cursor walk is exact.

v1 only has offset pages over a live, newest-first list. While we scan, new and updated products jump to the
front, shifting everything behind them: a naive scan reads some products twice and misses the ones that moved
behind it. So:

1. Pages overlap by one item. When a page doesn't start with the last item of the previous one, the boundary
   moved: find where the previous page's SKUs went (looking further ahead if needed) and continue after them.
   That keeps the scan exact for products that didn't change.
2. Products that did change floated to the front, newer than the scan's start. A reconciliation pass re-reads
   from the top everything newer than that, and repeats from the top until one page holds all changes made
   during the previous pass. "Newer" is judged by the supplier's own updated_at, so our clock doesn't matter.
3. Every version is deduplicated by (sku, updated_at); an older version never overwrites a newer one.

Progress is saved after every page in import_state, with that page's products in the same transaction, so a
failed import resumes where it stopped.
"""

import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import feeds
from shelfsense_api.db import ImportState
from shelfsense_api.queue import backoff_s

PAGE_SIZE = 100
MAX_SERVER_ERRORS = 3  # in a row, per request
MAX_RATE_LIMITED = 20
WIDE_WINDOW_PAGES = 5  # how far ahead to look for a page that moved


class SupplierUnavailable(Exception):
    pass


@dataclass
class ImportReport:
    api_version: str
    resumed: bool = False
    pages: int = 0
    items_seen: int = 0
    duplicates_dropped: int = 0
    windows_reread: int = 0
    reconcile_passes: int = 0
    rejected: int = 0
    rate_limited: int = 0
    upserted: feeds.Upserted = field(default_factory=feeds.Upserted)


def resume_point(window_skus: list[str], previous_page_skus: list[str]) -> int | None:
    """Where to continue in a window that should start with the previous page's last SKU: the index just after
    the last of the previous page's SKUs found in it. 1 when the boundary held; more when products were inserted
    before it; None when none of them is in the window (they moved, or the shift is longer than the window)."""
    positions = {sku: i for i, sku in enumerate(window_skus)}
    for sku in reversed(previous_page_skus):
        if sku in positions:
            return positions[sku] + 1
    return None


async def import_supplier(session: AsyncSession, http: httpx.AsyncClient, supplier_code: str, base_url: str,
                          api: str = "auto", page_size: int = PAGE_SIZE) -> ImportReport:
    """Import every product the supplier's API lists, resuming an unfinished import of the same supplier."""
    supplier_id = await feeds.ensure_supplier(session, supplier_code)
    state = await session.get(ImportState, supplier_id)
    if api == "auto":
        api = "v2" if (await http.get(f"{base_url}/v2/products", params={"limit": 1})).status_code == 200 else "v1"
    resumed = state is not None and state.status != "done" and state.base_url == base_url and state.api_version == api
    if not resumed:
        if state is None:
            state = ImportState(supplier_id=supplier_id)
            session.add(state)
        _start(state, base_url, api)
    assert state is not None
    await session.commit()

    report = ImportReport(api_version=api, resumed=resumed)
    seen: dict[str, datetime] = {}
    try:
        if api == "v2":
            await _scan_v2(session, http, state, page_size, report, seen)
        else:
            if state.status == "scanning":
                await _scan_v1(session, http, state, page_size, report, seen)
            await _reconcile_v1(session, http, state, page_size, report, seen)
    except (SupplierUnavailable, httpx.HTTPError) as exc:
        state.error = f"{type(exc).__name__}: {exc}"[:500]
        await session.commit()
        raise
    state.status, state.error = "done", None
    await session.commit()
    return report


def _start(state: ImportState, base_url: str, api: str) -> None:
    state.base_url, state.api_version, state.status = base_url, api, "scanning"
    state.scan_started_at = datetime.now(UTC)  # replaced by the supplier's own clock from the first page
    state.next_offset, state.last_page_skus = 0, []
    state.snapshot_token = state.page_cursor = state.error = None
    state.pages = state.items_seen = state.duplicates_dropped = state.windows_reread = 0


async def _scan_v1(session: AsyncSession, http: httpx.AsyncClient, state: ImportState, page_size: int,
                    report: ImportReport, seen: dict[str, datetime]) -> None:
    while True:
        offset = state.next_offset
        window_start = max(0, offset - 1)  # one item of overlap with the previous page
        data = await _get(http, f"{state.base_url}/v1/products", {"offset": window_start, "limit": page_size + 1},
                          report)
        items = data["items"]
        start = 0
        if offset:
            start = resume_point([i["sku"] for i in items], state.last_page_skus) or 0
            if start != 1:  # the boundary moved: find the previous page further ahead
                state.windows_reread += 1
                report.windows_reread += 1
                data = await _get(http, f"{state.base_url}/v1/products",
                                  {"offset": window_start, "limit": page_size * WIDE_WINDOW_PAGES}, report)
                items = data["items"]
                # Not found at all: carry on from here. Duplicates are dropped below, and anything that moved
                # behind us is newer than the scan's start, so reconciliation reads it.
                start = resume_point([i["sku"] for i in items], state.last_page_skus) or 1
        page = items[start:start + page_size]
        if offset == 0 and page:
            state.scan_started_at = max(_ts(i) for i in page)
        await _apply(session, state, page, report, seen)
        state.next_offset = window_start + start + len(page) if offset else len(page)
        state.last_page_skus = [i["sku"] for i in page]
        done = not page or state.next_offset >= data["total"]
        if done:
            state.status = "reconciling"
        await _save(session, state, report)
        if done:
            return


async def _reconcile_v1(session: AsyncSession, http: httpx.AsyncClient, state: ImportState, page_size: int,
                         report: ImportReport, seen: dict[str, datetime]) -> None:
    """Re-read from the top everything changed since `watermark`, until one page holds all of it."""
    watermark = state.scan_started_at
    while True:
        report.reconcile_passes += 1
        offset, pages, newest = 0, 0, watermark
        while True:
            data = await _get(http, f"{state.base_url}/v1/products", {"offset": offset, "limit": page_size}, report)
            items = data["items"]
            if pages == 0 and items:
                newest = max(_ts(i) for i in items)  # changes after this page was served are newer than this
            fresh = [i for i in items if _ts(i) > watermark]
            await _apply(session, state, fresh, report, seen)
            await _save(session, state, report)
            pages += 1
            if len(fresh) < len(items) or not items:
                break
            offset += page_size
        if pages == 1:
            return
        watermark = newest


async def _scan_v2(session: AsyncSession, http: httpx.AsyncClient, state: ImportState, page_size: int,
                    report: ImportReport, seen: dict[str, datetime]) -> None:
    while True:
        params: dict[str, Any] = {"limit": page_size}
        if state.snapshot_token:
            params |= {"snapshot_token": state.snapshot_token, "cursor": state.page_cursor}
        try:
            data = await _get(http, f"{state.base_url}/v2/products", {k: v for k, v in params.items() if v}, report)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 410 or not state.snapshot_token:
                raise
            state.snapshot_token = state.page_cursor = None  # the snapshot expired: start a new one
            continue
        state.snapshot_token, state.page_cursor = data["snapshot_token"], data["next_cursor"]
        await _apply(session, state, data["items"], report, seen)
        await _save(session, state, report)
        if data["next_cursor"] is None:
            return


async def _apply(session: AsyncSession, state: ImportState, items: list[dict[str, Any]], report: ImportReport,
                 seen: dict[str, datetime]) -> None:
    rows = []
    for item in items:
        report.items_seen += 1
        state.items_seen += 1
        known, version = seen.get(item["sku"]), _ts(item)
        if known is not None and known >= version:
            report.duplicates_dropped += 1  # this version, or a newer one, is already written
            state.duplicates_dropped += 1
            continue
        seen[item["sku"]] = version
        try:
            rows.append(feeds.FeedRow.model_validate({
                "sku": item["sku"], "title": item.get("title"), "description": item.get("description"),
                "brand": item.get("brand"), "gtin": item.get("gtin"), "price": item.get("price"),
                "currency": item.get("currency"),
                "attributes": {k: str(item[k]) for k in ("color", "size", "material", "gender") if item.get(k)},
            }))
        except ValidationError:
            report.rejected += 1
    if rows:
        upserted = await feeds.upsert_rows(session, state.supplier_id, rows)
        for name in ("inserted", "updated", "unchanged"):
            setattr(report.upserted, name, getattr(report.upserted, name) + getattr(upserted, name))
        report.upserted.product_ids += upserted.product_ids


async def _save(session: AsyncSession, state: ImportState, report: ImportReport) -> None:
    state.pages += 1
    report.pages += 1
    state.updated_at = datetime.now(UTC)
    await session.commit()  # the page's products and the progress past them, together


async def _get(http: httpx.AsyncClient, url: str, params: dict[str, Any], report: ImportReport) -> dict[str, Any]:
    """GET with retries: waits out 429s (honouring Retry-After), retries 5xx and connection errors with backoff."""
    server_errors = rate_limited = 0
    while True:
        try:
            response = await http.get(url, params=params)
        except httpx.TransportError as exc:
            error: str = repr(exc)
        else:
            if response.status_code == 429:
                rate_limited += 1
                report.rate_limited += 1
                if rate_limited > MAX_RATE_LIMITED:
                    raise SupplierUnavailable(f"still rate limited after {MAX_RATE_LIMITED} tries: {url}")
                await asyncio.sleep(float(response.headers.get("Retry-After", backoff_s(rate_limited, base=0.5))))
                continue
            if response.status_code < 500:
                response.raise_for_status()
                return response.json()
            error = f"HTTP {response.status_code}"
        server_errors += 1
        if server_errors >= MAX_SERVER_ERRORS:
            raise SupplierUnavailable(f"{error} {server_errors} times in a row: {url} {params}")
        await asyncio.sleep(backoff_s(server_errors, base=0.2, cap=5))


def _ts(item: dict[str, Any]) -> datetime:
    return datetime.fromisoformat(item["updated_at"])
