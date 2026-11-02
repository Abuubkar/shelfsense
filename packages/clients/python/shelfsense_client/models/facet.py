from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.facet_name import FacetName

if TYPE_CHECKING:
    from ..models.facet_value import FacetValue


T = TypeVar("T", bound="Facet")


@_attrs_define
class Facet:
    """
    Attributes:
        name (FacetName):
        values (list[FacetValue]):
    """

    name: FacetName
    values: list[FacetValue]
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        name = self.name.value

        values = []
        for values_item_data in self.values:
            values_item = values_item_data.to_dict()
            values.append(values_item)

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "name": name,
                "values": values,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facet_value import FacetValue  # noqa: PLC0415

        d = dict(src_dict)
        name = FacetName(d.pop("name"))

        values = []
        _values = d.pop("values")
        for values_item_data in _values:
            values_item = FacetValue.from_dict(values_item_data)

            values.append(values_item)

        facet = cls(
            name=name,
            values=values,
        )

        facet.additional_properties = d
        return facet

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
