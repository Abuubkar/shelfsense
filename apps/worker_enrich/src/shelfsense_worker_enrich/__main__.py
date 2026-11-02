"""uv run python -m shelfsense_worker_enrich"""

import asyncio
import logging
import signal

from shelfsense_api import aws, queue
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
        # Stop taking messages while every model slot is busy: a message waiting for a slot only burns its timeout.
        await queue.consume(sqs, settings.enrich_queue, make_handler(sqs, llm_slots),
                            concurrency=settings.enrich_message_concurrency, stop=stop,
                            should_receive=lambda: not llm_slots.locked())
    log.info("stopped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
