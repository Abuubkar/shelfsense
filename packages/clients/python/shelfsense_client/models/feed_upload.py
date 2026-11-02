from __future__ import annotations

import datetime
from collections.abc import Mapping
from typing import Any, TypeVar
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="FeedUpload")


@_attrs_define
class FeedUpload:
    """
    Attributes:
        feed_id (UUID):
        upload_url (str): Presigned URL; `PUT` the file's bytes to it.
        expires_at (datetime.datetime):
    """

    feed_id: UUID
    upload_url: str
    expires_at: datetime.datetime
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        feed_id = str(self.feed_id)

        upload_url = self.upload_url

        expires_at = self.expires_at.isoformat()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "feed_id": feed_id,
                "upload_url": upload_url,
                "expires_at": expires_at,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        feed_id = UUID(d.pop("feed_id"))

        upload_url = d.pop("upload_url")

        expires_at = datetime.datetime.fromisoformat(d.pop("expires_at"))

        feed_upload = cls(
            feed_id=feed_id,
            upload_url=upload_url,
            expires_at=expires_at,
        )

        feed_upload.additional_properties = d
        return feed_upload

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
