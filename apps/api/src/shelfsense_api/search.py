"""Product search in OpenSearch: the index, hybrid retrieval with reranking, facets, and deep pagination.

The result set of a query is every product that matches it lexically (BM25) or semantically (k-NN score at least
settings.knn_min_score), after filters. Its first HEAD_SIZE products are ranked by the hybrid pipeline and then
reranked by a cross-encoder; the rest follow in BM25 + k-NN score order. All pages of one query read one
point-in-time (PIT) snapshot, and the rest exclude the head's IDs, so every product appears exactly once even
while the index changes (docs/adr/0006).
"""

import asyncio
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from opensearchpy import AsyncOpenSearch, NotFoundError

from shelfsense_api import cursor
from shelfsense_api.embeddings import embed_query, rerank
from shelfsense_api.settings import settings

INDEX = "products_v1"
ALIAS = "products"
PIPELINE = "products-hybrid"
HEAD_SIZE = 50
# Price facet buckets in minor units: (key, from, to), `to` exclusive.
PRICE_BUCKETS = [("0-2500", None, 2500), ("2500-5000", 2500, 5000), ("5000-10000", 5000, 10000),
                 ("10000-20000", 10000, 20000), ("20000-", 20000, None)]
FACET_SIZE = 20
_SOURCE = {"excludes": ["embedding"]}
TAIL_SORT = [{"_score": "desc"}, {"product_id": "asc"}]  # with a PIT, search_after needs an explicit tiebreaker

# Added to products_v1 in place (slice 5a): adding fields never changes how existing ones are indexed. Changing
# or removing a field still means a new index version and an alias move.
NEW_FIELDS = {
    "gender": {"type": "keyword"},
    "material": {"type": "keyword"},
    "size_system": {"type": "keyword"},
    # Shoe sizes in EU numbers (normalize.shoe_size_eu), so "size 8" finds a boot listed as "EU 39.5".
    "size_eu": {"type": "float"},
}

INDEX_TEMPLATE = {
    "index_patterns": [INDEX],
    "template": {
        "settings": {"index": {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}},
        "mappings": {
            "dynamic": "strict",
            "properties": {
                "product_id": {"type": "keyword"},
                "supplier": {"type": "keyword"},
                "supplier_sku": {"type": "keyword"},
                "title": {"type": "text", "analyzer": "english"},
                "description": {"type": "text", "analyzer": "english"},
                "brand": {"type": "keyword", "fields": {"text": {"type": "text"}}},
                "gtin": {"type": "keyword"},
                "price_minor": {"type": "long"},
                "currency": {"type": "keyword"},
                # Base palette colour (normalize.BASE_COLORS), from the supplier's column or the listing's text.
                "color": {"type": "keyword", "normalizer": "lowercase"},
                "size": {"type": "keyword"},
                **NEW_FIELDS,
                "category_id": {"type": "integer"},
                "category_path": {"type": "text", "analyzer": "english"},
                "updated_at": {"type": "date"},
                "embedding": {"type": "knn_vector", "dimension": 384, "space_type": "cosinesimil",
                              "method": {"name": "hnsw", "engine": "faiss"}},
            },
        },
        "aliases": {ALIAS: {}},
    },
}


class SearchUnavailable(Exception):
    pass


class CursorExpired(Exception):
    pass


_client: AsyncOpenSearch | None = None


def client() -> AsyncOpenSearch:
    global _client
    if _client is None:
        _client = AsyncOpenSearch(hosts=[settings.opensearch_url])
    return _client


def pipeline_body(normalization: dict[str, Any] | None = None) -> dict[str, Any]:
    """The hybrid search pipeline: BM25 and k-NN scores normalized (min-max unless `normalization` says otherwise;
    the evals compare others), then a weighted arithmetic mean."""
    return {
        "description": "normalize BM25 and k-NN scores, then a weighted arithmetic mean",
        "phase_results_processors": [{"normalization-processor": {
            "normalization": normalization or {"technique": "min_max"},
            "combination": {"technique": "arithmetic_mean",
                            "parameters": {"weights": list(settings.hybrid_weights)}},
        }}],
        # Only acts when a search asks for explain=true (the debug block).
        "response_processors": [{"hybrid_score_explanation": {}}],
    }


async def ensure_index(os: AsyncOpenSearch) -> None:
    """The search pipeline, the index template, and the first index (which joins the alias from the template)."""
    await os.search_pipeline.put(id=PIPELINE, body=pipeline_body())
    await os.indices.put_index_template(name=INDEX, body=INDEX_TEMPLATE)
    if not await os.indices.exists(index=INDEX):
        await os.indices.create(index=INDEX)
    else:
        await os.indices.put_mapping(index=INDEX, body={"properties": NEW_FIELDS})


@dataclass(frozen=True)
class Filters:
    """Facet filters: values within one facet are OR'ed, facets are AND'ed. Prices are in minor units."""

    brand: tuple[str, ...] = ()
    color: tuple[str, ...] = ()
    category_id: tuple[int, ...] = ()
    price_min: int | None = None
    price_max: int | None = None
    gender: tuple[str, ...] = ()
    material: tuple[str, ...] = ()
    exclude_color: tuple[str, ...] = ()
    exclude_material: tuple[str, ...] = ()
    size: str | None = None  # a letter size ("M")
    size_eu: float | None = None  # a shoe size, in EU numbers


def filter_clauses(filters: Filters) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    for name in ("brand", "color", "category_id", "gender", "material"):
        values = getattr(filters, name)
        if values:
            clauses.append({"terms": {name: sorted(set(values))}})
    price = {op: v for op, v in (("gte", filters.price_min), ("lte", filters.price_max)) if v is not None}
    if price:
        clauses.append({"range": {"price_minor": price}})
    if filters.size:
        clauses.append({"term": {"size": filters.size}})
    if filters.size_eu is not None:
        clauses.append({"term": {"size_eu": filters.size_eu}})
    excluded = [{"terms": {name: sorted(set(values))}}
                for name, values in (("color", filters.exclude_color), ("material", filters.exclude_material))
                if values]
    if excluded:
        clauses.append({"bool": {"must_not": excluded}})
    return clauses


def lexical_query(q: str) -> dict[str, Any]:
    # cross_fields treats title, brand and category as one field, so "merrell hiking boot" can match brand and
    # title together; up to 2 terms must all match, longer queries 75% of them.
    return {"multi_match": {"query": q, "type": "cross_fields", "operator": "or", "minimum_should_match": "2<75%",
                            "fields": ["title^3", "brand.text^2", "category_path^2", "description"],
                            "_name": "lexical"}}


def semantic_query(vector: list[float], filters: Filters | None = None) -> dict[str, Any]:
    # Radial search (min_score instead of k): every product above the threshold, so it defines a set to page
    # through instead of a fixed top-k. Filters go inside the k-NN query: filtering only afterwards loses products,
    # because the approximate search over the whole index stops early (docs/challenges.md, slice 5b).
    knn: dict[str, Any] = {"vector": vector, "min_score": settings.knn_min_score, "_name": "semantic"}
    if filters is not None and (clauses := filter_clauses(filters)):
        knn["filter"] = {"bool": {"filter": clauses}}
    return {"knn": {"embedding": knn}}


def match_set(q: str, vector: list[float] | None, filters: Filters, exclude: list[str] | None = None) -> dict[str, Any]:
    """The query's whole result set as one bool query (no ranking subtleties: used for facets and the tail)."""
    bool_query: dict[str, Any] = {"filter": filter_clauses(filters)}
    if q and vector is not None:
        bool_query |= {"should": [lexical_query(q), semantic_query(vector, filters)], "minimum_should_match": 1}
    if exclude:
        bool_query["must_not"] = [{"ids": {"values": list(exclude)}}]
    return {"bool": bool_query}


@dataclass
class Hit:
    product_id: str
    source: dict[str, Any]
    stage: str  # "head" (hybrid + rerank) or "tail" (BM25 + k-NN score order)
    rank: int
    scores: dict[str, float] = field(default_factory=dict)
    sort: list[Any] | None = None  # the tail's search_after position


@dataclass
class FacetValue:
    value: str
    count: int


@dataclass
class SearchPage:
    hits: list[Hit]
    # One cursor per hit: the position just after it, so GraphQL edges can each resume from their own place.
    cursors: list[str]
    total: int
    facets: dict[str, list[FacetValue]]
    next_cursor: str | None
    timings_ms: dict[str, int]


async def search(os: AsyncOpenSearch, q: str, filters: Filters, page_size: int, after: str | None,
                 debug: bool = False, scope: dict[str, Any] | None = None,
                 carry: dict[str, Any] | None = None, index: str = ALIAS, pipeline: str = PIPELINE) -> SearchPage:
    """One page of a query's result set. A cursor holds the PIT, the rank reached, and the tail's search_after
    position. The head isn't stored in it: each page re-runs the hybrid query on the same PIT, which returns the
    same head, so cursors stay small enough to put one on every GraphQL edge.

    `scope` is what a cursor is bound to (by default the query and filters); `carry` rides along in every cursor
    for the caller, e.g. the query parse page 1 used, so later pages search exactly the same way. `index` and
    `pipeline` are for the evals, which search their own golden index with other score normalizations."""
    q = " ".join(q.split())
    scope = scope or {"q": q, "filters": asdict(filters)}
    timings: dict[str, int] = {}
    position = cursor.decode(after, scope, settings.cursor_secret) if after else {"rank": 0, "after": None}

    started = time.perf_counter()
    vector = await asyncio.to_thread(embed_query, q) if q else None
    timings["embed"] = _ms(started)

    try:
        pit = position.get("pit") or (await os.create_pit(
            index=index, params={"keep_alive": settings.search_cursor_ttl}))["pit_id"]
        facets_task = asyncio.create_task(_facets(os, pit, q, vector, filters))
        rank = position["rank"]
        # Reranking only matters for pages that show head products; later pages need just the head's IDs.
        head = await _head(os, pit, q, vector, filters, rank < HEAD_SIZE, debug, timings, pipeline) if q else []
        items = head[rank : rank + page_size]

        more = rank + len(items) < len(head)
        if not more:
            remaining = page_size - len(items)
            started = time.perf_counter()
            # One extra hit tells whether another page exists, so the last page is never an empty one.
            tail = await _tail(os, pit, q, vector, filters, [h.product_id for h in head], position["after"],
                               remaining + 1, debug, start_rank=max(rank, len(head)) + 1)
            timings["tail"] = _ms(started)
            more = len(tail) > remaining
            items += tail[:remaining]
        total, facets = await facets_task
    except NotFoundError as exc:
        raise CursorExpired("the search cursor expired; start the search again") from exc
    except ConnectionError as exc:
        raise SearchUnavailable(str(exc)) from exc

    extra = {"carry": carry} if carry else {}
    cursors = [cursor.encode({"pit": pit, "rank": h.rank, "after": h.sort, **extra}, scope, settings.cursor_secret)
               for h in items]
    if not more:
        await os.delete_pit(body={"pit_id": [pit]})
    if not debug:
        for hit in items:
            hit.scores = {}
    return SearchPage(items, cursors, total, facets, cursors[-1] if more and cursors else None, timings)


async def _head(os: AsyncOpenSearch, pit: str, q: str, vector: list[float] | None, filters: Filters,
                reranked: bool, debug: bool, timings: dict[str, int], pipeline: str = PIPELINE) -> list[Hit]:
    """The first HEAD_SIZE products by hybrid score, reranked by the cross-encoder when `reranked`."""
    hybrid: dict[str, Any] = {"queries": [lexical_query(q), semantic_query(vector or [])]}
    if clauses := filter_clauses(filters):
        hybrid["filter"] = {"bool": {"filter": clauses}}
    explain = debug and reranked
    params = {"search_pipeline": pipeline} | ({"explain": "true"} if explain else {})
    started = time.perf_counter()
    response = await os.search(body={"size": HEAD_SIZE, "_source": _SOURCE if reranked else False,
                                     "query": {"hybrid": hybrid},
                                     "pit": {"id": pit, "keep_alive": settings.search_cursor_ttl}}, params=params)
    timings["hybrid"] = _ms(started)
    raw = response["hits"]["hits"]
    if not reranked:
        return [Hit(h["_id"], {}, "head", n) for n, h in enumerate(raw, start=1)]

    started = time.perf_counter()
    rerank_scores = await asyncio.to_thread(rerank, q, [_rerank_text(h["_source"]) for h in raw]) if raw else []
    timings["rerank"] = _ms(started)
    hits = [Hit(h["_id"], h["_source"], "head", 0,
                {"hybrid": h["_score"], "rerank": s} | (_subquery_scores(h["_explanation"]) if explain else {}))
            for h, s in zip(raw, rerank_scores, strict=True)]
    # sort() is stable: ties (identical texts) keep the hybrid order, so every page of one PIT sees the same head.
    hits.sort(key=lambda h: -h.scores["rerank"])
    for n, hit in enumerate(hits, start=1):
        hit.rank = n
    return hits


def _rerank_text(source: dict[str, Any]) -> str:
    parts = [source["title"], source.get("brand"), source.get("category_path"), (source.get("description") or "")[:300]]
    return ". ".join(p for p in parts if p)


def _subquery_scores(explanation: dict[str, Any]) -> dict[str, float]:
    """BM25 and k-NN scores, raw and normalized, from a hybrid hit's explanation. Each top-level detail is one
    subquery that matched; a subquery that didn't match the product is absent."""
    scores: dict[str, float] = {}
    for detail in explanation.get("details", []):
        raw = detail["details"][0] if detail.get("details") else {}
        name = "knn" if "knn" in str(raw.get("description", "")).lower() else "bm25"
        scores[name] = raw.get("value", 0.0)
        scores[f"{name}_normalized"] = detail.get("value", 0.0)
    return scores


async def _tail(os: AsyncOpenSearch, pit: str, q: str, vector: list[float] | None, filters: Filters,
                head_ids: list[str], after: list[Any] | None, size: int, debug: bool, start_rank: int) -> list[Hit]:
    body: dict[str, Any] = {"size": size, "_source": _SOURCE, "query": match_set(q, vector, filters, head_ids),
                            "sort": TAIL_SORT, "track_total_hits": False,
                            "pit": {"id": pit, "keep_alive": settings.search_cursor_ttl}}
    if after:
        body["search_after"] = after
    params = {"include_named_queries_score": "true"} if debug else {}
    response = await os.search(body=body, params=params)
    hits = []
    for n, h in enumerate(response["hits"]["hits"]):
        named = h.get("matched_queries") if isinstance(h.get("matched_queries"), dict) else {}
        scores = {"tail": h["_score"] or 0.0}
        if "lexical" in named:
            scores["bm25"] = named["lexical"]
        if "semantic" in named:
            scores["knn"] = named["semantic"]
        hits.append(Hit(h["_id"], h["_source"], "tail", start_rank + n, scores, h["sort"]))
    return hits


async def _facets(os: AsyncOpenSearch, pit: str, q: str, vector: list[float] | None,
                  filters: Filters) -> tuple[int, dict[str, list[FacetValue]]]:
    """Total and facet counts over the whole result set, after all filters (drill-down facets)."""
    aggs = {name: {"terms": {"field": name, "size": FACET_SIZE}} for name in ("brand", "color", "category_id")}
    aggs["price"] = {"range": {"field": "price_minor", "ranges": [
        {"key": key} | ({"from": lo} if lo is not None else {}) | ({"to": hi} if hi is not None else {})
        for key, lo, hi in PRICE_BUCKETS]}}
    response = await os.search(body={"size": 0, "track_total_hits": True, "query": match_set(q, vector, filters),
                                     "aggs": aggs, "pit": {"id": pit, "keep_alive": settings.search_cursor_ttl}})
    facets = {name: [FacetValue(str(b["key"]), b["doc_count"]) for b in agg["buckets"] if b["doc_count"]]
              for name, agg in response["aggregations"].items()}
    return response["hits"]["total"]["value"], facets


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

