"""Backfill step of JSONB -> typed columns (docs/migrations.md): copy each product's attributes_json into
product_attributes and fill its typed columns, 20,000 products per transaction, in ID order. Progress is saved
with each batch, so a stopped run resumes where it left off. Safe to rerun: it rewrites the same values.

    uv run python scripts/backfill_attributes.py            # resume (or start)
    uv run python scripts/backfill_attributes.py --restart  # again from the first product: the catch-up pass
                                                            # after cutover, for rows old code wrote meanwhile

Runs between migrations 0005 (expand) and 0006 (contract). Raw SQL on purpose: the app's models no longer have
attributes_json.
"""

import asyncio
import sys
import time
from typing import Any

from sqlalchemy import text

from shelfsense_api.db import engine
from shelfsense_api.normalize import typed_attributes

BATCH = 20_000
NAME = "attributes"


async def main() -> None:
    restart = "--restart" in sys.argv
    async with engine.begin() as conn:
        await conn.execute(text("INSERT INTO backfill_state (name) VALUES (:name) ON CONFLICT DO NOTHING"),
                           {"name": NAME})
        if restart:
            await conn.execute(text("UPDATE backfill_state SET last_id = NULL, rows_done = 0, finished_at = NULL "
                                    "WHERE name = :name"), {"name": NAME})
        state = (await conn.execute(text("SELECT last_id, rows_done, finished_at FROM backfill_state "
                                         "WHERE name = :name"), {"name": NAME})).one()
    if state.finished_at:
        print(f"already finished at {state.finished_at:%H:%M:%S} ({state.rows_done} products); --restart to rerun")
        return

    last_id, done, started = state.last_id, state.rows_done, time.perf_counter()
    print(f"{'resuming after ' + str(last_id) if last_id else 'starting'} ({done} products done)")
    while True:
        batch_started = time.perf_counter()
        async with engine.begin() as conn:
            rows = (await conn.execute(text(
                "SELECT id, attributes_json FROM products WHERE (CAST(:last AS uuid) IS NULL OR id > :last) "
                "ORDER BY id LIMIT :batch"), {"last": last_id, "batch": BATCH})).all()
            if not rows:
                await conn.execute(text("UPDATE backfill_state SET finished_at = now(), updated_at = now() "
                                        "WHERE name = :name"), {"name": NAME})
                break
            await _write(conn, rows)
            last_id, done = rows[-1].id, done + len(rows)
            await conn.execute(text("UPDATE backfill_state SET last_id = :last, rows_done = :done, updated_at = now() "
                                    "WHERE name = :name"), {"last": last_id, "done": done, "name": NAME})
        print(f"  {done:>7} products  batch {len(rows)} in {time.perf_counter() - batch_started:.1f}s")
    elapsed = time.perf_counter() - started
    print(f"finished: {done} products, {done / max(elapsed, 1e-9):,.0f}/s this run")


async def _write(conn: Any, rows: list[Any]) -> None:
    # Only products that have attributes: an empty attributes_json was either never set, or written by code past
    # the expand step, which keeps attributes in product_attributes already.
    with_attrs = [r for r in rows if r.attributes_json]
    if not with_attrs:
        return
    ids = [r.id for r in with_attrs]
    typed = [typed_attributes(r.attributes_json) for r in with_attrs]
    await conn.execute(text("DELETE FROM product_attributes WHERE product_id = ANY(CAST(:ids AS uuid[]))"),
                       {"ids": ids})
    pairs = [(r.id, k, v) for r in with_attrs for k, v in r.attributes_json.items()]
    await conn.execute(text(
        "INSERT INTO product_attributes (product_id, name, value) "
        "SELECT * FROM unnest(CAST(:ids AS uuid[]), CAST(:names AS text[]), CAST(:values AS text[]))"),
        {"ids": [p[0] for p in pairs], "names": [p[1] for p in pairs], "values": [p[2] for p in pairs]})
    columns = ("color_base", "material", "gender", "size_system", "size_value")
    await conn.execute(text(
        "UPDATE products p SET color_base = v.color_base, material = v.material, gender = v.gender, "
        "size_system = v.size_system, size_value = v.size_value "
        "FROM unnest(CAST(:ids AS uuid[]), " + ", ".join(f"CAST(:{c} AS text[])" for c in columns) + ") "
        "AS v(id, " + ", ".join(columns) + ") WHERE p.id = v.id"),
        {"ids": ids, **{c: [t[c] for t in typed] for c in columns}})


if __name__ == "__main__":
    asyncio.run(main())
