from enum import StrEnum


class WorkQueue(StrEnum):
    ENRICH = "enrich"
    INDEX = "index"

    def __str__(self) -> str:
        return str(self.value)
