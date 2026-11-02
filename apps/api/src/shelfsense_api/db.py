import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shelfsense_api.settings import settings

engine = create_async_engine(settings.database_url)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

# bge-small-en-v1.5 vectors.
EMBEDDING_DIM = 384


async def get_session() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


class Base(DeclarativeBase):
    pass


class Supplier(Base):
    """A seller whose feeds we import, known by a short code (e.g. "acme-outdoor")."""

    __tablename__ = "suppliers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Product(Base):
    """One supplier's product as last imported. Postgres is the source of truth for the catalog."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("supplier_id", "supplier_sku"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    supplier_sku: Mapped[str] = mapped_column(String(128))
    title: Mapped[str]
    description: Mapped[str | None]
    brand: Mapped[str | None]
    gtin: Mapped[str | None] = mapped_column(String(14))
    # Integer minor units (cents) plus ISO 4217 code: money never passes through a float.
    price_minor: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    # Supplier-provided extra columns as given. Becomes typed columns for the hottest facets in slice 4.
    attributes_json: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # sha256 of the imported fields: a re-import only writes when this changes.
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Feed(Base):
    """One uploaded feed file. Its bytes live in the feeds bucket under the feed's ID; the hash and counts are
    filled in when it's committed. Committing it again changes nothing."""

    __tablename__ = "feeds"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    file_name: Mapped[str]
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    row_count: Mapped[int | None]
    rejected_count: Mapped[int | None]
    committed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class FeedRejection(Base):
    """A feed row that failed validation."""

    __tablename__ = "feed_rejections"
    __table_args__ = (UniqueConstraint("feed_id", "row_number"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("feeds.id"))
    # Spreadsheet-style: the header is row 1, so the first product is row 2.
    row_number: Mapped[int]
    reason_code: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str]
    excerpt: Mapped[str]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TaxonomyNode(Base):
    """One Google Product Taxonomy category in one taxonomy release, with its full path embedded."""

    __tablename__ = "taxonomy_nodes"
    __table_args__ = (
        ForeignKeyConstraint(["version", "parent_id"], ["taxonomy_nodes.version", "taxonomy_nodes.node_id"]),
    )

    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    node_id: Mapped[int] = mapped_column(primary_key=True)
    parent_id: Mapped[int | None]
    name: Mapped[str]
    full_path: Mapped[str]
    depth: Mapped[int]
    is_leaf: Mapped[bool]
    # No ANN index on purpose: ~5.6k nodes per release is an exact scan in milliseconds (docs/adr/0002).
    embedding: Mapped[list[float]] = mapped_column(VECTOR(EMBEDDING_DIM))


class ProductCategory(Base):
    """A product's category in one taxonomy release, with how it was decided."""

    __tablename__ = "product_categories"
    __table_args__ = (
        ForeignKeyConstraint(["taxonomy_version", "node_id"], ["taxonomy_nodes.version", "taxonomy_nodes.node_id"]),
    )

    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), primary_key=True)
    taxonomy_version: Mapped[str] = mapped_column(String(16), primary_key=True)
    # NULL when the model answered NONE: no candidate fits.
    node_id: Mapped[int | None]
    # The model's probability for the chosen ID, from its token logprobs (not a number it was asked to state).
    confidence: Mapped[float]
    # The embedding pre-filter's candidates, nearest first; the gold leaf being in here bounds accuracy.
    candidate_ids: Mapped[list[int]] = mapped_column(JSONB)
    model: Mapped[str]
    prompt_version: Mapped[str]
    # The product content this was decided from: a product whose hash has changed since needs enriching again.
    content_hash: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int]
    output_tokens: Mapped[int]
    total_ms: Mapped[int]
    prompt_eval_ms: Mapped[int]
    eval_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class EnrichmentRun(Base):
    """One model call to enrich one product, successful or not: the audit trail, and the measured rate that
    backpressure is computed from."""

    __tablename__ = "enrichment_runs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    product_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("products.id"), index=True)
    # Which delivery of the product's enrich request this was: 1, then 2 and 3 for resubmissions.
    attempt: Mapped[int]
    # "enriched" or "failed".
    outcome: Mapped[str] = mapped_column(String(16))
    error_code: Mapped[str | None] = mapped_column(String(32))
    model: Mapped[str]
    prompt_version: Mapped[str]
    content_hash: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int | None]
    output_tokens: Mapped[int | None]
    # Wall-clock time of the call as the worker saw it, queueing inside Ollama included.
    wall_ms: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class DeadLetter(Base):
    """A message, or one product of a message, that won't succeed by retrying. The row is written before the
    message goes to the DLQ, so it records why; `sent_at` says the DLQ send happened."""

    __tablename__ = "dead_letters"
    __table_args__ = (
        # A product has at most one open dead letter per queue, so a redelivered message doesn't dead-letter it twice.
        Index("dead_letters_open_product", "queue", "product_id", unique=True,
              postgresql_where=text("redriven_at IS NULL AND product_id IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, server_default=text("uuidv7()"))
    # The work queue it failed on ("enrich" or "index"), not the DLQ's name.
    queue: Mapped[str] = mapped_column(String(32))
    # NULL when a whole message failed (for example it didn't parse).
    product_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("products.id"))
    error_code: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str]
    message_body: Mapped[str]
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    redriven_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
