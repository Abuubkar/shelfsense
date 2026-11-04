"""uv run python -m shelfsense_worker_index"""

import asyncio
import logging
import signal

from shelfsense_api import aws, db, metrics, queue, search, telemetry
from shelfsense_api.indexing import BatchSizer
from shelfsense_api.settings import settings
from shelfsense_worker_index import make_handler

log = logging.getLogger("shelfsense_worker_index")


async def main() -> None:
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    os = search.client()
    sizer = BatchSizer()
    try:
        async with aws.sqs() as sqs:
            log.info("consuming %s", settings.index_queue)
            depths = metrics.QueueDepths([settings.index_queue, aws.dlq_name(settings.index_queue)])
            poller = asyncio.create_task(depths.poll(sqs))
            try:
                await queue.consume(sqs, settings.index_queue, make_handler(sqs, os, sizer),
                                    concurrency=settings.index_message_concurrency, stop=stop)
            finally:
                poller.cancel()
    finally:
        await os.close()
    log.info("stopped (batch size %d)", sizer.size)


if __name__ == "__main__":
    # Off unless OTEL_EXPORTER_OTLP_ENDPOINT is set (docs/adr/0022); JSON logs either way.
    if telemetry.setup_telemetry("shelfsense-worker-index", sqlalchemy_engines=[db.engine]):
        metrics.prime()
    try:
        asyncio.run(main())
    finally:
        telemetry.flush_telemetry()  # the last spans and metrics, before the process exits
