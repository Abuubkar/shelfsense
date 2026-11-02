"""SQS and S3 through aioboto3: clients, queue URLs and ARNs, and creating the bucket and queues.

Locally the endpoint is Floci (docs/adr/0008); set AWS_ENDPOINT_URL empty to use real AWS.
"""

import json
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from shelfsense_api.settings import settings

# SQS moves a message to its queue's DLQ after this many receives without a delete: the backstop for crashes and
# poison messages. Handled failures are dead-lettered explicitly, long before this.
MAX_RECEIVE_COUNT = 5
DLQ_RETENTION_S = 14 * 24 * 3600  # SQS's maximum

_session = aioboto3.Session()
_queue_urls: dict[tuple[str | None, str], str] = {}


def _client_kwargs() -> dict[str, Any]:
    return {
        "endpoint_url": settings.aws_endpoint_url or None,
        "region_name": settings.aws_region,
        "aws_access_key_id": settings.aws_access_key_id,
        "aws_secret_access_key": settings.aws_secret_access_key,
    }


def sqs() -> Any:
    """An SQS client; use as `async with aws.sqs() as sqs:`."""
    return _session.client("sqs", **_client_kwargs())


def s3() -> Any:
    """An S3 client; use as `async with aws.s3() as s3:`. SigV4 like current AWS regions require, and path-style
    URLs, since a local endpoint has no per-bucket DNS names."""
    config = Config(signature_version="s3v4", s3={"addressing_style": "path"})
    return _session.client("s3", config=config, **_client_kwargs())


def dlq_name(queue: str) -> str:
    return f"{queue}-dlq"  # SQS names allow letters, digits, - and _ only: "enrich.dlq" is rejected


async def queue_url(sqs: Any, queue: str) -> str:
    key = (settings.aws_endpoint_url, queue)
    if key not in _queue_urls:
        _queue_urls[key] = (await sqs.get_queue_url(QueueName=queue))["QueueUrl"]
    return _queue_urls[key]


async def queue_arn(sqs: Any, queue: str) -> str:
    attrs = await sqs.get_queue_attributes(QueueUrl=await queue_url(sqs, queue), AttributeNames=["QueueArn"])
    return attrs["Attributes"]["QueueArn"]


async def queue_depth(sqs: Any, queue: str) -> int:
    """Messages waiting, in flight, or delayed: all work the queue still holds (approximate, as SQS counts)."""
    names = ["ApproximateNumberOfMessages", "ApproximateNumberOfMessagesNotVisible",
             "ApproximateNumberOfMessagesDelayed"]
    attrs = await sqs.get_queue_attributes(QueueUrl=await queue_url(sqs, queue), AttributeNames=names)
    return sum(int(attrs["Attributes"].get(n, 0)) for n in names)


async def send(sqs: Any, queue: str, bodies: list[str], delay_s: int = 0) -> None:
    """Send messages in batches of 10 (SQS's limit), failing if any entry is refused."""
    url = await queue_url(sqs, queue)
    for start in range(0, len(bodies), 10):
        entries = [{"Id": str(i), "MessageBody": body, "DelaySeconds": delay_s}
                   for i, body in enumerate(bodies[start:start + 10])]
        response = await sqs.send_message_batch(QueueUrl=url, Entries=entries)
        if response.get("Failed"):
            raise RuntimeError(f"SQS refused {len(response['Failed'])} messages: {response['Failed'][0]}")


async def ensure_resources(sqs: Any, s3: Any) -> None:
    """The feeds bucket, and each work queue with its dead-letter queue and redrive policy. Safe to rerun."""
    try:
        await s3.create_bucket(Bucket=settings.feeds_bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    for queue in (settings.enrich_queue, settings.index_queue):
        dlq = await sqs.create_queue(QueueName=dlq_name(queue))
        await sqs.set_queue_attributes(QueueUrl=dlq["QueueUrl"],
                                       Attributes={"MessageRetentionPeriod": str(DLQ_RETENTION_S)})
        dlq_arn = await queue_arn(sqs, dlq_name(queue))
        source = await sqs.create_queue(QueueName=queue)
        # Set separately so a rerun updates a queue that already exists instead of failing on changed attributes.
        await sqs.set_queue_attributes(QueueUrl=source["QueueUrl"], Attributes={
            "VisibilityTimeout": str(settings.queue_visibility_timeout_s),
            "RedrivePolicy": json.dumps({"deadLetterTargetArn": dlq_arn, "maxReceiveCount": str(MAX_RECEIVE_COUNT)}),
        })
