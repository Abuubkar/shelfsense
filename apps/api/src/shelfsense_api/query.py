"""Query understanding: a shopper's search text as keywords plus filters (docs/adr/0014).

1. A rules fast path: a query with no price, size, colour, gender, material or negation words goes straight to
   search as keywords. No model call.
2. Otherwise the cache (Redis, 24 h, keyed on the normalized query, the prompt and the model).
3. Otherwise the small query model, structured output, within settings.query_timeout_s. A timeout or any model
   failure degrades to plain hybrid search with the whole query as keywords; degraded parses aren't cached.
"""

import dataclasses
import hashlib
import logging
import re
import time
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any, Literal

import redis.asyncio as redis
from pydantic import BaseModel, Field, ValidationError

from shelfsense_api import prompts
from shelfsense_api.llm import ModelError, chat_json, query_model
from shelfsense_api.normalize import (
    ALPHA_SIZE_WORDS,
    BASE_COLORS,
    COLOR_WORDS,
    GENDER_WORDS,
    KNOWN_MATERIALS,
    normalize_color,
    normalize_material,
)
from shelfsense_api.settings import settings

log = logging.getLogger(__name__)

Source = Literal["rules", "cache", "llm", "degraded"]

_PRICE = r"\$\s*\d|\d\s*(?:usd|dollars?|bucks)\b|\b(?:under|below|less than|cheaper than|over|above|more than|between|max|budget)\b"
_SIZE = r"\bsize\b|\b(?:us|uk|eu|eur)\s*\d|\b\d{1,2}(?:\.5)?\s*(?:us|uk|eu)\b"
_NEGATION = r"\b(?:not|no|without|non|except|excluding)\b|\bnon-"


def _words_pattern(words: set[str]) -> str:
    return r"\b(?:" + "|".join(sorted((re.escape(w) for w in words), key=len, reverse=True)) + r")\b"


_SIGNALS = re.compile("|".join([
    _PRICE, _SIZE, _NEGATION,
    _words_pattern({w for w in COLOR_WORDS if len(w) > 2}),
    # One-letter codes ("m", "w") and "all"/"adult" would fire on ordinary words.
    _words_pattern({w for w in GENDER_WORDS if len(w) > 1} - {"all", "adult"} | {"men's", "women's", "ladies'"}),
    _words_pattern(set(KNOWN_MATERIALS) | {"merino", "aluminium", "poly"}),
    _words_pattern({s for s in ALPHA_SIZE_WORDS if len(s) > 2}),
]), re.IGNORECASE)


class Size(BaseModel):
    system: Literal["US", "UK", "EU", "alpha"]
    value: str


class ParsedFilters(BaseModel):
    price_min: int | None = None  # minor units
    price_max: int | None = None
    colors: list[str] = []
    exclude_colors: list[str] = []
    materials: list[str] = []
    exclude_materials: list[str] = []
    gender: Literal["men", "women", "unisex", "kids"] | None = None
    size: Size | None = None


class QueryParse(BaseModel):
    source: Source
    keywords: str
    category_hint: str | None = None
    filters: ParsedFilters = Field(default_factory=ParsedFilters)
    # Set by search when the parsed price range matched nothing and was dropped.
    price_relaxed: bool = False
    ms: int = 0


def needs_model(q: str) -> bool:
    """True when the query has words the rules can't turn into filters themselves: a price, size, colour,
    gender, material or negation. Everything else is plain keywords."""
    return bool(_SIGNALS.search(q))


def normalize_query(q: str) -> str:
    """The cache key's text: Unicode-compatible forms folded, lowercase, single spaces, no surrounding punctuation.
    "  Women's  BOOTS!" and "women's boots" share a parse."""
    text = unicodedata.normalize("NFKC", q).lower()
    text = text.replace("’", "'")
    return " ".join(text.split()).strip(" .,!?;:")


def query_schema() -> dict[str, Any]:
    nullable_number = {"anyOf": [{"type": "number"}, {"type": "null"}]}
    strings = {"type": "array", "items": {"type": "string"}}
    colors = {"type": "array", "items": {"type": "string", "enum": list(BASE_COLORS)}}
    return {
        "type": "object",
        "properties": {
            "keywords": {"type": "string"},
            "category_hint": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "filters": {"type": "object", "properties": {
                "price_min": nullable_number, "price_max": nullable_number,
                "colors": colors, "exclude_colors": colors, "materials": strings, "exclude_materials": strings,
                "gender": {"anyOf": [{"type": "string", "enum": ["men", "women", "unisex", "kids"]}, {"type": "null"}]},
                "size": {"anyOf": [{"type": "object", "properties": {
                    "system": {"type": "string", "enum": ["US", "UK", "EU", "alpha"]}, "value": {"type": "string"}},
                    "required": ["system", "value"], "additionalProperties": False}, {"type": "null"}]},
            }, "required": ["price_min", "price_max", "colors", "exclude_colors", "materials", "exclude_materials",
                            "gender", "size"], "additionalProperties": False},
        },
        "required": ["keywords", "category_hint", "filters"],
        "additionalProperties": False,
    }


def _cache_key(normalized: str) -> str:
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:32]
    return f"qp:{prompts.QUERY_VERSION}:{settings.query_model}:{digest}"


_redis: redis.Redis | None = None


def cache() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, socket_timeout=0.2, socket_connect_timeout=0.2)
    return _redis


async def understand(q: str) -> QueryParse:
    """The parse of a search query. Never raises: a slow or failing model, or a cache that's down, only makes
    the parse plainer."""
    started = time.perf_counter()
    text = " ".join(q.split())
    if not needs_model(text):
        return QueryParse(source="rules", keywords=text)

    key = _cache_key(normalize_query(text))
    try:
        cached = await cache().get(key) if settings.query_cache_enabled else None
        if cached:
            parse = QueryParse.model_validate_json(cached)
            return parse.model_copy(update={"source": "cache", "ms": _ms(started)})
    except (redis.RedisError, OSError, ValidationError) as exc:
        log.warning("query cache read failed: %r", exc)

    try:
        reply = await chat_json(prompts.QUERY_SYSTEM, text, query_schema(), config=query_model())
        parse = _from_reply(reply.answer, text)
    except (ModelError, ValidationError) as exc:
        log.info("query parse degraded for %r: %s", text, exc)
        return QueryParse(source="degraded", keywords=text, ms=_ms(started))
    parse.ms = _ms(started)
    if not settings.query_cache_enabled:
        return parse
    try:
        await cache().set(key, parse.model_dump_json(), ex=settings.query_cache_ttl_s)
    except (redis.RedisError, OSError) as exc:
        log.warning("query cache write failed: %r", exc)
    return parse


async def warm() -> None:
    """Load the query model before the first shopper needs it: a cold load takes longer than the time limit."""
    try:
        await chat_json(prompts.QUERY_SYSTEM, "red socks", query_schema(),
                        config=dataclasses.replace(query_model(), timeout_s=60))
        log.info("query model %s warm", settings.query_model)
    except ModelError as exc:
        log.warning("query model warm-up failed: %s", exc)


def _from_reply(answer: dict[str, Any], text: str) -> QueryParse:
    """A model reply as a parse, values normalized like product attributes so filters match indexed values."""
    raw = answer.get("filters") or {}
    size = raw.get("size")
    # The small model writes "size 8" as a letter size; a number without a system is a US size (the prompt's rule).
    if size and size.get("system") == "alpha" and re.fullmatch(r"\d{1,2}(\.5)?", str(size.get("value", ""))):
        size = {**size, "system": "US"}
    price_min, price_max = _minor(raw.get("price_min")) or None, _minor(raw.get("price_max"))
    # The small model sometimes turns "under $100" into 100-100: one bound, by the query's own words.
    if price_min is not None and price_min == price_max:
        if re.search(r"\b(under|below|less than|cheaper than|up to|max)\b", text, re.IGNORECASE):
            price_min = None
        elif re.search(r"\b(over|above|more than|at least|from)\b", text, re.IGNORECASE):
            price_max = None
    filters = ParsedFilters(
        # A minimum of 0 is no minimum: the model fills it in for "under $X".
        price_min=price_min, price_max=price_max,
        colors=_unique(normalize_color(c) for c in raw.get("colors") or []),
        exclude_colors=_unique(normalize_color(c) for c in raw.get("exclude_colors") or []),
        materials=_unique(normalize_material(m) for m in raw.get("materials") or []),
        exclude_materials=_unique(normalize_material(m) for m in raw.get("exclude_materials") or []),
        gender=raw.get("gender"),
        size=Size.model_validate(size) if size else None,
    )
    keywords = " ".join(str(answer.get("keywords") or "").split()) or text
    hint = answer.get("category_hint")
    return QueryParse(source="llm", keywords=keywords, category_hint=hint or None, filters=filters)


def _minor(amount: Any) -> int | None:
    """Dollars from the model as integer cents. Money never stays a float (docs/adr/0003)."""
    if amount is None:
        return None
    try:
        value = Decimal(str(amount))
    except InvalidOperation:
        return None
    return int(value * 100) if value >= 0 else None


def _unique(values: Any) -> list[str]:
    return list(dict.fromkeys(v for v in values if v))


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
