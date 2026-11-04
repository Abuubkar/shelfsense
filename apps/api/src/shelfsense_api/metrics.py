"""Every Shelfsense metric, defined here and nowhere else (docs/adr/0022). Without telemetry set up they're no-op
instruments, so recording costs nothing in tests and scripts.

Prometheus names: the collector turns `shelfsense.enrich.items` (unit "{product}") into
`shelfsense_enrich_items_total`, and a histogram in seconds into `..._seconds_bucket`/`_sum`/`_count`.
Counters are primed at 0 per label set when a process starts (`prime`): Prometheus's OTLP receiver ignores start
times, so a series' first increment would otherwise never show in rate() or increase().
"""

import asyncio
import logging
import time
from typing import Any

from opentelemetry import metrics
from opentelemetry.instrumentation.utils import suppress_instrumentation
from opentelemetry.metrics import CallbackOptions, Observation

log = logging.getLogger(__name__)
_meter = metrics.get_meter("shelfsense")

# Pipeline.
feed_rows = _meter.create_counter("shelfsense.feed.rows", "{row}", "Feed rows imported, by outcome")
enrich_items = _meter.create_counter("shelfsense.enrich.items", "{product}",
                                     "Products through enrichment, by outcome (done, transient, permanent)")
llm_inflight = _meter.create_up_down_counter("shelfsense.llm.inflight", "{call}", "Model calls in progress")
enrich_seconds = _meter.create_histogram("shelfsense.enrich.duration", "s", "Seconds to enrich one product",
                                         explicit_bucket_boundaries_advisory=[0.5, 1, 2, 4, 8, 15, 30, 60, 120])
llm_tokens = _meter.create_counter("shelfsense.llm.tokens", "{token}", "Model tokens, by type and model")
attributes_extracted = _meter.create_counter("shelfsense.attributes.extracted", "{attribute}",
                                             "Attributes the model proposed, by result (grounded, ungrounded, "
                                             "unnormalized)")
queue_message_age = _meter.create_histogram("shelfsense.queue.message_age", "s",
                                            "How long a message waited in its queue before this receive",
                                            explicit_bucket_boundaries_advisory=[1, 10, 60, 300, 900, 3600, 21600])
bulk_batch_size = _meter.create_histogram("shelfsense.index.bulk_batch_size", "{doc}",
                                          "Documents per _bulk request (the adaptive batch size at work)",
                                          explicit_bucket_boundaries_advisory=[50, 100, 250, 500, 1000, 2000])
bulk_rejections = _meter.create_counter("shelfsense.index.bulk_rejections", "{doc}",
                                        "Bulk items OpenSearch rejected, by kind (transient, permanent)")
freshness_seconds = _meter.create_histogram("shelfsense.catalog.freshness", "s",
                                            "Seconds from a product's last change in Postgres to being indexed",
                                            explicit_bucket_boundaries_advisory=[10, 60, 300, 900, 1800, 3600,
                                                                                 7200, 14400])
# Search.
search_seconds = _meter.create_histogram("shelfsense.search.duration", "s",
                                         "Seconds per search request, by parse path (rules, cache, llm, degraded)",
                                         explicit_bucket_boundaries_advisory=[0.025, 0.05, 0.1, 0.15, 0.25, 0.5, 1,
                                                                              2, 3, 5])
searches = _meter.create_counter("shelfsense.search.requests", "{search}",
                                 "Searches, by parse path and whether they found anything")

_COUNTERS: list[tuple[Any, list[dict[str, str]]]] = [
    (feed_rows, [{"outcome": o} for o in ("accepted", "rejected")]),
    (enrich_items, [{"outcome": o} for o in ("done", "transient", "permanent")]),
    (attributes_extracted, [{"result": r} for r in ("grounded", "ungrounded", "unnormalized")]),
    (bulk_rejections, [{"kind": k} for k in ("transient", "permanent")]),
    (searches, [{"path": p, "results": r} for p in ("rules", "cache", "llm", "degraded", "unparsed")
                for r in ("some", "none")]),
]


def prime() -> None:
    """Every counter's label sets at 0, once per process (see the module docstring)."""
    for counter, label_sets in _COUNTERS:
        for labels in label_sets:
            counter.add(0, labels)


class QueueDepths:
    """Queue and DLQ depth as observable gauges, read from SQS GetQueueAttributes. A gauge callback can't await, so
    `poll` refreshes the numbers in the background and the callback reports the latest ones."""

    def __init__(self, queues: list[str]):
        self.queues = queues
        self.depths: dict[str, int] = {}
        _meter.create_observable_gauge("shelfsense.queue.depth", [self._observe], "{message}",
                                       "Messages a queue holds (waiting, in flight, delayed)")

    def _observe(self, _: CallbackOptions) -> list[Observation]:
        return [Observation(depth, {"queue": queue}) for queue, depth in self.depths.items()]

    async def poll(self, sqs: Any, every_s: float = 15) -> None:
        from shelfsense_api import aws
        while True:
            for queue in self.queues:
                try:
                    with suppress_instrumentation():  # a span every 15 s per queue would only be noise
                        self.depths[queue] = await aws.queue_depth(sqs, queue)
                except Exception as exc:  # a missed reading isn't fatal; the gauge keeps the last one
                    log.warning("queue depth for %s failed: %r", queue, exc)
            await asyncio.sleep(every_s)


class OllamaUp:
    """1 while Ollama answers, 0 when it doesn't (the alert's "unreachable for 2m"), probed in the background."""

    def __init__(self) -> None:
        self.up, self.checked = 0, 0.0
        _meter.create_observable_gauge("shelfsense.ollama.up", [self._observe], "", "Whether Ollama answers (1 or 0)")

    def _observe(self, _: CallbackOptions) -> list[Observation]:
        return [Observation(self.up)]

    async def poll(self, every_s: float = 15) -> None:
        import httpx

        from shelfsense_api.settings import settings
        async with httpx.AsyncClient(timeout=5) as http:
            while True:
                try:
                    with suppress_instrumentation():
                        self.up = int((await http.get(f"{settings.ollama_host}/api/version")).status_code == 200)
                except httpx.HTTPError:
                    self.up = 0
                self.checked = time.time()
                await asyncio.sleep(every_s)
