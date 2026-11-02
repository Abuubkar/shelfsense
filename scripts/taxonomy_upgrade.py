"""Prepare a taxonomy upgrade while the current release keeps being served (docs/migrations.md):

    uv run python scripts/taxonomy_upgrade.py build/taxonomy/2021-09-21-next.txt [--no-enqueue]
    uv run python scripts/taxonomy_upgrade.py build/taxonomy/2021-09-21-next.txt --status

1. Load the new release beside the served one (settings.taxonomy_version), paths embedded.
2. Diff the two (taxonomy.diff_releases) into taxonomy_remaps: same, renamed, split, merged, deleted.
3. Products in same, renamed or merged categories get their category in the new release by SQL, copied from the old.
4. Products in split or deleted categories are stale: they're queued for classification into the new release.
5. --status: how many products still lack a category in the new release. At 0, switch TAXONOMY_VERSION (restart
   the API and workers).
6. --reindex, after the switch (or a switch back): queue index requests for the products whose category changed
   (anything but "same"), so search shows the served release's paths. Other products keep their documents.
"""

import asyncio
import sys
from collections import Counter
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.dialects.postgresql import insert

from shelfsense_api import aws
from shelfsense_api.db import ProductCategory, SessionLocal, TaxonomyRemap
from shelfsense_api.messages import MAX_INDEX_IDS, EnrichRequest, IndexRequest
from shelfsense_api.settings import settings
from shelfsense_api.taxonomy import diff_releases, load_release, read_release

REPO = Path(__file__).resolve().parents[1]

REMAP_SQL = text("""
    INSERT INTO product_categories (product_id, taxonomy_version, node_id, confidence, candidate_ids, model,
                                    prompt_version, content_hash, prompt_tokens, output_tokens, total_ms,
                                    prompt_eval_ms, eval_ms, created_at)
    SELECT pc.product_id, r.new_version, r.new_node_id, pc.confidence, pc.candidate_ids, pc.model, pc.prompt_version,
           pc.content_hash, pc.prompt_tokens, pc.output_tokens, pc.total_ms, pc.prompt_eval_ms, pc.eval_ms, now()
    FROM product_categories pc
    JOIN taxonomy_remaps r ON r.old_version = pc.taxonomy_version AND r.old_node_id = pc.node_id
                          AND r.new_version = :new
    WHERE pc.taxonomy_version = :old AND r.kind IN ('same', 'renamed', 'merged')
    ON CONFLICT (product_id, taxonomy_version) DO NOTHING
""")
# A model that answered NONE (no candidate fit) answers the same in the new release until the product changes.
NONE_SQL = text("""
    INSERT INTO product_categories (product_id, taxonomy_version, node_id, confidence, candidate_ids, model,
                                    prompt_version, content_hash, prompt_tokens, output_tokens, total_ms,
                                    prompt_eval_ms, eval_ms, created_at)
    SELECT product_id, :new, NULL, confidence, candidate_ids, model, prompt_version, content_hash, prompt_tokens,
           output_tokens, total_ms, prompt_eval_ms, eval_ms, now()
    FROM product_categories WHERE taxonomy_version = :old AND node_id IS NULL
    ON CONFLICT (product_id, taxonomy_version) DO NOTHING
""")
STALE_SQL = text("""
    SELECT pc.product_id FROM product_categories pc
    JOIN taxonomy_remaps r ON r.old_version = pc.taxonomy_version AND r.old_node_id = pc.node_id
                          AND r.new_version = :new
    WHERE pc.taxonomy_version = :old AND r.kind IN ('split', 'deleted')
""")
CHANGED_SQL = text("""
    SELECT DISTINCT pc.product_id FROM product_categories pc
    JOIN taxonomy_remaps r ON r.old_version = pc.taxonomy_version AND r.old_node_id = pc.node_id
                          AND r.new_version = :new
    WHERE r.kind <> 'same'
""")
MISSING_SQL = text("""
    SELECT count(*) FROM product_categories old
    WHERE old.taxonomy_version = :old AND NOT EXISTS (
        SELECT 1 FROM product_categories new WHERE new.product_id = old.product_id AND new.taxonomy_version = :new)
""")


async def main() -> None:
    path = Path(sys.argv[1])
    old = settings.taxonomy_version
    new, _ = read_release(path)
    params = {"old": old, "new": new}
    async with SessionLocal() as session:
        if "--reindex" in sys.argv:
            # After the switch the served version is `new`, so the old one comes from the remaps. Works the same
            # after switching back (a rollback): the index follows whichever release is served.
            before = await session.scalar(select(TaxonomyRemap.old_version).where(TaxonomyRemap.new_version == new)
                                          .limit(1))
            if settings.taxonomy_version not in (before, new):
                raise SystemExit(f"serving {settings.taxonomy_version}, neither {before} nor {new}")
            changed = list(await session.scalars(CHANGED_SQL, {"old": before, "new": new}))
            async with aws.sqs() as sqs:
                await aws.send(sqs, settings.index_queue, [
                    IndexRequest(product_ids=changed[i:i + MAX_INDEX_IDS]).model_dump_json()
                    for i in range(0, len(changed), MAX_INDEX_IDS)])
            print(f"queued {len(changed)} products whose category changed, to reindex under "
                  f"{settings.taxonomy_version}")
            return
        if "--status" in sys.argv:
            missing = await session.scalar(MISSING_SQL, params)
            moved = await session.scalar(select(func.count()).select_from(ProductCategory)
                                         .where(ProductCategory.taxonomy_version == new))
            print(f"{new}: {moved} products categorized, {missing} still waiting"
                  + ("; ready to switch TAXONOMY_VERSION" if not missing else ""))
            return

        version, added = await load_release(session, path)
        print(f"loaded {version}: {added or 'already there, no'} new nodes")

        _, old_nodes = read_release(REPO / "data" / "taxonomy" / f"{old}.txt")
        _, new_nodes = read_release(path)
        remaps = diff_releases(old_nodes, new_nodes)
        await session.execute(delete(TaxonomyRemap).where(TaxonomyRemap.old_version == old,
                                                          TaxonomyRemap.new_version == new))
        rows = [{"old_version": old, "new_version": new, **r.__dict__} for r in remaps]
        for start in range(0, len(rows), 2000):
            await session.execute(insert(TaxonomyRemap).values(rows[start:start + 2000]))
        await session.commit()
        kinds = Counter(r.kind for r in remaps)
        print(f"remaps {old} -> {new}: {dict(kinds)}; {sum(r.needs_review for r in remaps)} need review")
        for r in remaps:
            if r.kind != "same":
                print(f"  {r.kind:8} {r.old_node_id:>7} -> {r.new_node_id or '-':>7}  {r.note}")

        by_kind = dict((await session.execute(text("""
            SELECT r.kind, count(*) FROM product_categories pc
            JOIN taxonomy_remaps r ON r.old_version = pc.taxonomy_version AND r.old_node_id = pc.node_id
                                  AND r.new_version = :new
            WHERE pc.taxonomy_version = :old GROUP BY r.kind"""), params)).all())
        remapped = (await session.execute(REMAP_SQL, params)).rowcount
        kept_none = (await session.execute(NONE_SQL, params)).rowcount
        await session.commit()
        stale = list(await session.scalars(STALE_SQL, params))
        print(f"products by kind of their category: {by_kind}")
        print(f"remapped {remapped} products by SQL, carried over {kept_none} NONE answers, {len(stale)} stale")

        if stale and "--no-enqueue" not in sys.argv:
            batch = settings.enrich_batch_size
            async with aws.sqs() as sqs:
                await aws.send(sqs, settings.enrich_queue, [
                    EnrichRequest(product_ids=stale[i:i + batch], taxonomy_version=new).model_dump_json()
                    for i in range(0, len(stale), batch)])
            print(f"queued {len(stale)} stale products for classification into {new}")
        print(f"next: run the enrich worker, then `{Path(sys.argv[0]).name} {path} --status`")


if __name__ == "__main__":
    asyncio.run(main())
