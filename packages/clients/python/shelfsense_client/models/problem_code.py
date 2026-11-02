from enum import StrEnum


class ProblemCode(StrEnum):
    CURSOR_EXPIRED = "cursor_expired"
    INVALID_CURSOR = "invalid_cursor"
    INVALID_REQUEST = "invalid_request"
    MODEL_TIMEOUT = "model_timeout"
    MODEL_UNAVAILABLE = "model_unavailable"
    NOT_FOUND = "not_found"
    SEARCH_UNAVAILABLE = "search_unavailable"

    def __str__(self) -> str:
        return str(self.value)
