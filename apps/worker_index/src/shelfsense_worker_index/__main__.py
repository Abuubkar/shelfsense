"""uv run python -m shelfsense_worker_index"""

import asyncio
import logging
import signal

from shelfsense_api import aws, queue, search
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
            await queue.consume(sqs, settings.index_queue, make_handler(sqs, os, sizer),
                                concurrency=settings.index_message_concurrency, stop=stop)
    finally:
        await os.close()
    log.info("stopped (batch size %d)", sizer.size)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    asyncio.run(main())
