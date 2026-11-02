from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, TypeVar, cast

from attrs import define as _attrs_define
from attrs import field as _attrs_field

from ..models.work_queue import WorkQueue

if TYPE_CHECKING:
    from ..models.redrive_result_reasons import RedriveResultReasons


T = TypeVar("T", bound="RedriveResult")


@_attrs_define
class RedriveResult:
    """
    Attributes:
        queue (WorkQueue):
        dry_run (bool):
        messages (int): Messages in the dead-letter queue (approximate, as SQS reports it).
        reasons (RedriveResultReasons): Dead letters not yet redriven, counted by error code.
        task_handle (None | str): The SQS move task's handle; null for a dry run.
    """

    queue: WorkQueue
    dry_run: bool
    messages: int
    reasons: RedriveResultReasons
    task_handle: None | str
    additional_properties: dict[str, Any] = _attrs_field(init=False, factory=dict)

    def to_dict(self) -> dict[str, Any]:
        queue = self.queue.value

        dry_run = self.dry_run

        messages = self.messages

        reasons = self.reasons.to_dict()

        task_handle: None | str
        task_handle = self.task_handle

        field_dict: dict[str, Any] = {}
        field_dict.update(self.additional_properties)
        field_dict.update(
            {
                "queue": queue,
                "dry_run": dry_run,
                "messages": messages,
                "reasons": reasons,
                "task_handle": task_handle,
            }
        )

        return field_dict

    @classmethod
    def from_dict(cls: type[T], src_dict: Mapping[str, Any]) -> T:
        from ..models.redrive_result_reasons import RedriveResultReasons  # noqa: PLC0415

        d = dict(src_dict)
        queue = WorkQueue(d.pop("queue"))

        dry_run = d.pop("dry_run")

        messages = d.pop("messages")

        reasons = RedriveResultReasons.from_dict(d.pop("reasons"))

        def _parse_task_handle(data: object) -> None | str:
            if data is None:
                return data
            return cast(None | str, data)

        task_handle = _parse_task_handle(d.pop("task_handle"))

        redrive_result = cls(
            queue=queue,
            dry_run=dry_run,
            messages=messages,
            reasons=reasons,
            task_handle=task_handle,
        )

        redrive_result.additional_properties = d
        return redrive_result

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
