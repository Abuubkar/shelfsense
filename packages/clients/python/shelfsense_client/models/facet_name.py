from enum import StrEnum


class FacetName(StrEnum):
    BRAND = "brand"
    CATEGORY_ID = "category_id"
    COLOR = "color"
    PRICE = "price"

    def __str__(self) -> str:
        return str(self.value)
