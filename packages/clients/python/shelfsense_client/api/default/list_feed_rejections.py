from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.problem import Problem
from ...models.rejection_page import RejectionPage
from ...types import UNSET, Response, Unset


def _get_kwargs(
    feed_id: UUID,
    *,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> dict[str, Any]:

    params: dict[str, Any] = {}

    params["limit"] = limit

    params["cursor"] = cursor

    params = {k: v for k, v in params.items() if v is not UNSET and v is not None}

    _kwargs: dict[str, Any] = {
        "method": "get",
        "url": "/v1/feeds/{feed_id}/rejections".format(
            feed_id=quote(str(feed_id), safe=""),
        ),
        "params": params,
    }

    return _kwargs


def _parse_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Problem | RejectionPage | None:
    if response.status_code == 200:
        response_200 = RejectionPage.from_dict(response.json())

        return response_200

    if response.status_code == 400:
        response_400 = Problem.from_dict(response.json())

        return response_400

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[Problem | RejectionPage]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Response[Problem | RejectionPage]:
    """Rows of a feed that failed validation, in row order

    Args:
        feed_id (UUID):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RejectionPage]
    """

    kwargs = _get_kwargs(
        feed_id=feed_id,
        limit=limit,
        cursor=cursor,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Problem | RejectionPage | None:
    """Rows of a feed that failed validation, in row order

    Args:
        feed_id (UUID):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RejectionPage
    """

    return sync_detailed(
        feed_id=feed_id,
        client=client,
        limit=limit,
        cursor=cursor,
    ).parsed


async def asyncio_detailed(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Response[Problem | RejectionPage]:
    """Rows of a feed that failed validation, in row order

    Args:
        feed_id (UUID):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[Problem | RejectionPage]
    """

    kwargs = _get_kwargs(
        feed_id=feed_id,
        limit=limit,
        cursor=cursor,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
    limit: int | Unset = 25,
    cursor: str | Unset = UNSET,
) -> Problem | RejectionPage | None:
    """Rows of a feed that failed validation, in row order

    Args:
        feed_id (UUID):
        limit (int | Unset):  Default: 25.
        cursor (str | Unset):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Problem | RejectionPage
    """

    return (
        await asyncio_detailed(
            feed_id=feed_id,
            client=client,
            limit=limit,
            cursor=cursor,
        )
    ).parsed
