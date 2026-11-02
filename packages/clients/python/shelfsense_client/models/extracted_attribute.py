from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="ExtractedAttribute")


@_attrs_define
class ExtractedAttribute:
    """
    Attributes:
        name (str): color, material, gender, size or length.
        value (str): Normalized (base colour, millimetres, "US 8", ...).
        unit (None | str):
        evidence_field (str): title, description, brand or raw_attributes.
        evidence_start (int): Offset into the field in Unicode code points (in JavaScript, index Array.from(text)).
        evidence_end (int):
        evidence_text (str): The exact quote; equals the field's text from evidence_start to evidence_end.
    """

    name: str
    value: str
    unit: None | str
    evidence_field: str
    evidence_start: int
    evidence_end: int
    evidence_text: str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name

        value = self.value

        unit: None | str
        unit = self.unit

        evidence_field = self.evidence_field

        evidence_start = self.evidence_start

        evidence_end = self.evidence_end

        evidence_text = self.evidence_text

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "value": value,
                "unit": unit,
                "evidence_field": evidence_field,
                "evidence_start": evidence_start,
                "evidence_end": evidence_end,
                "evidence_text": evidence_text,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        name = d.pop("name")

        value = d.pop("value")

        def _parse_unit(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        unit = _parse_unit(d.pop("unit"))

        evidence_field = d.pop("evidence_field")

        evidence_start = d.pop("evidence_start")

        evidence_end = d.pop("evidence_end")

        evidence_text = d.pop("evidence_text")

        extracted_attribute = cls(
            name=name,
            value=value,
            unit=unit,
            evidence_field=evidence_field,
            evidence_start=evidence_start,
            evidence_end=evidence_end,
            evidence_text=evidence_text,
        )

        extracted_attribute.additional_properties = d
        return extracted_attribute

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
