from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.query_parse_source import QueryParseSource

if TYPE_CHECKING:
    from ..models.parsed_filters import ParsedFilters


T = TypeVar("T", bound="QueryParse")


@_attrs_define
class QueryParse:
    """
    Attributes:
        source (QueryParseSource): rules = no filter words, searched as typed; cache = an earlier model parse; llm =
            parsed now;
            degraded = the model was too slow or failed, so `q` was searched as typed ("showing broader results").
        keywords (str): The text searched once filter words are taken out.
        category_hint (None | str):
        filters (ParsedFilters):
        price_relaxed (bool): The parsed price range matched nothing, so it was dropped.
        ms (int):
    """

    source: QueryParseSource
    keywords: str
    category_hint: None | str
    filters: ParsedFilters
    price_relaxed: bool
    ms: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        source = self.source.value

        keywords = self.keywords

        category_hint: None | str
        category_hint = self.category_hint

        filters = self.filters.to_dict()

        price_relaxed = self.price_relaxed

        ms = self.ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "source": source,
                "keywords": keywords,
                "category_hint": category_hint,
                "filters": filters,
                "price_relaxed": price_relaxed,
                "ms": ms,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.parsed_filters import ParsedFilters  # noqa: PLC0415

        d = dict(src_dict)
        source = QueryParseSource(d.pop("source"))

        keywords = d.pop("keywords")

        def _parse_category_hint(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        category_hint = _parse_category_hint(d.pop("category_hint"))

        filters = ParsedFilters.from_dict(d.pop("filters"))

        price_relaxed = d.pop("price_relaxed")

        ms = d.pop("ms")

        query_parse = cls(
            source=source,
            keywords=keywords,
            category_hint=category_hint,
            filters=filters,
            price_relaxed=price_relaxed,
            ms=ms,
        )

        query_parse.additional_properties = d
        return query_parse

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
