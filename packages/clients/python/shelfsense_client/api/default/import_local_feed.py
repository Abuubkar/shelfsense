from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.import_local_request import ImportLocalRequest
from ...models.import_result import ImportResult
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: ImportLocalRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/feeds:import-local",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> ImportResult | Problem | None:
    if response.status_code == 200:
        response_200 = ImportResult.from_dict(response.json())

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
) -> Response[ImportResult | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportLocalRequest,
) -> Response[ImportResult | Problem]:
    """Import a supplier feed CSV from the API's feed directory

     Streams the CSV, validates each row, upserts valid rows on (supplier, SKU) only when their content
    changed, and records invalid rows as rejections with their spreadsheet row number (header = row 1).
    Importing the same file again changes nothing and returns the same feed.

    Args:
        body (ImportLocalRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ImportResult | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = client.get_httpx_client().request(
        **kwargs,
    )

    return _build_response(client=client, response=response)


def sync(
    *,
    client: AuthenticatedClient | Client,
    body: ImportLocalRequest,
) -> ImportResult | Problem | None:
    """Import a supplier feed CSV from the API's feed directory

     Streams the CSV, validates each row, upserts valid rows on (supplier, SKU) only when their content
    changed, and records invalid rows as rejections with their spreadsheet row number (header = row 1).
    Importing the same file again changes nothing and returns the same feed.

    Args:
        body (ImportLocalRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ImportResult | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: ImportLocalRequest,
) -> Response[ImportResult | Problem]:
    """Import a supplier feed CSV from the API's feed directory

     Streams the CSV, validates each row, upserts valid rows on (supplier, SKU) only when their content
    changed, and records invalid rows as rejections with their spreadsheet row number (header = row 1).
    Importing the same file again changes nothing and returns the same feed.

    Args:
        body (ImportLocalRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[ImportResult | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: ImportLocalRequest,
) -> ImportResult | Problem | None:
    """Import a supplier feed CSV from the API's feed directory

     Streams the CSV, validates each row, upserts valid rows on (supplier, SKU) only when their content
    changed, and records invalid rows as rejections with their spreadsheet row number (header = row 1).
    Importing the same file again changes nothing and returns the same feed.

    Args:
        body (ImportLocalRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        ImportResult | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
