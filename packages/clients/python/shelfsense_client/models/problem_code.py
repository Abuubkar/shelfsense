from enum import StrEnum


class ProblemCode(StrEnum):
    BACKLOG_FULL = "backlog_full"
    CURSOR_EXPIRED = "cursor_expired"
    FEED_NOT_UPLOADED = "feed_not_uploaded"
    INVALID_CURSOR = "invalid_cursor"
    INVALID_REQUEST = "invalid_request"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    NOT_FOUND = "not_found"
    QUEUE_UNAVAILABLE = "queue_unavailable"
    REDRIVE_IN_PROGRESS = "redrive_in_progress"
    SEARCH_UNAVAILABLE = "search_unavailable"

    def __str__(self) -> str:
        return str(self.value)
