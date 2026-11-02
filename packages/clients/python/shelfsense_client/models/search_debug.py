from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

if TYPE_CHECKING:
    from ..models.search_debug_timings_ms import SearchDebugTimingsMs


T = TypeVar("T", bound="SearchDebug")


@_attrs_define
class SearchDebug:
    """
    Attributes:
        timings_ms (SearchDebugTimingsMs):
        head_size (int):
        hybrid_weights (list[float]):
        knn_min_score (float):
    """

    timings_ms: SearchDebugTimingsMs
    head_size: int
    hybrid_weights: list[float]
    knn_min_score: float
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        timings_ms = self.timings_ms.to_dict()

        head_size = self.head_size

        hybrid_weights = self.hybrid_weights

        knn_min_score = self.knn_min_score

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "timings_ms": timings_ms,
                "head_size": head_size,
                "hybrid_weights": hybrid_weights,
                "knn_min_score": knn_min_score,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.search_debug_timings_ms import SearchDebugTimingsMs  # noqa: PLC0415

        d = dict(src_dict)
        timings_ms = SearchDebugTimingsMs.from_dict(d.pop("timings_ms"))

        head_size = d.pop("head_size")

        hybrid_weights = cast(list[float], d.pop("hybrid_weights"))

        knn_min_score = d.pop("knn_min_score")

        search_debug = cls(
            timings_ms=timings_ms,
            head_size=head_size,
            hybrid_weights=hybrid_weights,
            knn_min_score=knn_min_score,
        )

        search_debug.additional_properties = d
        return search_debug

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
