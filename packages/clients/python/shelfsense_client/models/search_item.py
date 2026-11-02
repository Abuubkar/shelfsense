from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast
from uuid import UUID

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.money import Money
    from ..models.search_item_debug import SearchItemDebug


T = TypeVar("T", bound="SearchItem")


@_attrs_define
class SearchItem:
    """
    Attributes:
        id (UUID):
        rank (int): 1-based position in the whole result set.
        title (str):
        brand (None | str):
        price (Money):
        color (None | str):
        size (None | str):
        category_id (int | None):
        category_path (None | str):
        debug (None | SearchItemDebug | Unset):
    """

    id: UUID
    rank: int
    title: str
    brand: None | str
    price: Money
    color: None | str
    size: None | str
    category_id: int | None
    category_path: None | str
    debug: None | SearchItemDebug | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.search_item_debug import SearchItemDebug  # noqa: PLC0415

        id = str(self.id)

        rank = self.rank

        title = self.title

        brand: None | str
        brand = self.brand

        price = self.price.to_dict()

        color: None | str
        color = self.color

        size: None | str
        size = self.size

        category_id: int | None
        category_id = self.category_id

        category_path: None | str
        category_path = self.category_path

        debug: dict[str, Any] | None | Unset
        if isinstance(self.debug, Unset):
            debug = UNSET
        elif isinstance(self.debug, SearchItemDebug):
            debug = self.debug.to_dict()
        else:
            debug = self.debug

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "id": id,
                "rank": rank,
                "title": title,
                "brand": brand,
                "price": price,
                "color": color,
                "size": size,
                "category_id": category_id,
                "category_path": category_path,
            }
        )
        if debug is not UNSET:
            field_dict["debug"] = debug

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.money import Money  # noqa: PLC0415
        from ..models.search_item_debug import SearchItemDebug  # noqa: PLC0415

        d = dict(src_dict)
        id = UUID(d.pop("id"))

        rank = d.pop("rank")

        title = d.pop("title")

        def _parse_brand(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        brand = _parse_brand(d.pop("brand"))

        price = Money.from_dict(d.pop("price"))

        def _parse_color(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        color = _parse_color(d.pop("color"))

        def _parse_size(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        size = _parse_size(d.pop("size"))

        def _parse_category_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        category_id = _parse_category_id(d.pop("category_id"))

        def _parse_category_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        category_path = _parse_category_path(d.pop("category_path"))

        def _parse_debug(data: object) -> None | SearchItemDebug | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                debug_type_0 = SearchItemDebug.from_dict(data)

                return debug_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SearchItemDebug | Unset, data)

        debug = _parse_debug(d.pop("debug", UNSET))

        search_item = cls(
            id=id,
            rank=rank,
            title=title,
            brand=brand,
            price=price,
            color=color,
            size=size,
            category_id=category_id,
            category_path=category_path,
            debug=debug,
        )

        search_item.additional_properties = d
        return search_item

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
