"""Keep reading through the API while migrations and deploys happen, and count every error.

    uv run python -u scripts/search_loop.py [http://localhost:8020]

Each round: a search (rotating queries), a product page, one product, and a GraphQL search. The target base URL is
re-read from build/loop-target before every round, so a blue/green cutover is `echo http://... > build/loop-target`.
Prints a line every 10 s; stops (with a summary) when build/loop-stop exists, or on Ctrl-C.
"""

import asyncio
import signal
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import httpx

BUILD = Path(__file__).resolve().parents[1] / "build"
TARGET, STOP = BUILD / "loop-target", BUILD / "loop-stop"
QUERIES = ["hiking boots", "water bottle", "charger", "rain jacket", "yoga mat", "headphones", ""]
GRAPHQL = '{ search(query: "boots", first: 4) { total edges { node { id title } } } }'


async def main() -> None:
    BUILD.mkdir(exist_ok=True)
    STOP.unlink(missing_ok=True)
    if len(sys.argv) > 1 or not TARGET.exists():
        TARGET.write_text(sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8020")
    stop = asyncio.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(sig, stop.set)

    requests, errors, latencies, targets = Counter(), Counter(), [], Counter()
    first_errors: list[str] = []
    started = last_print = time.perf_counter()
    rounds = 0
    async with httpx.AsyncClient(timeout=10) as http:
        while not stop.is_set() and not STOP.exists():
            base = TARGET.read_text().strip()
            targets[base] += 1
            product_id = None
            calls = [("search", "GET", f"{base}/v1/search", {"q": QUERIES[rounds % len(QUERIES)], "page_size": 10}),
                     ("products", "GET", f"{base}/v1/products", {"limit": 5}),
                     ("product", "GET", None, None),
                     ("graphql", "POST", f"{base}/graphql", None)]
            for name, method, url, params in calls:
                if name == "product":
                    if product_id is None:
                        continue
                    url = f"{base}/v1/products/{product_id}"
                t = time.perf_counter()
                try:
                    if method == "POST":
                        response = await http.post(url, json={"query": GRAPHQL})
                        failed = response.status_code >= 400 or "errors" in response.json()
                    else:
                        response = await http.get(url, params=params)
                        failed = response.status_code >= 400
                    if name == "products" and not failed and response.json()["items"]:
                        product_id = response.json()["items"][rounds % len(response.json()["items"])]["id"]
                    detail = f"{response.status_code} {response.text[:160]}"
                except Exception as exc:  # connection refused, timeout: all count
                    failed, detail = True, repr(exc)[:160]
                latencies.append((time.perf_counter() - t) * 1000)
                requests[name] += 1
                if failed:
                    errors[name] += 1
                    if len(first_errors) < 10:
                        first_errors.append(f"{time.strftime('%H:%M:%S')} {name} {base}: {detail}")
            rounds += 1
            if time.perf_counter() - last_print >= 10:
                last_print = time.perf_counter()
                print(f"{time.strftime('%H:%M:%S')}  {sum(requests.values()):6} requests  "
                      f"{sum(errors.values())} errors  p95 {statistics.quantiles(latencies[-500:], n=20)[-1]:.0f} ms"
                      f"  -> {base}", flush=True)
            await asyncio.sleep(0.05)

    print(f"\nsummary: {sum(requests.values())} requests over {time.perf_counter() - started:.0f}s, "
          f"{sum(errors.values())} errors; by call {dict(requests)}; errors {dict(errors)}")
    print(f"rounds per target: {dict(targets)}")
    print(f"latency p50 {statistics.median(latencies):.0f} ms, p95 {statistics.quantiles(latencies, n=20)[-1]:.0f} ms,"
          f" max {max(latencies):.0f} ms")
    for line in first_errors:
        print("  error:", line)


if __name__ == "__main__":
    asyncio.run(main())
