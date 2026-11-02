from http import HTTPStatus
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.import_result import ImportResult
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    feed_id: UUID,
) -> dict[str, Any]:

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/feeds/{feed_id}:commit".format(
            feed_id=quote(str(feed_id), safe=""),
        ),
    }

    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ImportResult | Problem | None:
    if response.status_code == 200:
        response_200 = ImportResult.from_dict(response.json())

        return response_200

    if response.status_code == 404:
        response_404 = Problem.from_dict(response.json())

        return response_404

    if response.status_code == 409:
        response_409 = Problem.from_dict(response.json())

        return response_409

    if response.status_code == 429:
        response_429 = Problem.from_dict(response.json())

        return response_429

    if response.status_code == 503:
        response_503 = Problem.from_dict(response.json())

        return response_503

    if client.raise_on_unexpected_status:
        raise errors.UnexpectedStatus(response.status_code, response.content)
    else:
        return None


def _build_response(
    *, client: AuthenticatedClient | Client, response: httpx.Response
) -> Response[ImportResult | Problem]:
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
) -> Response[ImportResult | Problem]:
    """Import an uploaded feed and queue its products for enrichment

     Streams the uploaded CSV, validates each row, upserts valid rows on (supplier, SKU) only when their
    content changed, and records invalid rows as rejections with their spreadsheet row number
    (header = row 1). Products not yet enriched for their current content are queued for enrichment.
    Committing the same feed again changes nothing.

    Refused with 429 while the enrichment backlog is above its limit; `Retry-After` estimates when it
    will have drained enough, from the measured enrichment rate.

    Args:
        feed_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ImportResult | Problem]
    """

    kwargs = _get_kwargs(
        feed_id=feed_id,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> ImportResult | Problem | None:
    """Import an uploaded feed and queue its products for enrichment

     Streams the uploaded CSV, validates each row, upserts valid rows on (supplier, SKU) only when their
    content changed, and records invalid rows as rejections with their spreadsheet row number
    (header = row 1). Products not yet enriched for their current content are queued for enrichment.
    Committing the same feed again changes nothing.

    Refused with 429 while the enrichment backlog is above its limit; `Retry-After` estimates when it
    will have drained enough, from the measured enrichment rate.

    Args:
        feed_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ImportResult | Problem
    """

    return sync_detailed(
        feed_id=feed_id,
        client=client,
    ).parsed


async def asyncio_detailed(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> Response[ImportResult | Problem]:
    """Import an uploaded feed and queue its products for enrichment

     Streams the uploaded CSV, validates each row, upserts valid rows on (supplier, SKU) only when their
    content changed, and records invalid rows as rejections with their spreadsheet row number
    (header = row 1). Products not yet enriched for their current content are queued for enrichment.
    Committing the same feed again changes nothing.

    Refused with 429 while the enrichment backlog is above its limit; `Retry-After` estimates when it
    will have drained enough, from the measured enrichment rate.

    Args:
        feed_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ImportResult | Problem]
    """

    kwargs = _get_kwargs(
        feed_id=feed_id,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    feed_id: UUID,
    *,
    client: AuthenticatedClient | Client,
) -> ImportResult | Problem | None:
    """Import an uploaded feed and queue its products for enrichment

     Streams the uploaded CSV, validates each row, upserts valid rows on (supplier, SKU) only when their
    content changed, and records invalid rows as rejections with their spreadsheet row number
    (header = row 1). Products not yet enriched for their current content are queued for enrichment.
    Committing the same feed again changes nothing.

    Refused with 429 while the enrichment backlog is above its limit; `Retry-After` estimates when it
    will have drained enough, from the measured enrichment rate.

    Args:
        feed_id (UUID):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ImportResult | Problem
    """

    return (
        await asyncio_detailed(
            feed_id=feed_id,
            client=client,
        )
    ).parsed
