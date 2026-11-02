from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.product_page import ProductPage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    *,
    supplier: str | Unset = UNSET,
    category_id: int | Unset = UNSET,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["supplier"] = supplier

    params["category_id"] = category_id

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/products",
        "params": params,
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> Problem | ProductPage | None:
    if response.status_code == 200:
        response_200 = ProductPage.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | ProductPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    supplier: str | Unset = UNSET,
    category_id: int | Unset = UNSET,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Response[Problem | ProductPage]:
    """Products, oldest first

    Args:
        supplier (str | Unset):
        category_id (int | Unset):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | ProductPage]
    """

    kwargs = _get_kwargs(
        supplier=supplier,
        category_id=category_id,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    supplier: str | Unset = UNSET,
    category_id: int | Unset = UNSET,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Problem | ProductPage | None:
    """Products, oldest first

    Args:
        supplier (str | Unset):
        category_id (int | Unset):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | ProductPage
    """

    return sync_detailed(
        client=client,
        supplier=supplier,
        category_id=category_id,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    supplier: str | Unset = UNSET,
    category_id: int | Unset = UNSET,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Response[Problem | ProductPage]:
    """Products, oldest first

    Args:
        supplier (str | Unset):
        category_id (int | Unset):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | ProductPage]
    """

    kwargs = _get_kwargs(
        supplier=supplier,
        category_id=category_id,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    supplier: str | Unset = UNSET,
    category_id: int | Unset = UNSET,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Problem | ProductPage | None:
    """Products, oldest first

    Args:
        supplier (str | Unset):
        category_id (int | Unset):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | ProductPage
    """

    return (
        await asyncio_detailed(
            client=client,
            supplier=supplier,
            category_id=category_id,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
