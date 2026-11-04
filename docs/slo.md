# Service level objectives

What Shelfsense promises, how each promise is measured, and when it pages. The rules are in
`infra/prometheus/rules.yml` and `infra/prometheus/alerts.yml`; the dashboards are **Shelfsense / Pipeline** and
**Shelfsense / Search** (Grafana, http://localhost:3022 with `docker compose --profile observability up -d`).
Every alert links its runbook in `docs/runbooks/`.

| SLO | Target | SLI (good events / all events) | Error budget (30 days) |
|---|---|---|---|
| Catalog freshness | 95% of products searchable within 2 h of their last change, on the small profile | `shelfsense_catalog_freshness_seconds`: indexed products whose time from `products.updated_at` (set by the feed commit or import) to their bulk index is ≤ 7200 s | 5% of products late |
| Search availability | 99.9% of API requests don't fail | `traces_span_metrics_calls_total` for the API's server spans: not `STATUS_CODE_ERROR` (5xx; a 4xx isn't an error) | 0.1% of requests (~43 min of total outage) |
| Fast-path latency | 95% of first-page fast-path searches within 150 ms | `shelfsense_search_duration_seconds{path="rules"}`: searches the rules parsed (no model call), first pages only, ≤ 0.15 s | 5% of fast-path searches slow |

## Why these

- **Freshness** is the pipeline's promise to sellers: a feed row they commit shows up in search. 2 h on the small
  profile (5,000 products) leaves room for a full enrichment at the measured rate (~630 products/h per Ollama,
  `evals/REPORT.md`) plus indexing. A 200k feed takes longer by design. That's the backlog limit's job
  (`MAX_ENRICH_BACKLOG`, 409 with a retry time), not this SLO's.
- **Availability** counts what a shopper or a client sees: requests that fail. A degraded query parse isn't a
  failure: the search answers with keywords (ADR 0014).
- **Fast-path latency** is the slice 6 gate (p95 ≤ 150 ms) as an objective. CI's perf-smoke checks it on every
  search change (ADR 0020). The model path (target 3 s) and cache hits (180 ms) are watched on the dashboard, not
  budgeted: their volume is too small to budget meaningfully at this traffic.

## Burn-rate alerts

Multiwindow, multi-burn-rate, as in the Google SRE workbook. Each SLO has two alerts, and both windows must agree,
so a short blip doesn't page and a recovered incident stops paging quickly:

| Alert | Burn rate | Long window | Short window | For | Severity | Spends |
|---|---|---|---|---|---|---|
| `…FastBurn` | 14.4× | 1 h | 5 m | 2 m | page | 2% of the 30-day budget in an hour |
| `…SlowBurn` | 6× | 6 h | 30 m | 15 m | ticket | 5% of the budget in 6 hours |

The bad-event ratios are recorded per window as `shelfsense:<sli>_ratio:rate5m|30m|1h|6h`.

## Other alerts

| Alert | Condition | For | Runbook |
|---|---|---|---|
| `DLQDepthHigh` | a DLQ holds > 100 messages | 5 m | dlq-depth |
| `EnrichQueueStale` | enrich messages waited > 6 h before receive, or messages wait and none was received in 6 h | 10 m | enrich-queue-stale |
| `ProductsPerHourLow` | products/hour < 50% of its 24 h average, while work is queued | 30 m | products-per-hour-low |
| `OllamaUnreachable` | the Ollama probe fails | 2 m | ollama-unreachable |
| `UngroundedRateHigh` | > 6% of extracted attributes ungrounded (1 h) | 15 m | ungrounded-rate-high |
| `ZeroResultRateHigh` | > 4% of first-page searches find nothing | 30 m | zero-result-rate-high |
| `FastPathSearchSlow` | fast-path p95 > 150 ms | 10 m | fast-path-slow |

Gauges (queue depth, Ollama up) are read with `last_over_time(…[1m])`: OTLP leaves no staleness marker, so a
stopped process's last value would otherwise linger 5 minutes. Counters are primed at 0 when a process starts,
because Prometheus's OTLP receiver ignores start times and would miss a series' first increment.

## Limits

- SQS's oldest-message age is a CloudWatch metric, not a queue attribute. Queue age is measured when a worker
  receives a message (`SentTimestamp`), so a queue nobody reads is caught by the "none received" condition.
- Traces are tail-sampled at 5% plus every error, DLQ send, degraded parse and search over 1 s. The SLIs come from
  metrics (and span metrics, computed before sampling), so sampling never skews them.
- This is a development setup: one Prometheus, no Alertmanager. Alerts fire in Prometheus
  (http://localhost:9092/alerts); routing them to a pager is a deployment decision.
