"""Consumes the enrich queue: classifies each product of a message on its own, passes the enriched ones on to
the index queue, resubmits transient failures and dead-letters the rest."""

import asyncio
import uuid
from typing import Any

from shelfsense_api import aws, db
from shelfsense_api.classify import classify_product, needs_enrichment
from shelfsense_api.db import Product
from shelfsense_api.llm import TRANSIENT_CODES, ModelError
from shelfsense_api.messages import EnrichRequest, IndexRequest, parse
from shelfsense_api.queue import Handler, Outcome, backoff_s, dead_letter, plan_followups
from shelfsense_api.settings import settings


def make_handler(sqs: Any, llm_slots: asyncio.Semaphore) -> Handler:
    """The enrich handler. `llm_slots` caps model calls across all messages this worker is handling."""

    async def handle(body: str, receive_count: int) -> None:
        request = parse(EnrichRequest, body)
        async with db.SessionLocal() as session:
            pending = set(await needs_enrichment(session, request.product_ids))
        # Products enriched already (by an earlier delivery of this message, say) count as done: they're passed
        # on to indexing again, which is harmless, so a crash between enriching and sending loses nothing.
        outcomes = await asyncio.gather(*(
            enrich_one(product_id, request.attempt, llm_slots) if product_id in pending else _done(product_id)
            for product_id in request.product_ids
        ))
        plan = plan_followups(list(outcomes), request.attempt, settings.max_attempts)
        if plan.done:
            await aws.send(sqs, settings.index_queue, [IndexRequest(product_ids=plan.done).model_dump_json()])
        if plan.retry:
            retry = EnrichRequest(product_ids=plan.retry, attempt=request.attempt + 1, feed_id=request.feed_id)
            await aws.send(sqs, settings.enrich_queue, [retry.model_dump_json()], delay_s=backoff_s(request.attempt))
        for dead in plan.dead:
            # One message per product, so a redrive retries exactly the products that failed.
            one = EnrichRequest(product_ids=[dead.product_id], attempt=request.attempt, feed_id=request.feed_id)
            await dead_letter(sqs, settings.enrich_queue, one.model_dump_json(), dead.error_code or "unknown",
                              dead.detail, dead.product_id)

    return handle


async def _done(product_id: uuid.UUID) -> Outcome:
    return Outcome(product_id, "done")


async def enrich_one(product_id: uuid.UUID, attempt: int, llm_slots: asyncio.Semaphore) -> Outcome:
    async with llm_slots, db.SessionLocal() as session:
        product = await session.get(Product, product_id)
        if product is None:  # deleted since it was queued: nothing to do
            return Outcome(product_id, "done")
        try:
            await classify_product(session, product, attempt)
        except ModelError as exc:
            status = "transient" if exc.code in TRANSIENT_CODES else "permanent"
            return Outcome(product_id, status, exc.code, str(exc))
    return Outcome(product_id, "done")
