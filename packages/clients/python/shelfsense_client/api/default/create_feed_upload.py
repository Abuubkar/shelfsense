from http import HTTPStatus
from typing import Any

import httpx

from ... import errors
from ...client import AuthenticatedClient, Client
from ...models.feed_upload import FeedUpload
from ...models.feed_upload_request import FeedUploadRequest
from ...models.problem import Problem
from ...types import Response


def _get_kwargs(
    *,
    body: FeedUploadRequest,
) -> dict[str, Any]:
    headers: dict[str, Any] = {}

    _kwargs: dict[str, Any] = {
        "method": "post",
        "url": "/v1/feeds",
    }

    _kwargs["json"] = body.to_dict()

    headers["Content-Type"] = "application/json"

    _kwargs["headers"] = headers
    return _kwargs


def _parse_response(*, client: AuthenticatedClient | Client, response: httpx.Response) -> FeedUpload | Problem | None:
    if response.status_code == 201:
        response_201 = FeedUpload.from_dict(response.json())

        return response_201

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
) -> Response[FeedUpload | Problem]:
    return Response(
        status_code=HTTPStatus(response.status_code),
        content=response.content,
        headers=response.headers,
        parsed=_parse_response(client=client, response=response),
    )


def sync_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: FeedUploadRequest,
) -> Response[FeedUpload | Problem]:
    """Start a feed upload

     Records a new feed and returns a presigned URL to `PUT` the CSV to object storage directly, so large
    files never pass through the API. Then call `POST /v1/feeds/{feed_id}:commit`.

    Args:
        body (FeedUploadRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedUpload | Problem]
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
    body: FeedUploadRequest,
) -> FeedUpload | Problem | None:
    """Start a feed upload

     Records a new feed and returns a presigned URL to `PUT` the CSV to object storage directly, so large
    files never pass through the API. Then call `POST /v1/feeds/{feed_id}:commit`.

    Args:
        body (FeedUploadRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedUpload | Problem
    """

    return sync_detailed(
        client=client,
        body=body,
    ).parsed


async def asyncio_detailed(
    *,
    client: AuthenticatedClient | Client,
    body: FeedUploadRequest,
) -> Response[FeedUpload | Problem]:
    """Start a feed upload

     Records a new feed and returns a presigned URL to `PUT` the CSV to object storage directly, so large
    files never pass through the API. Then call `POST /v1/feeds/{feed_id}:commit`.

    Args:
        body (FeedUploadRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        Response[FeedUpload | Problem]
    """

    kwargs = _get_kwargs(
        body=body,
    )

    response = await client.get_async_httpx_client().request(**kwargs)

    return _build_response(client=client, response=response)


async def asyncio(
    *,
    client: AuthenticatedClient | Client,
    body: FeedUploadRequest,
) -> FeedUpload | Problem | None:
    """Start a feed upload

     Records a new feed and returns a presigned URL to `PUT` the CSV to object storage directly, so large
    files never pass through the API. Then call `POST /v1/feeds/{feed_id}:commit`.

    Args:
        body (FeedUploadRequest):

    Raises:
        errors.UnexpectedStatus: If the server returns an undocumented status code and Client.raise_on_unexpected_status is True.
        httpx.TimeoutException: If the request takes longer than Client.timeout.

    Returns:
        FeedUpload | Problem
    """

    return (
        await asyncio_detailed(
            client=client,
            body=body,
        )
    ).parsed
