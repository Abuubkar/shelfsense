import json
import uuid
from pathlib import Path
from typing import Any

import pytest
from opensearchpy import TransportError

from shelfsense_api import indexing
from shelfsense_api.indexing import BatchSizer, bulk_index
from shelfsense_api.messages import EnrichRequest, IndexRequest, json_schemas, parse
from shelfsense_api.queue import Outcome, PermanentError, plan_followups

REPO = Path(__file__).resolve().parents[3]
A, B, C, D = (uuid.UUID(int=i) for i in range(1, 5))


def test_followups_pass_on_done_retry_transient_and_dead_letter_permanent() -> None:
    plan = plan_followups([Outcome(A, "done"), Outcome(B, "transient", "model_timeout"),
                           Outcome(C, "permanent", "invalid_model_output")], attempt=1, max_attempts=3)
    assert (plan.done, plan.retry, [d.product_id for d in plan.dead]) == ([A], [B], [C])


def test_transient_failure_on_the_last_attempt_is_dead_lettered_with_its_code() -> None:
    plan = plan_followups([Outcome(B, "transient", "model_timeout", "no reply within 2s")], attempt=3, max_attempts=3)
    assert plan.retry == []
    assert [(d.product_id, d.error_code) for d in plan.dead] == [(B, "model_timeout")]
    assert plan.dead[0].detail == "still failing after 3 attempts: no reply within 2s"


def test_batch_size_halves_on_rejection_down_to_the_floor_and_grows_by_steps_to_the_cap() -> None:
    sizer = BatchSizer()
    assert sizer.size == 500
    for expected in (250, 125, 62, 50, 50):
        sizer.rejected()
        assert sizer.size == expected
    for _ in range(100):
        sizer.succeeded()
    assert sizer.size == 2000


class FakeOpenSearch:
    """Answers each _bulk call with the next scripted per-item statuses (or raises the scripted error)."""

    def __init__(self, script: list[dict[str, int] | Exception]):
        self.script = script
        self.batches: list[list[str]] = []

    async def bulk(self, body: str) -> dict[str, Any]:
        ids = [json.loads(line)["index"]["_id"] for line in body.splitlines()[::2]]
        self.batches.append(ids)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        items = []
        for product_id in ids:
            status = step.get(product_id, 201)
            error = {"type": "rejected_execution_exception" if status == 429 else "document_parsing_exception",
                     "reason": "nope"}
            items.append({"index": {"_id": product_id, "status": status, **({"error": error} if status >= 300 else {})}})
        return {"errors": any(i["index"]["status"] >= 300 for i in items), "items": items}


@pytest.mark.anyio
async def test_bulk_retries_only_rejected_items_and_gives_up_on_malformed_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indexing, "backoff_s", lambda *a, **k: 0)
    docs = {str(p): {"title": str(p)} for p in (A, B, C)}
    os = FakeOpenSearch([{str(B): 429, str(C): 400}, {}])
    sizer = BatchSizer()

    outcomes = await bulk_index(os, docs, sizer)  # type: ignore[arg-type]

    assert [(o.product_id, o.status) for o in outcomes] == [(A, "done"), (B, "done"), (C, "permanent")]
    assert os.batches == [[str(A), str(B), str(C)], [str(B)]]  # the second request carries only the rejected item
    assert outcomes[2].error_code == "document_parsing_exception"
    assert sizer.size == 250 + 50  # halved for the rejection, then grew back a step


@pytest.mark.anyio
async def test_whole_bulk_rejection_shrinks_the_batch_and_stays_transient_when_it_persists(
        monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(indexing, "backoff_s", lambda *a, **k: 0)
    rejected = TransportError(429, "rejected_execution_exception", {})
    os = FakeOpenSearch([rejected] * indexing.BULK_ROUNDS)
    sizer = BatchSizer()

    outcomes = await bulk_index(os, {str(A): {}}, sizer)  # type: ignore[arg-type]

    assert [(o.status, o.error_code) for o in outcomes] == [("transient", "bulk_429")]
    assert sizer.size == 50


def test_consumer_ignores_fields_added_by_a_newer_producer() -> None:
    body = json.dumps({"schema_version": 1, "product_ids": [str(A)], "priority": "high", "trace": {"id": "x"}})
    assert parse(EnrichRequest, body).product_ids == [A]


def test_unknown_schema_version_and_malformed_bodies_are_permanent() -> None:
    with pytest.raises(PermanentError) as newer:
        parse(EnrichRequest, json.dumps({"schema_version": 2, "product_ids": [str(A)]}))
    assert newer.value.code == "unsupported_schema_version"
    for body in ("not json", json.dumps({"product_ids": []}), json.dumps({"product_ids": [str(A)] * 51})):
        with pytest.raises(PermanentError) as bad:
            parse(EnrichRequest, body)
        assert bad.value.code == "invalid_message"
    assert parse(IndexRequest, json.dumps({"product_ids": [str(A)] * 500})).attempt == 1


def test_message_schema_files_match_code() -> None:
    """contracts/messages/ documents the queue messages for other producers; `make codegen` refreshes it."""
    for name, schema in json_schemas().items():
        assert json.loads((REPO / "contracts" / "messages" / name).read_text()) == schema
