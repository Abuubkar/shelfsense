from enum import StrEnum


class SearchItemDebugStage(StrEnum):
    HEAD = "head"
    TAIL = "tail"

    def __str__(self) -> str:
        return str(self.value)
