from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Rejection")


@_attrs_define
class Rejection:
    """
    Attributes:
        row_number (int): Spreadsheet row number; the header is row 1.
        reason_code (str): missing_sku, missing_title, invalid_gtin, invalid_price, negative_price, invalid_currency,
            invalid_encoding, wrong_column_count or duplicate_sku.
        detail (str):
        excerpt (str):
    """

    row_number: int
    reason_code: str
    detail: str
    excerpt: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        row_number = self.row_number

        reason_code = self.reason_code

        detail = self.detail

        excerpt = self.excerpt

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "row_number": row_number,
                "reason_code": reason_code,
                "detail": detail,
                "excerpt": excerpt,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        row_number = d.pop("row_number")

        reason_code = d.pop("reason_code")

        detail = d.pop("detail")

        excerpt = d.pop("excerpt")

        rejection = cls(
            row_number=row_number,
            reason_code=reason_code,
            detail=detail,
            excerpt=excerpt,
        )

        rejection.additional_properties = d
        return rejection

    @property
    def additional_keys(self) -> list[str]:
        return list(self.additional_properties.keys())

    def __getitem__(self, key: str) -> Any:
        return self.additional_properties[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self.additional_properties[key] = value

    def __delitem__(self, key: str) -> None:
        del self.additional_properties[key]

    def __contains__(self, key: str) -> bool:
        return key in self.additional_properties
