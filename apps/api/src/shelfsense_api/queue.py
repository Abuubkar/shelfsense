"""The one SQS consumer loop both workers run, and the failure rules they share.

A handler gets a message body and returns normally (the message is deleted), raises PermanentError (the message
is dead-lettered with its reason, then deleted), or raises anything else (the message is hidden for a backoff
delay and retried; after aws.MAX_RECEIVE_COUNT receives SQS moves it to the DLQ itself). While a handler runs, a
heartbeat keeps extending the message's visibility timeout, so a slow handler isn't mistaken for a dead one.

Handlers that process several products per message decide per product (plan_followups): finished products are
passed on, transient failures are resubmitted in a new message with attempt + 1, and the rest are dead-lettered
one product at a time. So one bad product never fails its batch.
"""

import asyncio
import logging
import random
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass, field
from typing import Any, Literal

from opentelemetry import propagate, trace
from opentelemetry.trace import Link, SpanKind, Status, StatusCode
from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from shelfsense_api import aws, db, metrics
from shelfsense_api.db import DeadLetter
from shelfsense_api.settings import settings

log = logging.getLogger(__name__)
_tracer = trace.get_tracer(__name__)

Handler = Callable[[str, int], Awaitable[None]]


class TransientError(Exception):
    """Worth retrying later: a dependency is down or overloaded."""


class PermanentError(Exception):
    """Retrying won't help: the message (or product) goes to the dead-letter queue with this code."""

    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class Outcome:
    """What happened to one product of a message."""

    product_id: uuid.UUID
    status: Literal["done", "transient", "permanent"]
    error_code: str | None = None
    detail: str = ""


@dataclass
class Followups:
    done: list[uuid.UUID] = field(default_factory=list)
    retry: list[uuid.UUID] = field(default_factory=list)
    dead: list[Outcome] = field(default_factory=list)


def plan_followups(outcomes: list[Outcome], attempt: int, max_attempts: int) -> Followups:
    """Sort a message's per-product outcomes: transient failures are retried in a new message until `attempt`
    reaches `max_attempts`, after which they're dead-lettered like permanent ones."""
    plan = Followups()
    for outcome in outcomes:
        if outcome.status == "done":
            plan.done.append(outcome.product_id)
        elif outcome.status == "transient" and attempt < max_attempts:
            plan.retry.append(outcome.product_id)
        elif outcome.status == "transient":
            plan.dead.append(Outcome(outcome.product_id, "permanent", outcome.error_code,
                                     f"still failing after {attempt} attempts: {outcome.detail}"))
        else:
            plan.dead.append(outcome)
    return plan


def backoff_s(attempt: int, base: float = 2.0, cap: float = 300.0) -> int:
    """Exponential backoff with full jitter: a random delay up to base * 2^attempt seconds, capped. The jitter
    spreads out retries of messages that failed together, so they don't all come back at once."""
    return max(1, round(random.uniform(0, min(cap, base * 2**attempt))))


async def consume(sqs: Any, queue: str, handler: Handler, *, concurrency: int, stop: asyncio.Event,
                  should_receive: Callable[[], bool] = lambda: True, visibility_timeout: int | None = None,
                  wait_s: int | None = None) -> None:
    """Receive and handle messages from `queue` until `stop` is set, at most `concurrency` at a time. Polling
    pauses while `should_receive()` is false, so messages aren't taken (and their timeouts started) before
    there's capacity to work on them. On stop, in-flight messages get settings.worker_shutdown_grace_s to finish;
    any still running are abandoned unacked, and SQS redelivers them after their visibility timeout."""
    timeout = visibility_timeout or settings.queue_visibility_timeout_s
    url = await aws.queue_url(sqs, queue)
    in_flight: set[asyncio.Task[None]] = set()
    try:
        while not stop.is_set():
            free = concurrency - len(in_flight)
            if free <= 0 or not should_receive():
                if in_flight:
                    await asyncio.wait(in_flight, timeout=0.5, return_when=asyncio.FIRST_COMPLETED)
                else:
                    await asyncio.sleep(0.5)
                continue
            response = await sqs.receive_message(
                QueueUrl=url, MaxNumberOfMessages=min(10, free), VisibilityTimeout=timeout,
                WaitTimeSeconds=settings.queue_wait_s if wait_s is None else wait_s,
                MessageSystemAttributeNames=["ApproximateReceiveCount", "SentTimestamp"],
                MessageAttributeNames=["traceparent", "tracestate"],
            )
            for message in response.get("Messages", []):
                task = asyncio.create_task(_process(sqs, queue, url, message, handler, timeout))
                in_flight.add(task)
                task.add_done_callback(in_flight.discard)
        if in_flight:
            await asyncio.wait(in_flight, timeout=settings.worker_shutdown_grace_s)
    finally:
        # Also runs when this task is cancelled: stop the handlers and their heartbeats without acking anything.
        for task in in_flight:
            task.cancel()
        await asyncio.gather(*in_flight, return_exceptions=True)


async def _process(sqs: Any, queue: str, url: str, message: dict[str, Any], handler: Handler, timeout: int) -> None:
    """One message, in a consumer span of its own: a new trace, linked to the span that sent the message (its
    traceparent attribute), so a product's path through the queues is a chain of linked traces."""
    attributes = message.get("Attributes", {})
    carrier = {k: v["StringValue"] for k, v in message.get("MessageAttributes", {}).items() if "StringValue" in v}
    producer = trace.get_current_span(propagate.extract(carrier)).get_span_context()
    if sent := attributes.get("SentTimestamp"):
        metrics.queue_message_age.record(max(0.0, time.time() - int(sent) / 1000), {"queue": queue})
    receive_count = int(attributes.get("ApproximateReceiveCount", 1))
    with _tracer.start_as_current_span(
            f"process {queue}", context=trace.set_span_in_context(trace.INVALID_SPAN), kind=SpanKind.CONSUMER,
            links=[Link(producer)] if producer.is_valid else [],
            attributes={"messaging.system": "aws_sqs", "messaging.destination.name": queue,
                        "messaging.operation.type": "process", "messaging.message.id": message["MessageId"],
                        "shelfsense.receive_count": receive_count}) as span:
        await _handle(sqs, queue, url, message, handler, timeout, receive_count, span)


async def _handle(sqs: Any, queue: str, url: str, message: dict[str, Any], handler: Handler, timeout: int,
                  receive_count: int, span: trace.Span) -> None:
    receipt = message["ReceiptHandle"]
    heartbeat = asyncio.create_task(_heartbeat(sqs, url, receipt, timeout))
    error: Exception | None = None
    try:
        await handler(message["Body"], receive_count)
    except Exception as exc:
        error = exc
        span.set_status(Status(StatusCode.ERROR))
        span.set_attribute("error.type", type(exc).__name__)
    finally:
        # Stop the heartbeat before acting on the message, or a late heartbeat could undo the backoff below.
        heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await heartbeat

    if error is None:
        await sqs.delete_message(QueueUrl=url, ReceiptHandle=receipt)
    elif isinstance(error, PermanentError):
        log.warning("%s message %s dead-lettered: %s", queue, message["MessageId"], error)
        await dead_letter(sqs, queue, message["Body"], error.code, error.detail)
        await sqs.delete_message(QueueUrl=url, ReceiptHandle=receipt)
    else:
        # TransientError, or a bug: retry after a backoff. The redrive policy stops a message that never succeeds.
        delay = backoff_s(receive_count)
        log.warning("%s message %s failed (receive %d), retrying in %ds: %r", queue, message["MessageId"],
                    receive_count, delay, error)
        await sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=delay)


async def _heartbeat(sqs: Any, url: str, receipt: str, timeout: int) -> None:
    while True:
        await asyncio.sleep(timeout / 3)
        try:
            await sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=receipt, VisibilityTimeout=timeout)
        except Exception as exc:  # one missed beat isn't fatal; the next one may get through
            log.warning("heartbeat failed: %r", exc)


async def dead_letter(sqs: Any, queue: str, body: str, error_code: str, detail: str,
                      product_id: uuid.UUID | None = None) -> None:
    """Record why `body` failed, then send it to `queue`'s DLQ. The row is committed first, so a message in the
    DLQ always has its reason on record. A product already dead-lettered on this queue (and not redriven) isn't
    sent again, so a redelivered message doesn't put it in the DLQ twice."""
    open_letter = (DeadLetter.queue == queue) & (DeadLetter.product_id == product_id) & DeadLetter.redriven_at.is_(None)
    async with db.SessionLocal() as session:
        stmt = insert(DeadLetter).values(queue=queue, product_id=product_id, error_code=error_code,
                                         detail=detail[:2000], message_body=body)
        if product_id is not None:
            stmt = stmt.on_conflict_do_nothing(index_elements=["queue", "product_id"],
                                               index_where=text("redriven_at IS NULL AND product_id IS NOT NULL"))
        letter_id = await session.scalar(stmt.returning(DeadLetter.id))
        if letter_id is None:  # an earlier delivery of this message got here first
            existing = await session.scalar(select(DeadLetter).where(open_letter))
            if existing is None or existing.sent_at is not None:
                return
            letter_id = existing.id
        await session.commit()

    await aws.send(sqs, aws.dlq_name(queue), [body])
    async with db.SessionLocal() as session:
        await session.execute(update(DeadLetter).where(DeadLetter.id == letter_id).values(sent_at=func.now()))
        await session.commit()
