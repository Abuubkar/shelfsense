"""Supplier feed files: validating rows and importing them into products."""

import csv
import hashlib
import json
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError
from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api.db import FeedRejection, Product, Supplier

# Columns with a place on the product; any other column is kept as-is in attributes_json.
PRODUCT_COLUMNS = ("sku", "title", "description", "brand", "gtin", "price", "currency")
GTIN_LENGTHS = (8, 12, 13, 14)
UPSERT_BATCH = 500


def gtin_is_valid(gtin: str) -> bool:
    """GS1 check digit: from the right, excluding the check digit, weights alternate 3, 1, 3, ..."""
    if len(gtin) not in GTIN_LENGTHS or not gtin.isdigit():
        return False
    body, check = gtin[:-1], int(gtin[-1])
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def _blank_to_none(value: Any) -> Any:
    return value.strip() or None if isinstance(value, str) else value


class FeedRow(BaseModel):
    """One valid feed row. Validators raise errors whose type is the rejection's reason code."""

    sku: str
    title: str
    description: str | None = None
    brand: str | None = None
    gtin: str | None = None
    price_minor: int = Field(validation_alias="price")
    currency: str = "USD"
    attributes: dict[str, str] = {}

    @field_validator("sku", "title", mode="before")
    @classmethod
    def required_text(cls, value: Any, info: Any) -> str:
        value = _blank_to_none(value)
        if value is None:
            raise PydanticCustomError(f"missing_{info.field_name}", "{field} is empty", {"field": info.field_name})
        return " ".join(value.split())

    @field_validator("description", "brand", mode="before")
    @classmethod
    def optional_text(cls, value: Any) -> str | None:
        return _blank_to_none(value)

    @field_validator("gtin", mode="before")
    @classmethod
    def valid_gtin(cls, value: Any) -> str | None:
        value = _blank_to_none(value)
        if value is None:
            return None
        # Suppliers space or hyphenate GTINs as printed on the barcode ("0 12345 67890 5").
        digits = re.sub(r"[\s-]", "", value)
        if not gtin_is_valid(digits):
            raise PydanticCustomError("invalid_gtin", "GTIN '{gtin}' fails the GS1 check digit or length", {"gtin": value})
        return digits

    @field_validator("price_minor", mode="before")
    @classmethod
    def price_in_minor_units(cls, value: Any) -> int:
        raw = _blank_to_none(value)
        try:
            amount = Decimal((raw or "").replace("$", "").replace(",", ""))
        except InvalidOperation:
            raise PydanticCustomError("invalid_price", "price '{price}' is not a number", {"price": raw}) from None
        if amount < 0:
            raise PydanticCustomError("negative_price", "price {price} is negative", {"price": raw})
        minor = amount * 100
        if minor != minor.to_integral_value():
            raise PydanticCustomError("invalid_price", "price {price} has more than 2 decimals", {"price": raw})
        return int(minor)

    @field_validator("currency", mode="before")
    @classmethod
    def iso_currency(cls, value: Any) -> str:
        value = (_blank_to_none(value) or "USD").upper()
        if not re.fullmatch(r"[A-Z]{3}", value):
            raise PydanticCustomError("invalid_currency", "currency '{currency}' is not an ISO 4217 code", {"currency": value})
        return str(value)

    def content_hash(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(), sort_keys=True).encode()).hexdigest()


@dataclass
class Rejection:
    row_number: int
    reason_code: str
    detail: str
    excerpt: str


def validate_row(row_number: int, header: list[str], values: list[str]) -> FeedRow | Rejection:
    """A feed row as a FeedRow, or the reason it can't be one. `values` were decoded with surrogateescape, so
    bytes that aren't UTF-8 show up as lone surrogates instead of failing the whole file."""
    excerpt = _excerpt(values)
    if any(re.search(r"[\udc80-\udcff]", v) for v in values):
        return Rejection(row_number, "invalid_encoding", "row contains bytes that are not valid UTF-8", excerpt)
    if len(values) != len(header):
        detail = f"{len(values)} fields, header has {len(header)}"
        return Rejection(row_number, "wrong_column_count", detail, excerpt)

    raw = dict(zip(header, values, strict=True))
    attributes = {k: v.strip() for k, v in raw.items() if k not in PRODUCT_COLUMNS and v.strip()}
    try:
        return FeedRow.model_validate({**{k: raw.get(k) for k in PRODUCT_COLUMNS}, "attributes": attributes})
    except ValidationError as exc:
        errors = exc.errors()
        return Rejection(row_number, errors[0]["type"], "; ".join(e["msg"] for e in errors), excerpt)


@dataclass
class ImportResult:
    file_sha256: str
    rows: int = 0
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0
    rejections: list[Rejection] = field(default_factory=list)


async def import_file(session: AsyncSession, path: Path, supplier_code: str) -> ImportResult:
    """Stream a feed CSV into products. Valid rows are upserted on (supplier, SKU) only when their content hash
    changed; invalid rows go to feed_rejections. Importing the same file twice changes nothing."""
    supplier_id = await _supplier_id(session, supplier_code)
    result = ImportResult(file_sha256=_sha256(path))
    seen_skus: set[str] = set()
    batch: list[FeedRow] = []

    with path.open(encoding="utf-8-sig", errors="surrogateescape", newline="") as f:
        reader = csv.reader(f)
        header = [h.strip().lower() for h in next(reader)]
        # Spreadsheet row numbers: the header is row 1. A quoted field may span lines, so this isn't the line number.
        for row_number, values in enumerate(reader, start=2):
            result.rows += 1
            outcome = validate_row(row_number, header, values)
            if isinstance(outcome, FeedRow) and outcome.sku in seen_skus:
                outcome = Rejection(row_number, "duplicate_sku", f"SKU {outcome.sku!r} appears earlier in the file",
                                    _excerpt(values))
            if isinstance(outcome, Rejection):
                result.rejections.append(outcome)
                continue
            seen_skus.add(outcome.sku)
            batch.append(outcome)
            if len(batch) == UPSERT_BATCH:
                await _upsert(session, supplier_id, batch, result)
                batch = []
    if batch:
        await _upsert(session, supplier_id, batch, result)

    if result.rejections:
        await session.execute(
            insert(FeedRejection)
            .values([{"supplier_id": supplier_id, "file_name": path.name, "file_sha256": result.file_sha256,
                      **r.__dict__} for r in result.rejections])
            .on_conflict_do_nothing(index_elements=["file_sha256", "row_number"])
        )
    await session.commit()
    return result


async def _supplier_id(session: AsyncSession, code: str) -> Any:
    await session.execute(insert(Supplier).values(code=code).on_conflict_do_nothing(index_elements=["code"]))
    return await session.scalar(select(Supplier.id).where(Supplier.code == code))


async def _upsert(session: AsyncSession, supplier_id: Any, batch: list[FeedRow], result: ImportResult) -> None:
    rows = [
        {"supplier_id": supplier_id, "supplier_sku": r.sku, "title": r.title, "description": r.description,
         "brand": r.brand, "gtin": r.gtin, "price_minor": r.price_minor, "currency": r.currency,
         "attributes_json": r.attributes, "content_hash": r.content_hash()}
        for r in batch
    ]
    stmt = insert(Product).values(rows)
    updatable = [k for k in rows[0] if k not in ("supplier_id", "supplier_sku")]
    stmt = stmt.on_conflict_do_update(
        index_elements=["supplier_id", "supplier_sku"],
        set_={**{k: stmt.excluded[k] for k in updatable}, "updated_at": literal_column("now()")},
        where=Product.content_hash != stmt.excluded.content_hash,
    ).returning(literal_column("xmax = 0"))  # xmax is 0 on a freshly inserted row, set on an updated one
    written = (await session.scalars(stmt)).all()
    result.inserted += sum(written)
    result.updated += len(written) - sum(written)
    result.unchanged += len(batch) - len(written)


def _excerpt(values: list[str]) -> str:
    """The row as text for a person to find it, with undecodable bytes shown as U+FFFD."""
    return ",".join(values).encode("utf-8", "surrogateescape").decode("utf-8", "replace")[:160]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
