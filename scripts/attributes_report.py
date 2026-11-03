"""Extracted attributes, shown with their evidence highlighted in the listing, plus grounding counts and, for seed
products, accuracy against the seed ground truth.

    uv run python scripts/attributes_report.py --sample 20 [--enqueue]   # 20 seed products (fixed sample)

--enqueue queues the sample for enrichment and waits until the enrich worker has done them (start it first).
"""

import argparse
import asyncio
import random
import time
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq
from sqlalchemy import func, select

from shelfsense_api import aws, prompts, service
from shelfsense_api.classify import evidence_fields
from shelfsense_api.db import (
    EnrichmentRun,
    Product,
    ProductAttribute,
    ProductCategory,
    ProductExtractedAttribute,
    SessionLocal,
    Supplier,
    TaxonomyNode,
)
from shelfsense_api.normalize import parse_size, shoe_size_eu
from shelfsense_api.settings import settings

REPO = Path(__file__).resolve().parents[1]
FIELDS = ("color", "material", "gender", "size", "length")


def sample_truth(n: int) -> list[dict[str, Any]]:
    rows = pq.read_table(REPO / "evals" / "ground_truth.parquet").to_pylist()
    return random.Random(5).sample(rows, n)


def truth_value(t: dict[str, Any], name: str) -> str | None:
    if name == "size":
        return f"US {t['size_value']}" if t["size_system"] == "US" else t["size_value"]
    if name == "length":
        return str(t["length_mm"]) if t["length_mm"] else None
    return t[{"color": "color_base"}.get(name, name)]


def same(name: str, extracted: str, truth: str, gender: str | None) -> bool:
    if name == "size" and extracted != truth:
        a, b = parse_size(extracted), parse_size(truth)
        if a and b and "alpha" not in (a[0], b[0]):
            return shoe_size_eu(*a, gender) == shoe_size_eu(*b, gender)
    if name == "length":  # the seeds state lengths in rounded inches or whole cm
        return abs(int(extracted) - int(truth)) <= 13
    return extracted == truth


def highlight(text: str, spans: list[tuple[int, int]]) -> str:
    for start, end in sorted(spans, reverse=True):
        text = f"{text[:start]}«{text[start:end]}»{text[end:]}"
    return text


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=int, default=20)
    parser.add_argument("--enqueue", action="store_true")
    args = parser.parse_args()
    truths = sample_truth(args.sample)

    async with SessionLocal() as session:
        keys = [(t["supplier"], t["sku"]) for t in truths]
        products = {(code, p.supplier_sku): p for p, code in (await session.execute(
            select(Product, Supplier.code).join(Supplier).where(Supplier.code.in_({k[0] for k in keys}),
                                                               Product.supplier_sku.in_({k[1] for k in keys}))))}
        ids = [products[k].id for k in keys]
        if args.enqueue:
            async with aws.sqs() as sqs:
                queued = await service.enqueue_enrichment(session, sqs, ids)
            print(f"queued {queued} for enrichment; waiting for the enrich worker")
            started = time.perf_counter()
            while await session.scalar(select(func.count()).select_from(ProductCategory).where(
                    ProductCategory.product_id.in_(ids), ProductCategory.taxonomy_version == settings.taxonomy_version,
                    ProductCategory.prompt_version == prompts.ENRICH_VERSION)) < len(ids):
                await asyncio.sleep(3)
                session.expire_all()
            print(f"enriched in {time.perf_counter() - started:.0f}s\n")

        stats: Counter[str] = Counter()
        for t, product_id in zip(truths, ids, strict=True):
            product = await session.get(Product, product_id)
            assert product is not None
            raw = dict((await session.execute(select(ProductAttribute.name, ProductAttribute.value)
                                              .where(ProductAttribute.product_id == product_id))).all())
            fields = evidence_fields(product.title, product.brand, product.description, raw)
            attrs = list(await session.scalars(select(ProductExtractedAttribute)
                                               .where(ProductExtractedAttribute.product_id == product_id)))
            run = await session.scalar(select(EnrichmentRun).where(EnrichmentRun.product_id == product_id,
                                                                    EnrichmentRun.outcome == "enriched")
                                       .order_by(EnrichmentRun.created_at.desc()).limit(1))
            category = await session.get(ProductCategory, (product_id, settings.taxonomy_version))
            path = await session.scalar(select(TaxonomyNode.full_path).where(
                TaxonomyNode.version == settings.taxonomy_version, TaxonomyNode.node_id == category.node_id)) \
                if category and category.node_id else None

            print(f"{t['supplier']} {t['sku']}  ({run.wall_ms / 1000:.1f}s)" if run else t["sku"])
            for name in ("title", "description", "raw_attributes"):
                spans = [(a.evidence_start, a.evidence_end) for a in attrs if a.evidence_field == name]
                print(f"  {name:15} {highlight(fields[name], spans)}")
            right_category = category is not None and category.node_id == t["category_id"]
            stats["category_right"] += right_category
            print(f"  {'category':15} {path} ({category.confidence if category else '-'})"
                  f" {'ok' if right_category else 'gold: ' + t['category_path']}")
            got = {a.name: a.value for a in attrs}
            marks = []
            for name in FIELDS:
                truth = truth_value(t, name)
                value = got.get(name)
                if value is not None:
                    stats[f"{name}_extracted"] += 1
                    ok = truth is not None and same(name, value, truth, t["gender"])
                    stats[f"{name}_correct"] += ok
                    marks.append(f"{name}={value}{'' if ok else ' (truth ' + str(truth) + ')'}")
                if truth is not None:
                    stats[f"{name}_truth"] += 1
                    stats[f"{name}_found"] += value is not None and same(name, value, truth, t["gender"])
            ungrounded, unnormalized = (run.ungrounded_attributes or 0, run.unnormalized_attributes or 0) if run \
                else (0, 0)
            stats["ungrounded"] += ungrounded
            stats["unnormalized"] += unnormalized
            stats["kept"] += len(attrs)
            stats["seconds"] += run.wall_ms / 1000 if run else 0
            print(f"  {'attributes':15} {', '.join(marks) or '(none)'}; dropped: {ungrounded} ungrounded, "
                  f"{unnormalized} unnormalized\n")

    n = len(truths)
    emitted = stats["kept"] + stats["ungrounded"] + stats["unnormalized"]
    print(f"# {n} seed products, enriched by {settings.llm_model} ({prompts.ENRICH_VERSION})")
    print(f"category accuracy {stats['category_right']}/{n}; {stats['seconds'] / n:.1f}s per product "
          f"(~{3600 / (stats['seconds'] / n):,.0f}/hour)")
    print(f"attributes emitted {emitted}: kept {stats['kept']}, ungrounded {stats['ungrounded']} "
          f"({stats['ungrounded'] / max(emitted, 1):.1%}), unnormalized {stats['unnormalized']}")
    print(f"{'attribute':10} {'precision':>10} {'recall':>8}")
    for name in FIELDS:
        precision = stats[f"{name}_correct"] / stats[f"{name}_extracted"] if stats[f"{name}_extracted"] else None
        recall = stats[f"{name}_found"] / stats[f"{name}_truth"] if stats[f"{name}_truth"] else None
        print(f"{name:10} {_pct(precision, stats[f'{name}_correct'], stats[f'{name}_extracted']):>10} "
              f"{_pct(recall, stats[f'{name}_found'], stats[f'{name}_truth']):>8}")


def _pct(value: float | None, num: int, den: int) -> str:
    return "-" if value is None else f"{num}/{den}"


if __name__ == "__main__":
    asyncio.run(main())
