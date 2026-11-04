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
from opentelemetry import trace

from shelfsense_api import cursor, embeddings
from shelfsense_api.embeddings import embed_query, rerank
from shelfsense_api.settings import settings

# What a fresh setup creates and puts the alias on, and what the eval gates read: the served version. v2 since
# 2026-11-04 (docs/migrations.md C); scripts/reindex.py moves the alias on existing setups.
INDEX = "products_v2"
ALIAS = "products"
PIPELINE = "products-hybrid"
HEAD_SIZE = 5  # reranked per search: ~5 ms a product on an M1 Pro, ~13 ms on a CI runner (docs/adr/0021)
# Price facet buckets in minor units: (key, from, to), `to` exclusive.
PRICE_BUCKETS = [("0-2500", None, 2500), ("2500-5000", 2500, 5000), ("5000-10000", 5000, 10000),
                 ("10000-20000", 10000, 20000), ("20000-", 20000, None)]
FACET_SIZE = 20
_SOURCE = {"excludes": ["embedding"]}
TAIL_SORT = [{"_score": "desc"}, {"product_id": "asc"}]  # with a PIT, search_after needs an explicit tiebreaker

# Added to products_v1 in place (slice 5a, 6c): adding fields never changes how existing ones are indexed. Changing
# or removing a field still means a new index version and an alias move.
NEW_FIELDS = {
    "gender": {"type": "keyword"},
    "material": {"type": "keyword"},
    "size_system": {"type": "keyword"},
    # Shoe sizes in EU numbers (normalize.shoe_size_eu), so "size 8" finds a boot listed as "EU 39.5".
    "size_eu": {"type": "float"},
    # Every facet value as a (name, value) pair, so a facet can be aggregated or filtered by name without a new
    # field per attribute. Part of products_v2; added to v1 too, so one document fits whichever index the alias
    # points at during a reindex (both are "dynamic": "strict").
    "facets": {"type": "nested", "properties": {"name": {"type": "keyword"}, "value": {"type": "keyword"}}},
}

_V1_PROPERTIES: dict[str, Any] = {
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
}

# Search-time synonyms for colour and material words (products_v2). Spelling variants are equivalent; a base
# colour or material also finds its named shades and kinds, but not the reverse ("red" finds a burgundy bag,
# "burgundy" doesn't find every red one). Taken from normalize's vocabulary, leaving out abbreviations and words
# that mostly mean something else ("steel", "wine", "rose", "lime", "walnut", "down", "iron", "print").
SYNONYMS = [
    "grey, gray",
    "aluminium, aluminum",
    "polyamide, nylon",
    "stainless steel, stainless",
    "black => black, onyx",
    "white => white, ivory, cream, off white",
    "gray => gray, grey, charcoal, graphite",
    "beige => beige, khaki",
    "red => red, burgundy, maroon, crimson",
    "pink => pink, fuchsia, blush",
    "yellow => yellow, mustard",
    "green => green, olive, sage",
    "blue => blue, navy, teal, cobalt, turquoise",
    "purple => purple, violet, lavender",
    "wool => wool, merino",
]

_V2_ANALYSIS = {
    "filter": {
        # The built-in english analyzer, rebuilt so synonyms can go into it (OpenSearch docs: English analyzer).
        "english_possessive_stemmer": {"type": "stemmer", "language": "possessive_english"},
        "english_stop": {"type": "stop", "stopwords": "_english_"},
        "english_keywords": {"type": "keyword_marker", "keywords": []},
        "english_stemmer": {"type": "stemmer", "language": "english"},
        # Search time only: at index time a multi-word synonym would shift later token positions. After the stop
        # filter (a stop filter after it breaks the graph), before stemming so stemming treats both sides alike.
        "color_material_synonyms": {"type": "synonym_graph", "synonyms": SYNONYMS, "lenient": True},
        "autocomplete_edge": {"type": "edge_ngram", "min_gram": 2, "max_gram": 15},
    },
    "analyzer": {
        "english_synonyms": {"type": "custom", "tokenizer": "standard", "filter": [
            "english_possessive_stemmer", "lowercase", "english_stop", "color_material_synonyms",
            "english_keywords", "english_stemmer"]},
        "autocomplete_index": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase", "autocomplete_edge"]},
        "autocomplete_search": {"type": "custom", "tokenizer": "standard", "filter": ["lowercase"]},
    },
}


def _with_synonyms(field: dict[str, Any]) -> dict[str, Any]:
    return field | {"search_analyzer": "english_synonyms"}


_V2_PROPERTIES = _V1_PROPERTIES | {
    # Prefixes of title words ("hik" -> hiking), for an autocomplete box: indexed as edge n-grams, searched whole.
    "title": _with_synonyms(_V1_PROPERTIES["title"]) | {"fields": {"autocomplete": {
        "type": "text", "analyzer": "autocomplete_index", "search_analyzer": "autocomplete_search"}}},
    "description": _with_synonyms(_V1_PROPERTIES["description"]),
    "category_path": _with_synonyms(_V1_PROPERTIES["category_path"]),
}

_SETTINGS = {"knn": True, "number_of_shards": 1, "number_of_replicas": 0}

# One template per index version. No template attaches the alias: a new version must not take searches before
# it is built and checked, so the alias is only ever moved by ensure_index (fresh setup) or scripts/reindex.py.
TEMPLATES = {
    "products_v1": {"index_patterns": ["products_v1"], "template": {
        "settings": {"index": _SETTINGS}, "mappings": {"dynamic": "strict", "properties": _V1_PROPERTIES}}},
    "products_v2": {"index_patterns": ["products_v2"], "template": {
        "settings": {"index": _SETTINGS, "analysis": _V2_ANALYSIS},
        "mappings": {"dynamic": "strict", "properties": _V2_PROPERTIES}}},
}


def template_changes(recorded: dict[str, Any], current: dict[str, Any]) -> tuple[list[str], list[str]]:
    """How a version's template moved from its recorded snapshot (contracts/index/): what changed in place, which
    needs a new index version, and which top-level fields were added, which is allowed (NEW_FIELDS) but must be
    recorded. Settings, analysis included, count as one thing that can change."""
    old, new = recorded["template"], current["template"]
    changed = ["settings"] if old["settings"] != new["settings"] else []
    old_fields, new_fields = old["mappings"]["properties"], new["mappings"]["properties"]
    changed += [f"field {name}" for name in old_fields if old_fields[name] != new_fields.get(name)]
    if {k: v for k, v in old["mappings"].items() if k != "properties"} != \
            {k: v for k, v in new["mappings"].items() if k != "properties"}:
        changed.append("mapping options")
    return changed, sorted(set(new_fields) - set(old_fields))


_tracer = trace.get_tracer(__name__)
# opensearch-py has no maintained instrumentation: its calls get these manual spans (the aiohttp client spans
# beneath them come from the aiohttp-client instrumentation).
_OS_SPAN = {"db.system.name": "opensearch", "db.operation.name": "search"}


async def _embed(q: str) -> list[float]:
    with _tracer.start_as_current_span("embed query"):
        return await asyncio.to_thread(embed_query, q)


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
    """The search pipeline and every version's template; then either the in-place field additions on whatever
    index the alias points at, or, on a fresh setup, the first index with the alias on it."""
    await os.search_pipeline.put(id=PIPELINE, body=pipeline_body())
    for name, template in TEMPLATES.items():
        await os.indices.put_index_template(name=name, body=template)
    if await os.indices.exists_alias(name=ALIAS):
        await os.indices.put_mapping(index=ALIAS, body={"properties": NEW_FIELDS})
    elif await os.indices.exists(index=INDEX):  # created by a version whose template still carried the alias
        await os.indices.put_mapping(index=INDEX, body={"properties": NEW_FIELDS})
        await os.indices.put_alias(index=INDEX, name=ALIAS)
    else:
        await os.indices.create(index=INDEX, body={"aliases": {ALIAS: {}}})


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
    position: dict[str, Any] = (cursor.decode(after, scope, settings.cursor_secret) if after
                                else {"rank": 0, "after": None})

    # Independent steps overlap: the PIT is opened while the query is embedded, facets count while the page is
    # built, and the tail is fetched while the head is reranked (it needs the head's IDs, not their order).
    started = time.perf_counter()
    embedding = asyncio.create_task(_embed(q)) if q else None

    try:
        pit = position.get("pit") or (await os.create_pit(
            index=index, params={"keep_alive": settings.search_cursor_ttl}))["pit_id"]
        timings["pit"] = _ms(started)
        vector = await embedding if embedding else None
        timings["embed"] = _ms(started)
        facets_task = asyncio.create_task(_facets(os, pit, q, vector, filters, timings))
        rank = position["rank"]
        # Reranking only matters for pages that show head products; later pages need just the head's IDs.
        reranked = rank < HEAD_SIZE
        raw = await _hybrid_head(os, pit, q, vector, filters, reranked, debug, timings, pipeline) if q else []
        ordering = asyncio.create_task(_order_head(raw, q, reranked, debug and reranked, timings))
        shown = len(raw[rank : rank + page_size])

        more = rank + shown < len(raw)
        tail: list[Hit] = []
        if not more:
            remaining = page_size - shown
            started = time.perf_counter()
            # One extra hit tells whether another page exists, so the last page is never an empty one.
            tail = await _tail(os, pit, q, vector, filters, [h["_id"] for h in raw], position["after"],
                               remaining + 1, debug, start_rank=max(rank, len(raw)) + 1)
            timings["tail"] = _ms(started)
            more = len(tail) > remaining
            tail = tail[:remaining]
        items = (await ordering)[rank : rank + page_size] + tail
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


async def _hybrid_head(os: AsyncOpenSearch, pit: str, q: str, vector: list[float] | None, filters: Filters,
                       reranked: bool, debug: bool, timings: dict[str, int], pipeline: str = PIPELINE) -> list[dict]:
    """The first HEAD_SIZE products by hybrid score, as OpenSearch returns them (with their text when they'll be
    reranked)."""
    hybrid: dict[str, Any] = {"queries": [lexical_query(q), semantic_query(vector or [])]}
    if clauses := filter_clauses(filters):
        hybrid["filter"] = {"bool": {"filter": clauses}}
    explain = debug and reranked
    params = {"search_pipeline": pipeline} | ({"explain": "true"} if explain else {})
    started = time.perf_counter()
    with _tracer.start_as_current_span("opensearch hybrid", attributes=_OS_SPAN):
        response = await os.search(body={"size": HEAD_SIZE, "_source": _SOURCE if reranked else False,
                                         "query": {"hybrid": hybrid},
                                         "pit": {"id": pit, "keep_alive": settings.search_cursor_ttl}}, params=params)
    timings["hybrid"] = _ms(started)
    return response["hits"]["hits"]


async def _order_head(raw: list[dict], q: str, reranked: bool, explain: bool, timings: dict[str, int]) -> list[Hit]:
    """The head in its final order: reranked by the cross-encoder when `reranked`, else as the hybrid ranked it."""
    if not reranked:
        return [Hit(h["_id"], {}, "head", n) for n, h in enumerate(raw, start=1)]

    started = time.perf_counter()
    with _tracer.start_as_current_span("rerank", attributes={"shelfsense.rerank_docs": len(raw),
                                                             "shelfsense.rerank_model": embeddings.RERANK_MODEL}):
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
    with _tracer.start_as_current_span("opensearch tail", attributes=_OS_SPAN):
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
                  filters: Filters, timings: dict[str, int]) -> tuple[int, dict[str, list[FacetValue]]]:
    """Total and facet counts over the whole result set, after all filters (drill-down facets)."""
    aggs: dict[str, Any] = {name: {"terms": {"field": name, "size": FACET_SIZE}}
                            for name in ("brand", "color", "category_id")}
    aggs["price"] = {"range": {"field": "price_minor", "ranges": [
        {"key": key} | ({"from": lo} if lo is not None else {}) | ({"to": hi} if hi is not None else {})
        for key, lo, hi in PRICE_BUCKETS]}}
    started = time.perf_counter()
    with _tracer.start_as_current_span("opensearch facets", attributes=_OS_SPAN):
        response = await os.search(body={
            "size": 0, "track_total_hits": True, "query": match_set(q, vector, filters), "aggs": aggs,
            "pit": {"id": pit, "keep_alive": settings.search_cursor_ttl}})
    timings["facets"] = _ms(started)
    facets = {name: [FacetValue(str(b["key"]), b["doc_count"]) for b in agg["buckets"] if b["doc_count"]]
              for name, agg in response["aggregations"].items()}
    return response["hits"]["total"]["value"], facets


def _ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)

