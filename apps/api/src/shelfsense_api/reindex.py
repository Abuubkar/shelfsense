"""Zero-downtime reindex into a new index version (docs/adr/0019): build it from Postgres, catch up, check, then move
the `products` alias in one atomic request and keep the previous version for 24 hours.

Searches and writes keep going through the alias the whole time, so until the swap the index worker writes to the
old index only. Catch-up passes reindex every product changed since the previous pass started: its row, its
category (each enrichment writes an `enrichment_runs` row in the same transaction), or its extracted attributes.
A pass looks back OVERLAP further than its mark, because a row's timestamp is its transaction's start, which can
be well before the commit. The last pass runs after the swap, through the alias: it covers what the worker wrote
to the old index between the pre-swap pass and the swap. Reindexing a product twice is harmless.

Progress lives in the new index's mapping `_meta` ("reindex"), so a stopped run resumes where it was, and the
state goes away with the index.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Any

from opensearchpy import AsyncOpenSearch
from sqlalchemy import String, cast, func, select, union
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api.db import EnrichmentRun, Product, ProductCategory, ProductExtractedAttribute
from shelfsense_api.embeddings import embed_query
from shelfsense_api.indexing import BatchSizer, bulk_index, product_docs
from shelfsense_api.search import ALIAS, Filters, ensure_index, match_set

CHUNK = 2000  # products embedded and held in memory at once
OVERLAP = timedelta(minutes=10)
KEEP_PREVIOUS = timedelta(hours=24)
PARITY_SAMPLE = 50


class ReindexError(Exception):
    pass


async def read_state(os: AsyncOpenSearch, index: str) -> dict[str, Any] | None:
    if not await os.indices.exists(index=index):
        return None
    mapping = await os.indices.get_mapping(index=index)
    return mapping[index]["mappings"].get("_meta", {}).get("reindex")


async def save_state(os: AsyncOpenSearch, index: str, state: dict[str, Any]) -> None:
    await os.indices.put_mapping(index=index, body={"_meta": {"reindex": state}})


async def served_indices(os: AsyncOpenSearch) -> list[str]:
    return sorted(await os.indices.get_alias(name=ALIAS)) if await os.indices.exists_alias(name=ALIAS) else []


async def db_now(session: AsyncSession) -> datetime:
    # Not now(): that is the transaction's start, and a reindex session stays in one read transaction for hours.
    now: datetime = (await session.execute(select(func.statement_timestamp()))).scalar_one()
    return now


async def changed_since(session: AsyncSession, since: datetime) -> list[uuid.UUID]:
    """Products whose search document may have changed since `since`."""
    query = union(
        select(Product.id).where(Product.updated_at >= since),
        select(EnrichmentRun.product_id).where(EnrichmentRun.created_at >= since),
        select(ProductExtractedAttribute.product_id).where(ProductExtractedAttribute.created_at >= since),
        select(ProductCategory.product_id).where(ProductCategory.created_at >= since),
    )
    return sorted(await session.scalars(query))


async def start(os: AsyncOpenSearch, session: AsyncSession, target: str) -> dict[str, Any]:
    """Create `target` from its template (without the alias), or pick up the state of a run already under way."""
    await ensure_index(os)
    if target in await served_indices(os):
        raise ReindexError(f"{target} is already behind '{ALIAS}'")
    if await os.indices.exists(index=target):
        state = await read_state(os, target)
        if state is None:
            raise ReindexError(f"{target} exists but wasn't created by a reindex; delete it or pick another name")
        return state
    await os.indices.create(index=target, body={"settings": {"index": {"refresh_interval": "-1"}}})
    state = {"phase": "building", "started_at": (await db_now(session)).isoformat(), "after_id": None, "indexed": 0}
    await save_state(os, target, state)
    return state


async def _index(os: AsyncOpenSearch, session: AsyncSession, index: str, ids: list[uuid.UUID], sizer: BatchSizer) -> int:
    docs = await product_docs(session, ids)
    # Forget the rows just read: a long run's session would otherwise hand a catch-up pass the version it loaded
    # first (sessions don't expire on commit), and hold the whole catalog in memory.
    session.expunge_all()
    outcomes = await bulk_index(os, docs, sizer, index=index)
    failed = [o for o in outcomes if o.status != "done"]
    if failed:
        raise ReindexError(f"{len(failed)} products failed to index into {index}, e.g. {failed[0].product_id}: "
                           f"{failed[0].error_code} {failed[0].detail[:120]}; run again to resume")
    return len(outcomes)


async def build(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any],
                progress: Any = print) -> None:
    """Every product into `target`, in product ID order, saving the position after each chunk."""
    sizer = BatchSizer()
    total = await session.scalar(select(func.count()).select_from(Product))
    while state["phase"] == "building":
        query = select(Product.id).order_by(Product.id).limit(CHUNK)
        if state["after_id"]:
            query = query.where(Product.id > uuid.UUID(state["after_id"]))
        ids = list(await session.scalars(query))
        if not ids:
            state["phase"] = "built"
        else:
            state["indexed"] += await _index(os, session, target, ids, sizer)
            state["after_id"] = str(ids[-1])
            progress(f"  built {state['indexed']} of ~{total}")
        await save_state(os, target, state)


async def catch_up(os: AsyncOpenSearch, session: AsyncSession, index: str, since: datetime) -> tuple[datetime, int]:
    """Reindex into `index` every product changed since `since` (minus OVERLAP). Returns this pass's mark (the
    `since` of the next pass) and how many products it reindexed."""
    mark = await db_now(session)
    ids = await changed_since(session, since - OVERLAP)
    sizer, done = BatchSizer(), 0
    for n in range(0, len(ids), CHUNK):
        done += await _index(os, session, index, ids[n:n + CHUNK], sizer)
    return mark, done


async def catch_up_target(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any]) -> int:
    mark, done = await catch_up(os, session, target, datetime.fromisoformat(state.get("caught_up_to")
                                                                             or state["started_at"]))
    state["caught_up_to"] = mark.isoformat()
    await save_state(os, target, state)
    return done


async def check(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any],
                sample: int = PARITY_SAMPLE) -> dict[str, Any]:
    """Doc count against Postgres, and a parity sample against the served index: product titles as queries (a
    title that found itself in the top 10 must still do so, and no query may match fewer products; v2's synonyms
    only widen matches). Turns refresh back on first, so the swap serves a refreshed index."""
    await os.indices.put_settings(index=target, body={"index": {"refresh_interval": None}})
    await os.indices.refresh(index=target)
    served = (await served_indices(os))[0]
    products = await session.scalar(select(func.count()).select_from(Product))
    count = (await os.count(index=target))["count"]
    rows = (await session.execute(select(Product.id, Product.title).order_by(func.md5(cast(Product.id, String)))
                                  .limit(sample))).all()
    mismatches = []
    for product_id, title in rows:
        vector = await asyncio.to_thread(embed_query, title)
        (before_total, before_top), (after_total, after_top) = [
            await _known_item(os, index, title, vector, str(product_id)) for index in (served, target)]
        if (before_top and not after_top) or after_total < before_total:
            mismatches.append({"q": title, "served": [before_total, before_top], "target": [after_total, after_top]})
    result = {"products": products, "target_docs": count, "served": served,
              "served_docs": (await os.count(index=served))["count"], "parity_queries": len(rows),
              "parity_mismatches": mismatches, "passed": count == products and not mismatches}
    state["checks"] = result
    if result["passed"]:
        state["phase"] = "checked"
    await save_state(os, target, state)
    return result


async def _known_item(os: AsyncOpenSearch, index: str, title: str, vector: list[float],
                      product_id: str) -> tuple[int, bool]:
    """How many products a title matches, and whether the title finds itself in the top 10: its own product, or
    one with the identical title (seeded catalogs repeat titles, and the order among identical listings turns on
    score differences in the second decimal)."""
    response = await os.search(index=index, body={"size": 10, "_source": ["title"], "track_total_hits": True,
                                                  "query": match_set(title, vector, Filters())})
    hits = response["hits"]["hits"]
    return response["hits"]["total"]["value"], any(h["_id"] == product_id or h["_source"]["title"] == title
                                                   for h in hits)


async def swap(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any]) -> dict[str, Any]:
    """A last catch-up, the alias moved to `target` in one atomic request, then the catch-up after it."""
    if state["phase"] != "checked":
        raise ReindexError(f"{target} is '{state['phase']}', not 'checked': run the checks first")
    before = await catch_up_target(os, session, target, state)
    previous = await served_indices(os)
    actions = [{"remove": {"index": index, "alias": ALIAS}} for index in previous]
    await os.indices.update_aliases(body={"actions": [*actions, {"add": {"index": target, "alias": ALIAS}}]})
    swapped = await db_now(session)
    after = await catch_up_target(os, session, target, state)
    state |= {"phase": "swapped", "previous": previous, "swapped_at": swapped.isoformat(),
              "keep_until": (swapped + KEEP_PREVIOUS).isoformat(), "caught_up_around_swap": [before, after]}
    await save_state(os, target, state)
    return state


async def rollback(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any]) -> dict[str, Any]:
    """The alias back to the previous version, which first catches up on what changed since the swap."""
    if state["phase"] != "swapped":
        raise ReindexError(f"{target} is '{state['phase']}', not 'swapped'")
    previous = state["previous"]
    for index in previous:
        await catch_up(os, session, index, datetime.fromisoformat(state["swapped_at"]))
    actions = [{"add": {"index": index, "alias": ALIAS}} for index in previous]
    await os.indices.update_aliases(body={"actions": [{"remove": {"index": target, "alias": ALIAS}}, *actions]})
    for index in previous:  # what the worker wrote to `target` between that catch-up and the move
        await catch_up(os, session, index, datetime.fromisoformat(state["swapped_at"]))
    state |= {"phase": "rolled_back", "rolled_back_at": (await db_now(session)).isoformat()}
    await save_state(os, target, state)
    return state


async def drop_previous(os: AsyncOpenSearch, session: AsyncSession, target: str, state: dict[str, Any]) -> list[str]:
    """Delete the versions the swap replaced, once KEEP_PREVIOUS has passed and nothing serves from them."""
    if state["phase"] != "swapped":
        raise ReindexError(f"{target} is '{state['phase']}', not 'swapped'")
    if await db_now(session) < datetime.fromisoformat(state["keep_until"]):
        raise ReindexError(f"the previous version is kept until {state['keep_until']}")
    served = await served_indices(os)
    dropped = [index for index in state["previous"] if index not in served and await os.indices.exists(index=index)]
    for index in dropped:
        await os.indices.delete(index=index)
    return dropped
