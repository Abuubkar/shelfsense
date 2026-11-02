# Problem codes

Errors are RFC 9457 `application/problem+json` documents. `type` links to the code's entry here; `code` is the
stable value to branch on.

## invalid_request

400. A parameter or body field is missing, malformed, or out of range (for example `page_size` above 48).
`detail` names the field.

## not_found

404. No product, feed or feed file with that ID or path.

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
