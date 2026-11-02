from enum import StrEnum


class QueryParseSource(StrEnum):
    CACHE = "cache"
    DEGRADED = "degraded"
    LLM = "llm"
    RULES = "rules"

    def __str__(self) -> str:
        return str(self.value)
