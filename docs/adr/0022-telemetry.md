---
status: accepted
date: 2026-11-04
---

# Telemetry: OpenTelemetry from feed row to search, with seller and shopper text hashed

**Chosen.** Every process calls `telemetry.setup_telemetry` once: the API, both workers, and any script that
wants it. It's off unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set, so tests, evals and CI pay nothing. When on, it
sends traces, metrics and logs over OTLP to an OpenTelemetry Collector. The collector tail-samples traces into
Jaeger, writes metrics to Prometheus (its OTLP receiver), and sends logs to Loki. Grafana shows two dashboards
built by `scripts/make_dashboards.py`. Objectives and alerts are in docs/slo.md; runbooks are in docs/runbooks/.

- **Auto-instrumented:**
  - FastAPI;
  - SQLAlchemy (0.66b2 doesn't declare SQLAlchemy 2.1, so `skip_dep_check`; its spans appear);
  - Redis;
  - httpx (Ollama's client);
  - aiohttp (opensearch-py's transport);
  - aiobotocore, for SQS and S3: `AiobotocoreInstrumentor`, since `BotocoreInstrumentor` covers only sync botocore.

  opensearch-py has no maintained instrumentation, so search stages get manual spans (`opensearch hybrid`,
  `tail`, `facets`, `bulk`), with the aiohttp spans beneath them.
- **SQS propagation is ours.** The botocore SQS extension records the queue and message ID, but it doesn't
  inject or extract trace context (checked in its source). `aws.send` opens a producer span and writes its W3C
  `traceparent` into each message's attributes. `queue._process` starts a consumer span as a **new trace linked
  to the producer**, not a child of it: a message can wait hours, and a child would stretch the feed commit's
  trace across them. The consumer span records the queue, message ID and receive count, plus how long the message
  waited (`SentTimestamp`). Each product of an enrich message gets its own span, with its model call beneath it,
  so one slow or failing product stands out in a message of 50.
- **Model spans** are `chat <model>` (client kind). They follow the GenAI semantic conventions:
  - the conventions now live in their own repository (open-telemetry/semantic-conventions-genai), still at
    Development status;
  - attributes: `gen_ai.operation.name`, `gen_ai.provider.name=ollama` (plus `gen_ai.system`, the attribute's
    name before it was renamed), request and response models, `gen_ai.usage.input_tokens` and `output_tokens`;
  - stable attributes such as `error.type` and `server.address` follow semantic conventions v1.45.0;
  - ours: `shelfsense.tokens_per_second`, `shelfsense.prompt_version` and, on the query path,
    `shelfsense.parse_source`.
- **No seller or shopper text leaves the process.** `HashingSpanProcessor` hands the exporter a copy of each span
  with denylisted attributes replaced by a short sha256: equal inputs give equal hashes across spans, and the text
  can't be read back. It hashes:
  - keys naming product or query text (title, description, query, keywords, prompt, …);
  - URL query strings (FastAPI's `url.query`/`http.target`, which hold `?q=`);
  - Redis commands (a cached parse holds the query's keywords);
  - exception messages (a validation error repeats the model's reply).

  Postgres SQL is kept: values are bound parameters. The query-degraded log line hashes the query too. A unit test
  pins all of this.
- **Metrics** are defined only in `shelfsense_api/metrics.py`. Counters are primed at 0 per label set when a
  process starts, because Prometheus's OTLP receiver ignores start times and would miss a series' first increment.
  Queue and DLQ depth come from GetQueueAttributes and Ollama up/down from a probe, both polled in the workers with
  instrumentation suppressed (a span every 15 s is noise). Histograms carry exemplars.
- **Collector:**
  - Every span goes to the `span_metrics` connector, so per-route rate, errors and duration stay complete.
  - A second pipeline tail-samples into Jaeger. It keeps errors, DLQ sends (`shelfsense.dlq`), degraded parses,
    searches over 1 s, and 5% of the rest (`TRACE_SAMPLE_PERCENT`; 100 when you need any given product's trace).
- **Services** run behind the compose `observability` profile, on ports that don't clash with Ledgerline's stack
  on the same machine: collector 4328, Jaeger 16687, Prometheus 9092, Grafana 3022.

## Alternatives

- **The consumer span as a child of the producer:** one trace per product end to end, but traces hours long
  whenever a queue backs up. Each would hold every retry's delay, and tail sampling would have to wait out the
  longest. Links keep traces short; `scripts/trace_tree.py --product` follows them.
- **Dropping denylisted attributes, as Ledgerline does:** simpler, but a hash still answers "is this the same
  query?" across spans and searches without exposing it. The plan asked for hashes.
- **Scraping Prometheus endpoints in each process:** one more port per worker, and no exemplar or log
  correlation. OTLP to one collector carries all three signals.
- **Head sampling in the SDK:** cheaper, but it decides before a span knows it'll fail. Tail sampling keeps every
  error and DLQ send.
- **A GenAI instrumentation library for Ollama:** none is maintained for the `ollama` client at a stable version.
  Our one `_call` is the only model call site, so the span is a few lines.

## Assumptions

- Processes that exit cleanly flush their telemetry (`flush_telemetry`). A SIGKILLed worker loses its last
  export: the chaos run's enrich counters read 1,870 done against 1,976 enriched.
- SQS's oldest-message age isn't a queue attribute, so queue age is measured when a message is received. A queue
  nobody reads is caught by the alert's "none received" condition (docs/slo.md).
- The GenAI conventions are still at Development status: attribute names may change again. They're set in one
  function (`llm._call`).
