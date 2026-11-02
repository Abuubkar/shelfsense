from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

T = TypeVar("T", bound="Category")


@_attrs_define
class Category:
    """A product's category in one taxonomy release, and how it was decided.

    Attributes:
        taxonomy_version (str):
        node_id (int | None): Null when no candidate fit.
        full_path (None | str):
        confidence (float): The model's probability for the chosen ID, from its token log-probabilities.
        candidate_ids (list[int]):
        model (str):
        prompt_version (str):
        prompt_tokens (int):
        output_tokens (int):
        total_ms (int):
    """

    taxonomy_version: str
    node_id: int | None
    full_path: None | str
    confidence: float
    candidate_ids: list[int]
    model: str
    prompt_version: str
    prompt_tokens: int
    output_tokens: int
    total_ms: int
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        taxonomy_version = self.taxonomy_version

        node_id: int | None
        node_id = self.node_id

        full_path: None | str
        full_path = self.full_path

        confidence = self.confidence

        candidate_ids = self.candidate_ids

        model = self.model

        prompt_version = self.prompt_version

        prompt_tokens = self.prompt_tokens

        output_tokens = self.output_tokens

        total_ms = self.total_ms

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "taxonomy_version": taxonomy_version,
                "node_id": node_id,
                "full_path": full_path,
                "confidence": confidence,
                "candidate_ids": candidate_ids,
                "model": model,
                "prompt_version": prompt_version,
                "prompt_tokens": prompt_tokens,
                "output_tokens": output_tokens,
                "total_ms": total_ms,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        d = dict(src_dict)
        taxonomy_version = d.pop("taxonomy_version")

        def _parse_node_id(data: object) -> int | None:
            if data is None:
                return data
            return cast(int | None, data)

        node_id = _parse_node_id(d.pop("node_id"))

        def _parse_full_path(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        full_path = _parse_full_path(d.pop("full_path"))

        confidence = d.pop("confidence")

        candidate_ids = cast(list[int], d.pop("candidate_ids"))

        model = d.pop("model")

        prompt_version = d.pop("prompt_version")

        prompt_tokens = d.pop("prompt_tokens")

        output_tokens = d.pop("output_tokens")

        total_ms = d.pop("total_ms")

        category = cls(
            taxonomy_version=taxonomy_version,
            node_id=node_id,
            full_path=full_path,
            confidence=confidence,
            candidate_ids=candidate_ids,
            model=model,
            prompt_version=prompt_version,
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            total_ms=total_ms,
        )

        category.additional_properties = d
        return category

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
