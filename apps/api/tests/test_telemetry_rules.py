"""No product text or shopper query text leaves the process in a span: the denylist hashes it (docs/adr/0022)."""

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from shelfsense_api.telemetry import HashingSpanProcessor, fingerprint

QUERY, TITLE = "waterproof red boots under $120", "Merrell Moab 3 Waterproof Hiking Boot"


def export(attributes: dict, event: dict | None = None) -> dict:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(HashingSpanProcessor(SimpleSpanProcessor(exporter)))
    with provider.get_tracer("test").start_as_current_span("span", attributes=attributes) as span:
        if event:
            span.add_event("exception", event)
    (finished,) = exporter.get_finished_spans()
    return {"attributes": dict(finished.attributes or {}), "events": [dict(e.attributes or {}) for e in finished.events]}


def test_product_and_query_text_is_hashed_and_numbers_and_ids_are_kept() -> None:
    kept = {"shelfsense.product_id": "01a1a41a-2837-76c6-ac4c-1c99eb6c93c3", "gen_ai.usage.input_tokens": 812,
            "gen_ai.request.model": "qwen2.5:7b-instruct", "shelfsense.parse_source": "degraded",
            "shelfsense.query_hash": fingerprint(QUERY), "url.path": "/v1/search"}
    out = export(kept | {
        "url.query": "q=waterproof+red+boots+under+%24120", "http.target": f"/v1/search?q={QUERY}",
        "shelfsense.product_title": TITLE, "product.description": "Full-grain leather...",
    }, event={"exception.type": "ValidationError", "exception.message": f"bad reply for {TITLE}"})
    attributes = out["attributes"]
    assert attributes["url.query"] == fingerprint("q=waterproof+red+boots+under+%24120")
    assert attributes["http.target"].startswith("sha256:")
    assert attributes["shelfsense.product_title"] == fingerprint(TITLE)  # same text, same hash, in every span
    assert attributes["product.description"].startswith("sha256:")
    assert out["events"][0] == {"exception.type": "ValidationError",
                                "exception.message": fingerprint(f"bad reply for {TITLE}")}
    assert {k: attributes[k] for k in kept} == kept
    assert "boots" not in repr(out).lower() and "Merrell" not in repr(out)


def test_sql_is_kept_for_postgres_but_a_redis_command_is_hashed() -> None:
    sql = "SELECT products.id FROM products WHERE products.id = $1::UUID"
    redis = 'SET qp:query/1:qwen2.5:3b-instruct:9f2c {"keywords": "red boots"}'
    assert export({"db.system.name": "postgresql", "db.query.text": sql})["attributes"]["db.query.text"] == sql
    assert export({"db.system": "redis", "db.statement": redis})["attributes"]["db.statement"] == fingerprint(redis)
