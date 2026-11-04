"""Queue behaviour that would lose or duplicate work if it broke, on real SQS (Floci) and Postgres containers.
The model is stubbed at llm.chat_json's boundary; embeddings and the candidate pre-filter run for real."""

import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import numpy as np
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from shelfsense_api import aws, classify, db, queue, schemas, service
from shelfsense_api.db import DeadLetter, EnrichmentRun, Product, ProductCategory, Supplier, TaxonomyNode
from shelfsense_api.llm import ModelReply
from shelfsense_api.messages import EnrichRequest
from shelfsense_api.settings import settings
from shelfsense_worker_enrich import make_handler

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


def reply(category_id: str) -> ModelReply:
    tokens = [('{"category_id": "', 0.0), (category_id, -0.01), ('"}', 0.0)]
    return ModelReply(answer={"category_id": category_id}, tokens=tokens, model="stub", prompt_tokens=120,
                      output_tokens=9, total_ms=5, prompt_eval_ms=2, eval_ms=2)


def first_candidate(schema: dict[str, Any]) -> str:
    return schema["properties"]["category_id"]["enum"][0]


@pytest.fixture
async def stack(migrated_postgres_url: str, floci_url: str, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Any]:
    """Settings and sessions pointed at the containers, fresh queues for this test, taxonomy leaves to pick
    candidates from, and a supplier to own products."""
    engine = create_async_engine(migrated_postgres_url)
    monkeypatch.setattr(db, "SessionLocal", async_sessionmaker(engine, expire_on_commit=False))
    suffix = uuid.uuid4().hex[:8]
    for name, value in {"aws_endpoint_url": floci_url, "enrich_queue": f"enrich-{suffix}",
                        "index_queue": f"index-{suffix}", "max_attempts": 3}.items():
        monkeypatch.setattr(settings, name, value)
    async with db.SessionLocal() as session:
        if not await session.scalar(select(func.count()).select_from(TaxonomyNode)):
            vectors = np.random.default_rng(7).normal(size=(20, db.EMBEDDING_DIM))
            session.add_all(TaxonomyNode(version=settings.taxonomy_version, node_id=1000 + i, parent_id=None,
                                         name=f"Leaf {i}", full_path=f"Root > Leaf {i}", depth=1, is_leaf=True,
                                         embedding=(v / np.linalg.norm(v)).tolist())
                            for i, v in enumerate(vectors))
        supplier = Supplier(code=f"test-{suffix}")
        session.add(supplier)
        await session.commit()
    async with aws.sqs() as sqs, aws.s3() as s3:
        await aws.ensure_resources(sqs, s3)
        yield sqs, supplier.id
    await engine.dispose()


async def add_products(supplier_id: uuid.UUID, n: int) -> list[uuid.UUID]:
    async with db.SessionLocal() as session:
        products = [Product(supplier_id=supplier_id, supplier_sku=f"SKU-{i}", title=f"Test product {i}",
                            price_minor=1000 + i, currency="USD", content_hash=f"{i:064d}") for i in range(n)]
        session.add_all(products)
        await session.commit()
        return [p.id for p in products]


async def until(check: Callable[[], Awaitable[bool]], timeout: float = 60) -> None:
    async with asyncio.timeout(timeout):
        while not await check():
            await asyncio.sleep(0.3)


async def count(query: Any) -> int:
    async with db.SessionLocal() as session:
        return await session.scalar(query) or 0


def categories_of(ids: list[uuid.UUID]) -> Any:
    return select(func.count()).select_from(ProductCategory).where(ProductCategory.product_id.in_(ids))


async def depth_is(sqs: Any, queue_name: str, n: int) -> bool:
    return await aws.queue_depth(sqs, queue_name) == n


async def test_heartbeat_keeps_a_long_handler_from_being_redelivered(stack: Any) -> None:
    sqs, _ = stack
    await aws.send(sqs, settings.enrich_queue, ["slow job"])
    receives: list[int] = []
    finished = asyncio.Event()

    async def slow(body: str, receive_count: int) -> None:
        receives.append(receive_count)
        await asyncio.sleep(7)  # 3.5 visibility timeouts
        finished.set()

    async def started() -> bool:
        return bool(receives)

    stop = asyncio.Event()
    consumer = asyncio.create_task(queue.consume(sqs, settings.enrich_queue, slow, concurrency=1, stop=stop,
                                                 visibility_timeout=2, wait_s=1))
    await until(started)
    # A second consumer polls for as long as the handler runs. Without the heartbeat, the message would become
    # visible again 2 s in, and this consumer would get it.
    url, stolen = await aws.queue_url(sqs, settings.enrich_queue), []
    while not finished.is_set():
        response = await sqs.receive_message(QueueUrl=url, WaitTimeSeconds=1, VisibilityTimeout=2)
        stolen += response.get("Messages", [])
    await until(lambda: depth_is(sqs, settings.enrich_queue, 0))
    stop.set()
    await consumer

    assert stolen == []
    assert receives == [1]


async def test_redelivery_after_a_crash_midway_only_enriches_what_wasnt_written(
        stack: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sqs, supplier_id = stack
    ids = await add_products(supplier_id, 50)
    await aws.send(sqs, settings.enrich_queue, [EnrichRequest(product_ids=ids).model_dump_json()])
    calls = {"first": 0, "second": 0}

    async def crashes_after_25(system: str, user: str, schema: dict[str, Any], follow_up: Any = None, **_: Any) -> ModelReply:
        calls["first"] += 1
        if calls["first"] > 25:
            await asyncio.Event().wait()  # stuck here when the worker dies
        return reply(first_candidate(schema))

    async def healthy(system: str, user: str, schema: dict[str, Any], follow_up: Any = None, **_: Any) -> ModelReply:
        calls["second"] += 1
        return reply(first_candidate(schema))

    monkeypatch.setattr(classify, "chat_json", crashes_after_25)
    worker = asyncio.create_task(queue.consume(sqs, settings.enrich_queue, make_handler(sqs, asyncio.Semaphore(1)),
                                               concurrency=1, stop=asyncio.Event(), visibility_timeout=3, wait_s=1))

    async def half_written() -> bool:
        return await count(categories_of(ids)) == 25

    await until(half_written)
    worker.cancel()  # the crash: no ack, no visibility change; SQS redelivers after the timeout
    await asyncio.gather(worker, return_exceptions=True)

    monkeypatch.setattr(classify, "chat_json", healthy)
    stop = asyncio.Event()
    replacement = asyncio.create_task(queue.consume(sqs, settings.enrich_queue,
                                                    make_handler(sqs, asyncio.Semaphore(1)), concurrency=1, stop=stop,
                                                    visibility_timeout=3, wait_s=1))

    async def all_done() -> bool:
        return await count(categories_of(ids)) == 50 and await depth_is(sqs, settings.enrich_queue, 0)

    await until(all_done)
    stop.set()
    await replacement

    assert calls["second"] == 25
    twice = select(func.count()).select_from(
        select(EnrichmentRun.product_id).where(EnrichmentRun.product_id.in_(ids), EnrichmentRun.outcome == "enriched")
        .group_by(EnrichmentRun.product_id).having(func.count() > 1).subquery())
    assert await count(twice) == 0
    # The redelivered message passes all 50 on to indexing: 25 it enriched, and 25 the crashed worker wrote.
    url = await aws.queue_url(sqs, settings.index_queue)
    response = await sqs.receive_message(QueueUrl=url, MaxNumberOfMessages=10, WaitTimeSeconds=1)
    indexed = {i for m in response.get("Messages", []) for i in json.loads(m["Body"])["product_ids"]}
    assert {str(i) for i in ids} <= indexed


async def test_permanent_failure_is_dead_lettered_alone_and_redrive_moves_it_back(
        stack: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    sqs, supplier_id = stack
    bad, good = await add_products(supplier_id, 2)

    async def rejects_product_0(system: str, user: str, schema: dict[str, Any], follow_up: Any = None, **_: Any) -> ModelReply:
        # Product 0 gets an answer outside its candidates every time, retry included.
        return reply("999999" if "Test product 0" in user else first_candidate(schema))

    monkeypatch.setattr(classify, "chat_json", rejects_product_0)
    await aws.send(sqs, settings.enrich_queue, [EnrichRequest(product_ids=[bad, good]).model_dump_json()])
    stop = asyncio.Event()
    worker = asyncio.create_task(queue.consume(sqs, settings.enrich_queue, make_handler(sqs, asyncio.Semaphore(1)),
                                               concurrency=1, stop=stop, wait_s=1))
    dlq = aws.dlq_name(settings.enrich_queue)

    async def settled() -> bool:
        return await depth_is(sqs, settings.enrich_queue, 0) and await depth_is(sqs, dlq, 1)

    await until(settled)
    stop.set()
    await worker

    assert await count(categories_of([good])) == 1  # its batch-mate still went through
    failed_calls = select(func.count()).select_from(EnrichmentRun).where(EnrichmentRun.product_id == bad)
    assert await count(failed_calls) == 2  # the first reply and the retry with the validation error
    async with db.SessionLocal() as session:
        letter = await session.scalar(select(DeadLetter).where(DeadLetter.product_id == bad))
        assert letter is not None and letter.sent_at is not None
        assert letter.error_code == "invalid_model_output"

        preview = await service.redrive(session, schemas.WorkQueue.ENRICH, dry_run=True)
        assert (preview.messages, preview.reasons, preview.task_handle) == (1, {"invalid_model_output": 1}, None)
        moved = await service.redrive(session, schemas.WorkQueue.ENRICH, dry_run=False)
        assert moved.task_handle

    async def moved_back() -> bool:
        return await depth_is(sqs, dlq, 0) and await depth_is(sqs, settings.enrich_queue, 1)

    await until(moved_back)
    url = await aws.queue_url(sqs, settings.enrich_queue)
    message = (await sqs.receive_message(QueueUrl=url, WaitTimeSeconds=1))["Messages"][0]
    assert json.loads(message["Body"])["product_ids"] == [str(bad)]
    assert await count(select(func.count()).select_from(DeadLetter)
                       .where(DeadLetter.product_id == bad, DeadLetter.redriven_at.is_(None))) == 0
