"""Import a supplier's product API (v2 snapshot if offered, else drifting v1 offsets) and queue what needs
enriching. Resumes an unfinished import of the same supplier.

    uv run python scripts/import_supplier.py ridgeway http://localhost:8030 [--api v1|v2] [--no-enqueue]
"""

import asyncio
import sys
import time

import httpx

from shelfsense_api import aws, service
from shelfsense_api.db import SessionLocal
from shelfsense_api.supplier_import import import_supplier


async def main() -> None:
    supplier, base_url = sys.argv[1], sys.argv[2]
    api = sys.argv[sys.argv.index("--api") + 1] if "--api" in sys.argv else "auto"
    started = time.perf_counter()
    async with SessionLocal() as session, httpx.AsyncClient(timeout=30) as http:
        report = await import_supplier(session, http, supplier, base_url, api=api)
        enqueued = 0
        if "--no-enqueue" not in sys.argv:
            async with aws.sqs() as sqs:
                enqueued = await service.enqueue_enrichment(session, sqs, report.upserted.product_ids)
    u = report.upserted
    print(f"{supplier} via {report.api_version}{' (resumed)' if report.resumed else ''}: {report.pages} pages, "
          f"{report.items_seen} items read, {report.duplicates_dropped} duplicates dropped, "
          f"{report.windows_reread} shifted windows re-read, {report.reconcile_passes} reconcile passes, "
          f"{report.rate_limited} rate-limited requests; {u.inserted} inserted, {u.updated} updated, "
          f"{u.unchanged} unchanged, {report.rejected} rejected; {enqueued} queued for enrichment "
          f"({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    asyncio.run(main())
