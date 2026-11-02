---
status: accepted
date: 2026-11-02
---

# Feeds upload to object storage; a feed is one upload

**Chosen.** `POST /v1/feeds {supplier, file_name}` records a feed and returns a presigned S3 PUT URL (15 minutes).
The client uploads straight to the bucket, so large files never pass through the API. `POST
/v1/feeds/{id}:commit` streams the object to a temporary file (never held in memory), runs slice 1's import on
it, and queues the products that aren't enriched for their current content. Commit is safe to repeat.

`POST /v1/feeds:import-local` is removed: it read the API server's own disk, and keeping it would mean two ways
into the import. `scripts/upload_feed.py` does presign, PUT and commit in one command.

A feed is now identified by its upload, not by its bytes: the unique `(supplier, file_sha256)` is gone, and
uploading the same file twice makes two feeds (with their own rejections) while changing no products. The hash
and counts are filled in on commit.

## Alternatives

- **Keep feeds unique by hash** and answer a duplicate commit with 409 and the earlier feed: needs a hashing pass
  before the import, and a supplier re-sending a file is normal, not an error.
- **Parse straight from the S3 stream**: no temp file, but `csv` is synchronous and a quoted field can span
  chunks; spooling to disk keeps slice 1's import unchanged at the cost of one local copy.
- **Multipart upload through the API**: simple for clients, but every byte goes through the API process.

## Assumptions

- The API host has local disk for one feed file at a time per commit.
- Commit runs inside the request. A 100k-row feed takes tens of seconds; an async commit with a status endpoint
  is in docs/backlog.md.
