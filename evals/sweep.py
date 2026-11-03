"""Model sweep on the dev split: which local model to use for enrichment and for query parsing.

    make sweep                 # replays evals/recordings/sweep-dev-{enrich,parse}.jsonl.gz: no Ollama needed
    make sweep LIVE=1          # asks each model again, recording its replies (~80 min)
    uv run python evals/sweep.py --live --only parse   # re-asks only the query models; enrichment replays

Each enrichment model runs `run.eval_enrichment` and each query model `run.eval_parse`, with the same prompts,
options and golden data as `make eval`; only `settings.llm_model` / `settings.query_model` (and, for one row, the
query time limit) change. Defaults are not changed here: the sweep reports, and the choice is written up
separately.

Each section has its own recording, so a live run of one section replays the other. Memory is what Ollama
reports for the loaded model (`ollama ps`: weights plus the KV cache at our num_ctx), read live after each
model's run with every other model unloaded; a replayed section carries it over from the last results, since a
recording holds replies, not memory. Models are compared on the same items with McNemar's exact test against
the first model of each section (the current default).

Writes evals/results/sweep-dev.json and evals/SWEEP.md; the previous results and recordings are archived.
"""

import argparse
import asyncio
import json
import shutil
from datetime import UTC, datetime
from typing import Any

import ollama
from metrics import mcnemar_p
from run import EVALS, GATES, eval_enrichment, eval_parse, load

from shelfsense_api import db, llm, prompts, search
from shelfsense_api.settings import settings

ENRICH_MODELS = ["qwen2.5:7b-instruct", "llama3.1:8b"]
# (label, model, time limit in seconds; None = production's QUERY_TIMEOUT_S)
QUERY_MODELS = [
    ("qwen2.5:3b-instruct", "qwen2.5:3b-instruct", None),
    ("qwen2.5:7b-instruct", "qwen2.5:7b-instruct", None),
    # The 7B mostly runs past the production limit, which hides its parse quality; this row measures it.
    ("qwen2.5:7b-instruct, no time limit", "qwen2.5:7b-instruct", 30.0),
]
# Named in the plan but not run, with the reason (shown in the report).
SKIPPED = {
    "qwen2.5:14b-instruct": "not run: its 4-bit weights are ~9 GB, and on this 16 GB Mac ~7 GB is free with the "
                            "stack's containers up (Metal's working-set limit is ~10.7 GB), so it would swap and "
                            "its throughput would measure the swap",
}
ENRICH_ROWS = [  # (metric, label, format)
    ("leaf_accuracy", "Leaf accuracy", "{:.3f}"), ("hierarchical_f1", "Hierarchical F1", "{:.3f}"),
    ("candidate_recall", "Candidate recall", "{:.3f}"), ("attribute_macro_f1", "Attribute macro F1", "{:.3f}"),
    ("ungrounded_rate", "Ungrounded", "{:.1%}"), ("schema_validity", "Schema valid first try", "{:.1%}"),
    ("none_rate", "Answered NONE", "{:.1%}"), ("error_rate", "Errors", "{:.1%}"),
    ("seconds_per_product", "Seconds per product", "{:.2f}"), ("products_per_hour", "Products per hour", "{:,}"),
    ("tokens_per_second", "Output tokens/s", "{:.1f}"), ("memory_gb", "Memory (GB)", "{:.1f}"),
]
PARSE_ROWS = [
    ("exact_match", "Exact match", "{:.3f}"), ("slot_f1", "Slot F1", "{:.3f}"), ("keyword_f1", "Keyword F1", "{:.3f}"),
    ("degraded_rate", "Degraded (timeout or invalid)", "{:.1%}"), ("llm_p50_ms", "Model-path p50 ms", "{:,.0f}"),
    ("llm_p95_ms", "Model-path p95 ms", "{:,.0f}"), ("memory_gb", "Memory (GB)", "{:.1f}"),
]


async def unload_all(client: ollama.AsyncClient) -> None:
    for m in (await client.ps()).models:
        await client.generate(model=m.model, keep_alive=0)


async def memory_gb(client: ollama.AsyncClient, model: str) -> float | None:
    loaded = {m.model: m for m in (await client.ps()).models}
    return round(loaded[model].size / 1e9, 1) if model in loaded else None


def paired(wrong: dict[str, set[str]], total: int) -> dict[str, dict[str, Any]]:
    """Each model against the first (the default) on the same items: how many only one of them got right."""
    base, *_ = wrong
    out = {}
    for label, misses in list(wrong.items())[1:]:
        only_base, only_this = len(misses - wrong[base]), len(wrong[base] - misses)
        out[label] = {"against": base, "items": total, "only_base": only_base, "only_this": only_this,
                      "p": round(mcnemar_p(only_base, only_this), 4)}
    return out


def gate_mark(section: str, metric: str, value: Any) -> str:
    for key, op, threshold in GATES:
        if key == f"{section}.{metric}" and value is not None:
            return "" if (value >= threshold if op == ">=" else value <= threshold) else " (miss)"
    return ""


def table(section: str, rows: list[tuple[str, str, str]], results: dict[str, dict[str, Any]]) -> list[str]:
    models = list(results)
    lines = ["| Metric | " + " | ".join(f"`{m}`" for m in models) + " |", "|---|" + "---:|" * len(models)]
    for metric, label, fmt in rows:
        cells = []
        for m in models:
            value = results[m].get(metric)
            cells.append("n/a" if value is None else fmt.format(value) + gate_mark(section, metric, value))
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    return lines


def paired_lines(what: str, comparisons: dict[str, dict[str, Any]]) -> list[str]:
    return [f"- `{label}` vs `{c['against']}`, {what}: {c['only_this']} items only it got right, {c['only_base']} "
            f"only the default did (McNemar exact p = {c['p']:.3f}, over {c['items']} items)."
            for label, c in comparisons.items()]


def report(result: dict[str, Any]) -> str:
    enrich, parse = result["enrichment"], result["parse"]
    lines = ["# Shelfsense model sweep (dev split)", "",
             f"Enrichment {result['modes']['enrich']}, query parsing {result['modes']['parse']}; written "
             f"{result['finished']}. Prompts {result['prompts']['enrich']} and {result['prompts']['query']}, "
             f"taxonomy {result['taxonomy']}. Written by `evals/sweep.py`; the numbers are in "
             "`evals/results/sweep-dev.json`. (miss) marks a value outside its `make eval` gate.", "",
             f"## Enrichment ({next(iter(enrich.values()))['products']} products)", ""]
    lines += table("enrichment", ENRICH_ROWS, enrich)
    lines += [""] + paired_lines("leaf accuracy", result["paired"]["enrichment"])
    types = sorted({t for r in enrich.values() for t in r["leaf_accuracy_by_type"]})
    lines += ["", "Leaf accuracy by product type:", "",
              "| Type | " + " | ".join(f"`{m}`" for m in enrich) + " |", "|---|" + "---:|" * len(enrich)]
    lines += [f"| {t} | " + " | ".join(f"{r['leaf_accuracy_by_type'].get(t, 0):.3f}" for r in enrich.values()) + " |"
              for t in types]
    lines += ["", "Attribute F1:", "", "| Attribute | " + " | ".join(f"`{m}`" for m in enrich) + " |",
              "|---|" + "---:|" * len(enrich)]
    lines += [f"| {a} | " + " | ".join(f"{r['attributes'][a]['f1']:.3f}" for r in enrich.values()) + " |"
              for a in prompts.ATTRIBUTE_NAMES]
    lines += ["", f"## Query parsing ({next(iter(parse.values()))['queries']} queries)", ""]
    lines += table("parse", PARSE_ROWS, parse)
    lines += [""] + paired_lines("exact match", result["paired"]["parse"])
    lines += ["", f"Rows without a time limit in their name run under production's `QUERY_TIMEOUT_S` "
              f"({result['query_timeout_s']} s); a parse past it degrades to keywords.", ""]
    lines += ["## Not run", ""] + [f"- `{m}`: {why}." for m, why in result["skipped"].items()]
    return "\n".join(lines) + "\n"


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true", help="call Ollama and record its replies")
    parser.add_argument("--only", default="enrich,parse", help="with --live, the sections to ask again")
    args = parser.parse_args()
    asked = set(args.only.split(",")) if args.live else set()
    products, queries, _ = load("dev")
    settings.query_cache_enabled = False
    default_enrich, default_query, default_timeout = settings.llm_model, settings.query_model, settings.query_timeout_s

    results_path = EVALS / "results" / "sweep-dev.json"
    previous = json.loads(results_path.read_text()) if results_path.exists() else {}
    stamp = f"{datetime.now(UTC):%Y%m%dT%H%M%S}"
    client = ollama.AsyncClient(host=settings.ollama_host)
    result: dict[str, Any] = {"enrichment": {}, "parse": {}}

    def start(section: str) -> llm.Cassette:
        recording = EVALS / "recordings" / f"sweep-dev-{section}.jsonl.gz"
        if section in asked and recording.exists():
            (EVALS / "archive" / "recordings").mkdir(parents=True, exist_ok=True)
            shutil.copy2(recording, EVALS / "archive" / "recordings" / f"sweep-dev-{section}-{stamp}.jsonl.gz")
        return llm.use_cassette(recording, "record" if section in asked else "replay")

    async def run_model(section: str, key: str, label: str, model: str, cassette: llm.Cassette, evaluate: Any) -> None:
        print(f"{key}: {label}", flush=True)
        if section in asked:
            await unload_all(client)
        try:
            metrics = await evaluate(cassette)
        finally:
            if section in asked:
                cassette.save()
        memory = (await memory_gb(client, model) if section in asked
                  else previous.get(key, {}).get(label, {}).get("memory_gb"))
        result[key][label] = metrics | {"memory_gb": memory}

    async with db.SessionLocal() as session:
        cassette = start("enrich")
        for model in ENRICH_MODELS:
            settings.llm_model = model
            await run_model("enrich", "enrichment", model, model, cassette,
                            lambda c: eval_enrichment(session, products, c, "enrich" in asked))
        settings.llm_model = default_enrich
        cassette = start("parse")
        for label, model, timeout in QUERY_MODELS:
            settings.query_model, settings.query_timeout_s = model, timeout or default_timeout
            await run_model("parse", "parse", label, model, cassette, lambda c: eval_parse(queries, c))
        settings.query_model, settings.query_timeout_s = default_query, default_timeout
        llm.stop_cassette()
    await search.client().close()

    result["paired"] = {
        "enrichment": paired({m: set(r["wrong_leaf"]) for m, r in result["enrichment"].items()}, len(products)),
        "parse": paired({m: {x["q"] for x in r["misses"]} for m, r in result["parse"].items()}, len(queries)),
    }
    result = {"split": "dev", "modes": {s: "live" if s in asked else "replay" for s in ("enrich", "parse")},
              "finished": f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC",
              "prompts": {"enrich": prompts.ENRICH_VERSION, "query": prompts.QUERY_VERSION},
              "taxonomy": settings.taxonomy_version, "query_timeout_s": default_timeout,
              "defaults": {"enrich": default_enrich, "query": default_query}, "skipped": SKIPPED} | result
    if results_path.exists():  # results are kept, never overwritten (evals/archive/)
        (EVALS / "archive" / "results").mkdir(parents=True, exist_ok=True)
        shutil.copy2(results_path, EVALS / "archive" / "results" / f"sweep-dev-{stamp}.json")
    results_path.write_text(json.dumps(result, indent=2) + "\n")
    (EVALS / "SWEEP.md").write_text(report(result))
    print(f"wrote {results_path.relative_to(EVALS.parent)} and evals/SWEEP.md")


if __name__ == "__main__":
    asyncio.run(main())
