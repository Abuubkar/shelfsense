"""What the API does, independent of REST or GraphQL: both call these functions, so no business rule is written
twice. Errors are raised as ApiProblem."""

import math
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from opensearchpy import AsyncOpenSearch
from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import aws, cursor, feeds, schemas, search
from shelfsense_api.classify import classify_product, needs_enrichment
from shelfsense_api.db import (
    DeadLetter,
    EnrichmentRun,
    Feed,
    FeedRejection,
    Product,
    ProductCategory,
    Supplier,
    TaxonomyNode,
)
from shelfsense_api.llm import ModelError
from shelfsense_api.messages import EnrichRequest, IndexRequest
from shelfsense_api.schemas import ApiProblem, ProblemCode
from shelfsense_api.settings import settings


@contextmanager
def _aws_errors() -> Iterator[None]:
    """SQS or S3 unreachable or refusing: a 503 for the client to retry, not a 500."""
    try:
        yield
    except (BotoCoreError, ClientError) as exc:
        raise ApiProblem(503, ProblemCode.QUEUE_UNAVAILABLE, "Queues or storage unavailable", str(exc)) from exc


def _feed_key(feed_id: uuid.UUID) -> str:
    return f"{feed_id}.csv"


async def create_feed_upload(session: AsyncSession, supplier: str, file_name: str) -> schemas.FeedUpload:
    feed = Feed(supplier_id=await feeds.ensure_supplier(session, supplier), file_name=file_name)
    session.add(feed)
    await session.commit()
    with _aws_errors():
        async with aws.s3() as s3:
            url = await s3.generate_presigned_url("put_object", ExpiresIn=settings.feed_upload_expiry_s,
                                                  Params={"Bucket": settings.feeds_bucket, "Key": _feed_key(feed.id)})
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.feed_upload_expiry_s)
    return schemas.FeedUpload(feed_id=feed.id, upload_url=url, expires_at=expires_at)


async def commit_feed(session: AsyncSession, feed_id: uuid.UUID) -> schemas.ImportResult:
    """Import the uploaded file and queue its products that need enriching. Refused while the enrich backlog
    is full. Safe to repeat: products upsert on their content hash and rejections on their row number, and the
    queued products are those still not enriched, which workers skip if they finish first."""
    feed = await session.get(Feed, feed_id)
    if feed is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Feed not found")
    with _aws_errors():
        async with aws.sqs() as sqs, aws.s3() as s3:
            await _check_backlog(session, sqs)
            # Spooled to a temporary file, never held in memory: feeds can be hundreds of MB.
            with tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "feed.csv"
                try:
                    obj = await s3.get_object(Bucket=settings.feeds_bucket, Key=_feed_key(feed_id))
                except ClientError as exc:
                    if exc.response["Error"]["Code"] != "NoSuchKey":
                        raise
                    raise ApiProblem(409, ProblemCode.FEED_NOT_UPLOADED, "Feed not uploaded",
                                     "PUT the file to the feed's upload_url first") from None
                with path.open("wb") as f:
                    async for chunk in obj["Body"].iter_chunks(1 << 20):
                        f.write(chunk)
                result = await feeds.import_file(session, path, feed_id, feed.supplier_id)

            to_enrich: list[uuid.UUID] = []
            for start in range(0, len(result.product_ids), 5000):
                to_enrich += await needs_enrichment(session, result.product_ids[start:start + 5000])
            batch = settings.enrich_batch_size
            await aws.send(sqs, settings.enrich_queue, [
                EnrichRequest(product_ids=to_enrich[i:i + batch], feed_id=feed_id).model_dump_json()
                for i in range(0, len(to_enrich), batch)
            ])
    return schemas.ImportResult(
        **{k: v for k, v in result.__dict__.items() if k not in ("rejections", "product_ids")},
        rejected=len(result.rejections),
        enqueued=len(to_enrich),
        rejections=[schemas.Rejection(**r.__dict__) for r in result.rejections],
    )


async def _check_backlog(session: AsyncSession, sqs: Any) -> None:
    """Backpressure: refuse new work while the enrich queue is over its limit, and say when to come back, from
    how fast products were enriched over the last hour."""
    depth = await aws.queue_depth(sqs, settings.enrich_queue)
    if depth <= settings.max_enrich_backlog:
        return
    enriched_last_hour = await session.scalar(
        select(func.count()).select_from(EnrichmentRun)
        .where(EnrichmentRun.outcome == "enriched", EnrichmentRun.created_at > func.now() - timedelta(hours=1))
    ) or 0
    excess_products = (depth - settings.max_enrich_backlog) * settings.enrich_batch_size
    # No recent enrichments (workers stopped?): a fixed 5 minutes rather than "never".
    seconds = 300 if not enriched_last_hour else math.ceil(excess_products / (enriched_last_hour / 3600))
    retry_after = min(max(seconds, 30), 3600)
    raise ApiProblem(429, ProblemCode.BACKLOG_FULL, "Enrichment backlog is full",
                     f"{depth} messages queued, limit {settings.max_enrich_backlog}; "
                     f"{enriched_last_hour} products enriched in the last hour",
                     headers={"Retry-After": str(retry_after)})


async def redrive(session: AsyncSession, queue: schemas.WorkQueue, dry_run: bool) -> schemas.RedriveResult:
    name = settings.enrich_queue if queue == schemas.WorkQueue.ENRICH else settings.index_queue
    reasons = dict((await session.execute(
        select(DeadLetter.error_code, func.count())
        .where(DeadLetter.queue == name, DeadLetter.redriven_at.is_(None)).group_by(DeadLetter.error_code)
    )).all())
    task_handle = None
    with _aws_errors():
        async with aws.sqs() as sqs:
            messages = await aws.queue_depth(sqs, aws.dlq_name(name))
            if not dry_run:
                try:
                    task = await sqs.start_message_move_task(SourceArn=await aws.queue_arn(sqs, aws.dlq_name(name)),
                                                             DestinationArn=await aws.queue_arn(sqs, name))
                except ClientError as exc:
                    if "already a task running" not in exc.response["Error"].get("Message", ""):
                        raise
                    raise ApiProblem(409, ProblemCode.REDRIVE_IN_PROGRESS, "A redrive is already running",
                                     exc.response["Error"]["Message"]) from None
                task_handle = task["TaskHandle"]
                await session.execute(update(DeadLetter).where(DeadLetter.queue == name, DeadLetter.redriven_at.is_(None))
                                      .values(redriven_at=func.now()))
                await session.commit()
    return schemas.RedriveResult(queue=queue, dry_run=dry_run, messages=messages, reasons=reasons,
                                 task_handle=task_handle)


async def list_rejections(session: AsyncSession, feed_id: uuid.UUID, limit: int,
                          after: str | None) -> schemas.RejectionPage:
    if await session.get(Feed, feed_id) is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Feed not found")
    scope = {"feed": str(feed_id)}
    query = select(FeedRejection).where(FeedRejection.feed_id == feed_id).order_by(FeedRejection.row_number)
    if after:
        query = query.where(FeedRejection.row_number > _decode(after, scope)["row"])
    rows = list(await session.scalars(query.limit(limit + 1)))
    page, more = rows[:limit], len(rows) > limit
    return schemas.RejectionPage(
        items=[schemas.Rejection(row_number=r.row_number, reason_code=r.reason_code, detail=r.detail,
                                 excerpt=r.excerpt) for r in page],
        next_cursor=cursor.encode({"row": page[-1].row_number}, scope, settings.cursor_secret) if more else None,
    )


def _products() -> Select[Any]:
    """Products with their supplier code and their category in the current taxonomy release."""
    return (
        select(Product, Supplier.code, ProductCategory, TaxonomyNode.full_path)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .outerjoin(ProductCategory, (ProductCategory.product_id == Product.id)
                   & (ProductCategory.taxonomy_version == settings.taxonomy_version))
        .outerjoin(TaxonomyNode, (TaxonomyNode.version == ProductCategory.taxonomy_version)
                   & (TaxonomyNode.node_id == ProductCategory.node_id))
    )


def _product(row: Any) -> schemas.Product:
    product, supplier, category, full_path = row
    return schemas.Product(
        id=product.id, supplier=supplier, supplier_sku=product.supplier_sku, title=product.title,
        description=product.description, brand=product.brand, gtin=product.gtin,
        price=schemas.Money(amount_minor=product.price_minor, currency=product.currency),
        attributes=product.attributes_json,
        category=None if category is None else schemas.Category(
            full_path=full_path, **{f: getattr(category, f) for f in schemas.Category.model_fields if f != "full_path"}
        ),
    )


def product_cursor(product_id: uuid.UUID, supplier: str | None, category_id: int | None) -> str:
    """Resumes a product listing (with these filters) just after this product."""
    return cursor.encode({"id": str(product_id)}, {"supplier": supplier, "category_id": category_id},
                         settings.cursor_secret)


async def list_products(session: AsyncSession, limit: int, after: str | None, supplier: str | None = None,
                        category_id: int | None = None) -> schemas.ProductPage:
    scope = {"supplier": supplier, "category_id": category_id}
    # uuidv7 IDs are time-ordered, so ID order is creation order and a stable keyset.
    query = _products().order_by(Product.id)
    if supplier is not None:
        query = query.where(Supplier.code == supplier)
    if category_id is not None:
        query = query.where(ProductCategory.node_id == category_id)
    if after:
        query = query.where(Product.id > uuid.UUID(_decode(after, scope)["id"]))
    rows = (await session.execute(query.limit(limit + 1))).all()
    page, more = rows[:limit], len(rows) > limit
    return schemas.ProductPage(
        items=[_product(r) for r in page],
        next_cursor=product_cursor(page[-1][0].id, supplier, category_id) if more else None,
    )


async def get_product(session: AsyncSession, product_id: uuid.UUID) -> schemas.Product:
    row = (await session.execute(_products().where(Product.id == product_id))).one_or_none()
    if row is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Product not found")
    return _product(row)


async def enrich_product(session: AsyncSession, product_id: uuid.UUID) -> schemas.Product:
    product = await session.get(Product, product_id)
    if product is None:
        raise ApiProblem(404, ProblemCode.NOT_FOUND, "Product not found")
    try:
        await classify_product(session, product)
    except ModelError as exc:
        if exc.code == "model_timeout":
            raise ApiProblem(504, ProblemCode.MODEL_TIMEOUT, "The model timed out", str(exc)) from exc
        raise ApiProblem(502, ProblemCode.MODEL_UNAVAILABLE, "The model gave no usable reply", f"{exc.code}: {exc}") from exc
    # Like the enrich worker: a new category reaches search through the index queue.
    with _aws_errors():
        async with aws.sqs() as sqs:
            await aws.send(sqs, settings.index_queue, [IndexRequest(product_ids=[product_id]).model_dump_json()])
    return await get_product(session, product_id)


async def search_products(session: AsyncSession, os: AsyncOpenSearch, q: str, filters: search.Filters,
                          page_size: int, after: str | None, debug: bool = False) -> schemas.SearchResponse:
    response, _ = await search_page(session, os, q, filters, page_size, after, debug)
    return response


async def search_page(session: AsyncSession, os: AsyncOpenSearch, q: str, filters: search.Filters, page_size: int,
                      after: str | None, debug: bool = False) -> tuple[schemas.SearchResponse, list[str]]:
    """One search page and the cursor after each of its items (GraphQL puts one on every edge)."""
    try:
        page = await search.search(os, q, filters, page_size, after, debug)
    except cursor.InvalidCursor as exc:
        raise ApiProblem(400, ProblemCode.INVALID_CURSOR, "Invalid cursor", str(exc)) from exc
    except search.CursorExpired as exc:
        raise ApiProblem(400, ProblemCode.CURSOR_EXPIRED, "Cursor expired", str(exc)) from exc
    except search.SearchUnavailable as exc:
        raise ApiProblem(503, ProblemCode.SEARCH_UNAVAILABLE, "Search is unavailable", str(exc)) from exc

    category_ids = [int(v.value) for v in page.facets.get("category_id", [])]
    paths = dict((await session.execute(
        select(TaxonomyNode.node_id, TaxonomyNode.full_path)
        .where(TaxonomyNode.version == settings.taxonomy_version, TaxonomyNode.node_id.in_(category_ids))
    )).all()) if category_ids else {}
    labels = {"category_id": {str(k): v for k, v in paths.items()},
              "price": {key: _price_label(lo, hi) for key, lo, hi in search.PRICE_BUCKETS}}

    response = schemas.SearchResponse(
        items=[_search_item(h, debug) for h in page.hits],
        total=page.total,
        facets=[schemas.Facet(name=schemas.FacetName(name), values=[
            schemas.FacetValue(value=v.value, label=labels.get(name, {}).get(v.value, v.value), count=v.count)
            for v in values]) for name, values in page.facets.items()],
        next_cursor=page.next_cursor,
        debug=schemas.SearchDebug(timings_ms=page.timings_ms, head_size=search.HEAD_SIZE,
                                  hybrid_weights=list(settings.hybrid_weights),
                                  knn_min_score=settings.knn_min_score) if debug else None,
    )
    return response, page.cursors


def _search_item(hit: search.Hit, debug: bool) -> schemas.SearchItem:
    s = hit.source
    return schemas.SearchItem(
        id=uuid.UUID(hit.product_id), rank=hit.rank, title=s["title"], brand=s.get("brand"),
        price=schemas.Money(amount_minor=s["price_minor"], currency=s["currency"]), color=s.get("color"),
        size=s.get("size"), category_id=s.get("category_id"), category_path=s.get("category_path"),
        debug=schemas.SearchItemDebug(stage=schemas.SearchStage(hit.stage), scores=hit.scores) if debug else None,
    )


def _price_label(lo: int | None, hi: int | None) -> str:
    if lo is None:
        return f"Under {hi / 100:.2f}"  # display only: amounts stay integers everywhere else
    if hi is None:
        return f"{lo / 100:.2f} and up"
    return f"{lo / 100:.2f}–{hi / 100:.2f}"


def _decode(after: str, scope: dict[str, Any]) -> dict[str, Any]:
    try:
        return cursor.decode(after, scope, settings.cursor_secret)
    except cursor.InvalidCursor as exc:
        raise ApiProblem(400, ProblemCode.INVALID_CURSOR, "Invalid cursor", str(exc)) from exc
