"""Request and response shapes for the REST API. contracts/openapi.yaml is the source of truth; these mirror it,
and `make contract-check` fails if they drift in a way that would break a client."""

import enum
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ProblemCode(enum.StrEnum):
    INVALID_REQUEST = "invalid_request"
    NOT_FOUND = "not_found"
    INVALID_CURSOR = "invalid_cursor"
    CURSOR_EXPIRED = "cursor_expired"
    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_TIMEOUT = "model_timeout"
    SEARCH_UNAVAILABLE = "search_unavailable"
    FEED_NOT_UPLOADED = "feed_not_uploaded"
    BACKLOG_FULL = "backlog_full"
    REDRIVE_IN_PROGRESS = "redrive_in_progress"
    QUEUE_UNAVAILABLE = "queue_unavailable"


class Problem(BaseModel):
    """RFC 9457 problem details, plus our stable `code`."""

    model_config = ConfigDict(use_enum_values=True)

    type: str
    title: str
    status: int
    detail: str | None = None
    code: ProblemCode


class ApiProblem(Exception):
    """Raised anywhere in request handling (REST or GraphQL); REST renders it as application/problem+json."""

    def __init__(self, status: int, code: ProblemCode, title: str, detail: str | None = None,
                 headers: dict[str, str] | None = None):
        super().__init__(f"{status} {code}: {detail or title}")
        self.headers = headers
        self.problem = Problem(type=f"https://github.com/Abuubkar/shelfsense/blob/main/docs/problems.md#{code}",
                               title=title, status=status, detail=detail, code=code)


class Money(BaseModel):
    amount_minor: int
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class FeedUploadRequest(BaseModel):
    supplier: str
    file_name: str = Field(min_length=1, max_length=200)


class FeedUpload(BaseModel):
    feed_id: uuid.UUID
    upload_url: str
    expires_at: datetime


class Rejection(BaseModel):
    row_number: int
    reason_code: str
    detail: str
    excerpt: str


class ImportResult(BaseModel):
    feed_id: uuid.UUID
    file_sha256: str
    rows: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int
    enqueued: int
    rejections: list[Rejection]


class RejectionPage(BaseModel):
    items: list[Rejection]
    next_cursor: str | None


class Category(BaseModel):
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


class ExtractedAttribute(BaseModel):
    name: str
    value: str
    unit: str | None
    evidence_field: str
    evidence_start: int
    evidence_end: int
    evidence_text: str


class Product(BaseModel):
    id: uuid.UUID
    supplier: str
    supplier_sku: str
    title: str
    description: str | None
    brand: str | None
    gtin: str | None
    price: Money
    attributes: dict[str, str]
    color_base: str | None
    material: str | None
    gender: str | None
    size_system: str | None
    size_value: str | None
    extracted_attributes: list[ExtractedAttribute]
    category: Category | None


class ProductPage(BaseModel):
    items: list[Product]
    next_cursor: str | None


class SearchStage(enum.StrEnum):
    HEAD = "head"
    TAIL = "tail"


class SearchItemDebug(BaseModel):
    stage: SearchStage
    scores: dict[str, float]


class SearchItem(BaseModel):
    id: uuid.UUID
    rank: int
    title: str
    brand: str | None
    price: Money
    color: str | None
    size: str | None
    category_id: int | None
    category_path: str | None
    debug: SearchItemDebug | None = None


class FacetName(enum.StrEnum):
    BRAND = "brand"
    COLOR = "color"
    CATEGORY_ID = "category_id"
    PRICE = "price"


class FacetValue(BaseModel):
    value: str
    label: str
    count: int


class Facet(BaseModel):
    name: FacetName
    values: list[FacetValue]


class SearchDebug(BaseModel):
    timings_ms: dict[str, int]
    head_size: int
    hybrid_weights: list[float]
    knn_min_score: float


class ParsedSize(BaseModel):
    system: Literal["US", "UK", "EU", "alpha"]
    value: str


class ParsedFilters(BaseModel):
    price_min: int | None
    price_max: int | None
    colors: list[str]
    exclude_colors: list[str]
    materials: list[str]
    exclude_materials: list[str]
    gender: str | None
    size: ParsedSize | None


class QueryParse(BaseModel):
    source: Literal["rules", "cache", "llm", "degraded"]
    keywords: str
    category_hint: str | None
    filters: ParsedFilters
    price_relaxed: bool
    ms: int


class SearchResponse(BaseModel):
    items: list[SearchItem]
    total: int
    facets: list[Facet]
    next_cursor: str | None
    debug: SearchDebug | None = None
    query_parse: QueryParse | None = None


class WorkQueue(enum.StrEnum):
    ENRICH = "enrich"
    INDEX = "index"


class RedriveRequest(BaseModel):
    dry_run: bool = True


class RedriveResult(BaseModel):
    queue: WorkQueue
    dry_run: bool
    messages: int
    reasons: dict[str, int]
    task_handle: str | None
