from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FeedUploadRequest")


@_attrs_define
class FeedUploadRequest:
    """
    Attributes:
        supplier (str): The supplier's code; created on first use.
        file_name (str): The file's original name, kept for people; the feed is identified by its ID.
    """

    supplier: str
    file_name: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        supplier = self.supplier

        file_name = self.file_name

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "supplier": supplier,
                "file_name": file_name,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        supplier = d.pop("supplier")

        file_name = d.pop("file_name")

        feed_upload_request = cls(
            supplier=supplier,
            file_name=file_name,
        )

        feed_upload_request.additional_properties = d
        return feed_upload_request

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
