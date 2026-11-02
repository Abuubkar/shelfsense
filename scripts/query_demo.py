"""Natural-language queries through the search API, showing how each was read and what it found.

    uv run python scripts/query_demo.py [--fresh]   # --fresh clears cached parses first

Runs the API app in-process (the same code as the server), so the last query can force a timeout by shrinking the
model's time limit for that one request.
"""

import asyncio
import sys
from typing import Any

import httpx

from shelfsense_api import query
from shelfsense_api.main import app
from shelfsense_api.settings import settings

QUERIES = [
    "hiking boots",
    "waterproof women's hiking boots under $120 size 8",
    "waterproof women's hiking boots under $120 size 8",  # again: the cache
    "navy rain jacket for men",
    "black water bottle under 30 dollars",
    "non-leather wallet",
    "yoga mat between 20 and 50",
    "kids rain boots green",
    "headphones under $5",  # nothing that cheap: the price is relaxed
]
FORCED_TIMEOUT = "white mens tee size L"


def show(q: str, body: dict[str, Any], note: str = "") -> None:
    parse = body.get("query_parse") or {}
    filters = {k: v for k, v in (parse.get("filters") or {}).items() if v not in (None, [], {})}
    print(f"\n> {q}{note}")
    print(f"  parse: {parse.get('source')} in {parse.get('ms')} ms; keywords {parse.get('keywords')!r}; "
          f"hint {parse.get('category_hint')!r}; filters {filters}"
          + ("; PRICE RELAXED" if parse.get("price_relaxed") else ""))
    print(f"  {body['total']} results")
    for item in body["items"][:3]:
        print(f"    {item['rank']}. {item['title'][:46]:46} {item['price']['amount_minor'] / 100:>7.2f} "
              f"{item['color'] or '-':6} {item['category_path'] or ''}"[:140])


async def main() -> None:
    if "--fresh" in sys.argv:
        async for key in query.cache().scan_iter("qp:*"):
            await query.cache().delete(key)
    await query.warm()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://api", timeout=30) as http:
        for q in QUERIES:
            response = await http.get("/v1/search", params={"q": q, "page_size": 5})
            response.raise_for_status()
            show(q, response.json())
        normal, settings.query_timeout_s = settings.query_timeout_s, 0.01
        try:
            response = await http.get("/v1/search", params={"q": FORCED_TIMEOUT, "page_size": 5})
        finally:
            settings.query_timeout_s = normal
        response.raise_for_status()
        show(FORCED_TIMEOUT, response.json(), "   [time limit forced to 10 ms]")


if __name__ == "__main__":
    asyncio.run(main())
