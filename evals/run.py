"""Shelfsense evals: enrichment, query parsing and search ranking over the golden set (evals/golden/), with gates.

    make eval                  # the dev split, replaying recorded model replies: no Ollama needed
    make eval LIVE=1           # the dev split against local Ollama, recording its replies
    make eval-test             # the test split (LIVE=1 to record it)
    uv run python evals/run.py [--split dev|test] [--live] [--only enrich,parse,search,latency]
                               [--baseline evals/baseline.json] [--write-baseline] [--latency-queries 1000]
                               [--fail-on misses|regressions]

Writes evals/results/<split>.json and evals/REPORT.md (REPORT-test.md for the test split) and exits 1 when a
gate is missed, or with --baseline when a gated quality metric drops more than 1.5 points. CI runs it with
--fail-on regressions against main's results: then only a drop, or a gate main passes that now misses, fails it;
known misses are reported, not failed on (the gates themselves don't change).

Every model call goes through llm.chat_json, which records it by prompt hash (evals/recordings/<split>.jsonl.gz)
or replays it, with its recorded wall time, so a replay reports the same metrics as the live run it recorded.
The search eval runs for real either way, on its own index of the golden products (gold categories, as if
enrichment were perfect), so ranking is measured apart from classification. `latency` replays 1,000 queries
through the API's search path against the catalog and is live only (and not part of `make eval`).
"""

import argparse
import asyncio
import gzip
import json
import random
import shutil
import sys
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from grading import grade
from metrics import (
    SLOTS,
    Counts,
    attribute_sets,
    hierarchical_f1,
    ndcg,
    percentile,
    reciprocal_rank,
    score_parse,
)
from sqlalchemy import select

from shelfsense_api import classify, db, embeddings, llm, prompts, query, search, service
from shelfsense_api.db import Product, TaxonomyNode
from shelfsense_api.embeddings import embed_passages, embed_query, product_text
from shelfsense_api.indexing import product_doc
from shelfsense_api.normalize import typed_attributes
from shelfsense_api.settings import settings

EVALS = Path(__file__).parent
GOLDEN = EVALS / "golden"
SPLITS = {"products": 280, "queries": 80}  # dev sizes; the rest is the test split
TOP = 50  # results scored per query (the head)

# The production pipeline and the alternatives for the BM25-ties problem (docs/challenges.md): min-max maps the
# lowest BM25 score of the head to 0, so when most of it ties at that score the keyword side adds nothing.
NORMALIZATIONS: dict[str, dict[str, Any] | None] = {
    "min-max (shipped)": None,
    "min-max, BM25 floor 0": {"technique": "min_max", "parameters": {
        "lower_bounds": [{"mode": "apply", "min_score": 0.0}, {"mode": "ignore"}]}},
    "l2": {"technique": "l2"},
    "z-score": {"technique": "z_score"},
}
RRF = "RRF (rank 60)"

GATES: list[tuple[str, str, float]] = [
    ("enrichment.leaf_accuracy", ">=", 0.80),
    ("enrichment.hierarchical_f1", ">=", 0.90),
    ("enrichment.candidate_recall", ">=", 0.97),
    ("enrichment.attribute_macro_f1", ">=", 0.85),
    ("enrichment.ungrounded_rate", "<=", 0.05),
    ("enrichment.schema_validity", ">=", 0.98),
    ("enrichment.products_per_hour", ">=", 400),
    ("parse.exact_match", ">=", 0.75),
    ("parse.slot_f1", ">=", 0.90),
    ("search.ndcg10", ">=", 0.72),
    ("search.ndcg10_over_bm25", ">=", 0.08),
    ("search.zero_result_rate", "<=", 0.02),
    ("latency.rules_p95_ms", "<=", 150),
    ("latency.llm_p95_ms", "<=", 3000),
    ("latency.cache_p95_ms", "<=", 180),
]
BASELINE_TOLERANCE = 0.015  # 1.5 points, for the 0-1 quality metrics


def load(split: str) -> tuple[list[dict], list[dict], list[dict]]:
    """The split's products and queries (a fixed hash split), and every product (the search corpus)."""
    def read(name: str) -> list[dict]:
        return [json.loads(line) for line in (GOLDEN / name).read_text().splitlines() if line.strip()]

    def pick(items: list[dict], dev_size: int) -> list[dict]:
        ordered = sorted(items, key=lambda i: uuid.uuid5(uuid.NAMESPACE_URL, i["id"]).hex)
        chosen = ordered[:dev_size] if split == "dev" else ordered[dev_size:]
        return sorted(chosen, key=lambda i: i["id"])

    products, queries = read("products.jsonl"), read("queries.jsonl")
    return pick(products, SPLITS["products"]), pick(queries, SPLITS["queries"]), products


def doc_id(golden_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"shelfsense-golden/{golden_id}"))


# Enrichment -----------------------------------------------------------------------------------------------------


class Candidates:
    """The embedding pre-filter's candidates for each golden product, recorded beside a live run's model replies
    (evals/recordings/<split>-candidates.json.gz) and used by replays instead of being recomputed. On another
    machine, such as CI's x86 runners, float differences in the embeddings can swap a near-tied candidate, which
    changes the prompt and misses its recorded reply; with the live run's candidates, a replay reproduces the live
    run everywhere, candidate recall included. Missing (or a live run): computed, then saved."""

    def __init__(self, path: Path, live: bool):
        self.path, self.current = path, ""
        self.ids: dict[str, list[int]] = {}
        if path.exists() and not live:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self.ids = json.load(f)
        self.changed = False
        self._compute = classify.nearest_leaves

    async def leaves(self, session: Any, version: str, query: list[float], k: int) -> list[TaxonomyNode]:
        if self.current in self.ids:
            ids = self.ids[self.current]
            rows = {n.node_id: n for n in await session.scalars(
                select(TaxonomyNode).where(TaxonomyNode.version == version, TaxonomyNode.node_id.in_(ids)))}
            return [rows[i] for i in ids]
        nodes = await self._compute(session, version, query, k)
        self.ids[self.current], self.changed = [n.node_id for n in nodes], True
        return nodes

    def save(self) -> None:
        if self.changed:
            with gzip.open(self.path, "wt", encoding="utf-8") as f:
                json.dump(dict(sorted(self.ids.items())), f)


async def eval_enrichment(session: Any, products: list[dict], cassette: llm.Cassette, live: bool,
                          candidates: Candidates | None = None) -> dict[str, Any]:
    per_attribute = {name: Counts() for name in prompts.ATTRIBUTE_NAMES}
    pairs: list[tuple[str | None, str]] = []
    rows = []
    extracted = ungrounded = unnormalized = 0
    output_tokens = eval_ms = 0
    started = time.perf_counter()
    if candidates:
        classify.nearest_leaves = candidates.leaves  # type: ignore[assignment]
    for n, p in enumerate(products, start=1):
        mark = len(cassette.calls)
        if candidates:
            candidates.current = p["id"]
        d = await classify.decide(session, p["title"], p["brand"], p["description"], p["attributes"])
        call_ms = sum(ms for _, ms in cassette.calls[mark:])
        paths = {str(c.node_id): c.full_path for c in d.candidates}
        predicted = paths.get(d.chosen or "")
        gold = p["gold"]
        attributes = {a.name: a.value for a in d.grounding.attributes} if d.grounding else {}
        for name, counts in per_attribute.items():
            counts.add(*attribute_sets(attributes.get(name), gold["attributes"][name]))
        if d.grounding:
            extracted += len(d.grounding.attributes) + len(d.grounding.ungrounded) + len(d.grounding.unnormalized)
            ungrounded, unnormalized = ungrounded + len(d.grounding.ungrounded), unnormalized + len(d.grounding.unnormalized)
        if d.reply:
            output_tokens, eval_ms = output_tokens + d.reply.output_tokens, eval_ms + d.reply.eval_ms
        pairs.append((predicted, gold["path"]))
        rows.append({"id": p["id"], "type": p.get("hard_type", "rendered"), "gold": gold["path"],
                     "predicted": predicted, "none": d.chosen == classify.NONE, "error": d.error.code if d.error else None,
                     "recall": str(gold["node_id"]) in paths, "first_try_valid": not d.failures, "ms": call_ms})
        if live and n == 10:
            per = (time.perf_counter() - started) / 10
            print(f"  10 products in {per * 10:.0f}s: {per:.1f}s each, {len(products)} projected at "
                  f"{per * len(products) / 60:.0f} min", flush=True)
        if n % 50 == 0:
            print(f"  enrichment {n}/{len(products)}", flush=True)

    if candidates:
        classify.nearest_leaves = candidates._compute  # type: ignore[assignment]
        candidates.save()
    total = len(rows)
    seconds = sum(r["ms"] for r in rows) / 1000 / total
    confused = Counter((r["gold"], r["predicted"] or "NONE") for r in rows if r["predicted"] != r["gold"])
    depth2 = Counter((_depth(r["gold"], 2), _depth(r["predicted"], 2)) for r in rows)
    by_type: dict[str, list[bool]] = {}
    for r in rows:
        by_type.setdefault(r["type"], []).append(r["predicted"] == r["gold"])
    return {
        "products": total,
        "candidate_recall": _share(r["recall"] for r in rows),
        "leaf_accuracy": _share(r["predicted"] == r["gold"] for r in rows),
        "hierarchical_f1": round(hierarchical_f1(pairs), 4),
        "attributes": {name: {"precision": round(c.precision, 4), "recall": round(c.recall, 4), "f1": round(c.f1, 4),
                              "tp": c.tp, "fp": c.fp, "fn": c.fn} for name, c in per_attribute.items()},
        "attribute_macro_f1": round(sum(c.f1 for c in per_attribute.values()) / len(per_attribute), 4),
        "ungrounded_rate": round(ungrounded / extracted, 4) if extracted else 0.0,
        "unnormalized_rate": round(unnormalized / extracted, 4) if extracted else 0.0,
        "none_rate": _share(r["none"] for r in rows),
        "error_rate": _share(r["error"] is not None for r in rows),
        "schema_validity": _share(r["first_try_valid"] for r in rows),
        "seconds_per_product": round(seconds, 2),
        "products_per_hour": round(3600 / seconds) if seconds else 0,
        "tokens_per_second": round(output_tokens / (eval_ms / 1000), 1) if eval_ms else 0.0,
        "leaf_accuracy_by_type": {t: round(sum(v) / len(v), 4) for t, v in sorted(by_type.items())},
        "wrong_leaf": sorted(r["id"] for r in rows if r["predicted"] != r["gold"]),  # for paired comparisons
        "confusion_depth2": [[g, p, n] for (g, p), n in sorted(depth2.items(), key=lambda x: (-x[1], x[0]))],
        "top_confused": [[g, p, n] for (g, p), n in sorted(confused.items(), key=lambda x: (-x[1], x[0]))[:15]],
    }


def _depth(path: str | None, depth: int) -> str:
    return " > ".join(path.split(" > ")[:depth]) if path else "NONE"


def _share(flags: Any) -> float:
    flags = list(flags)
    return round(sum(flags) / len(flags), 4) if flags else 0.0


# Query parsing --------------------------------------------------------------------------------------------------


async def eval_parse(queries: list[dict], cassette: llm.Cassette) -> dict[str, Any]:
    await query.warm()  # recorded like every call; a cold load would time the first queries out
    per_slot: dict[str, Counts] = {}
    keywords = Counts()
    exact, sources, latencies, llm_latencies, misses = [], Counter(), [], [], []
    for q in queries:
        mark = len(cassette.calls)
        parse = await query.understand(q["q"])
        ms = sum(ms for _, ms in cassette.calls[mark:])  # model time; the rules path makes no call
        predicted = {"keywords": parse.keywords, "filters": parse.filters.model_dump()}
        right = score_parse(predicted, q["parse"], per_slot, keywords)
        exact.append(right)
        sources[parse.source] += 1
        latencies.append(ms)
        if parse.source != "rules":
            llm_latencies.append(ms)
        if not right:
            misses.append({"q": q["q"], "source": parse.source, "got": _filters_text(predicted["filters"]),
                           "want": _filters_text(q["parse"]["filters"])})
    total = Counts(*(sum(getattr(c, f) for c in per_slot.values()) for f in ("tp", "fp", "fn")))
    return {
        "queries": len(queries),
        "exact_match": _share(exact),
        "slot_f1": round(total.f1, 4),
        "slots": {s: {"f1": round(per_slot[s].f1, 4), "tp": per_slot[s].tp, "fp": per_slot[s].fp,
                      "fn": per_slot[s].fn} for s in SLOTS},
        "keyword_f1": round(keywords.f1, 4),
        "fast_path_rate": round(sources["rules"] / len(queries), 4),
        "degraded_rate": round(sources["degraded"] / len(queries), 4),
        "sources": dict(sorted(sources.items())),
        "p50_ms": percentile(latencies, 50), "p95_ms": percentile(latencies, 95),
        "llm_p50_ms": percentile(llm_latencies, 50), "llm_p95_ms": percentile(llm_latencies, 95),
        "misses": misses,
    }


def _filters_text(filters: dict[str, Any]) -> str:
    parts = []
    for key, value in filters.items():
        if value in (None, []):
            continue
        if isinstance(value, dict):
            value = f"{value['system']} {value['value']}"
        parts.append(f"{key}={','.join(value) if isinstance(value, list) else value}")
    return " ".join(parts) or "(none)"


# Search ---------------------------------------------------------------------------------------------------------


def golden_index(mapping: str) -> str:
    return f"evals-golden-{mapping.removeprefix('products_')}"  # products_v2 -> evals-golden-v2


async def build_index(os: Any, products: list[dict], mapping: str) -> str:
    """A throwaway index of every golden product, mapped like `mapping` (a search.TEMPLATES version), with
    documents built by the same
    function the index worker uses. Facets come from the supplier columns (normalize.typed_attributes), then, as
    in production, from the extracted attributes, which here are the gold ones: like the gold categories, search
    is measured as if enrichment were perfect."""
    template, index = search.TEMPLATES[mapping]["template"], golden_index(mapping)
    if await os.indices.exists(index=index):
        await os.indices.delete(index=index)
    await os.indices.create(index=index, body={"settings": template["settings"], "mappings": template["mappings"]})
    vectors = await asyncio.to_thread(embed_passages, [product_text(p["title"], p["brand"], p["description"])
                                                        for p in products])
    lines = []
    for p, vector in zip(products, vectors, strict=True):
        product = Product(id=uuid.UUID(doc_id(p["id"])), supplier_sku=p["id"], title=p["title"],
                          description=p["description"], brand=p["brand"], gtin=None, price_minor=p["price_minor"],
                          currency=p["currency"], updated_at=datetime(2026, 1, 1, tzinfo=UTC),
                          **typed_attributes(p["attributes"]))
        extracted = {k: v for k, v in p["gold"]["attributes"].items() if v != "ABSENT"}
        doc = product_doc(product, p.get("supplier", "golden"), p["gold"]["node_id"], p["gold"]["path"], extracted,
                          vector)
        lines += [json.dumps({"index": {"_index": index, "_id": doc["product_id"]}}), json.dumps(doc)]
    response = await os.bulk(body="\n".join(lines) + "\n", refresh="true")
    if response["errors"]:
        raise SystemExit(f"indexing the golden products failed: {response['items'][:3]}")
    return index


async def put_pipelines(os: Any) -> dict[str, str]:
    # The shipped path (service.search_page) uses production's pipeline; on a fresh OpenSearch, as in CI, nothing
    # else has created it.
    await os.search_pipeline.put(id=search.PIPELINE, body=search.pipeline_body())
    ids = {}
    for n, (name, normalization) in enumerate(NORMALIZATIONS.items()):
        ids[name] = f"evals-hybrid-{n}"
        await os.search_pipeline.put(id=ids[name], body=search.pipeline_body(normalization))
    ids[RRF] = "evals-hybrid-rrf"
    await os.search_pipeline.put(id=ids[RRF], body={
        "description": "reciprocal rank fusion of BM25 and k-NN ranks",
        "phase_results_processors": [{"score-ranker-processor": {"combination": {"technique": "rrf",
                                                                                 "rank_constant": 60}}}],
        "response_processors": [{"hybrid_score_explanation": {}}],
    })
    return ids


def cache_rerank() -> None:
    """Cross-encoder scores per (query, text) are computed once and shared by every pipeline variant: they only
    differ in which products reach the head."""
    scores: dict[tuple[str, str], float] = {}

    def cached(q: str, texts: list[str]) -> list[float]:
        missing = list(dict.fromkeys(t for t in texts if (q, t) not in scores))
        if missing:
            scores.update(zip(((q, t) for t in missing), embeddings.rerank(q, missing), strict=True))
        return [scores[(q, t)] for t in texts]

    search.rerank = cached


async def eval_search(session: Any, corpus: list[dict], queries: list[dict], mapping: str) -> dict[str, Any]:
    os = search.client()
    index = await build_index(os, corpus, mapping)
    pipelines = await put_pipelines(os)
    cache_rerank()
    by_doc = {doc_id(p["id"]): p for p in corpus}
    configs: dict[str, list[list[str]]] = {}
    shipped = "hybrid + rerank + parsed filters (shipped)"

    def add(name: str, ids: list[str]) -> None:
        configs.setdefault(name, []).append(ids)

    for n, q in enumerate(queries, start=1):
        text = q["q"]
        vector = await asyncio.to_thread(embed_query, text)
        for name, body in (("BM25 only", search.lexical_query(text)), ("vector only", search.semantic_query(vector))):
            response = await os.search(index=index, body={"size": TOP, "_source": False, "query": body})
            add(name, [h["_id"] for h in response["hits"]["hits"]])
        for name, pipeline in pipelines.items():
            page = await search.search(os, text, search.Filters(), TOP, None, debug=True, index=index,
                                       pipeline=pipeline)
            head = [h for h in page.hits if h.stage == "head"]
            tail = [h.product_id for h in page.hits if h.stage == "tail"]
            by_hybrid = sorted(head, key=lambda h: (-h.scores["hybrid"], h.product_id))
            add(f"hybrid, {name}", [h.product_id for h in by_hybrid] + tail)
            add(f"hybrid + rerank, {name}", [h.product_id for h in page.hits])
        response, _ = await service.search_page(session, os, text, search.Filters(), TOP, None, parse=True,
                                                index=index)
        add(shipped, [str(item.id) for item in response.items])
        if n % 20 == 0:
            print(f"  search {n}/{len(queries)}", flush=True)

    rows = {}
    for name, ranked_lists in configs.items():
        ndcgs, rrs, zero, judged = [], [], 0, 0
        for q, ids in zip(queries, ranked_lists, strict=True):
            grades = [grade(q, by_doc[i]) for i in ids]
            value = ndcg(grades, [grade(q, p) for p in corpus])
            zero += not ids
            if value is not None:
                judged += 1
                ndcgs.append(value)
                rrs.append(reciprocal_rank(grades))
        rows[name] = {"ndcg10": round(sum(ndcgs) / len(ndcgs), 4), "mrr": round(sum(rrs) / len(rrs), 4),
                      "zero_result_rate": round(zero / len(queries), 4), "judged": judged}
    best = rows[shipped]
    per_query = [{"q": q["q"], "tier": q["tier"],
                  "ndcg10": round(ndcg([grade(q, by_doc[i]) for i in ids], [grade(q, p) for p in corpus]) or 0, 4)}
                 for q, ids in zip(queries, configs[shipped], strict=True)]
    tiers = {t: round(sum(r["ndcg10"] for r in per_query if r["tier"] == t) /
                      max(1, sum(r["tier"] == t for r in per_query)), 4) for t in ("head", "torso", "tail")}
    return {"queries": len(queries), "corpus": len(corpus), "ndcg10": best["ndcg10"], "mrr": best["mrr"],
            "zero_result_rate": best["zero_result_rate"],
            "ndcg10_over_bm25": round(best["ndcg10"] - rows["BM25 only"]["ndcg10"], 4),
            "ndcg10_by_tier": tiers, "ablation": rows,
            "worst": sorted(per_query, key=lambda r: r["ndcg10"])[:10], "per_query": per_query}


def compare_mappings(by_mapping: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Each index version's search numbers side by side, and the queries whose shipped-path nDCG@10 moved
    between the served version (search.INDEX) and each other one."""
    served = by_mapping[search.INDEX]
    out: dict[str, Any] = {"served": search.INDEX, "versions": {}}
    for mapping, r in by_mapping.items():
        out["versions"][mapping] = {
            "ndcg10": r["ndcg10"], "mrr": r["mrr"], "zero_result_rate": r["zero_result_rate"],
            "ndcg10_by_tier": r["ndcg10_by_tier"], "bm25_ndcg10": r["ablation"]["BM25 only"]["ndcg10"],
            "hybrid_rerank_ndcg10": r["ablation"]["hybrid + rerank, min-max (shipped)"]["ndcg10"]}
        if mapping != search.INDEX:
            before = {q["q"]: q["ndcg10"] for q in served["per_query"]}
            out["versions"][mapping]["changed"] = sorted(
                ({"q": q["q"], "tier": q["tier"], "served": before[q["q"]], "this": q["ndcg10"]}
                 for q in r["per_query"] if q["ndcg10"] != before[q["q"]]),
                key=lambda c: c["this"] - c["served"])
    return out


# Latency (live only) --------------------------------------------------------------------------------------------


async def eval_latency(session: Any, queries: list[dict], count: int) -> dict[str, Any]:
    """`count` searches through the API's search path on the catalog, drawn 60/30/10 from head, torso and tail
    queries so popular queries repeat (cache hits after their first parse). Wall time per search, by parse path.
    The cache is cleared for these queries first, so first sightings are real cache misses."""
    llm.stop_cassette()
    settings.query_cache_enabled = True
    rng = random.Random(7)
    tiers = {t: [q["q"] for q in queries if q["tier"] == t] for t in ("head", "torso", "tail")}
    log = [rng.choice(tiers[rng.choices(("head", "torso", "tail"), (60, 30, 10))[0]]) for _ in range(count)]
    await query.cache().delete(*{query._cache_key(query.normalize_query(q)) for q in log})
    await query.warm()
    os = search.client()
    by_path: dict[str, list[float]] = {}
    for n, text in enumerate(log, start=1):
        started = time.perf_counter()
        response, _ = await service.search_page(session, os, text, search.Filters(), 24, None)
        ms = (time.perf_counter() - started) * 1000
        source = response.query_parse.source if response.query_parse else "rules"
        by_path.setdefault(source, []).append(ms)
        if n % 100 == 0:
            print(f"  latency {n}/{count}", flush=True)
    result: dict[str, Any] = {"searches": count, "counts": {s: len(v) for s, v in sorted(by_path.items())}}
    for source, values in sorted(by_path.items()):
        result[f"{source}_p50_ms"] = round(percentile(values, 50))
        result[f"{source}_p95_ms"] = round(percentile(values, 95))
    return result


# Gates, baseline, report ----------------------------------------------------------------------------------------


def lookup(metrics: dict[str, Any], key: str) -> Any:
    value: Any = metrics
    for part in key.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def check_gates(metrics: dict[str, Any]) -> list[dict[str, Any]]:
    results = []
    for key, op, threshold in GATES:
        value = lookup(metrics, key)
        if value is None:
            continue
        passed = value >= threshold if op == ">=" else value <= threshold
        results.append({"metric": key, "value": value, "gate": f"{op} {threshold:g}", "passed": passed})
    return results


def newly_missed(gates: list[dict[str, Any]], baseline: dict[str, Any]) -> list[str]:
    """Gates this run misses that the baseline passed."""
    before = {g["metric"]: g["passed"] for g in check_gates(baseline)}
    return [g["metric"] for g in gates if not g["passed"] and before.get(g["metric"])]


def check_baseline(metrics: dict[str, Any], baseline: dict[str, Any]) -> list[str]:
    """Gated 0-1 quality metrics that got worse than the baseline by more than 1.5 points."""
    drops = []
    for key, op, threshold in GATES:
        value, before = lookup(metrics, key), lookup(baseline, key)
        if value is None or before is None or threshold > 1:
            continue
        worse = before - value if op == ">=" else value - before
        if worse > BASELINE_TOLERANCE:
            drops.append(f"{key}: {before:g} -> {value:g}")
    return drops


def report(result: dict[str, Any]) -> str:
    m = result["metrics"]
    lines = [f"# Shelfsense eval report ({result['split']} split)", "",
             f"{result['mode']} run, {result['finished']}. Enrichment model `{result['models']['enrich']}` "
             f"({result['prompts']['enrich']}), query model `{result['models']['query']}` "
             f"({result['prompts']['query']}), taxonomy {result['taxonomy']}.", "",
             "Written by `evals/run.py`; the numbers are in `evals/results/" + result["split"] + ".json`.", "",
             "## Gates", "", "| Metric | Value | Gate | |", "|---|---:|---|---|"]
    lines += [f"| {g['metric']} | {g['value']:g} | {g['gate']} | {'pass' if g['passed'] else '**miss**'} |"
              for g in result["gates"]]
    if result.get("baseline_drops") is not None:
        lines += ["", "Against the baseline: " + ("; ".join(result["baseline_drops"]) or "no drop over 1.5 points.")]
    if e := m.get("enrichment"):
        lines += ["", f"## Enrichment ({e['products']} products)", "",
                  "| | |", "|---|---:|",
                  *(f"| {k.replace('_', ' ')} | {e[k]:g} |" for k in (
                      "candidate_recall", "leaf_accuracy", "hierarchical_f1", "attribute_macro_f1", "ungrounded_rate",
                      "unnormalized_rate", "none_rate", "error_rate", "schema_validity", "seconds_per_product",
                      "products_per_hour", "tokens_per_second")),
                  "", "Seconds per product is model time (the recorded wall time of its model calls).", "",
                  "| Attribute | Precision | Recall | F1 | TP | FP | FN |", "|---|---:|---:|---:|---:|---:|---:|"]
        lines += [f"| {n} | {a['precision']:.3f} | {a['recall']:.3f} | {a['f1']:.3f} | {a['tp']} | {a['fp']} | {a['fn']} |"
                  for n, a in e["attributes"].items()]
        lines += ["", "| Products | Leaf accuracy |", "|---|---:|"]
        lines += [f"| {t} | {v:.3f} |" for t, v in e["leaf_accuracy_by_type"].items()]
        lines += ["", "Depth-2 confusion (gold → predicted, off-diagonal):", "", "| Gold | Predicted | n |",
                  "|---|---|---:|"]
        lines += [f"| {g} | {p} | {n} |" for g, p, n in e["confusion_depth2"] if g != p]
        lines += ["", "Top confused leaf pairs:", "", "| Gold | Predicted | n |", "|---|---|---:|"]
        lines += [f"| {g} | {p} | {n} |" for g, p, n in e["top_confused"]]
    if p := m.get("parse"):
        lines += ["", f"## Query parsing ({p['queries']} queries)", "",
                  f"Exact match (all filters right) {p['exact_match']:.3f}, slot F1 {p['slot_f1']:.3f}, keyword F1 "
                  f"{p['keyword_f1']:.3f}. Fast path {p['fast_path_rate']:.1%}, degraded {p['degraded_rate']:.1%} "
                  f"({p['sources']}). Model time p50 {p['p50_ms']:g} ms, p95 {p['p95_ms']:g} ms; on the model path "
                  f"p50 {p['llm_p50_ms']:g} ms, p95 {p['llm_p95_ms']:g} ms.", "",
                  "| Slot | F1 | TP | FP | FN |", "|---|---:|---:|---:|---:|"]
        lines += [f"| {s} | {v['f1']:.3f} | {v['tp']} | {v['fp']} | {v['fn']} |" for s, v in p["slots"].items()]
        lines += ["", "Wrong parses:", "", "| Query | Source | Got | Wanted |", "|---|---|---|---|"]
        lines += [f"| {x['q']} | {x['source']} | {x['got']} | {x['want']} |" for x in p["misses"]]
    if s := m.get("search"):
        lines += ["", f"## Search ({s['queries']} queries over {s['corpus']} golden products)", "",
                  f"nDCG@10 by tier: {s['ndcg10_by_tier']}.", "",
                  "| Configuration | nDCG@10 | MRR | Zero results |", "|---|---:|---:|---:|"]
        lines += [f"| {name} | {r['ndcg10']:.4f} | {r['mrr']:.4f} | {r['zero_result_rate']:.1%} |"
                  for name, r in s["ablation"].items()]
        lines += ["", "Lowest nDCG@10 (shipped configuration):", "", "| Query | Tier | nDCG@10 |", "|---|---|---:|"]
        lines += [f"| {w['q']} | {w['tier']} | {w['ndcg10']:.3f} |" for w in s["worst"]]
    if mappings := m.get("search_mappings"):
        lines += ["", f"## Index versions (served: `{mappings['served']}`)", "",
                  "| Version | nDCG@10 (shipped path) | MRR | Zero results | BM25 only | Hybrid + rerank | Head / torso / tail |",
                  "|---|---:|---:|---:|---:|---:|---|"]
        for name, v in mappings["versions"].items():
            tiers = " / ".join(f"{v['ndcg10_by_tier'][t]:.3f}" for t in ("head", "torso", "tail"))
            lines.append(f"| `{name}` | {v['ndcg10']:.4f} | {v['mrr']:.4f} | {v['zero_result_rate']:.1%} | "
                         f"{v['bm25_ndcg10']:.4f} | {v['hybrid_rerank_ndcg10']:.4f} | {tiers} |")
        for name, v in mappings["versions"].items():
            if "changed" in v and not v["changed"]:
                lines += ["", f"No query's nDCG@10 moved on `{name}`."]
            elif "changed" in v:
                lines += ["", f"Queries whose nDCG@10 moved on `{name}` ({len(v['changed'])}):", "",
                          f"| Query | Tier | `{mappings['served']}` | `{name}` |", "|---|---|---:|---:|"]
                lines += [f"| {c['q']} | {c['tier']} | {c['served']:.3f} | {c['this']:.3f} |" for c in v["changed"]]
    if lat := m.get("latency"):
        lines += ["", f"## Search latency ({lat['searches']} searches on the catalog, live)", "",
                  "| Parse path | Searches | p50 ms | p95 ms |", "|---|---:|---:|---:|"]
        lines += [f"| {src} | {n} | {lat[f'{src}_p50_ms']} | {lat[f'{src}_p95_ms']} |"
                  for src, n in lat["counts"].items()]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", choices=("dev", "test"), default="dev")
    parser.add_argument("--live", action="store_true", help="call Ollama and record its replies")
    parser.add_argument("--only", default="enrich,parse,search")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--fail-on", choices=("misses", "regressions"), default="misses",
                        help="regressions: fail only on baseline drops and newly missed gates (needs --baseline)")
    parser.add_argument("--latency-queries", type=int, default=1000)
    args = parser.parse_args()
    sections = set(args.only.split(","))
    products, queries, corpus = load(args.split)
    settings.query_cache_enabled = False  # every parse is the model's own, and recorded

    recording = EVALS / "recordings" / f"{args.split}.jsonl.gz"
    recording.parent.mkdir(exist_ok=True)
    cassette = llm.use_cassette(recording, "record" if args.live else "replay")
    if args.live and recording.exists() and sections & {"enrich", "parse", "search"}:
        archived = EVALS / "archive" / "recordings" / f"{args.split}-{datetime.now(UTC):%Y%m%dT%H%M%S}.jsonl.gz"
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(recording, archived)
        print(f"previous recording kept as {archived.relative_to(EVALS.parent)}")
        if "enrich" in sections and (kept := recording.with_name(f"{args.split}-candidates.json.gz")).exists():
            shutil.copy2(kept, archived.with_name(archived.name.replace(".jsonl.gz", "-candidates.json.gz")))
        # Ask the model again for the sections being run; keep the other model's replies (a partial run).
        asked = ({settings.llm_model} if "enrich" in sections else set()) | (
            {settings.query_model} if sections & {"parse", "search"} else set())
        with gzip.open(recording, "rt", encoding="utf-8") as f:
            cassette.entries = {e["key"]: e for e in map(json.loads, f) if e["model"] not in asked}

    results_path = EVALS / "results" / f"{args.split}.json"
    previous = json.loads(results_path.read_text()) if results_path.exists() else {}
    metrics: dict[str, Any] = {k: v for k, v in previous.get("metrics", {}).items()
                               if k not in sections and not (k == "enrichment" and "enrich" in sections)}
    print(f"{args.split} split: {len(products)} products, {len(queries)} queries "
          f"({'live, recording' if args.live else 'replaying'} {recording.relative_to(EVALS.parent)})", flush=True)
    async with db.SessionLocal() as session:
        try:
            if "enrich" in sections:
                candidates = Candidates(EVALS / "recordings" / f"{args.split}-candidates.json.gz", args.live)
                metrics["enrichment"] = await eval_enrichment(session, products, cassette, args.live, candidates)
            if "parse" in sections:
                metrics["parse"] = await eval_parse(queries, cassette)
            if "search" in sections:
                # Every index version is measured; gates and the baseline read the served one.
                by_mapping = {m: await eval_search(session, corpus, queries, m) for m in search.TEMPLATES}
                metrics["search_mappings"] = compare_mappings(by_mapping)
                metrics["search"] = {k: v for k, v in by_mapping[search.INDEX].items() if k != "per_query"}
        finally:
            if args.live and sections & {"enrich", "parse", "search"}:  # a latency-only run records nothing
                cassette.save()
        if "latency" in sections:
            if not args.live:
                raise SystemExit("latency needs --live: it times real searches against the catalog")
            metrics["latency"] = await eval_latency(session, queries, args.latency_queries)
    await search.client().close()

    result = {
        "split": args.split, "mode": "live" if args.live else "replay", "finished": f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
        "models": {"enrich": settings.llm_model, "query": settings.query_model},
        "prompts": {"enrich": prompts.ENRICH_VERSION, "query": prompts.QUERY_VERSION},
        "taxonomy": settings.taxonomy_version, "metrics": metrics, "gates": check_gates(metrics),
    }
    if args.fail_on == "regressions" and not args.baseline:
        raise SystemExit("--fail-on regressions needs --baseline")
    if args.baseline:
        before = json.loads(args.baseline.read_text())["metrics"]
        result["baseline_drops"] = check_baseline(metrics, before)
        result["newly_missed"] = newly_missed(result["gates"], before)
    results_path.parent.mkdir(exist_ok=True)
    if results_path.exists():  # results are kept, never overwritten (evals/archive/)
        archived = EVALS / "archive" / "results" / f"{args.split}-{previous.get('mode', 'run')}-" \
            f"{datetime.fromtimestamp(results_path.stat().st_mtime, UTC):%Y%m%dT%H%M%S}.json"
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(results_path, archived)
    results_path.write_text(json.dumps(result, indent=2) + "\n")
    report_path = EVALS / ("REPORT.md" if args.split == "dev" else f"REPORT-{args.split}.md")
    report_path.write_text(report(result))
    if args.write_baseline:
        (EVALS / "baseline.json").write_text(json.dumps({"split": args.split, "metrics": metrics}, indent=2) + "\n")
    missed = [g["metric"] for g in result["gates"] if not g["passed"]]
    print(f"wrote {results_path.relative_to(EVALS.parent)} and {report_path.relative_to(EVALS.parent)}")
    print("gates missed: " + (", ".join(missed) or "none"))
    if result.get("baseline_drops"):
        print("baseline drops: " + "; ".join(result["baseline_drops"]))
    if result.get("newly_missed"):
        print("newly missed (passed in the baseline): " + ", ".join(result["newly_missed"]))
    if args.fail_on == "regressions":
        sys.exit(1 if result["baseline_drops"] or result["newly_missed"] else 0)
    sys.exit(1 if missed or result.get("baseline_drops") else 0)


if __name__ == "__main__":
    asyncio.run(main())
