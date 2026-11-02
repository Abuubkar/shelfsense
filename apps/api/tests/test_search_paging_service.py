"""Deep pagination returns every product of a result set exactly once, even while the index changes underneath."""

import math
import random

import pytest
from opensearchpy import AsyncOpenSearch
from opensearchpy.helpers import async_bulk

from shelfsense_api.embeddings import embed_query
from shelfsense_api.search import ALIAS, Filters, ensure_index, search

pytestmark = [pytest.mark.integration, pytest.mark.anyio]

QUERY = "widget"
LEXICAL, SEMANTIC_ONLY, UNRELATED = 4900, 100, 300


def _near(vector: list[float], rng: random.Random, noise: float) -> list[float]:
    """A unit vector close to `vector` (cosine falls as noise grows)."""
    v = [x + rng.gauss(0, noise) for x in vector]
    norm = math.sqrt(sum(x * x for x in v))
    return [x / norm for x in v]


def _doc(i: int, title: str, vector: list[float]) -> dict:
    return {"_index": ALIAS, "_id": f"p{i:05d}", "_source": {
        "product_id": f"p{i:05d}", "supplier": "test", "supplier_sku": f"SKU-{i}", "title": title,
        "description": None, "brand": f"Brand{i % 7}", "gtin": None, "price_minor": 100 * (i % 300),
        "currency": "USD", "color": None, "size": None, "category_id": None, "category_path": None,
        "updated_at": "2026-11-02T00:00:00Z", "embedding": vector}}


async def test_every_product_appears_exactly_once_while_the_index_changes(opensearch_url: str) -> None:
    rng = random.Random(7)
    query_vector = embed_query(QUERY)
    os = AsyncOpenSearch(hosts=[opensearch_url])
    try:
        await ensure_index(os)
        docs = (
            # Lexical matches with unrelated vectors.
            [_doc(i, f"{QUERY} model {i}", _near([rng.gauss(0, 1) for _ in query_vector], rng, 0)) for i in range(LEXICAL)]
            # No query word in the title, but a vector close to the query's: semantic-only matches.
            + [_doc(i, f"gadget model {i}", _near(query_vector, rng, 0.02)) for i in range(LEXICAL, LEXICAL + SEMANTIC_ONLY)]
            # Neither: must not appear.
            + [_doc(i, f"sprocket {i}", _near([rng.gauss(0, 1) for _ in query_vector], rng, 0))
               for i in range(LEXICAL + SEMANTIC_ONLY, LEXICAL + SEMANTIC_ONLY + UNRELATED)]
        )
        await async_bulk(os, docs, refresh="wait_for")
        expected = {d["_id"] for d in docs[: LEXICAL + SEMANTIC_ONLY]}

        seen: list[str] = []
        after = None
        page_no = 0
        while True:
            page = await search(os, QUERY, Filters(), 48, after)
            if page_no == 0:
                assert page.total == len(expected)
            seen += [h.product_id for h in page.hits]
            page_no += 1
            # Between pages: rename some matches out of the result set, delete some, and add new matches.
            changes = [{"_op_type": "update", "_index": ALIAS, "_id": f"p{rng.randrange(LEXICAL):05d}",
                        "doc": {"title": "renamed sprocket"}} for _ in range(20)]
            changes += [{"_op_type": "delete", "_index": ALIAS, "_id": f"p{rng.randrange(LEXICAL):05d}"}
                        for _ in range(10)]
            changes += [_doc(10_000 + page_no * 100 + n, f"{QUERY} new {n}", query_vector) for n in range(10)]
            await async_bulk(os, changes, refresh="wait_for", raise_on_error=False)
            if page.next_cursor is None:
                break
            after = page.next_cursor

        assert len(seen) == len(set(seen)), "a product appeared on two pages"
        assert set(seen) == expected, "the snapshot's result set changed while paging"
        assert page_no == math.ceil(len(expected) / 48)
    finally:
        await os.close()
