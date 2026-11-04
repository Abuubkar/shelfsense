"""Writing products from Postgres into OpenSearch: one way, used by the index worker and scripts/sync_index.py.

A _bulk request can partly fail: each item has its own status. Items OpenSearch rejected for load (429) or
failed on a 5xx are retried on their own, in smaller batches; items it refused as malformed (a mapping error)
won't index on a retry and are reported as permanent failures.
"""

import asyncio
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal

from opensearchpy import AsyncOpenSearch, TransportError
from opensearchpy import ConnectionError as OpenSearchConnectionError
from opentelemetry import trace
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import metrics
from shelfsense_api.db import Product, ProductCategory, ProductExtractedAttribute, Supplier, TaxonomyNode
from shelfsense_api.embeddings import embed_passages, product_text
from shelfsense_api.normalize import parse_size, shoe_size_eu
from shelfsense_api.queue import Outcome, backoff_s
from shelfsense_api.search import ALIAS
from shelfsense_api.settings import settings

# Retry rounds for rejected items within one call; what's still failing after them is returned as transient.
BULK_ROUNDS = 4
_tracer = trace.get_tracer(__name__)


@dataclass
class BatchSizer:
    """Bulk batch size by AIMD, as TCP sizes its window: halve on rejection, grow by a step on success. Halving
    sheds load at once when OpenSearch is overwhelmed; growing slowly finds the limit again without slamming it."""

    size: int = 500
    min_size: int = 50
    max_size: int = 2000
    step: int = 50

    def rejected(self) -> None:
        self.size = max(self.min_size, self.size // 2)

    def succeeded(self) -> None:
        self.size = min(self.max_size, self.size + self.step)


async def product_docs(session: AsyncSession, product_ids: list[uuid.UUID]) -> dict[str, dict[str, Any]]:
    """Search documents for these products, by product ID, with their category in the current taxonomy release.
    Products that no longer exist are left out."""
    rows = (await session.execute(
        select(Product, Supplier.code, ProductCategory.node_id, TaxonomyNode.full_path)
        .join(Supplier, Supplier.id == Product.supplier_id)
        .outerjoin(ProductCategory, (ProductCategory.product_id == Product.id)
                   & (ProductCategory.taxonomy_version == settings.taxonomy_version))
        .outerjoin(TaxonomyNode, (TaxonomyNode.version == ProductCategory.taxonomy_version)
                   & (TaxonomyNode.node_id == ProductCategory.node_id))
        .where(Product.id.in_(product_ids))
        .order_by(Product.id)
    )).all()
    extracted: dict[Any, dict[str, str]] = {}
    for product_id, name, value in (await session.execute(
            select(ProductExtractedAttribute.product_id, ProductExtractedAttribute.name, ProductExtractedAttribute.value)
            .where(ProductExtractedAttribute.product_id.in_(product_ids)))).all():
        extracted.setdefault(product_id, {})[name] = value
    texts = [product_text(p.title, p.brand, p.description) for p, *_ in rows]
    # fastembed runs on the CPU and blocks; keep it off the event loop.
    vectors = await asyncio.to_thread(embed_passages, texts) if texts else []
    return {str(p.id): product_doc(p, supplier, node_id, path, extracted.get(p.id, {}), v)
            for (p, supplier, node_id, path), v in zip(rows, vectors, strict=True)}


def product_doc(p: Product, supplier: str, node_id: int | None, path: str | None, extracted: dict[str, str],
                vector: list[float]) -> dict[str, Any]:
    """One product's search document (the evals build their golden index with it too)."""
    return {
        "product_id": str(p.id), "supplier": supplier, "supplier_sku": p.supplier_sku, "title": p.title,
        "description": p.description, "brand": p.brand, "gtin": p.gtin, "price_minor": p.price_minor,
        "currency": p.currency, **_facets(p, extracted),
        "category_id": node_id, "category_path": path, "updated_at": p.updated_at.isoformat(), "embedding": vector,
    }


def _facets(p: Product, extracted: dict[str, str]) -> dict[str, Any]:
    """Facet values: the supplier's own columns first, then what the model read from the listing (grounded)."""
    gender = p.gender or extracted.get("gender")
    system: str | None
    size: str | None
    if p.size_system and p.size_value:
        system, size = p.size_system, p.size_value
    else:
        parsed = parse_size(extracted["size"]) if extracted.get("size") else None
        system, size = parsed if parsed else (None, None)
    eu = shoe_size_eu(system, size, gender) if system and system != "alpha" and size else None
    values = {"color": p.color_base or extracted.get("color"), "material": p.material or extracted.get("material"),
              "gender": gender, "size": size}
    return values | {"size_system": system, "size_eu": float(eu) if eu is not None else None,
                     "facets": [{"name": k, "value": v} for k, v in ({"brand": p.brand} | values).items() if v]}


async def bulk_index(os: AsyncOpenSearch, docs: dict[str, dict[str, Any]], sizer: BatchSizer,
                     index: str = ALIAS) -> list[Outcome]:
    """Index `docs` (product ID -> document) through the `products` alias (or into `index`, for a reindex), in
    batches of `sizer.size`, adapting the size as OpenSearch accepts or rejects them. Returns one outcome per product: done, transient (still
    rejected or failing after BULK_ROUNDS) or permanent (refused as malformed)."""
    outcomes: dict[str, Outcome] = {}
    pending = dict(docs)
    for round_ in range(BULK_ROUNDS):
        if not pending:
            break
        if round_:
            await asyncio.sleep(backoff_s(round_, base=0.5, cap=10))
        ids, retry, start = list(pending), {}, 0
        while start < len(ids):
            batch = ids[start:start + sizer.size]
            start += len(batch)
            for product_id, outcome in (await _bulk(os, batch, pending, sizer, index)).items():
                if outcome.status == "transient":
                    retry[product_id] = pending[product_id]
                outcomes[product_id] = outcome
        pending = retry
    return [outcomes[product_id] for product_id in docs]


async def _bulk(os: AsyncOpenSearch, batch: list[str], docs: dict[str, dict[str, Any]],
                sizer: BatchSizer, index: str) -> dict[str, Outcome]:
    with _tracer.start_as_current_span("opensearch bulk", attributes={
            "db.system.name": "opensearch", "db.operation.name": "bulk", "shelfsense.batch_size": len(batch)}) as span:
        outcomes = await _bulk_request(os, batch, docs, sizer, index)
        rejected = {kind: sum(1 for o in outcomes.values() if o.status == kind) for kind in ("transient", "permanent")}
        span.set_attributes({f"shelfsense.rejected.{kind}": n for kind, n in rejected.items()})
    metrics.bulk_batch_size.record(len(batch))
    for kind, n in rejected.items():
        metrics.bulk_rejections.add(n, {"kind": kind})
    return outcomes


async def _bulk_request(os: AsyncOpenSearch, batch: list[str], docs: dict[str, dict[str, Any]],
                        sizer: BatchSizer, index: str) -> dict[str, Outcome]:
    lines = []
    for product_id in batch:
        lines.append(json.dumps({"index": {"_index": index, "_id": product_id}}))
        lines.append(json.dumps(docs[product_id]))
    try:
        response = await os.bulk(body="\n".join(lines) + "\n")
    except OpenSearchConnectionError as exc:
        return {p: Outcome(uuid.UUID(p), "transient", "search_unavailable", str(exc)) for p in batch}
    except TransportError as exc:
        # The whole request refused: 429 when indexing pressure or the write queue is full.
        if exc.status_code == 429:
            sizer.rejected()
        transient = exc.status_code == 429 or (isinstance(exc.status_code, int) and exc.status_code >= 500)
        kind: Literal["transient", "permanent"] = "transient" if transient else "permanent"
        return {p: Outcome(uuid.UUID(p), kind, f"bulk_{exc.status_code}", str(exc.error)) for p in batch}

    outcomes, rejected = {}, False
    for item in response["items"]:
        result = item["index"]
        product_id, status = result["_id"], result["status"]
        error = result.get("error") or {}
        if status < 300:
            outcomes[product_id] = Outcome(uuid.UUID(product_id), "done")
        elif status == 429 or status >= 500:
            rejected |= status == 429
            outcomes[product_id] = Outcome(uuid.UUID(product_id), "transient", error.get("type", str(status))[:32],
                                           error.get("reason", ""))
        else:
            outcomes[product_id] = Outcome(uuid.UUID(product_id), "permanent", error.get("type", str(status))[:32],
                                           error.get("reason", ""))
    if rejected:
        sizer.rejected()
    else:
        sizer.succeeded()
    return outcomes
