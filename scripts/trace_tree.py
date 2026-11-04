"""Print a trace from Jaeger as a span tree, with durations, the attributes that matter and span links.

    uv run python scripts/trace_tree.py --product <uuid>    # its enrich trace, then the linked index trace
    uv run python scripts/trace_tree.py --search [--path llm|rules|cache|degraded]   # the latest such search
    uv run python scripts/trace_tree.py --trace <trace id>

Reads Jaeger's v3 query API (http://localhost:16687, JAEGER_URL to change it). Traces are tail-sampled
(infra/otel-collector.yaml): start the collector with TRACE_SAMPLE_PERCENT=100 to find any given product.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from typing import Any

JAEGER = os.environ.get("JAEGER_URL", "http://localhost:16687")
SHOWN = ("shelfsense.product_id", "shelfsense.outcome", "shelfsense.parse_source", "shelfsense.prompt_version",
         "gen_ai.request.model", "gen_ai.usage.input_tokens", "gen_ai.usage.output_tokens",
         "shelfsense.tokens_per_second", "shelfsense.batch_size", "shelfsense.rerank_docs", "shelfsense.total",
         "messaging.destination.name", "messaging.message.id", "shelfsense.receive_count", "error.type",
         "http.route", "db.operation.name")
LABELS = {"gen_ai.request.model": "model", "gen_ai.usage.input_tokens": "in", "gen_ai.usage.output_tokens": "out",
          "messaging.destination.name": "queue", "messaging.message.id": "message", "db.operation.name": "op"}


def get(path: str, **params: str) -> dict[str, Any]:
    url = f"{JAEGER}{path}" + (f"?{urllib.parse.urlencode(params)}" if params else "")
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.load(response)


def spans_of(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Every span of an OTLP-JSON result, each tagged with its service name."""
    out = []
    for resource in result.get("result", {}).get("resourceSpans", []):
        service = next((a["value"].get("stringValue") for a in resource["resource"]["attributes"]
                        if a["key"] == "service.name"), "?")
        for scope in resource.get("scopeSpans", []):
            for span in scope.get("spans", []):
                out.append(span | {"service": service})
    return out


def attrs(span: dict[str, Any]) -> dict[str, Any]:
    return {a["key"]: next(iter(a["value"].values()), None) for a in span.get("attributes", [])}


def find(service: str, operation: str | None, hours: float = 6, **attributes: str) -> list[list[dict[str, Any]]]:
    """Traces of `service` (holding an `operation` span with these attributes, if given), newest first."""
    now = datetime.now(UTC)
    params = {"query.service_name": service, "query.num_traces": "100",
              "query.start_time_min": (now - timedelta(hours=hours)).isoformat().replace("+00:00", "Z"),
              "query.start_time_max": now.isoformat().replace("+00:00", "Z")}
    if operation:
        params["query.operation_name"] = operation
    if attributes:
        params["query.attributes"] = json.dumps(attributes)
    try:
        spans = spans_of(get("/api/v3/traces", **params))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []
        raise
    traces: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        traces.setdefault(span["traceId"], []).append(span)
    return sorted(traces.values(), key=lambda t: -min(int(s["startTimeUnixNano"]) for s in t))


def show(spans: list[dict[str, Any]], focus: str | None = None) -> None:
    """The tree; with `focus` (a product ID), other products' `enrich product` subtrees fold into one count."""
    by_id = {s["spanId"]: s for s in spans}
    children: dict[str, list[dict[str, Any]]] = {}
    for span in spans:
        parent = span.get("parentSpanId") or ""
        children.setdefault(parent if parent in by_id else "", []).append(span)
    print(f"trace {spans[0]['traceId']}")

    def walk(span: dict[str, Any], depth: int) -> None:
        ms = (int(span["endTimeUnixNano"]) - int(span["startTimeUnixNano"])) / 1e6
        a = attrs(span)
        detail = ", ".join(f"{LABELS.get(k, k.split('.')[-1])}={a[k]}" for k in SHOWN if k in a)
        status = " ERROR" if span.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR") else ""
        print(f"{'  ' * depth}{span['name']}  [{span['service']}]  {ms:,.1f} ms{status}" + (f"  ({detail})" if detail else ""))
        for link in span.get("links", []):
            print(f"{'  ' * depth}  -> linked to span {link['spanId']} in trace {link['traceId']}")
        kids = sorted(children.get(span["spanId"], []), key=lambda s: int(s["startTimeUnixNano"]))
        others = [k for k in kids if focus and k["name"] == "enrich product"
                  and attrs(k).get("shelfsense.product_id") != focus]
        for child in kids:
            if child not in others:
                walk(child, depth + 1)
        if others:
            failed = sum(1 for k in others if k.get("status", {}).get("code") in (2, "STATUS_CODE_ERROR"))
            print(f"{'  ' * (depth + 1)}(+ {len(others)} other products in this message, {failed} failed)")

    for root in sorted(children.get("", []), key=lambda s: int(s["startTimeUnixNano"])):
        walk(root, 0)


def product(product_id: str) -> None:
    traces = find("shelfsense-worker-enrich", "enrich product", **{"shelfsense.product_id": product_id})
    if not traces:
        sys.exit(f"no enrich trace for {product_id} in Jaeger (sampled out? TRACE_SAMPLE_PERCENT=100)")
    enrich = spans_of(get(f"/api/v3/traces/{traces[0][0]['traceId']}"))
    show(enrich, focus=product_id)
    # Forward along the link: the index worker's consumer span (named for the queue the send went to) links back
    # to this trace's send span.
    for send in (s for s in enrich if s["name"].startswith("send ")):
        queue = attrs(send).get("messaging.destination.name", "")
        for trace in find("shelfsense-worker-index", f"process {queue}"):
            consumer = next(s for s in trace if s["name"] == f"process {queue}")
            if any(link["spanId"] == send["spanId"] for link in consumer.get("links", [])):
                print()
                show(spans_of(get(f"/api/v3/traces/{consumer['traceId']}")))
                return
    print("\n(no index trace linked to it yet)")


def latest_search(path: str | None) -> None:
    attributes = {"shelfsense.parse_source": path} if path else {}
    traces = find("shelfsense-api", "search", hours=1, **attributes)
    if not traces:
        sys.exit("no matching search trace in the last hour")
    show(spans_of(get(f"/api/v3/traces/{traces[0][0]['traceId']}")))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--product")
    group.add_argument("--search", action="store_true")
    group.add_argument("--trace")
    parser.add_argument("--path")
    args = parser.parse_args()
    for attempt in range(3):  # a just-finished trace waits out the collector's sampling decision
        try:
            if args.product:
                product(args.product)
            elif args.search:
                latest_search(args.path)
            else:
                show(spans_of(get(f"/api/v3/traces/{args.trace}")))
            break
        except urllib.error.URLError as exc:
            if attempt == 2:
                sys.exit(f"Jaeger at {JAEGER} didn't answer: {exc}")
            time.sleep(2)
