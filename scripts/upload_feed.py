"""Upload a feed CSV and commit it, through the generated client: presigned URL, PUT, commit.

    uv run python scripts/upload_feed.py data/feeds/sample.csv acme-outdoor [api_base]
"""

import sys
from pathlib import Path

import httpx

from shelfsense_client import Client
from shelfsense_client.api.default import commit_feed, create_feed_upload
from shelfsense_client.models import FeedUpload, FeedUploadRequest, ImportResult, Problem


def upload(client: Client, path: Path, supplier: str) -> ImportResult:
    feed = create_feed_upload.sync(client=client, body=FeedUploadRequest(supplier=supplier, file_name=path.name))
    if not isinstance(feed, FeedUpload):
        raise SystemExit(f"create upload failed: {feed}")
    # Streamed from disk; the bytes go straight to object storage, not through the API.
    with path.open("rb") as f:
        httpx.put(feed.upload_url, content=f, timeout=300).raise_for_status()
    result = commit_feed.sync(client=client, feed_id=feed.feed_id)
    if isinstance(result, Problem):
        raise SystemExit(f"commit failed: {result.code.value}: {result.detail}")
    assert isinstance(result, ImportResult), result
    return result


def main() -> None:
    path, supplier = Path(sys.argv[1]), sys.argv[2]
    client = Client(base_url=sys.argv[3] if len(sys.argv) > 3 else "http://localhost:8020", timeout=600)
    result = upload(client, path, supplier)
    print(f"feed {result.feed_id}: {result.rows} rows, {result.inserted} inserted, {result.updated} updated, "
          f"{result.unchanged} unchanged, {result.rejected} rejected, {result.enqueued} queued for enrichment")
    for r in result.rejections[:10]:
        print(f"  row {r.row_number}: {r.reason_code}: {r.detail}")


if __name__ == "__main__":
    main()
