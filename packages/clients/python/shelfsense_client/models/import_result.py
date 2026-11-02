from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.rejection import Rejection


T = TypeVar("T", bound="ImportResult")


@_attrs_define
class ImportResult:
    """
    Attributes:
        feed_id (UUID):
        file_sha256 (str):
        rows (int):
        inserted (int):
        updated (int):
        unchanged (int):
        rejected (int):
        rejections (list[Rejection]):
    """

    feed_id: UUID
    file_sha256: str
    rows: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int
    rejections: list[Rejection]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feed_id = str(self.feed_id)

        file_sha256 = self.file_sha256

        rows = self.rows

        inserted = self.inserted

        updated = self.updated

        unchanged = self.unchanged

        rejected = self.rejected

        rejections = []
        for rejections_item_data in self.rejections:
            rejections_item = rejections_item_data.to_dict()
            rejections.append(rejections_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feed_id": feed_id,
                "file_sha256": file_sha256,
                "rows": rows,
                "inserted": inserted,
                "updated": updated,
                "unchanged": unchanged,
                "rejected": rejected,
                "rejections": rejections,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.rejection import Rejection  # noqa: PLC0415

        d = dict(src_dict)
        feed_id = UUID(d.pop("feed_id"))

        file_sha256 = d.pop("file_sha256")

        rows = d.pop("rows")

        inserted = d.pop("inserted")

        updated = d.pop("updated")

        unchanged = d.pop("unchanged")

        rejected = d.pop("rejected")

        rejections = []
        _rejections = d.pop("rejections")
        for rejections_item_data in _rejections:
            rejections_item = Rejection.from_dict(rejections_item_data)

            rejections.append(rejections_item)

        import_result = cls(
            feed_id=feed_id,
            file_sha256=file_sha256,
            rows=rows,
            inserted=inserted,
            updated=updated,
            unchanged=unchanged,
            rejected=rejected,
            rejections=rejections,
        )

        import_result.additional_properties = d
        return import_result

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
