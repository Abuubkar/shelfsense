"""Generate the Grafana dashboards "Shelfsense / Pipeline" and "Shelfsense / Search" (infra/grafana/dashboards/,
docs/adr/0022). Edit the panels here and rerun; Grafana picks the files up within a minute. Never edit the JSON.

    uv run python scripts/make_dashboards.py
"""

import json
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parents[1] / "infra" / "grafana" / "dashboards"
P = {"type": "prometheus", "uid": "prometheus"}


class Board:
    def __init__(self, uid: str, title: str, description: str):
        self.uid, self.title, self.description = uid, title, description
        self.panels: list[dict[str, Any]] = []
        self.y = 0

    def row(self, title: str) -> None:
        self.panels.append({"type": "row", "title": title, "collapsed": False, "panels": [],
                            "gridPos": {"h": 1, "w": 24, "x": 0, "y": self.y}})
        self.y += 1

    def stat(self, title: str, expr: str, unit: str, x: int, w: int = 6, steps: list | None = None, desc: str = "",
             mappings: list | None = None, decimals: int | None = None) -> None:
        defaults: dict[str, Any] = {"unit": unit, "mappings": mappings or [],
                                    "thresholds": {"mode": "absolute", "steps": steps or [{"color": "green", "value": None}]}}
        if decimals is not None:
            defaults["decimals"] = decimals
        self.panels.append({
            "type": "stat", "title": title, "description": desc, "datasource": P,
            "gridPos": {"h": 4, "w": w, "x": x, "y": self.y}, "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "background", "graphMode": "area"},
            "targets": [{"datasource": P, "expr": expr, "refId": "A", "range": True}]})

    def series(self, title: str, targets: list[tuple[str, str]], unit: str = "short", x: int = 0, w: int = 12,
               exemplar: bool = False, threshold: float | None = None, desc: str = "") -> None:
        # Points on every sample and a Last / Max legend: a short run reads as a run, not a single spike.
        defaults: dict[str, Any] = {"unit": unit, "custom": {"lineWidth": 2, "fillOpacity": 10, "showPoints": "always",
                                                            "pointSize": 4}}
        if threshold is not None:
            defaults["thresholds"] = {"mode": "absolute", "steps": [{"color": "green", "value": None},
                                                                    {"color": "red", "value": threshold}]}
            defaults["custom"]["thresholdsStyle"] = {"mode": "line"}
        self.panels.append({
            "type": "timeseries", "title": title, "description": desc, "datasource": P,
            "gridPos": {"h": 9, "w": w, "x": x, "y": self.y}, "fieldConfig": {"defaults": defaults, "overrides": []},
            "options": {"legend": {"displayMode": "table", "placement": "bottom", "calcs": ["lastNotNull", "max"]},
                        "tooltip": {"mode": "multi"}},
            "targets": [{"datasource": P, "expr": expr, "legendFormat": legend, "refId": chr(65 + i),
                         "exemplar": exemplar} for i, (expr, legend) in enumerate(targets)]})

    def next_line(self, h: int) -> None:
        self.y += h

    def write(self) -> None:
        board = {"uid": self.uid, "title": self.title, "description": self.description, "tags": ["shelfsense"],
                 "timezone": "browser", "schemaVersion": 39, "refresh": "30s", "time": {"from": "now-6h", "to": "now"},
                 "panels": self.panels}
        (OUT / f"{self.uid.removeprefix('shelfsense-')}.json").write_text(json.dumps(board, indent=2) + "\n")


def pipeline() -> Board:
    b = Board("shelfsense-pipeline", "Shelfsense / Pipeline",
              "Feed rows to searchable products: enrichment, queues and indexing (docs/slo.md, docs/runbooks/).")
    b.row("Service level")
    b.stat("Fresh within 2 h (1 h)", "1 - shelfsense:freshness_late_ratio:rate1h", "percentunit", 0,
           steps=[{"color": "red", "value": None}, {"color": "orange", "value": 0.9}, {"color": "green", "value": 0.95}],
           desc="Share of products indexed within 2 hours of their last change. SLO: 95% (docs/slo.md).")
    b.stat("Products enriched / hour", "shelfsense:products_enriched_per_hour", "short", 6, decimals=0,
           desc="From the last 15 minutes' rate. Alert: under half the 24-hour average while work is queued.")
    b.stat("Ollama", "max(last_over_time(shelfsense_ollama_up[1m]))", "none", 12,
           steps=[{"color": "red", "value": None}, {"color": "green", "value": 1}],
           mappings=[{"type": "value", "options": {"0": {"text": "down"}, "1": {"text": "up"}}}],
           desc="Does Ollama answer? Alert: down for 2 minutes.")
    b.stat("DLQ depth", 'sum(last_over_time(shelfsense_queue_depth{queue=~".*-dlq"}[1m]))', "short", 18,
           steps=[{"color": "green", "value": None}, {"color": "orange", "value": 1}, {"color": "red", "value": 100}],
           desc="Messages in the dead-letter queues. Alert: over 100.")
    b.next_line(4)
    b.row("Enrichment")
    b.series("Products by outcome", [('sum by (outcome) (rate(shelfsense_enrich_items_total[5m])) * 60', "{{outcome}}")],
             "short", desc="Per minute. transient: resubmitted; permanent: dead-lettered.")
    b.series("Seconds per product", [
        ('histogram_quantile(0.5, sum by (le) (rate(shelfsense_enrich_duration_seconds_bucket[5m])))', "p50"),
        ('histogram_quantile(0.95, sum by (le) (rate(shelfsense_enrich_duration_seconds_bucket[5m])))', "p95")],
        "s", x=12, exemplar=True, desc="Waiting for a model slot included. Exemplars open the product's trace.")
    b.next_line(9)
    b.series("Model calls in flight", [("sum by (model) (shelfsense_llm_inflight)", "{{model}}")], "short",
             desc="Capped by LLM_MAX_CONCURRENCY.")
    b.series("Model tokens", [('sum by (type) (rate(shelfsense_llm_tokens_total[5m]))', "{{type}}")], "short", x=12,
             desc="Per second, input and output.")
    b.next_line(9)
    b.series("Attributes by result", [('sum by (result) (rate(shelfsense_attributes_extracted_total[15m])) * 60', "{{result}}")],
             "short", desc="Ungrounded: the model's value isn't in the listing (ADR 0015). Alert: over 6%.")
    b.series("Ungrounded ratio", [("shelfsense:ungrounded_ratio:rate1h", "ungrounded")], "percentunit", x=12,
             threshold=0.06)
    b.next_line(9)
    b.row("Queues and indexing")
    b.series("Queue depth", [("max by (queue) (last_over_time(shelfsense_queue_depth[1m]))", "{{queue}}")], "short",
             desc="From SQS GetQueueAttributes every 15 s: waiting, in flight and delayed.")
    b.series("Message wait before receive (p95)", [
        ('histogram_quantile(0.95, sum by (le, queue) (rate(shelfsense_queue_message_age_seconds_bucket[5m])))', "{{queue}}")],
        "s", x=12, threshold=21600, desc="Alert: enrich messages waiting over 6 hours.")
    b.next_line(9)
    b.series("Bulk batch size", [
        ('histogram_quantile(0.5, sum by (le) (rate(shelfsense_index_bulk_batch_size_bucket[5m])))', "p50"),
        ('histogram_quantile(0.95, sum by (le) (rate(shelfsense_index_bulk_batch_size_bucket[5m])))', "p95")],
        "short", desc="The adaptive batch size: halves on rejections, grows on success.")
    b.series("Bulk rejections", [('sum by (kind) (rate(shelfsense_index_bulk_rejections_total[5m])) * 60', "{{kind}}")],
             "short", x=12, desc="Per minute. transient: 429/5xx, retried; permanent: mapping errors.")
    b.next_line(9)
    b.series("Catalog freshness", [
        ('histogram_quantile(0.5, sum by (le) (rate(shelfsense_catalog_freshness_seconds_bucket[15m])))', "p50"),
        ('histogram_quantile(0.95, sum by (le) (rate(shelfsense_catalog_freshness_seconds_bucket[15m])))', "p95")],
        "s", threshold=7200, exemplar=True, desc="Last change in Postgres to indexed. SLO: 95% within 2 h.")
    b.series("Feed rows", [('sum by (outcome) (rate(shelfsense_feed_rows_total[15m])) * 60', "{{outcome}}")], "short",
             x=12, desc="Per minute, from committed feeds.")
    b.next_line(9)
    return b


def search() -> Board:
    b = Board("shelfsense-search", "Shelfsense / Search",
              "Search requests by parse path, latency, zero results and errors (docs/slo.md, docs/runbooks/).")
    b.row("Service level")
    b.stat("Fast path p95 (5 m)", "shelfsense:fastpath_p95_seconds:rate5m", "s", 0,
           steps=[{"color": "green", "value": None}, {"color": "red", "value": 0.15}],
           desc="First-page searches the rules parsed (no model call). Alert: over 150 ms for 10 minutes.")
    b.stat("Fast path within 150 ms (1 h)", "1 - shelfsense:fastpath_slow_ratio:rate1h", "percentunit", 6,
           steps=[{"color": "red", "value": None}, {"color": "green", "value": 0.95}], desc="SLO: 95%.")
    b.stat("Availability (1 h)", "1 - shelfsense:search_errors_ratio:rate1h", "percentunit", 12,
           steps=[{"color": "red", "value": None}, {"color": "green", "value": 0.999}],
           desc="API requests that didn't fail with a 5xx, from span metrics. SLO: 99.9%.")
    b.stat("Zero results (5 m)", "shelfsense:zero_result_ratio:rate5m", "percentunit", 18,
           steps=[{"color": "green", "value": None}, {"color": "red", "value": 0.04}], desc="Alert: over 4% for 30 minutes.")
    b.next_line(4)
    b.row("Searches")
    b.series("Latency by parse path (p95)", [
        ('histogram_quantile(0.95, sum by (le, path) (rate(shelfsense_search_duration_seconds_bucket[5m])))', "{{path}}")],
        "s", exemplar=True, threshold=0.15, desc="rules: no model; cache: parse from Redis; llm: the query model; "
                                                 "degraded: the model failed or was too slow. Exemplars open the trace.")
    b.series("Parse source mix", [('sum by (path) (rate(shelfsense_search_requests_total[5m])) * 60', "{{path}}")],
             "short", x=12, desc="First-page searches per minute by how the query was read.")
    b.next_line(9)
    b.series("Searches with no results", [
        ('sum(rate(shelfsense_search_requests_total{results="none"}[5m])) * 60', "zero results")], "short",
        desc="Per minute.")
    b.series("API routes (span metrics)", [
        ('sum by (http_route) (rate(traces_span_metrics_calls_total{service_name="shelfsense-api", span_kind="SPAN_KIND_SERVER"}[5m]))', "{{http_route}}")],
        "reqps", x=12, desc="From every span, before sampling.")
    b.next_line(9)
    b.series("API route p95 (span metrics)", [
        ('histogram_quantile(0.95, sum by (le, http_route) (rate(traces_span_metrics_duration_milliseconds_bucket{service_name="shelfsense-api", span_kind="SPAN_KIND_SERVER"}[5m])))', "{{http_route}}")],
        "ms", desc="Whole request, as the server saw it.")
    b.series("API errors (span metrics)", [
        ('sum by (http_route) (rate(traces_span_metrics_calls_total{service_name="shelfsense-api", span_kind="SPAN_KIND_SERVER", status_code="STATUS_CODE_ERROR"}[5m]))', "{{http_route}}")],
        "reqps", x=12)
    b.next_line(9)
    return b


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for board in (pipeline(), search()):
        board.write()
        print(OUT / f"{board.uid.removeprefix('shelfsense-')}.json")
