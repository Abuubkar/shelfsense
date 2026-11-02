from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.parsed_size import ParsedSize


T = TypeVar("T", bound="ParsedFilters")


@_attrs_define
class ParsedFilters:
    """
    Attributes:
        price_min (int | None): Minor units.
        price_max (int | None):
        colors (list[str]):
        exclude_colors (list[str]):
        materials (list[str]):
        exclude_materials (list[str]):
        gender (None | str):
        size (None | ParsedSize):
    """

    price_min: int | None
    price_max: int | None
    colors: list[str]
    exclude_colors: list[str]
    materials: list[str]
    exclude_materials: list[str]
    gender: None | str
    size: None | ParsedSize
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.parsed_size import ParsedSize  # noqa: PLC0415

        price_min: int | None
        price_min = self.price_min

        price_max: int | None
        price_max = self.price_max

        colors = self.colors

        exclude_colors = self.exclude_colors

        materials = self.materials

        exclude_materials = self.exclude_materials

        gender: None | str
        gender = self.gender

        size: dict[str, Any] | None
        if isinstance(self.size, ParsedSize):
            size = self.size.to_dict()
        else:
            size = self.size

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "price_min": price_min,
                "price_max": price_max,
                "colors": colors,
                "exclude_colors": exclude_colors,
                "materials": materials,
                "exclude_materials": exclude_materials,
                "gender": gender,
                "size": size,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.parsed_size import ParsedSize  # noqa: PLC0415

        d = dict(src_dict)

        def _parse_price_min(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        price_min = _parse_price_min(d.pop("price_min"))

        def _parse_price_max(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        price_max = _parse_price_max(d.pop("price_max"))

        colors = cast(list[str], d.pop("colors"))

        exclude_colors = cast(list[str], d.pop("exclude_colors"))

        materials = cast(list[str], d.pop("materials"))

        exclude_materials = cast(list[str], d.pop("exclude_materials"))

        def _parse_gender(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        gender = _parse_gender(d.pop("gender"))

        def _parse_size(data: object) -> None | ParsedSize:
            if data is None:
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                size_type_0 = ParsedSize.from_dict(data)

                return size_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | ParsedSize, data)

        size = _parse_size(d.pop("size"))

        parsed_filters = cls(
            price_min=price_min,
            price_max=price_max,
            colors=colors,
            exclude_colors=exclude_colors,
            materials=materials,
            exclude_materials=exclude_materials,
            gender=gender,
            size=size,
        )

        parsed_filters.additional_properties = d
        return parsed_filters

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
