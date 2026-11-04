"""uv run python -m shelfsense_worker_enrich"""

import asyncio
import logging
import signal

from shelfsense_api import aws, db, metrics, queue, telemetry
from shelfsense_api.settings import settings
from shelfsense_worker_enrich import make_handler

log = logging.getLogger("shelfsense_worker_enrich")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    llm_slots = asyncio.Semaphore(settings.llm_max_concurrency)
    async with aws.sqs() as sqs:
        log.info("consuming %s, %d model calls at a time", settings.enrich_queue, settings.llm_max_concurrency)
        # Gauges: this queue's depth and its DLQ's, and whether Ollama answers (the alerts read them).
        depths = metrics.QueueDepths([settings.enrich_queue, aws.dlq_name(settings.enrich_queue)])
        pollers = [asyncio.create_task(depths.poll(sqs)), asyncio.create_task(metrics.OllamaUp().poll())]
        try:
            # Stop taking messages while every model slot is busy: a message waiting for a slot only burns its
            # timeout.
            await queue.consume(sqs, settings.enrich_queue, make_handler(sqs, llm_slots),
                                concurrency=settings.enrich_message_concurrency, stop=stop,
                                should_receive=lambda: not llm_slots.locked())
        finally:
            for poller in pollers:
                poller.cancel()
    log.info("stopped")


if __name__ == "__main__":
    # Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (docs/adr/0022); JSON logs either way.
    if telemetry.setup_telemetry("shelfsense-worker-enrich", sqlalchemy_engines=[db.engine]):
        metrics.prime()
    try:
        asyncio.run(main())
    finally:
        telemetry.flush_telemetry()  # the last spans and metrics, before the process exits
