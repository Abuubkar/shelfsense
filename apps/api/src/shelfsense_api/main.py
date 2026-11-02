import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import feeds
from shelfsense_api.classify import classify_product
from shelfsense_api.db import Product, ProductCategory, TaxonomyNode, get_session
from shelfsense_api.llm import ModelError
from shelfsense_api.settings import settings

app = FastAPI(title="Shelfsense", version="0.1.0")
Session = Annotated[AsyncSession, Depends(get_session)]


class ImportLocalRequest(BaseModel):
    # A file under FEEDS_DIR on the API's machine. Uploads to S3 replace this in slice 3.
    path: str
    supplier: str


class RejectionOut(BaseModel):
    row_number: int
    reason_code: str
    detail: str
    excerpt: str


class ImportResultOut(BaseModel):
    file_sha256: str
    rows: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int
    rejections: list[RejectionOut]


class CategoryOut(BaseModel):
    taxonomy_version: str
    node_id: int | None
    full_path: str | None
    confidence: float
    candidate_ids: list[int]
    model: str
    prompt_version: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int


class ProductOut(BaseModel):
    id: uuid.UUID
    supplier_sku: str
    title: str
    description: str | None
    brand: str | None
    gtin: str | None
    price_minor: int
    currency: str
    attributes: dict[str, str]
    category: CategoryOut | None


@app.post("/v1/feeds:import-local")
async def import_local_feed(body: ImportLocalRequest, session: Session) -> ImportResultOut:
    feeds_dir = Path(settings.feeds_dir).resolve()
    path = (feeds_dir / body.path).resolve()
    if not path.is_relative_to(feeds_dir) or not path.is_file():
        raise HTTPException(404, f"no feed file {body.path!r} under {settings.feeds_dir}")
    result = await feeds.import_file(session, path, body.supplier)
    return ImportResultOut(
        **{k: v for k, v in result.__dict__.items() if k != "rejections"},
        rejected=len(result.rejections),
        rejections=[RejectionOut(**r.__dict__) for r in result.rejections],
    )


@app.post("/v1/products/{product_id:uuid}:enrich")
async def enrich_product(product_id: uuid.UUID, session: Session) -> ProductOut:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "product not found")
    try:
        await classify_product(session, product)
    except ModelError as exc:
        raise HTTPException(504 if exc.code == "model_timeout" else 502, f"{exc.code}: {exc}") from exc
    return await get_product(product_id, session)


@app.get("/v1/products/{product_id:uuid}")
async def get_product(product_id: uuid.UUID, session: Session) -> ProductOut:
    product = await session.get(Product, product_id)
    if product is None:
        raise HTTPException(404, "product not found")
    row = (await session.execute(
        select(ProductCategory, TaxonomyNode.full_path)
        .outerjoin(TaxonomyNode, (TaxonomyNode.version == ProductCategory.taxonomy_version)
                   & (TaxonomyNode.node_id == ProductCategory.node_id))
        .where(ProductCategory.product_id == product_id,
               ProductCategory.taxonomy_version == settings.taxonomy_version)
    )).one_or_none()
    category = None
    if row is not None:
        pc, full_path = row
        category = CategoryOut(full_path=full_path, **{f: getattr(pc, f) for f in CategoryOut.model_fields
                                                       if f != "full_path"})
    return ProductOut(
        id=product.id, supplier_sku=product.supplier_sku, title=product.title, description=product.description,
        brand=product.brand, gtin=product.gtin, price_minor=product.price_minor, currency=product.currency,
        attributes=product.attributes_json, category=category,
    )
