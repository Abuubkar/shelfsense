"""Slice 3's Done-when: a 2,000-product feed through the queues while things fail, then check nothing was lost or
done twice.

Starts its own API (port 8021) and workers on fresh queues, with the model replaced by a stub that returns 3%
HTTP 500s, 2% timeouts and 1% invalid output (which also fails its retry), and OpenSearch behind a proxy that
rejects 10% of bulk calls with 429. Two enrich workers run; one is killed with SIGKILL partway through.

Then checks: every valid product is enriched or in the DLQ with a reason; the DLQ holds exactly the
persistently invalid products; no product was enriched twice; indexed count equals enriched count.

    uv run python scripts/chaos.py [--keep]     # --keep leaves the run's products, queues and documents behind

Needs docker compose up (Postgres, OpenSearch, Floci) and migrations applied. No Ollama needed.
"""

import asyncio
import csv
import random
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path
from typing import Any

import uvicorn
from chaos_stubs import model_stub, opensearch_proxy, persistently_invalid
from opensearchpy import AsyncOpenSearch
from sqlalchemy import delete, func, select
from upload_feed import upload

from shelfsense_api import aws, db
from shelfsense_api.db import DeadLetter, EnrichmentRun, Feed, FeedRejection, Product, ProductCategory, Supplier
from shelfsense_api.settings import settings
from shelfsense_client import Client

REPO = Path(__file__).resolve().parents[1]
RUN = time.strftime("%Y%m%d-%H%M%S")
SUPPLIER = f"chaos-{RUN}"
VALID, INVALID = 2000, 20
API_PORT, MODEL_PORT, PROXY_PORT = 8021, 11500, 9301
KILL_AT = 0.3  # kill one enrich worker once this share of products is enriched
TIMEOUT_S = 20 * 60

# This process (its API) and the workers use fresh queues. Only the workers see the stubs.
QUEUES = {"enrich_queue": f"chaos-enrich-{RUN}", "index_queue": f"chaos-index-{RUN}"}
WORKER_ENV = {
    **{k.upper(): v for k, v in QUEUES.items()},
    "OLLAMA_HOST": f"http://127.0.0.1:{MODEL_PORT}",
    "OPENSEARCH_URL": f"http://127.0.0.1:{PROXY_PORT}",
    "LLM_TIMEOUT_S": "2",
    "LLM_MAX_CONCURRENCY": "8",
    "QUEUE_VISIBILITY_TIMEOUT_S": "15",  # how soon the killed worker's messages come back
    "QUEUE_WAIT_S": "2",
    "WORKER_SHUTDOWN_GRACE_S": "10",
}

NOUNS = ["Hiking Boot", "Rain Jacket", "Water Bottle", "Daypack", "Headlamp", "Tent", "Sleeping Bag", "Trekking Pole",
         "Camp Stove", "Yoga Mat", "Running Shoe", "Fleece Pullover", "Dog Collar", "Skillet", "Chef Knife",
         "USB-C Charger", "Headphones", "Desk Lamp", "Backpack Cooler", "Wool Socks"]
ADJECTIVES = ["Ultralight", "Waterproof", "Insulated", "Packable", "Rugged", "Classic", "Pro", "Compact", "Trail",
              "All-Weather"]
BRANDS = ["Northpeak", "Voltix", "Trailcraft", "Summitline", "Hearthware", "Barkley"]


def write_feed(path: Path) -> list[str]:
    """2,000 valid rows and 20 invalid ones, shuffled. Returns the valid titles."""
    rng = random.Random(11)
    rows, titles = [], []
    for i in range(VALID):
        title = f"{rng.choice(ADJECTIVES)} {rng.choice(NOUNS)} {rng.choice(['', 'Mens ', 'Womens '])}Model {i:04d}"
        titles.append(title)
        rows.append([f"CH-{i:05d}", title, f"{title}. Built for everyday use.", rng.choice(BRANDS), "",
                     f"{rng.randint(5, 300)}.{rng.randint(0, 99):02d}", "USD"])
    rows += [[f"CH-BAD-{i}", "", "no title", "Voltix", "", "9.99", "USD"] for i in range(INVALID // 2)]
    rows += [[f"CH-NEG-{i}", f"Broken Item {i}", "", "Voltix", "", "-5.00", "USD"] for i in range(INVALID // 2)]
    rng.shuffle(rows)
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sku", "title", "description", "brand", "gtin", "price", "currency"])
        writer.writerows(rows)
    return titles


async def serve(app: Any, port: int) -> tuple[uvicorn.Server, asyncio.Task[None]]:
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]  # this script handles signals
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.05)
    return server, task


def start_worker(module: str, log: Path) -> subprocess.Popen[bytes]:
    import os
    return subprocess.Popen([sys.executable, "-m", module], cwd=REPO, env={**os.environ, **WORKER_ENV},
                            stdout=log.open("wb"), stderr=subprocess.STDOUT)


async def scalar(query: Any) -> int:
    async with db.SessionLocal() as session:
        return await session.scalar(query) or 0


def supplier_products() -> Any:
    return select(Product.id).join(Supplier, Supplier.id == Product.supplier_id).where(Supplier.code == SUPPLIER)


async def snapshot(sqs: Any, os: AsyncOpenSearch) -> dict[str, int]:
    products = supplier_products()
    await os.indices.refresh(index="products")
    return {
        "enriched": await scalar(select(func.count()).select_from(ProductCategory)
                                 .where(ProductCategory.product_id.in_(products))),
        "dead": await scalar(select(func.count(func.distinct(DeadLetter.product_id)))
                             .where(DeadLetter.queue == settings.enrich_queue, DeadLetter.product_id.in_(products))),
        "enrich_queue": await aws.queue_depth(sqs, settings.enrich_queue),
        "index_queue": await aws.queue_depth(sqs, settings.index_queue),
        "indexed": (await os.count(index="products", body={"query": {"term": {"supplier": SUPPLIER}}}))["count"],
    }


async def main() -> None:
    keep = "--keep" in sys.argv
    for name, value in QUEUES.items():
        setattr(settings, name, value)
    run_dir = REPO / "build" / "chaos" / RUN
    run_dir.mkdir(parents=True)
    stats: Counter[str] = Counter()
    os = AsyncOpenSearch(hosts=[settings.opensearch_url])  # the real one, for counting

    from shelfsense_api.main import app as api  # imported after the queue names are set
    servers = [await serve(api, API_PORT), await serve(model_stub(stats, timeout_s=2), MODEL_PORT),
               await serve(opensearch_proxy(settings.opensearch_url, stats), PROXY_PORT)]
    async with aws.sqs() as sqs, aws.s3() as s3:
        await aws.ensure_resources(sqs, s3)
        enrichers = [start_worker("shelfsense_worker_enrich", run_dir / f"enrich-{i}.log") for i in (1, 2)]
        indexer = start_worker("shelfsense_worker_index", run_dir / "index.log")
        titles = write_feed(run_dir / "feed.csv")
        expected_dead = {t for t in titles if persistently_invalid(t)}

        started = time.perf_counter()
        client = Client(base_url=f"http://127.0.0.1:{API_PORT}", timeout=600)
        # The client is synchronous and the API runs on this event loop: call it from a thread.
        result = await asyncio.to_thread(upload, client, run_dir / "feed.csv", SUPPLIER)
        print(f"run {RUN}: feed {result.feed_id}: {result.rows} rows, {result.inserted} inserted, "
              f"{result.rejected} rejected, {result.enqueued} queued for enrichment "
              f"({time.perf_counter() - started:.1f}s)")

        killed_at = None
        try:
            async with asyncio.timeout(TIMEOUT_S):
                while True:
                    await asyncio.sleep(2)
                    s = await snapshot(sqs, os)
                    elapsed = time.perf_counter() - started
                    print(f"  {elapsed:5.0f}s  enriched {s['enriched']:4}  dead {s['dead']:3}  "
                          f"queued enrich {s['enrich_queue']:3} index {s['index_queue']:3}  indexed {s['indexed']:4}")
                    if killed_at is None and s["enriched"] >= KILL_AT * VALID:
                        enrichers[0].send_signal(signal.SIGKILL)
                        killed_at = (elapsed, s["enriched"])
                        print(f"  {elapsed:5.0f}s  SIGKILL enrich worker 1 (pid {enrichers[0].pid})")
                    if (s["enriched"] + s["dead"] == VALID and s["enrich_queue"] == 0 and s["index_queue"] == 0
                            and s["indexed"] == s["enriched"]):
                        break
        finally:
            for worker in [*enrichers, indexer]:
                if worker.poll() is None:
                    worker.send_signal(signal.SIGTERM)
            for worker in [*enrichers, indexer]:
                worker.wait(timeout=30)
        duration = time.perf_counter() - started
        final = await snapshot(sqs, os)
        ok = await report(sqs, final, expected_dead, killed_at, duration, stats, enrichers[0].returncode, run_dir)

        if not keep:
            await cleanup(sqs, s3, os, result.feed_id)
    for server, _ in servers:
        server.should_exit = True
    await asyncio.gather(*(task for _, task in servers))
    await os.close()
    raise SystemExit(0 if ok else 1)


async def report(sqs: Any, s: dict[str, int], expected_dead: set[str], killed_at: Any, duration: float,
                 stats: Counter[str], killed_code: int | None, run_dir: Path) -> bool:
    products = supplier_products()
    async with db.SessionLocal() as session:
        dead = (await session.execute(
            select(Product.title, DeadLetter.error_code, DeadLetter.sent_at)
            .join(Product, Product.id == DeadLetter.product_id)
            .where(DeadLetter.queue == settings.enrich_queue, DeadLetter.product_id.in_(products))
        )).all()
        enriched_twice = await session.scalar(select(func.count()).select_from(
            select(EnrichmentRun.product_id).where(EnrichmentRun.product_id.in_(products),
                                                   EnrichmentRun.outcome == "enriched")
            .group_by(EnrichmentRun.product_id).having(func.count() > 1).subquery()))
        runs = Counter((await session.execute(
            select(EnrichmentRun.outcome, EnrichmentRun.error_code, EnrichmentRun.attempt)
            .where(EnrichmentRun.product_id.in_(products)))).all())
    dlq_messages = await aws.queue_depth(sqs, aws.dlq_name(settings.enrich_queue))
    index_dlq = await aws.queue_depth(sqs, aws.dlq_name(settings.index_queue))
    dead_titles = {t for t, _, _ in dead}
    reasons = Counter(code for _, code, _ in dead)

    print(f"\n# run {RUN}: {duration:.0f}s, {VALID / duration * 3600:,.0f} products/hour through the stub")
    print(f"faults injected: {stats['model_500']} model 500s, {stats['model_timeout']} model timeouts, "
          f"{stats['model_invalid']} invalid replies; {stats['bulk_rejected_whole']} bulk calls rejected whole, "
          f"{stats['bulk_rejected_items']} bulk items rejected")
    print(f"enrich worker 1 killed at {killed_at[0]:.0f}s with {killed_at[1]} enriched (exit {killed_code})"
          if killed_at else "enrich worker 1 was never killed")
    print("model calls: " + ", ".join(f"{n} {o}{' ' + c if c else ''} (attempt {a})"
                                      for (o, c, a), n in sorted(runs.items(), key=lambda kv: -kv[1])))
    print(f"dead letters by reason: {dict(reasons)}; all sent to the DLQ: {all(sent for _, _, sent in dead)}")
    checks = [
        (f"valid products enriched or dead-lettered: {s['enriched']} + {s['dead']} = {VALID}",
         s["enriched"] + s["dead"] == VALID),
        (f"DLQ messages equal dead-lettered products: {dlq_messages} = {s['dead']}", dlq_messages == s["dead"]),
        (f"dead-lettered for invalid output are exactly the persistently invalid products: "
         f"{reasons['invalid_model_output']} = {len(expected_dead)}",
         {t for t, c, _ in dead if c == "invalid_model_output"} == expected_dead),
        (f"products enriched more than once: {enriched_twice}", enriched_twice == 0),
        (f"indexed equals enriched: {s['indexed']} = {s['enriched']}", s["indexed"] == s["enriched"]),
        (f"index DLQ empty: {index_dlq}", index_dlq == 0),
    ]
    other = dead_titles - expected_dead
    if other:
        print(f"note: {len(other)} dead-lettered after exhausting transient retries: {sorted(reasons)}")
    for text, passed in checks:
        print(f"  {'PASS' if passed else 'FAIL'}  {text}")
    print(f"worker logs: {run_dir}")
    return all(passed for _, passed in checks)


async def cleanup(sqs: Any, s3: Any, os: AsyncOpenSearch, feed_id: Any) -> None:
    """Remove what this run created, so repeated runs don't pile up in the dev catalog."""
    await os.delete_by_query(index="products", body={"query": {"term": {"supplier": SUPPLIER}}}, refresh=True)
    # Deleted documents stay in the HNSW graphs until their segments merge, and crowd live ones out of k-NN
    # results (docs/challenges.md): 2,000 deleted near-duplicates cut a radial search from 13 matches to 5.
    # Right after the delete, an expunge keeps them (they're still retained as recent soft deletes), so retry.
    for _ in range(24):
        await os.indices.forcemerge(index="products", only_expunge_deletes=True)
        await os.indices.refresh(index="products")
        stats = await os.indices.stats(index="products", metric="docs")
        if stats["_all"]["primaries"]["docs"]["deleted"] == 0:
            break
        await asyncio.sleep(5)
    else:
        print("warning: deleted documents still in the index; k-NN recall stays low until segments merge")
    async with db.SessionLocal() as session:
        ids = select(Product.id).join(Supplier, Supplier.id == Product.supplier_id).where(Supplier.code == SUPPLIER)
        for model in (DeadLetter, EnrichmentRun, ProductCategory):
            await session.execute(delete(model).where(model.product_id.in_(ids)))
        await session.execute(delete(DeadLetter).where(DeadLetter.queue == settings.enrich_queue))
        await session.execute(delete(FeedRejection).where(FeedRejection.feed_id == feed_id))
        await session.execute(delete(Feed).where(Feed.id == feed_id))
        await session.execute(delete(Product).where(Product.id.in_(ids)))
        await session.execute(delete(Supplier).where(Supplier.code == SUPPLIER))
        await session.commit()
    for queue in QUEUES.values():
        for name in (queue, aws.dlq_name(queue)):
            await sqs.delete_queue(QueueUrl=await aws.queue_url(sqs, name))
    await s3.delete_object(Bucket=settings.feeds_bucket, Key=f"{feed_id}.csv")
    print(f"cleaned up supplier {SUPPLIER}, its queues and documents (--keep to leave them)")


if __name__ == "__main__":
    asyncio.run(main())
