"""Realistic catalog volume from known ground truth: 50 seed suppliers, each with its own quirks, write products
generated from structured items, so every messy value has a correct answer on record.

    uv run python scripts/seed.py --profile small|large [--seed 42] [--feed] [--commit-feed] [--reset]

- small: 5,000 products; large: 200,000. The same --seed always generates the same catalog.
- Each supplier has a quirk profile: how it writes colours ("blk/wht"), lengths ("12in", "30 cm", '12"'), sizes
  ("US 8", "8 US", "EU 41"), gender, its column names, its title template, and a typo rate.
- Products go in through the normal feed import (one feed file per supplier), so they're validated, hashed and
  normalized like any other. Ground truth goes to evals/ground_truth.parquet (regenerable, not committed).
- --feed also writes a 100,000-row feed with 0.5% invalid rows and uploads it to the feeds bucket (a feed awaiting
  commit); --commit-feed then imports it, queueing into a throwaway queue that's deleted afterwards.
- --reset first deletes everything owned by seed suppliers (codes starting "seed-").
"""

import argparse
import asyncio
import csv
import random
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from sqlalchemy import delete, func, select

from shelfsense_api import aws, db, feeds, service
from shelfsense_api.db import Feed, FeedRejection, ImportState, Product, Supplier
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import read_release

REPO = Path(__file__).resolve().parents[1]
PROFILES = {"small": 5_000, "large": 200_000}
SUPPLIERS = 50
FEED_ROWS, FEED_INVALID = 100_000, 0.005


@dataclass(frozen=True)
class Kind:
    noun: str
    path: str  # gold category, a leaf of the current taxonomy release
    materials: tuple[str, ...]
    size: str | None  # "shoe", "alpha" or None
    genders: bool
    length_cm: tuple[int, int] | None  # a dimension worth stating, in whole cm
    price: tuple[int, int]  # USD, whole dollars


KINDS = [
    Kind("Hiking Boot", "Apparel & Accessories > Shoes", ("leather", "nylon", "mesh"), "shoe", True, None, (60, 220)),
    Kind("Trail Running Shoe", "Apparel & Accessories > Shoes", ("mesh", "nylon"), "shoe", True, None, (50, 180)),
    Kind("Rain Jacket", "Apparel & Accessories > Clothing > Outerwear > Coats & Jackets", ("nylon", "polyester"),
         "alpha", True, None, (40, 300)),
    Kind("Down Parka", "Apparel & Accessories > Clothing > Outerwear > Coats & Jackets", ("down", "nylon"), "alpha",
         True, None, (120, 450)),
    Kind("Crew Neck Tee", "Apparel & Accessories > Clothing > Shirts & Tops", ("cotton", "polyester"), "alpha", True,
         None, (10, 45)),
    Kind("Hiking Pants", "Apparel & Accessories > Clothing > Pants", ("nylon", "cotton"), "alpha", True, None,
         (35, 120)),
    Kind("Running Shorts", "Apparel & Accessories > Clothing > Shorts", ("polyester", "nylon"), "alpha", True, None,
         (15, 60)),
    Kind("Hiking Socks", "Apparel & Accessories > Clothing > Underwear & Socks > Socks", ("wool", "cotton"), "alpha",
         True, None, (8, 30)),
    Kind("Sun Hat", "Apparel & Accessories > Clothing Accessories > Hats", ("cotton", "polyester"), "alpha", True,
         None, (12, 50)),
    Kind("Bifold Wallet", "Apparel & Accessories > Handbags, Wallets & Cases > Wallets & Money Clips", ("leather",),
         None, False, (10, 12), (15, 90)),
    Kind("Dog Collar", "Animals & Pet Supplies > Pet Supplies > Pet Collars & Harnesses", ("nylon", "leather"),
         "alpha", False, (25, 60), (8, 40)),
    Kind("Over-Ear Headphones", "Electronics > Audio > Audio Components > Headphones & Headsets > Headphones",
         ("plastic", "aluminum"), None, False, None, (30, 400)),
    Kind("USB-C Charger", "Electronics > Electronics Accessories > Power > Power Adapters & Chargers", ("plastic",),
         None, False, None, (12, 70)),
    Kind("Daypack", "Luggage & Bags > Backpacks", ("nylon", "polyester", "canvas"), None, False, (40, 55),
         (30, 160)),
    Kind("Yoga Mat", "Sporting Goods > Exercise & Fitness > Yoga & Pilates > Yoga & Pilates Mats", ("tpu", "rubber",
         "foam"), None, False, (170, 190), (20, 120)),
    Kind("Insulated Water Bottle", "Home & Garden > Kitchen & Dining > Food & Beverage Carriers > Water Bottles",
         ("stainless steel", "plastic"), None, False, (20, 30), (15, 50)),
    Kind("Cast Iron Skillet",
         "Home & Garden > Kitchen & Dining > Cookware & Bakeware > Cookware > Skillets & Frying Pans", ("cast iron",),
         None, False, (20, 36), (20, 90)),
    Kind("Throw Pillow Cover", "Home & Garden > Decor > Throw Pillows", ("cotton", "polyester", "wool"), None, False,
         (40, 60), (10, 45)),
]
COLORS = ("black", "white", "gray", "brown", "beige", "red", "pink", "orange", "yellow", "green", "blue", "navy",
          "purple", "gold", "silver", "multicolor")
ABBREVIATIONS = {"black": "blk", "white": "wht", "gray": "gry", "brown": "brn", "beige": "tan", "red": "rd",
                 "pink": "pnk", "orange": "orng", "yellow": "ylw", "green": "olive", "blue": "blu", "navy": "nvy",
                 "purple": "prpl", "gold": "gld", "silver": "slvr", "multicolor": "assorted"}
ADJECTIVES = ("Ultralight", "Waterproof", "Classic", "Pro", "Packable", "Rugged", "Everyday", "Trail", "Insulated",
              "Premium", "Compact", "Heritage")
BRANDS = ("Northpeak", "Voltix", "Ridgeway", "Summitline", "Hearthware", "Barkley", "Trailcraft", "Lumen & Co",
          "Basecamp", "Stridewell")
FLUFF = ("BEST SELLER!!!", "Free shipping on orders over $50.", "Our customers love it.", "Limited stock.",
         "Built to last.", "Perfect gift.", "Satisfaction guaranteed.")
TEMPLATES = ("{brand} {adj} {noun}", "{adj} {noun} - {color}", "{noun} {adj} {gender_word}",
             "{brand} {noun} ({color})", "{ADJ} {NOUN}", "{noun}, {adj}, {size}")


@dataclass(frozen=True)
class Quirks:
    code: str
    color_style: str  # full, abbrev, upper
    unit_style: str  # in, cm, inch_mark, both
    size_style: str  # system_first ("US 8"), system_last ("8 US"), eu ("EU 41")
    gender_style: str  # word ("Mens"), letter ("M"), possessive ("Men's")
    columns: tuple[str, str, str, str]  # names for colour, material, gender, size
    template: str
    typo_rate: float
    price_style: str  # plain, dollar


def make_suppliers(rng: random.Random) -> list[Quirks]:
    color_cols, material_cols, gender_cols, size_cols = ("color", "colour", "col"), ("material", "fabric"), (
        "gender", "sex", "dept"), ("size", "sz")
    return [Quirks(
        code=f"seed-{i:02d}", color_style=rng.choice(("full", "abbrev", "upper")),
        unit_style=rng.choice(("in", "cm", "inch_mark", "both")),
        size_style=rng.choice(("system_first", "system_last", "eu")),
        gender_style=rng.choice(("word", "letter", "possessive")),
        columns=(rng.choice(color_cols), rng.choice(material_cols), rng.choice(gender_cols), rng.choice(size_cols)),
        template=rng.choice(TEMPLATES), typo_rate=rng.choice((0.0, 0.0, 0.01, 0.03, 0.06)),
        price_style=rng.choice(("plain", "dollar")),
    ) for i in range(SUPPLIERS)]


def make_truth(rng: random.Random, kind: Kind) -> dict[str, Any]:
    gender = rng.choice(("men", "women", "unisex")) if kind.genders else None
    size: tuple[str, str] | None = None
    if kind.size == "shoe":
        size = ("US", str(rng.randint(6, 12)) + rng.choice(("", ".5")))
    elif kind.size == "alpha":
        size = ("alpha", rng.choice(("XS", "S", "M", "L", "XL", "XXL")))
    length_cm = rng.randint(*kind.length_cm) if kind.length_cm else None
    return {"kind": kind.noun, "color_base": rng.choice(COLORS), "material": rng.choice(kind.materials),
            "gender": gender, "size_system": size[0] if size else None, "size_value": size[1] if size else None,
            "length_mm": length_cm * 10 if length_cm else None, "brand": rng.choice(BRANDS),
            "adjective": rng.choice(ADJECTIVES), "price_minor": rng.randint(kind.price[0] * 100, kind.price[1] * 100 - 1)}


def render(rng: random.Random, q: Quirks, kind: Kind, t: dict[str, Any], sku: str) -> dict[str, str]:
    """One feed row as this supplier would write the item."""
    color = {"full": t["color_base"], "abbrev": ABBREVIATIONS[t["color_base"]],
             "upper": t["color_base"].upper()}[q.color_style]
    if q.color_style == "abbrev" and rng.random() < 0.3:
        color = f"{color}/{ABBREVIATIONS[rng.choice(COLORS[:4])]}"  # a two-tone "blk/gry": the first colour is base
    gender = None
    if t["gender"]:
        gender = {"word": {"men": "Mens", "women": "Womens", "unisex": "Unisex"},
                  "letter": {"men": "M", "women": "W", "unisex": "U"},
                  "possessive": {"men": "Men's", "women": "Women's", "unisex": "Unisex"}}[q.gender_style][t["gender"]]
    size = None
    if t["size_system"] == "US":
        us = t["size_value"]
        size = {"system_first": f"US {us}", "system_last": f"{us} US",
                "eu": f"EU {_eu(us, t['gender'])}"}[q.size_style]
    elif t["size_system"] == "alpha":
        size = t["size_value"]
    length = None
    if t["length_mm"]:
        cm = t["length_mm"] // 10
        inches = round(cm / 2.54)
        length = {"in": f"{inches}in", "cm": f"{cm} cm", "inch_mark": f'{inches}"',
                  "both": f"{inches}in / {cm}cm"}[q.unit_style]
    words = {"brand": t["brand"], "adj": t["adjective"], "noun": kind.noun, "color": color,
             "gender_word": gender or "", "size": size or "", "ADJ": t["adjective"].upper(),
             "NOUN": kind.noun.upper()}
    title = " ".join(_typo(rng, w, q.typo_rate) for w in q.template.format(**words).split())
    description = " ".join(filter(None, [
        rng.choice(FLUFF), f"{t['adjective']} {kind.noun.lower()} in {t['material']}.",
        f"Measures {length}." if length else None, f"Colour: {color}." if rng.random() < 0.5 else None,
    ]))
    dollars = f"{t['price_minor'] // 100}.{t['price_minor'] % 100:02d}"
    row = {"sku": sku, "title": title, "description": description, "brand": t["brand"], "gtin": "",
           "price": f"${dollars}" if q.price_style == "dollar" else dollars, "currency": "USD"}
    color_col, material_col, gender_col, size_col = q.columns
    row |= {color_col: color, material_col: t["material"], gender_col: gender or "", size_col: size or "",
            "length": length or ""}
    return row


def _eu(us: str, gender: str | None) -> str:
    # The same arithmetic as normalize.shoe_size_eu, written out so the seeds don't test the code with itself.
    uk = float(us) - (1 if gender == "men" else 2)
    eu = round((1.27 * uk + 32) * 2) / 2
    return f"{eu:g}"


def _typo(rng: random.Random, word: str, rate: float) -> str:
    if len(word) < 4 or rng.random() >= rate:
        return word
    i = rng.randrange(1, len(word) - 1)
    return word[:i] + word[i + 1] + word[i] + word[i + 2:] if rng.random() < 0.5 else word[:i] + word[i + 1:]


async def reset() -> None:
    async with db.SessionLocal() as session:
        seed_suppliers = select(Supplier.id).where(Supplier.code.like("seed-%"))
        feeds_of = select(Feed.id).where(Feed.supplier_id.in_(seed_suppliers))
        await session.execute(delete(FeedRejection).where(FeedRejection.feed_id.in_(feeds_of)))
        await session.execute(delete(Feed).where(Feed.supplier_id.in_(seed_suppliers)))
        await session.execute(delete(ImportState).where(ImportState.supplier_id.in_(seed_suppliers)))
        removed = (await session.execute(delete(Product).where(Product.supplier_id.in_(seed_suppliers)))).rowcount
        await session.execute(delete(Supplier).where(Supplier.code.like("seed-%")))
        await session.commit()
    print(f"reset: removed {removed} seed products")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=PROFILES, default="small")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--feed", action="store_true")
    parser.add_argument("--commit-feed", action="store_true")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    if args.reset:
        await reset()

    _, nodes = read_release(REPO / "data" / "taxonomy" / f"{settings.taxonomy_version}.txt")
    paths = {node.full_path: node.node_id for node in nodes}
    missing = {k.path for k in KINDS} - paths.keys()
    if missing:
        raise SystemExit(f"not in taxonomy {settings.taxonomy_version}: {sorted(missing)}")

    rng = random.Random(args.seed)
    suppliers = make_suppliers(rng)
    out = REPO / "build" / "seeds" / f"{args.profile}-{args.seed}"
    out.mkdir(parents=True, exist_ok=True)
    total, truth_rows, files = PROFILES[args.profile], [], []
    started = time.perf_counter()
    for n, q in enumerate(suppliers):
        count = total // SUPPLIERS + (1 if n < total % SUPPLIERS else 0)
        rows = []
        for i in range(count):
            kind = rng.choice(KINDS)
            truth = make_truth(rng, kind)
            row = render(rng, q, kind, truth, sku=f"{q.code.upper()}-{i:06d}")
            rows.append(row)
            truth_rows.append({"supplier": q.code, "sku": row["sku"], "title": row["title"],
                               "description": row["description"], "category_id": paths[kind.path],
                               "category_path": kind.path, "quirks": str(asdict(q)), **truth})
        path = out / f"{q.code}.csv"
        with path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        files.append((q.code, path))
    generated = time.perf_counter() - started
    print(f"generated {total:,} products for {SUPPLIERS} suppliers in {generated:.1f}s")

    started = time.perf_counter()
    inserted = updated = unchanged = rejected = 0
    async with db.SessionLocal() as session:
        for code, path in files:
            supplier_id = await feeds.ensure_supplier(session, code)
            feed = Feed(supplier_id=supplier_id, file_name=path.name)
            session.add(feed)
            await session.commit()
            result = await feeds.import_file(session, path, feed.id, supplier_id)
            inserted, updated = inserted + result.inserted, updated + result.updated
            unchanged, rejected = unchanged + result.unchanged, rejected + len(result.rejections)
    loaded = time.perf_counter() - started
    print(f"loaded {total:,} rows in {loaded:.1f}s ({total / loaded:,.0f} rows/s): {inserted:,} inserted, "
          f"{updated:,} updated, {unchanged:,} unchanged, {rejected} rejected")

    await check_normalization(truth_rows)

    (REPO / "evals").mkdir(exist_ok=True)
    pq.write_table(pa.Table.from_pylist(truth_rows), REPO / "evals" / "ground_truth.parquet", compression="zstd")
    print(f"ground truth: evals/ground_truth.parquet ({len(truth_rows):,} rows)")

    async with db.SessionLocal() as session:
        counts = (await session.execute(select(func.count(func.distinct(Product.supplier_id)), func.count())
                                        .select_from(Product).join(Supplier)
                                        .where(Supplier.code.like("seed-%")))).one()
        print(f"database: {counts[1]:,} seed products from {counts[0]} seed suppliers")

    if args.feed or args.commit_feed:
        await big_feed(rng, suppliers[0], paths, out, args.commit_feed)


async def check_normalization(truth_rows: list[dict[str, Any]]) -> None:
    """How often the stored typed columns equal the ground truth: the normalizers' accuracy on these quirks."""
    async with db.SessionLocal() as session:
        stored = {(code, sku): (c, m, g, s, v) for code, sku, c, m, g, s, v in (await session.execute(
            select(Supplier.code, Product.supplier_sku, Product.color_base, Product.material, Product.gender,
                   Product.size_system, Product.size_value).join(Supplier).where(Supplier.code.like("seed-%"))
        ))}
    fields = ("color_base", "material", "gender", "size")
    right = dict.fromkeys(fields, 0)
    for t in truth_rows:
        c, m, g, system, value = stored[(t["supplier"], t["sku"])]
        right["color_base"] += c == t["color_base"]
        right["material"] += m == t["material"]
        right["gender"] += g == t["gender"]
        # A US size the supplier wrote in EU counts as right when it names the same size.
        right["size"] += (system, value) == (t["size_system"], t["size_value"]) or (
            system == "EU" and t["size_system"] == "US" and value == _eu(t["size_value"], t["gender"]))
    print("normalized columns matching ground truth: " +
          ", ".join(f"{f} {right[f] / len(truth_rows):.1%}" for f in fields))


async def big_feed(rng: random.Random, q: Quirks, paths: dict[str, int], out: Path, commit: bool) -> None:
    """A 100,000-row feed with 0.5% invalid rows, uploaded as a feed awaiting commit."""
    path = out / "bulk-feed.csv"
    bad = set(rng.sample(range(FEED_ROWS), int(FEED_ROWS * FEED_INVALID)))
    breakers = [("title", ""), ("price", "-4.00"), ("price", "abc"), ("currency", "DOLLARS"), ("gtin", "12345")]
    with path.open("w", newline="") as f:
        writer = None
        for i in range(FEED_ROWS):
            kind = rng.choice(KINDS)
            row = render(rng, q, kind, make_truth(rng, kind), sku=f"BULK-{i:06d}")
            if i in bad:
                column, value = breakers[i % len(breakers)]
                row[column] = value
            if writer is None:
                writer = csv.DictWriter(f, fieldnames=list(row))
                writer.writeheader()
            writer.writerow(row)
    print(f"bulk feed: {FEED_ROWS:,} rows, {len(bad)} invalid, {path.stat().st_size / 1e6:.1f} MB")

    async with db.SessionLocal() as session:
        upload = await service.create_feed_upload(session, "seed-bulk", path.name)
        async with aws.s3() as s3:
            with path.open("rb") as f:
                await s3.put_object(Bucket=settings.feeds_bucket, Key=f"{upload.feed_id}.csv", Body=f)
        print(f"uploaded as feed {upload.feed_id} (awaiting commit)")
        if not commit:
            return
        # Measure the import, but keep its 100k enrichment requests out of the real queue.
        real_queue, settings.enrich_queue = settings.enrich_queue, f"seed-throwaway-{upload.feed_id.hex[:8]}"
        try:
            async with aws.sqs() as sqs, aws.s3() as s3:
                await aws.ensure_resources(sqs, s3)
            started = time.perf_counter()
            result = await service.commit_feed(session, upload.feed_id)
            took = time.perf_counter() - started
            print(f"committed: {result.rows:,} rows in {took:.1f}s ({result.rows / took:,.0f} rows/s), "
                  f"{result.inserted:,} inserted, {result.rejected} rejected, {result.enqueued:,} queued "
                  f"(throwaway queue)")
            reasons: dict[str, int] = {}
            for r in result.rejections:
                reasons[r.reason_code] = reasons.get(r.reason_code, 0) + 1
            print(f"  rejections by reason: {reasons}")
        finally:
            async with aws.sqs() as sqs:
                for name in (settings.enrich_queue, aws.dlq_name(settings.enrich_queue)):
                    await sqs.delete_queue(QueueUrl=await aws.queue_url(sqs, name))
            settings.enrich_queue = real_queue


if __name__ == "__main__":
    asyncio.run(main())
