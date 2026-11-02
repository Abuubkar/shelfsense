"""End-to-end smoke test against the running API, using only the generated typed client.

Runs 5 searches with debug scores and facets, pages through one result set to the end (checking every product
appears exactly once and the count matches `total`), then checks GraphQL returns the same first page.
Usage: uv run python scripts/smoke.py [api_base]
"""

import sys

from shelfsense_client import Client
from shelfsense_client.api.default import search_products
from shelfsense_client.models import Problem, SearchResponse
from shelfsense_client.types import Unset

SEARCHES = [
    ("hiking boots", {}),
    ("chargr for laptop", {}),  # typo: only the semantic side can match it
    ("something to keep drinks cold", {}),
    ("gift for a runner", {"price_max": 4999}),
    ("", {"brand": ["Northpeak", "Voltix"]}),  # browse with a facet filter
]
PAGED_QUERY, PAGE_SIZE = "outdoor gear for the trail", 4

GRAPHQL_SEARCH = """
query ($query: String!, $first: Int!) {
  search(query: $query, first: $first) {
    total
    edges { cursor node { id rank title } }
    pageInfo { hasNextPage endCursor }
  }
}"""


def search(client: Client, q: str, **kwargs) -> SearchResponse:
    result = search_products.sync(client=client, q=q, **kwargs)
    if isinstance(result, Problem):
        raise SystemExit(f"search {q!r} failed: {result.code.value}: {result.detail}")
    assert isinstance(result, SearchResponse), result
    return result


def show(q: str, filters: dict, page: SearchResponse) -> None:
    timings = page.debug.timings_ms.additional_properties if page.debug and not isinstance(page.debug, Unset) else {}
    print(f"\n# q={q!r} filters={filters} → total {page.total}, timings {timings}")
    for item in page.items[:3]:
        debug = item.debug if item.debug and not isinstance(item.debug, Unset) else None
        scores = " ".join(f"{k}={v:.3f}" for k, v in debug.scores.additional_properties.items()) if debug else ""
        print(f"  {item.rank:2} [{debug.stage.value if debug else '-'}] {item.title[:42]:42} "
              f"{item.price.amount_minor / 100:>7.2f} {item.price.currency}  {scores}")
    for facet in page.facets:
        print(f"  facet {facet.name.value:11} " + ", ".join(f"{v.label} ({v.count})" for v in facet.values[:4]))


def main() -> None:
    base = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8020"
    client = Client(base_url=base, timeout=120)

    for q, filters in SEARCHES:
        show(q, filters, search(client, q, debug=True, page_size=5, **filters))

    print(f"\n# paging q={PAGED_QUERY!r} page_size={PAGE_SIZE}")
    seen: list[str] = []
    cursor: str | None = None
    first_page_ids: list[str] = []
    total = None
    while True:
        page = search(client, PAGED_QUERY, page_size=PAGE_SIZE, **({"cursor": cursor} if cursor else {}))
        total = page.total if total is None else total
        ids = [str(i.id) for i in page.items]
        first_page_ids = first_page_ids or ids
        seen += ids
        print(f"  page {len(seen) // PAGE_SIZE + (len(seen) % PAGE_SIZE > 0):2}: ranks "
              f"{[i.rank for i in page.items]} next={'yes' if page.next_cursor else 'end'}")
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    assert len(seen) == len(set(seen)), "a product appeared twice"
    assert len(seen) == total, f"paged {len(seen)} products, total says {total}"
    print(f"  {len(seen)} products, each once, matching total {total}")

    response = client.get_httpx_client().post(
        "/graphql", json={"query": GRAPHQL_SEARCH, "variables": {"query": PAGED_QUERY, "first": PAGE_SIZE}})
    data = response.json()
    assert "errors" not in data, data
    gql = data["data"]["search"]
    gql_ids = [e["node"]["id"] for e in gql["edges"]]
    print(f"\n# GraphQL search first page: {[e['node']['title'][:30] for e in gql['edges']]}")
    assert gql_ids == first_page_ids, (gql_ids, first_page_ids)
    assert gql["total"] == total
    print(f"  same {len(gql_ids)} products in the same order as REST, total {gql['total']}, "
          f"hasNextPage={gql['pageInfo']['hasNextPage']}")


if __name__ == "__main__":
    main()
