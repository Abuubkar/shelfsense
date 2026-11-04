"""Enriching a product: its Google Product Taxonomy category (embedding pre-filter, then a constrained model pick)
and its attributes, each grounded in an exact quote from the listing (attributes.py), in one model call."""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api import metrics, prompts
from shelfsense_api.attributes import Grounding, ground
from shelfsense_api.db import (
    EnrichmentRun,
    Product,
    ProductAttribute,
    ProductCategory,
    ProductExtractedAttribute,
    TaxonomyNode,
)
from shelfsense_api.embeddings import embed_query, product_text
from shelfsense_api.llm import ModelError, ModelReply, chat_json, value_probability
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import nearest_leaves

NONE = "NONE"


EVIDENCE_FIELDS = ("title", "description", "brand", "raw_attributes")


def category_schema(candidate_ids: list[int]) -> dict[str, Any]:
    """The reply schema for one product: category_id may only be one of its candidates or NONE, so the model
    can't answer with a category the pre-filter didn't offer, or one that doesn't exist. Attribute names, units
    and evidence fields are enums too; whether the evidence really is in the listing is checked in code."""
    ids = list(dict.fromkeys(str(i) for i in candidate_ids))
    attribute = {
        "type": "object",
        "properties": {
            "name": {"type": "string", "enum": list(prompts.ATTRIBUTE_NAMES)},
            "value": {"type": "string"},
            "unit": {"type": "string", "enum": [*prompts.LENGTH_UNITS, "none"]},
            "evidence_field": {"type": "string", "enum": list(EVIDENCE_FIELDS)},
            "evidence_text": {"type": "string"},
        },
        "required": ["name", "value", "unit", "evidence_field", "evidence_text"],
        "additionalProperties": False,
    }
    return {
        "type": "object",
        "properties": {"category_id": {"type": "string", "enum": [*ids, NONE]},
                       "attributes": {"type": "array", "items": attribute}},
        "required": ["category_id", "attributes"],
        "additionalProperties": False,
    }


def evidence_fields(title: str, brand: str | None, description: str | None,
                    attributes: dict[str, str]) -> dict[str, str]:
    """The texts an attribute may quote, exactly as the model was shown them."""
    return {"title": title, "description": (description or "")[:prompts.MAX_DESCRIPTION_CHARS],
            "brand": brand or "", "raw_attributes": prompts.raw_attributes_text(attributes)}


async def needs_enrichment(session: AsyncSession, product_ids: list[uuid.UUID],
                           taxonomy_version: str | None = None) -> list[uuid.UUID]:
    """The products that have no category for their current content from the taxonomy release (the served one
    by default) and current prompt. Enriching any other product would only repeat a stored answer."""
    current = ((ProductCategory.product_id == Product.id)
               & (ProductCategory.taxonomy_version == (taxonomy_version or settings.taxonomy_version))
               & (ProductCategory.prompt_version == prompts.ENRICH_VERSION)
               & (ProductCategory.content_hash == Product.content_hash))
    query = (select(Product.id).outerjoin(ProductCategory, current)
             .where(Product.id.in_(product_ids), ProductCategory.product_id.is_(None)))
    return list(await session.scalars(query))


@dataclass
class Failure:
    """One model call whose reply was refused or never came."""

    code: str
    prompt_version: str
    wall_ms: int


@dataclass
class Decision:
    """What enrichment decided for one listing, before anything is stored. `error` is set when no valid reply came
    (after the one retry for an invalid reply); `failures` lists every refused call, the first try's included."""

    candidates: list[TaxonomyNode]
    chosen: str | None = None  # a candidate id or NONE
    confidence: float = 0.0
    reply: ModelReply | None = None
    grounding: Grounding | None = None
    prompt_version: str = prompts.ENRICH_VERSION
    wall_ms: int = 0  # of the call that produced `reply`
    failures: list[Failure] = field(default_factory=list)
    error: ModelError | None = None


async def decide(session: AsyncSession, title: str, brand: str | None, description: str | None,
                 raw: dict[str, str], taxonomy_version: str | None = None) -> Decision:
    """A listing's leaf category in a taxonomy release (the served one by default) and its grounded attributes:
    embedding pre-filter, one constrained model call, and one retry that shows an invalid reply back to the model
    with the reason. Stores nothing (classify_product does; the evals call this directly)."""
    # fastembed runs on the CPU and blocks; keep it off the event loop.
    query = await asyncio.to_thread(embed_query, product_text(title, brand, description))
    version = taxonomy_version or settings.taxonomy_version
    candidates = await nearest_leaves(session, version, query, settings.candidate_count)
    candidate_ids = [c.node_id for c in candidates]
    user = prompts.enrich_user(title, brand, description, raw, [(c.node_id, c.full_path) for c in candidates])
    decision = Decision(candidates)
    follow_up: list[dict[str, str]] = []

    while True:
        started = time.perf_counter()
        try:
            reply = await chat_json(prompts.ENRICH_SYSTEM, user, category_schema(candidate_ids), follow_up,
                                    prompt_version=decision.prompt_version)
            chosen = reply.answer.get("category_id")
            if chosen != NONE and chosen not in {str(i) for i in candidate_ids}:
                raise ModelError("invalid_model_output", f"category_id {chosen!r} is not a candidate",
                                 json.dumps(reply.answer))
        except ModelError as exc:
            decision.failures.append(Failure(exc.code, decision.prompt_version, _ms(started)))
            if exc.code != "invalid_model_output" or follow_up:
                decision.error = exc
                return decision
            follow_up = [{"role": "assistant", "content": exc.content or ""},
                         {"role": "user", "content": prompts.enrich_retry(str(exc))}]
            decision.prompt_version = f"{prompts.ENRICH_VERSION}+{prompts.ENRICH_RETRY_VERSION}"
            continue
        break

    decision.chosen, decision.reply, decision.wall_ms = chosen, reply, _ms(started)
    decision.confidence = round(value_probability(reply.tokens, chosen), 4)
    decision.grounding = ground(reply.answer.get("attributes") or [], evidence_fields(title, brand, description, raw))
    return decision


async def classify_product(session: AsyncSession, product: Product, attempt: int = 1,
                           taxonomy_version: str | None = None) -> ProductCategory:
    """Decide the product's category and grounded attributes (decide) and store both with how they were decided.
    A taxonomy upgrade classifies into the next release before it's served.
    Every model call is recorded in enrichment_runs; a failure is recorded, then raised as ModelError."""
    version = taxonomy_version or settings.taxonomy_version
    raw = dict((await session.execute(select(ProductAttribute.name, ProductAttribute.value)
                                      .where(ProductAttribute.product_id == product.id))).all())
    decision = await decide(session, product.title, product.brand, product.description, raw, version)
    session.add_all(_run(product, attempt, f.prompt_version, f.wall_ms, None, f.code) for f in decision.failures)
    if decision.error:
        await session.commit()
        raise decision.error
    reply, chosen = decision.reply, decision.chosen
    assert reply is not None and chosen is not None and decision.grounding is not None

    values = {
        "product_id": product.id,
        "taxonomy_version": version,
        "node_id": None if chosen == NONE else int(chosen),
        "confidence": decision.confidence,
        "candidate_ids": [c.node_id for c in decision.candidates],
        "model": reply.model,
        # The base prompt's version even after a retry: it's what decides whether the answer is current.
        "prompt_version": prompts.ENRICH_VERSION,
        "content_hash": product.content_hash,
        "prompt_tokens": reply.prompt_tokens,
        "output_tokens": reply.output_tokens,
        "total_ms": reply.total_ms,
        "prompt_eval_ms": reply.prompt_eval_ms,
        "eval_ms": reply.eval_ms,
    }
    row = insert(ProductCategory).values(values)
    stmt = row.on_conflict_do_update(
        index_elements=["product_id", "taxonomy_version"],
        set_={k: row.excluded[k] for k in values if k not in ("product_id", "taxonomy_version")}
        | {"created_at": row.excluded.created_at},
    ).returning(ProductCategory)
    category = (await session.scalars(stmt)).one()
    grounding = decision.grounding
    await session.execute(delete(ProductExtractedAttribute).where(ProductExtractedAttribute.product_id == product.id))
    session.add_all(ProductExtractedAttribute(
        product_id=product.id, name=a.name, value=a.value, unit=a.unit, evidence_field=a.evidence_field,
        evidence_start=a.evidence_start, evidence_end=a.evidence_end, evidence_text=a.evidence_text,
        content_hash=product.content_hash, model=reply.model, prompt_version=prompts.ENRICH_VERSION,
    ) for a in grounding.attributes)
    # Same transaction as the category: a crash leaves all of it or none.
    session.add(_run(product, attempt, decision.prompt_version, decision.wall_ms, reply, None, grounding))
    await session.commit()
    for result, found in (("grounded", grounding.attributes), ("ungrounded", grounding.ungrounded),
                          ("unnormalized", grounding.unnormalized)):
        metrics.attributes_extracted.add(len(found), {"result": result})
    return category


def _run(product: Product, attempt: int, prompt_version: str, wall_ms: int, reply: ModelReply | None,
         error_code: str | None, grounding: Grounding | None = None) -> EnrichmentRun:
    return EnrichmentRun(
        product_id=product.id, attempt=attempt, outcome="failed" if error_code else "enriched",
        error_code=error_code, model=reply.model if reply else settings.llm_model, prompt_version=prompt_version,
        content_hash=product.content_hash, prompt_tokens=reply.prompt_tokens if reply else None,
        output_tokens=reply.output_tokens if reply else None, wall_ms=wall_ms,
        ungrounded_attributes=len(grounding.ungrounded) if grounding else None,
        unnormalized_attributes=len(grounding.unnormalized) if grounding else None,
    )


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
