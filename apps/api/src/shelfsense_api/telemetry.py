"""One telemetry setup for every Shelfsense process (API, both workers, scripts that want it): traces, metrics and
logs over OTLP to the OpenTelemetry Collector (docs/adr/0022), the libraries we use instrumented automatically,
and log lines as JSON carrying the current trace and span ids.

Telemetry is off unless OTEL_EXPORTER_OTLP_ENDPOINT is set: tracing calls then cost next to nothing, and nothing
tries to reach a collector that isn't running (tests, evals, CI).

Seller data and shopper queries never leave the process as text. Every span passes `HashingSpanProcessor` before
export: attributes that can carry product text, query text or prompts are replaced by a short hash (equal inputs
still match across spans), and URL query strings are hashed whole.
"""

import hashlib
import logging
import os
import socket
from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any

import structlog
from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import Event, ReadableSpan, Span, SpanProcessor, TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

log = logging.getLogger("shelfsense.telemetry")

# Attributes that can carry product text (titles, descriptions, supplier values), shopper query text, prompts or
# model answers. Whole keys, or DENIED_PARTS anywhere in a key. Exception messages too: a validation error repeats
# the model's reply, and shelfsense.error_code says what failed without it.
DENIED_KEYS = frozenset({
    "gen_ai.input.messages", "gen_ai.output.messages", "gen_ai.system_instructions", "gen_ai.tool.definitions",
    "exception.message", "exception.stacktrace", "url.query", "url.full", "http.url", "http.target",
    "db.statement", "db.query.text",
})
DENIED_PARTS = ("query", "title", "description", "text", "content", "body", "prompt", "keywords")
# Keys that contain a denied part but hold no seller or shopper text. SQL statements are kept for Postgres only
# (_clean): every query binds its values as parameters, so the statement holds none of them.
ALLOWED_KEYS = frozenset({"shelfsense.prompt_version", "shelfsense.parse_source", "shelfsense.query_hash",
                          "shelfsense.query_words", "db.query.summary"})


def fingerprint(value: Any) -> str:
    """A short stable hash: the same query or title gives the same value in every span, and can't be read back."""
    return "sha256:" + hashlib.sha256(str(value).encode()).hexdigest()[:16]


def denied(key: str) -> bool:
    if key in ALLOWED_KEYS:
        return False
    lowered = key.lower()
    return key in DENIED_KEYS or any(part in lowered for part in DENIED_PARTS)


def _clean(attributes: Mapping[str, Any] | None) -> dict[str, Any]:
    attributes = dict(attributes or {})
    sql = attributes.get("db.system.name", attributes.get("db.system")) == "postgresql"
    out = {}
    for key, value in attributes.items():
        if sql and key in ("db.statement", "db.query.text"):
            out[key] = value
        elif denied(key):
            out[key] = fingerprint(value)
        else:
            out[key] = value
    return out


class HashingSpanProcessor(SpanProcessor):
    """Replaces denylisted attributes (on the span and its events) with hashes before the span reaches the
    exporter. A finished span is read-only, so the exporter gets a cleaned copy."""

    def __init__(self, inner: SpanProcessor):
        self.inner = inner

    def on_start(self, span: Span, parent_context: Context | None = None) -> None:
        self.inner.on_start(span, parent_context)

    def on_end(self, span: ReadableSpan) -> None:
        events = [Event(e.name, _clean(e.attributes), e.timestamp) for e in span.events]
        self.inner.on_end(ReadableSpan(
            name=span.name, context=span.context, parent=span.parent, resource=span.resource,
            attributes=_clean(span.attributes), events=events, links=span.links, kind=span.kind, status=span.status,
            start_time=span.start_time, end_time=span.end_time, instrumentation_scope=span.instrumentation_scope,
        ))

    def shutdown(self) -> None:
        self.inner.shutdown()

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return self.inner.force_flush(timeout_millis)


def _trace_ids(_logger: Any, _method: str, event: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """structlog processor: the current trace and span ids on every log line, so Loki links a line to its trace."""
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event["trace_id"], event["span_id"] = format(context.trace_id, "032x"), format(context.span_id, "016x")
    return event


def setup_logging(level: int = logging.INFO) -> None:
    """Every stdlib log record (ours and the libraries') as one JSON line on stderr, with trace ids inside a span."""
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[structlog.stdlib.add_log_level, structlog.stdlib.add_logger_name,
                           structlog.processors.TimeStamper(fmt="iso", utc=True), _trace_ids],
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, structlog.processors.format_exc_info,
                    structlog.processors.JSONRenderer()],
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [h for h in root.handlers if not isinstance(h, logging.StreamHandler)] + [handler]
    root.setLevel(level)
    # httpx and opensearch-py log every request at INFO, URL included (each model call, each search): noise, and a
    # URL can carry a query string. Their warnings and errors still come through.
    for name in ("httpx", "opensearch"):
        logging.getLogger(name).setLevel(logging.WARNING)


def setup_telemetry(service_name: str, *, fastapi_app: Any = None, sqlalchemy_engines: Iterable[Any] = ()) -> bool:
    """Start telemetry for this process; returns False (and only sets up JSON logging) when no OTLP endpoint is
    configured. Call it once, before work starts. Engines created before the call are passed in."""
    setup_logging()
    if not os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT"):
        return False
    from opentelemetry._logs import set_logger_provider
    from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.botocore import AiobotocoreInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    resource = Resource.create({
        "service.name": service_name,
        # One per process (Prometheus's `instance` label): host and pid, readable where the SDK's default is a uuid.
        "service.instance.id": f"{socket.gethostname()}-{os.getpid()}",
        "service.version": os.environ.get("SHELFSENSE_VERSION", "dev"),
        "deployment.environment.name": os.environ.get("DEPLOYMENT_ENVIRONMENT", "development"),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(HashingSpanProcessor(BatchSpanProcessor(OTLPSpanExporter())))
    trace.set_tracer_provider(provider)
    # Metrics every 15 s. Histograms keep exemplars (a trace id per bucket) from sampled spans: the SDK's default.
    metrics.set_meter_provider(MeterProvider(resource=resource, metric_readers=[
        PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=15_000)]))
    # Log records through the collector to Loki, carrying the trace context of the span they're written in.
    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))
    set_logger_provider(logger_provider)
    logging.getLogger().addHandler(LoggingHandler(level=logging.INFO, logger_provider=logger_provider))

    engines = [e.sync_engine if hasattr(e, "sync_engine") else e for e in sqlalchemy_engines]
    # 0.66b2 declares sqlalchemy < 2.1 and would silently do nothing on 2.1; the engine events it hooks are the
    # same in 2.1 (its spans show in the trace trees in docs/slo.md).
    SQLAlchemyInstrumentor().instrument(engines=engines, skip_dep_check=True)
    HTTPXClientInstrumentor().instrument()  # Ollama's client
    AioHttpClientInstrumentor().instrument()  # opensearch-py's transport
    RedisInstrumentor().instrument()
    AiobotocoreInstrumentor().instrument()  # SQS and S3 (aioboto3; BotocoreInstrumentor covers sync botocore only)
    if fastapi_app is not None:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        # No spans for each ASGI receive/send chunk: noise next to the request span.
        FastAPIInstrumentor.instrument_app(fastapi_app, exclude_spans=["receive", "send"])
    log.info("telemetry on: %s -> %s", service_name, os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"])
    return True


def flush_telemetry() -> None:
    """Send whatever is buffered now, for a process about to exit."""
    from opentelemetry._logs import get_logger_provider
    for provider in (trace.get_tracer_provider(), metrics.get_meter_provider(), get_logger_provider()):
        if hasattr(provider, "force_flush"):
            provider.force_flush()
