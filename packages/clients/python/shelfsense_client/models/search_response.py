from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..types import UNSET, Unset

if TYPE_CHECKING:
    from ..models.facet import Facet
    from ..models.search_debug import SearchDebug
    from ..models.search_item import SearchItem


T = TypeVar("T", bound="SearchResponse")


@_attrs_define
class SearchResponse:
    """
    Attributes:
        items (list[SearchItem]):
        total (int): Products in the whole result set.
        facets (list[Facet]):
        next_cursor (None | str):
        debug (None | SearchDebug | Unset):
    """

    items: list[SearchItem]
    total: int
    facets: list[Facet]
    next_cursor: None | str
    debug: None | SearchDebug | Unset = UNSET
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from ..models.search_debug import SearchDebug  # noqa: PLC0415

        items = []
        for items_item_data in self.items:
            items_item = items_item_data.to_dict()
            items.append(items_item)

        total = self.total

        facets = []
        for facets_item_data in self.facets:
            facets_item = facets_item_data.to_dict()
            facets.append(facets_item)

        next_cursor: None | str
        next_cursor = self.next_cursor

        debug: dict[str, Any] | None | Unset
        if isinstance(self.debug, Unset):
            debug = UNSET
        elif isinstance(self.debug, SearchDebug):
            debug = self.debug.to_dict()
        else:
            debug = self.debug

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "items": items,
                "total": total,
                "facets": facets,
                "next_cursor": next_cursor,
            }
        )
        if debug is not UNSET:
            field_dict["debug"] = debug

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.facet import Facet  # noqa: PLC0415
        from ..models.search_debug import SearchDebug  # noqa: PLC0415
        from ..models.search_item import SearchItem  # noqa: PLC0415

        d = dict(src_dict)
        items = []
        _items = d.pop("items")
        for items_item_data in _items:
            items_item = SearchItem.from_dict(items_item_data)

            items.append(items_item)

        total = d.pop("total")

        facets = []
        _facets = d.pop("facets")
        for facets_item_data in _facets:
            facets_item = Facet.from_dict(facets_item_data)

            facets.append(facets_item)

        def _parse_next_cursor(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        next_cursor = _parse_next_cursor(d.pop("next_cursor"))

        def _parse_debug(data: object) -> None | SearchDebug | Unset:
            if data is None:
                return data
            if isinstance(data, Unset):
                return data
            try:
                if not isinstance(data, dict):
                    raise TypeError()
                debug_type_0 = SearchDebug.from_dict(data)

                return debug_type_0
            except (TypeError, ValueError, AttributeError, KeyError):
                pass
            return cast(None | SearchDebug | Unset, data)

        debug = _parse_debug(d.pop("debug", UNSET))

        search_response = cls(
            items=items,
            total=total,
            facets=facets,
            next_cursor=next_cursor,
            debug=debug,
        )

        search_response.additional_properties = d
        return search_response

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
