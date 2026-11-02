# Problem codes

Errors are RFC 9457 `application/problem+json` documents. `type` links to the code's entry here; `code` is the
stable value to branch on.

## invalid_request

400. A parameter or body field is missing, malformed, or out of range (for example `page_size` above 48).
`detail` names the field.

## not_found

404. No product or feed with that ID.

## invalid_cursor

400. The cursor was edited, signed with another secret, or issued for a different query or filters. Start again
from the first page.

## cursor_expired

400. A search cursor wasn't used within 5 minutes, so its point-in-time snapshot was released (or the result set
was already read to the end). Start the search again.

## model_unavailable

502. Ollama couldn't be reached, or its reply was unusable (not the requested JSON, truncated, or naming a
category that wasn't a candidate). `detail` starts with the specific reason.

## model_timeout

504. The model didn't reply within `LLM_TIMEOUT_S`.

## search_unavailable

503. OpenSearch couldn't be reached.

## feed_not_uploaded

409. The feed was committed before its file was uploaded. `PUT` the file to the feed's `upload_url` (it expires
after 15 minutes; create a new feed if it has), then commit again.

## backlog_full

429. The enrichment queue holds more than `MAX_ENRICH_BACKLOG` messages, so new feeds are refused for now. Retry
after the `Retry-After` header's seconds, estimated from the products enriched in the last hour.

## redrive_in_progress

409. A redrive of this dead-letter queue is already moving messages. SQS allows one move task per queue at a time.

## queue_unavailable

503. SQS or S3 couldn't be reached, or refused the request. `detail` has the underlying error. Retry later.
