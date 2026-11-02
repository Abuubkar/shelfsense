"""Consumes the index queue: writes products from Postgres to OpenSearch with adaptive bulk batches, retries
rejected items on their own, resubmits what's still failing and dead-letters items OpenSearch refuses."""

from typing import Any

from opensearchpy import AsyncOpenSearch

from shelfsense_api import aws, db
from shelfsense_api.indexing import BatchSizer, bulk_index, product_docs
from shelfsense_api.messages import IndexRequest, parse
from shelfsense_api.queue import Handler, backoff_s, dead_letter, plan_followups
from shelfsense_api.settings import settings


def make_handler(sqs: Any, os: AsyncOpenSearch, sizer: BatchSizer) -> Handler:
    """The index handler. `sizer` is shared by every message this worker handles, so the batch size it learned
    carries over from one message to the next."""

    async def handle(body: str, receive_count: int) -> None:
        request = parse(IndexRequest, body)
        async with db.SessionLocal() as session:
            docs = await product_docs(session, request.product_ids)
        outcomes = await bulk_index(os, docs, sizer)
        plan = plan_followups(outcomes, request.attempt, settings.max_attempts)
        if plan.retry:
            retry = IndexRequest(product_ids=plan.retry, attempt=request.attempt + 1)
            await aws.send(sqs, settings.index_queue, [retry.model_dump_json()], delay_s=backoff_s(request.attempt))
        for dead in plan.dead:
            one = IndexRequest(product_ids=[dead.product_id], attempt=request.attempt)
            await dead_letter(sqs, settings.index_queue, one.model_dump_json(), dead.error_code or "unknown",
                              dead.detail, dead.product_id)

    return handle
