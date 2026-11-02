"""Queue message bodies. These models are the source of the JSON Schemas in contracts/messages/ (`make codegen`).

Compatibility: adding an optional field keeps schema_version; anything an old consumer would misread bumps it.
Consumers ignore fields they don't know, and refuse a schema_version newer than theirs.
"""

import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shelfsense_api.queue import PermanentError

SCHEMA_VERSION = 1

# One message's products are processed together and acked together.
MAX_ENRICH_IDS = 50
MAX_INDEX_IDS = 500


class EnrichRequest(BaseModel):
    """Classify these products. Sent by a feed commit, and by the enrich worker to resubmit transient failures."""

    model_config = ConfigDict(extra="ignore", title="EnrichRequest")

    schema_version: int = SCHEMA_VERSION
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_ENRICH_IDS)
    # 1 for the first delivery; each resubmission of transient failures adds one.
    attempt: int = Field(default=1, ge=1)
    feed_id: uuid.UUID | None = None


class IndexRequest(BaseModel):
    """Index these products from Postgres into OpenSearch. Sent by the enrich worker for products it enriched."""

    model_config = ConfigDict(extra="ignore", title="IndexRequest")

    schema_version: int = SCHEMA_VERSION
    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=MAX_INDEX_IDS)
    attempt: int = Field(default=1, ge=1)


def parse[M: BaseModel](model: type[M], body: str) -> M:
    """A message body as `model`, or PermanentError: a body that doesn't parse never will."""
    try:
        data: Any = json.loads(body)
    except ValueError as exc:
        raise PermanentError("invalid_message", f"not JSON: {exc}") from None
    if isinstance(data, dict) and isinstance(data.get("schema_version"), int) and data["schema_version"] > SCHEMA_VERSION:
        raise PermanentError("unsupported_schema_version",
                             f"schema_version {data['schema_version']}, this consumer reads up to {SCHEMA_VERSION}")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        raise PermanentError("invalid_message", str(exc).splitlines()[0]) from None


def json_schemas() -> dict[str, dict[str, Any]]:
    """File name -> JSON Schema, for contracts/messages/."""
    return {f"{m.__name__}.schema.json": m.model_json_schema() for m in (EnrichRequest, IndexRequest)}
