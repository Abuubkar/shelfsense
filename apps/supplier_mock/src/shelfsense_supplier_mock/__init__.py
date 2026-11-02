"""A supplier's product API for testing imports against: uv run uvicorn shelfsense_supplier_mock:app --port 8030

v1 (`GET /v1/products?offset=&limit=`) pages through the live catalog newest first (updated_at desc), and the
catalog changes on every request: new products appear and existing ones are updated, which moves them to the
front. So a naive offset scan sees some products twice and misses the ones that moved behind it.
v2 (`GET /v2/products?limit=&snapshot_token=&cursor=`) pages through a frozen copy taken on the first page.
Both return 429 with Retry-After at a configurable rate, and can be told to fail with 500s for a while.

`POST /admin/reset` sets the catalog and the misbehaviour; `GET /admin/catalog` returns the live catalog, the
truth an import is checked against.
"""

import random
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

COLORS = ["blk", "Black", "wht", "navy", "nvy", "Charcoal", "olive", "red", "blk/gry", "Royal Blue", "tan"]
SIZES = ["S", "M", "L", "XL", "US 8", "US 9", "EU 42", "UK 7", ""]
NOUNS = ["Trail Runner", "Rain Shell", "Fleece Jacket", "Camp Mug", "Headlamp", "Dry Bag", "Hiking Sock",
         "Sun Hoodie", "Trekking Pole", "Water Filter"]


class Config(BaseModel):
    seed: int = 1
    products: int = 1000
    # Applied to the live catalog before each v1 or v2 page is served.
    inserts_per_request: int = 0
    updates_per_request: int = 0
    rate_429: float = 0.0
    # Requests number from 1 after a reset; these ones get a 500.
    fail_requests: list[int] = []


class _State:
    def __init__(self) -> None:
        self.reset(Config())

    def reset(self, config: Config) -> None:
        self.config = config
        self.rng = random.Random(config.seed)
        self.requests = 0
        self.next_sku = 0
        self.catalog: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, list[dict[str, Any]]] = {}
        self.clock = now = datetime.now(UTC)
        for _ in range(config.products):
            # Existing products were last changed some time in the past month.
            self._add(now - timedelta(seconds=self.rng.randint(3600, 30 * 86400)))

    def _add(self, updated_at: datetime) -> None:
        sku = f"SUP-{self.next_sku:07d}"
        self.next_sku += 1
        noun = self.rng.choice(NOUNS)
        self.catalog[sku] = {
            "sku": sku, "title": f"{noun} {self.rng.choice(['Pro', 'Lite', 'Classic', 'Max'])} {sku[-4:]}",
            "description": f"{noun} for everyday adventures.", "brand": self.rng.choice(["Ridgeway", "Northpeak"]),
            "price": f"{self.rng.randint(5, 250)}.{self.rng.randint(0, 99):02d}", "currency": "USD",
            "color": self.rng.choice(COLORS), "size": self.rng.choice(SIZES),
            "updated_at": updated_at.isoformat(timespec="microseconds"),
        }

    def now(self) -> datetime:
        """Wall-clock time, but strictly increasing: each change gets a later timestamp than the one before."""
        self.clock = max(datetime.now(UTC), self.clock + timedelta(microseconds=1))
        return self.clock

    def drift(self) -> None:
        now = self.now()
        for _ in range(self.config.inserts_per_request):
            self._add(now)
        for sku in self.rng.sample(sorted(self.catalog), min(self.config.updates_per_request, len(self.catalog))):
            item = self.catalog[sku]
            item["price"] = f"{self.rng.randint(5, 250)}.{self.rng.randint(0, 99):02d}"
            item["updated_at"] = now.isoformat(timespec="microseconds")

    def newest_first(self) -> list[dict[str, Any]]:
        return sorted(self.catalog.values(), key=lambda i: (-datetime.fromisoformat(i["updated_at"]).timestamp(),
                                                            i["sku"]))

    def misbehave(self) -> JSONResponse | None:
        self.requests += 1
        if self.requests in self.config.fail_requests:
            return JSONResponse({"error": "upstream database unavailable"}, status_code=500)
        if self.rng.random() < self.config.rate_429:
            return JSONResponse({"error": "rate limited"}, status_code=429, headers={"Retry-After": "1"})
        return None


state = _State()
app = FastAPI(title="Supplier mock")


@app.post("/admin/reset")
def reset(config: Config) -> dict[str, int]:
    state.reset(config)
    return {"products": len(state.catalog)}


@app.get("/admin/catalog")
def catalog() -> list[dict[str, str]]:
    return [{"sku": i["sku"], "updated_at": i["updated_at"], "price": i["price"]} for i in state.catalog.values()]


@app.get("/v1/products", response_model=None)
def v1_products(offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500)) -> Any:
    if (error := state.misbehave()) is not None:
        return error
    state.drift()
    items = state.newest_first()
    return {"items": items[offset:offset + limit], "total": len(items)}


@app.get("/v2/products", response_model=None)
def v2_products(limit: int = Query(100, ge=1, le=500), snapshot_token: str | None = None,
                cursor: str | None = None) -> Any:
    if (error := state.misbehave()) is not None:
        return error
    state.drift()
    if snapshot_token is None:
        snapshot_token = uuid.uuid4().hex
        state.snapshots[snapshot_token] = sorted((dict(i) for i in state.catalog.values()), key=lambda i: i["sku"])
    snapshot = state.snapshots.get(snapshot_token)
    if snapshot is None:
        raise HTTPException(410, "snapshot expired")
    start = 0 if cursor is None else next((n for n, i in enumerate(snapshot) if i["sku"] > cursor), len(snapshot))
    items = snapshot[start:start + limit]
    more = start + limit < len(snapshot)
    return {"items": items, "snapshot_token": snapshot_token, "next_cursor": items[-1]["sku"] if more else None}
