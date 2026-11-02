import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.exceptions import HTTPException as StarletteHTTPException

from shelfsense_api import schemas, search, service
from shelfsense_api.db import get_session
from shelfsense_api.graphql import graphql_router
from shelfsense_api.schemas import ApiProblem, Problem, ProblemCode


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    yield
    await search.client().close()


app = FastAPI(title="Shelfsense", version="0.4.0", lifespan=lifespan)
app.include_router(graphql_router, prefix="/graphql")

PROBLEM_JSON = "application/problem+json"
Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]


def problem_response(problem: Problem, headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(problem.model_dump(mode="json"), status_code=problem.status, media_type=PROBLEM_JSON,
                        headers=headers)


@app.exception_handler(ApiProblem)
async def api_problem_handler(_: Request, exc: ApiProblem) -> JSONResponse:
    return problem_response(exc.problem, exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
    details = "; ".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())
    return problem_response(ApiProblem(400, ProblemCode.INVALID_REQUEST, "Invalid request", details).problem)


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = ProblemCode.NOT_FOUND if exc.status_code == 404 else ProblemCode.INVALID_REQUEST
    return problem_response(ApiProblem(exc.status_code, code, str(exc.detail)).problem)


def _problems(*statuses: int) -> dict[int | str, dict[str, Any]]:
    responses: dict[int | str, dict[str, Any]] = {
        status: {"model": Problem, "description": "An RFC 9457 problem."} for status in statuses
    }
    if 429 in responses:
        responses[429]["headers"] = {"Retry-After": {"description": "Seconds to wait before retrying.",
                                                     "schema": {"type": "integer"}}}
    return responses


@app.post("/v1/feeds", operation_id="createFeedUpload", status_code=201, responses=_problems(400, 503))
async def create_feed_upload(body: schemas.FeedUploadRequest, session: Session) -> schemas.FeedUpload:
    return await service.create_feed_upload(session, body.supplier, body.file_name)


@app.post("/v1/feeds/{feed_id}:commit", operation_id="commitFeed", responses=_problems(404, 409, 429, 503))
async def commit_feed(feed_id: uuid.UUID, session: Session) -> schemas.ImportResult:
    return await service.commit_feed(session, feed_id)


@app.get("/v1/feeds/{feed_id}/rejections", operation_id="listFeedRejections", responses=_problems(400, 404))
async def list_feed_rejections(feed_id: uuid.UUID, session: Session, limit: Limit = 25,
                               cursor: str | None = None) -> schemas.RejectionPage:
    return await service.list_rejections(session, feed_id, limit, cursor)


@app.get("/v1/products", operation_id="listProducts", responses=_problems(400))
async def list_products(session: Session, supplier: str | None = None, category_id: int | None = None,
                        limit: Limit = 25, cursor: str | None = None) -> schemas.ProductPage:
    return await service.list_products(session, limit, cursor, supplier, category_id)


@app.get("/v1/products/{product_id}", operation_id="getProduct", responses=_problems(404))
async def get_product(product_id: uuid.UUID, session: Session) -> schemas.Product:
    return await service.get_product(session, product_id)


@app.post("/v1/products/{product_id}:enrich", operation_id="enrichProduct", responses=_problems(404, 502, 504))
async def enrich_product(product_id: uuid.UUID, session: Session) -> schemas.Product:
    return await service.enrich_product(session, product_id)


@app.get("/v1/search", operation_id="searchProducts", responses=_problems(400, 503))
async def search_products(
    session: Session,
    q: Annotated[str, Query(max_length=200)] = "",
    brand: Annotated[list[str], Query()] = [],  # noqa: B006  # FastAPI copies query defaults per request
    color: Annotated[list[str], Query()] = [],  # noqa: B006
    category_id: Annotated[list[int], Query()] = [],  # noqa: B006
    price_min: Annotated[int | None, Query(ge=0)] = None,
    price_max: Annotated[int | None, Query(ge=0)] = None,
    page_size: Annotated[int, Query(ge=1, le=48)] = 24,
    cursor: str | None = None,
    debug: bool = False,
) -> schemas.SearchResponse:
    filters = search.Filters(tuple(brand), tuple(color), tuple(category_id), price_min, price_max)
    return await service.search_products(session, search.client(), q, filters, page_size, cursor, debug)


@app.post("/v1/admin/dlq/{queue}/redrive", operation_id="redriveDeadLetters", responses=_problems(400, 409, 503))
async def redrive_dead_letters(queue: schemas.WorkQueue, body: schemas.RedriveRequest,
                               session: Session) -> schemas.RedriveResult:
    return await service.redrive(session, queue, body.dry_run)


_default_openapi = app.openapi


def openapi_with_problem_json() -> dict[str, Any]:
    """FastAPI documents every response model as application/json and adds a 422 validation response to each
    route. Ours differ: errors are application/problem+json, and validation failures are 400 problems."""
    if app.openapi_schema is None:
        schema = _default_openapi()
        for operations in schema["paths"].values():
            for operation in operations.values():
                responses = operation.get("responses", {})
                if "HTTPValidationError" in str(responses.get("422", "")):
                    del responses["422"]
                for status, response in responses.items():
                    content = response.get("content", {})
                    if int(status) >= 400 and "application/json" in content:
                        response["content"] = {PROBLEM_JSON: content["application/json"]}
        for unused in ("HTTPValidationError", "ValidationError"):
            schema["components"]["schemas"].pop(unused, None)
    assert app.openapi_schema is not None  # FastAPI's openapi() stores the schema it builds
    return app.openapi_schema


app.openapi = openapi_with_problem_json  # type: ignore[method-assign]  # FastAPI's documented way to customize the schema
