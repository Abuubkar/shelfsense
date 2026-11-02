"""Create the feeds bucket and the work queues with their dead-letter queues. Safe to rerun.

    uv run python scripts/init_aws.py
"""

import asyncio

from shelfsense_api import aws
from shelfsense_api.settings import settings


async def main() -> None:
    async with aws.sqs() as sqs, aws.s3() as s3:
        await aws.ensure_resources(sqs, s3)
        for queue in (settings.enrich_queue, settings.index_queue):
            print(f"{queue}: {await aws.queue_url(sqs, queue)}  ->  {aws.dlq_name(queue)} after "
                  f"{aws.MAX_RECEIVE_COUNT} receives")
    print(f"bucket: {settings.feeds_bucket}")


if __name__ == "__main__":
    asyncio.run(main())
