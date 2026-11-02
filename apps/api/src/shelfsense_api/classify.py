"""Classifying a product into the Google Product Taxonomy: embedding pre-filter, then a constrained model pick."""

import asyncio
import json
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import prompts
from shelfsense_api.db import EnrichmentRun, Product, ProductCategory
from shelfsense_api.embeddings import embed_query, product_text
from shelfsense_api.llm import ModelError, ModelReply, chat_json, value_probability
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


async def needs_enrichment(session: AsyncSession, product_ids: list[uuid.UUID]) -> list[uuid.UUID]:
    """The products that have no category for their current content from the current taxonomy release and
    prompt. Enriching any other product would only repeat a stored answer."""
    current = ((ProductCategory.product_id == Product.id)
               & (ProductCategory.taxonomy_version == settings.taxonomy_version)
               & (ProductCategory.prompt_version == prompts.CLASSIFY_VERSION)
               & (ProductCategory.content_hash == Product.content_hash))
    query = (select(Product.id).outerjoin(ProductCategory, current)
             .where(Product.id.in_(product_ids), ProductCategory.product_id.is_(None)))
    return list(await session.scalars(query))


async def classify_product(session: AsyncSession, product: Product, attempt: int = 1) -> ProductCategory:
    """Pick the product's leaf category in the current taxonomy release and store it with how it was decided.
    A reply that fails validation is retried once, shown back to the model with the reason. Every model call
    is recorded in enrichment_runs; a failure is recorded, then raised as ModelError."""
    # fastembed runs on the CPU and blocks; keep it off the event loop.
    query = await asyncio.to_thread(embed_query, product_text(product.title, product.brand, product.description))
    candidates = await nearest_leaves(session, settings.taxonomy_version, query, settings.candidate_count)
    candidate_ids = [c.node_id for c in candidates]
    user = prompts.classify_user(product.title, product.brand, product.description,
                                 [(c.node_id, c.full_path) for c in candidates])
    follow_up: list[dict[str, str]] = []
    prompt_version = prompts.CLASSIFY_VERSION

    while True:
        started = time.perf_counter()
        try:
            reply = await chat_json(prompts.CLASSIFY_SYSTEM, user, category_schema(candidate_ids), follow_up)
            chosen = reply.answer.get("category_id")
            if chosen != NONE and chosen not in {str(i) for i in candidate_ids}:
                raise ModelError("invalid_model_output", f"category_id {chosen!r} is not a candidate",
                                 json.dumps(reply.answer))
        except ModelError as exc:
            session.add(_run(product, attempt, prompt_version, started, None, exc.code))
            await session.commit()
            if exc.code != "invalid_model_output" or follow_up:
                raise
            follow_up = [{"role": "assistant", "content": exc.content or ""},
                         {"role": "user", "content": prompts.classify_retry(str(exc))}]
            prompt_version = f"{prompts.CLASSIFY_VERSION}+{prompts.CLASSIFY_RETRY_VERSION}"
            continue
        break

    values = {
        "product_id": product.id,
        "taxonomy_version": settings.taxonomy_version,
        "node_id": None if chosen == NONE else int(chosen),
        "confidence": round(value_probability(reply.tokens, chosen), 4),
        "candidate_ids": candidate_ids,
        "model": reply.model,
        # The base prompt's version even after a retry: it's what decides whether the answer is current.
        "prompt_version": prompts.CLASSIFY_VERSION,
        "content_hash": product.content_hash,
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
    # Same transaction as the category: a crash leaves both or neither.
    session.add(_run(product, attempt, prompt_version, started, reply, None))
    await session.commit()
    return category


def _run(product: Product, attempt: int, prompt_version: str, started: float, reply: ModelReply | None,
         error_code: str | None) -> EnrichmentRun:
    return EnrichmentRun(
        product_id=product.id, attempt=attempt, outcome="failed" if error_code else "enriched",
        error_code=error_code, model=reply.model if reply else settings.llm_model, prompt_version=prompt_version,
        content_hash=product.content_hash, prompt_tokens=reply.prompt_tokens if reply else None,
        output_tokens=reply.output_tokens if reply else None, wall_ms=round((time.perf_counter() - started) * 1000),
    )
