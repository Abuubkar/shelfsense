"""Classifying a product into the Google Product Taxonomy: embedding pre-filter, then a constrained model pick."""

import asyncio
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import prompts
from shelfsense_api.db import Product, ProductCategory
from shelfsense_api.embeddings import embed_query, product_text
from shelfsense_api.llm import ModelError, chat_json, value_probability
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import nearest_leaves

NONE = "NONE"


def category_schema(candidate_ids: list[int]) -> dict[str, Any]:
    """The reply schema for one product: category_id may only be one of its candidates or NONE, so the model
    can't answer with a category the pre-filter didn't offer, or one that doesn't exist."""
    ids = list(dict.fromkeys(str(i) for i in candidate_ids))
    return {
        "type": "object",
        "properties": {"category_id": {"type": "string", "enum": [*ids, NONE]}},
        "required": ["category_id"],
        "additionalProperties": False,
    }


async def classify_product(session: AsyncSession, product: Product) -> ProductCategory:
    """Pick the product's leaf category in the current taxonomy release and store it with how it was decided."""
    # fastembed runs on the CPU and blocks; keep it off the event loop.
    query = await asyncio.to_thread(embed_query, product_text(product.title, product.brand, product.description))
    candidates = await nearest_leaves(session, settings.taxonomy_version, query, settings.candidate_count)
    candidate_ids = [c.node_id for c in candidates]

    reply = await chat_json(
        prompts.CLASSIFY_SYSTEM,
        prompts.classify_user(product.title, product.brand, product.description,
                              [(c.node_id, c.full_path) for c in candidates]),
        category_schema(candidate_ids),
    )
    chosen = reply.answer.get("category_id")
    if chosen != NONE and chosen not in {str(i) for i in candidate_ids}:
        raise ModelError("invalid_model_output", f"category_id {chosen!r} is not a candidate")

    values = {
        "product_id": product.id,
        "taxonomy_version": settings.taxonomy_version,
        "node_id": None if chosen == NONE else int(chosen),
        "confidence": round(value_probability(reply.tokens, chosen), 4),
        "candidate_ids": candidate_ids,
        "model": reply.model,
        "prompt_version": prompts.CLASSIFY_VERSION,
        "prompt_tokens": reply.prompt_tokens,
        "output_tokens": reply.output_tokens,
        "total_ms": reply.total_ms,
        "prompt_eval_ms": reply.prompt_eval_ms,
        "eval_ms": reply.eval_ms,
    }
    stmt = insert(ProductCategory).values(values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["product_id", "taxonomy_version"],
        set_={k: stmt.excluded[k] for k in values if k not in ("product_id", "taxonomy_version")}
        | {"created_at": stmt.excluded.created_at},
    ).returning(ProductCategory)
    category = (await session.scalars(stmt)).one()
    await session.commit()
    return category
