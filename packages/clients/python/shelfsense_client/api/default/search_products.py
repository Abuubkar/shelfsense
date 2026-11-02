from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.search_response import SearchResponse
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    q: str | Unset = "",
    brand: list[str] | Unset = UNSET,
    color: list[str] | Unset = UNSET,
    category_id: list[int] | Unset = UNSET,
    price_min: int | Unset = UNSET,
    price_max: int | Unset = UNSET,
    page_size: int | Unset = 24,
    cursor: str | Unset = UNSET,
    debug: bool | Unset = False,
    parse: bool | Unset = True,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["q"] = q

    json_brand: list[str] | Unset = UNSET
    if not isinstance(brand, Unset):
        json_brand = brand

    params["brand"] = json_brand

    json_color: list[str] | Unset = UNSET
    if not isinstance(color, Unset):
        json_color = color

    params["color"] = json_color

    json_category_id: list[int] | Unset = UNSET
    if not isinstance(category_id, Unset):
        json_category_id = category_id

    params["category_id"] = json_category_id

    params["price_min"] = price_min

    params["price_max"] = price_max

    params["page_size"] = page_size

    params["cursor"] = cursor

    params["debug"] = debug

    params["parse"] = parse

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/search",
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | SearchResponse | None:
    if response.status_code == 200:
        response_200 = SearchResponse.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 503:
        response_503 = Problem.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | SearchResponse]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: str | Unset = "",
    brand: list[str] | Unset = UNSET,
    color: list[str] | Unset = UNSET,
    category_id: list[int] | Unset = UNSET,
    price_min: int | Unset = UNSET,
    price_max: int | Unset = UNSET,
    page_size: int | Unset = 24,
    cursor: str | Unset = UNSET,
    debug: bool | Unset = False,
    parse: bool | Unset = True,
) -> Response[Problem | SearchResponse]:
    """Faceted hybrid search over products

     Matches products lexically (BM25) or by meaning (embedding similarity), after filters. The first 50
    are
    ranked by a hybrid of both scores and then reranked by a cross-encoder; the rest follow in combined
    score order. Facet counts cover the whole result set after all filters. Values within one facet are
    OR'ed; different facets are AND'ed. An empty `q` browses the filtered catalog.

    Args:
        q (str | Unset):  Default: ''.
        brand (list[str] | Unset):
        color (list[str] | Unset):
        category_id (list[int] | Unset):
        price_min (int | Unset):
        price_max (int | Unset):
        page_size (int | Unset):  Default: 24.
        cursor (str | Unset):
        debug (bool | Unset):  Default: False.
        parse (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchResponse]
    """

    kwargs = _get_kwargs(
        q=q,
        brand=brand,
        color=color,
        category_id=category_id,
        price_min=price_min,
        price_max=price_max,
        page_size=page_size,
        cursor=cursor,
        debug=debug,
        parse=parse,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    q: str | Unset = "",
    brand: list[str] | Unset = UNSET,
    color: list[str] | Unset = UNSET,
    category_id: list[int] | Unset = UNSET,
    price_min: int | Unset = UNSET,
    price_max: int | Unset = UNSET,
    page_size: int | Unset = 24,
    cursor: str | Unset = UNSET,
    debug: bool | Unset = False,
    parse: bool | Unset = True,
) -> Problem | SearchResponse | None:
    """Faceted hybrid search over products

     Matches products lexically (BM25) or by meaning (embedding similarity), after filters. The first 50
    are
    ranked by a hybrid of both scores and then reranked by a cross-encoder; the rest follow in combined
    score order. Facet counts cover the whole result set after all filters. Values within one facet are
    OR'ed; different facets are AND'ed. An empty `q` browses the filtered catalog.

    Args:
        q (str | Unset):  Default: ''.
        brand (list[str] | Unset):
        color (list[str] | Unset):
        category_id (list[int] | Unset):
        price_min (int | Unset):
        price_max (int | Unset):
        page_size (int | Unset):  Default: 24.
        cursor (str | Unset):
        debug (bool | Unset):  Default: False.
        parse (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchResponse
    """

    return sync_detailed(
        client=client,
        q=q,
        brand=brand,
        color=color,
        category_id=category_id,
        price_min=price_min,
        price_max=price_max,
        page_size=page_size,
        cursor=cursor,
        debug=debug,
        parse=parse,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    q: str | Unset = "",
    brand: list[str] | Unset = UNSET,
    color: list[str] | Unset = UNSET,
    category_id: list[int] | Unset = UNSET,
    price_min: int | Unset = UNSET,
    price_max: int | Unset = UNSET,
    page_size: int | Unset = 24,
    cursor: str | Unset = UNSET,
    debug: bool | Unset = False,
    parse: bool | Unset = True,
) -> Response[Problem | SearchResponse]:
    """Faceted hybrid search over products

     Matches products lexically (BM25) or by meaning (embedding similarity), after filters. The first 50
    are
    ranked by a hybrid of both scores and then reranked by a cross-encoder; the rest follow in combined
    score order. Facet counts cover the whole result set after all filters. Values within one facet are
    OR'ed; different facets are AND'ed. An empty `q` browses the filtered catalog.

    Args:
        q (str | Unset):  Default: ''.
        brand (list[str] | Unset):
        color (list[str] | Unset):
        category_id (list[int] | Unset):
        price_min (int | Unset):
        price_max (int | Unset):
        page_size (int | Unset):  Default: 24.
        cursor (str | Unset):
        debug (bool | Unset):  Default: False.
        parse (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | SearchResponse]
    """

    kwargs = _get_kwargs(
        q=q,
        brand=brand,
        color=color,
        category_id=category_id,
        price_min=price_min,
        price_max=price_max,
        page_size=page_size,
        cursor=cursor,
        debug=debug,
        parse=parse,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    q: str | Unset = "",
    brand: list[str] | Unset = UNSET,
    color: list[str] | Unset = UNSET,
    category_id: list[int] | Unset = UNSET,
    price_min: int | Unset = UNSET,
    price_max: int | Unset = UNSET,
    page_size: int | Unset = 24,
    cursor: str | Unset = UNSET,
    debug: bool | Unset = False,
    parse: bool | Unset = True,
) -> Problem | SearchResponse | None:
    """Faceted hybrid search over products

     Matches products lexically (BM25) or by meaning (embedding similarity), after filters. The first 50
    are
    ranked by a hybrid of both scores and then reranked by a cross-encoder; the rest follow in combined
    score order. Facet counts cover the whole result set after all filters. Values within one facet are
    OR'ed; different facets are AND'ed. An empty `q` browses the filtered catalog.

    Args:
        q (str | Unset):  Default: ''.
        brand (list[str] | Unset):
        color (list[str] | Unset):
        category_id (list[int] | Unset):
        price_min (int | Unset):
        price_max (int | Unset):
        page_size (int | Unset):  Default: 24.
        cursor (str | Unset):
        debug (bool | Unset):  Default: False.
        parse (bool | Unset):  Default: True.

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | SearchResponse
    """

    return (
        await asyncio_detailed(
            client=client,
            q=q,
            brand=brand,
            color=color,
            category_id=category_id,
            price_min=price_min,
            price_max=price_max,
            page_size=page_size,
            cursor=cursor,
            debug=debug,
            parse=parse,
        )
    ).parsed
