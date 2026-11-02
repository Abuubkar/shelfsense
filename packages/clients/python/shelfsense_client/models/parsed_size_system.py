from enum import StrEnum


class ParsedSizeSystem(StrEnum):
    ALPHA = "alpha"
    EU = "EU"
    UK = "UK"
    US = "US"

    def __str__(self) -> str:
        return str(self.value)
