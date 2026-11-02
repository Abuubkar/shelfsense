"""GraphQL for the UI's reads: product(id), products and search, as Relay connections. Resolvers call the same
service functions as REST, so there is no business logic here. The schema is printed to contracts/schema.graphql
(`make codegen`); a test fails if they drift."""

import uuid
from collections.abc import AsyncIterator

import strawberry
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from strawberry import relay
from strawberry.fastapi import BaseContext, GraphQLRouter

from shelfsense_api import schemas, search, service
from shelfsense_api.db import get_session


class Context(BaseContext):
    def __init__(self, session: AsyncSession):
        super().__init__()
        self.session = session


async def get_context(session: AsyncSession = Depends(get_session)) -> AsyncIterator[Context]:
    yield Context(session)


@strawberry.type(description="An amount as an integer count of the currency's minor unit, plus its ISO 4217 code.")
class Money:
    amount_minor: int
    currency: str

    @classmethod
    def of(cls, money: schemas.Money) -> "Money":
        return cls(amount_minor=money.amount_minor, currency=money.currency)


@strawberry.type(description="A product's category in one taxonomy release, and how it was decided.")
class Category:
    taxonomy_version: str
    node_id: int | None
    full_path: str | None
    confidence: float
    model: str
    prompt_version: str


@strawberry.type
class Attribute:
    name: str
    value: str


@strawberry.type
class Product:
    id: uuid.UUID
    supplier: str
    supplier_sku: str
    title: str
    description: str | None
    brand: str | None
    gtin: str | None
    price: Money
    attributes: list[Attribute]
    category: Category | None

    @classmethod
    def of(cls, p: schemas.Product) -> "Product":
        c = p.category
        return cls(
            id=p.id, supplier=p.supplier, supplier_sku=p.supplier_sku, title=p.title, description=p.description,
            brand=p.brand, gtin=p.gtin, price=Money.of(p.price),
            attributes=[Attribute(name=k, value=v) for k, v in sorted(p.attributes.items())],
            category=None if c is None else Category(
                taxonomy_version=c.taxonomy_version, node_id=c.node_id, full_path=c.full_path,
                confidence=c.confidence, model=c.model, prompt_version=c.prompt_version),
        )


@strawberry.type
class Score:
    stage: str
    value: float


@strawberry.type(description="One search result. `scores` is empty unless the search asked for debug.")
class SearchResult:
    id: uuid.UUID
    rank: int
    title: str
    brand: str | None
    price: Money
    color: str | None
    size: str | None
    category_id: int | None
    category_path: str | None
    stage: str | None
    scores: list[Score]

    @classmethod
    def of(cls, item: schemas.SearchItem) -> "SearchResult":
        d = item.debug
        return cls(
            id=item.id, rank=item.rank, title=item.title, brand=item.brand, price=Money.of(item.price),
            color=item.color, size=item.size, category_id=item.category_id, category_path=item.category_path,
            stage=d.stage.value if d else None,
            scores=[Score(stage=k, value=v) for k, v in d.scores.items()] if d else [],
        )


@strawberry.type
class FacetValue:
    value: str
    label: str
    count: int


@strawberry.type
class Facet:
    name: str
    values: list[FacetValue]


@strawberry.input(description="Facet filters: values within one field are OR'ed, fields are AND'ed.")
class SearchFilters:
    brand: list[str] = strawberry.field(default_factory=list)
    color: list[str] = strawberry.field(default_factory=list)
    category_id: list[int] = strawberry.field(default_factory=list)
    price_min: int | None = strawberry.field(default=None, description="Inclusive, in minor units.")
    price_max: int | None = strawberry.field(default=None, description="Inclusive, in minor units.")


# Our nodes aren't relay.Node: cursors are signed positions, not global IDs.
@strawberry.type
class ProductConnection(relay.Connection[Product]):  # type: ignore[type-var]
    pass


@strawberry.type
class SearchConnection(relay.Connection[SearchResult]):  # type: ignore[type-var]
    total: int
    facets: list[Facet]


def _page_info(cursors: list[str], after: str | None, has_next: bool) -> relay.PageInfo:
    return relay.PageInfo(has_next_page=has_next, has_previous_page=after is not None,
                          start_cursor=cursors[0] if cursors else None, end_cursor=cursors[-1] if cursors else None)


def _check_first(first: int, maximum: int) -> None:
    if not 1 <= first <= maximum:
        raise ValueError(f"first must be between 1 and {maximum}")


@strawberry.type
class Query:
    @strawberry.field
    async def product(self, info: strawberry.Info[Context], id: uuid.UUID) -> Product | None:
        try:
            return Product.of(await service.get_product(info.context.session, id))
        except schemas.ApiProblem as exc:
            if exc.problem.status == 404:
                return None
            raise

    @strawberry.field(description="Products, oldest first.")
    async def products(self, info: strawberry.Info[Context], first: int = 25, after: str | None = None,
                       supplier: str | None = None, category_id: int | None = None) -> ProductConnection:
        _check_first(first, 100)
        page = await service.list_products(info.context.session, first, after, supplier, category_id)
        # Keyset cursors from the service are page-level; each edge gets the cursor that resumes after it.
        cursors = [service.product_cursor(p.id, supplier, category_id) for p in page.items]
        return ProductConnection(
            edges=[relay.Edge(node=Product.of(p), cursor=c) for p, c in zip(page.items, cursors, strict=True)],  # type: ignore[type-var]
            page_info=_page_info(cursors, after, page.next_cursor is not None),
        )

    @strawberry.field(description="Faceted hybrid search; the same results and order as GET /v1/search.")
    async def search(self, info: strawberry.Info[Context], query: str = "", filters: SearchFilters | None = None,
                     first: int = 24, after: str | None = None, debug: bool = False) -> SearchConnection:
        _check_first(first, 48)
        f = filters or SearchFilters()
        response, cursors = await service.search_page(
            info.context.session, search.client(), query,
            search.Filters(tuple(f.brand), tuple(f.color), tuple(f.category_id), f.price_min, f.price_max),
            first, after, debug,
        )
        return SearchConnection(
            edges=[relay.Edge(node=SearchResult.of(i), cursor=c) for i, c in zip(response.items, cursors, strict=True)],  # type: ignore[type-var]
            page_info=_page_info(cursors, after, response.next_cursor is not None),
            total=response.total,
            facets=[Facet(name=fa.name.value, values=[FacetValue(value=v.value, label=v.label, count=v.count)
                                                      for v in fa.values]) for fa in response.facets],
        )


schema = strawberry.Schema(query=Query)
graphql_router: GraphQLRouter[Context, None] = GraphQLRouter(schema, context_getter=get_context)
