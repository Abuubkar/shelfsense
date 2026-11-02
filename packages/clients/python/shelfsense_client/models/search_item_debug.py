from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.search_item_debug_stage import SearchItemDebugStage

if TYPE_CHECKING:
    from ..models.search_item_debug_scores import SearchItemDebugScores


T = TypeVar("T", bound="SearchItemDebug")


@_attrs_define
class SearchItemDebug:
    """
    Attributes:
        stage (SearchItemDebugStage): head = hybrid-ranked and reranked (the first 50); tail = the rest, by combined
            score.
        scores (SearchItemDebugScores): Per-stage scores. Head: bm25 and knn (raw), bm25_normalized and knn_normalized,
            hybrid (their
            weighted mean), rerank (cross-encoder). Tail: bm25, knn, tail (their sum). A stage that didn't
            match the product is absent. Only head items on the first page, or any page with debug, carry the
            head scores.
    """

    stage: SearchItemDebugStage
    scores: SearchItemDebugScores
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        stage = self.stage.value

        scores = self.scores.to_dict()

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "stage": stage,
                "scores": scores,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.search_item_debug_scores import SearchItemDebugScores  # noqa: PLC0415

        d = dict(src_dict)
        stage = SearchItemDebugStage(d.pop("stage"))

        scores = SearchItemDebugScores.from_dict(d.pop("scores"))

        search_item_debug = cls(
            stage=stage,
            scores=scores,
        )

        search_item_debug.additional_properties = d
        return search_item_debug

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
