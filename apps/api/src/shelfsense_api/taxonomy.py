"""The Google Product Taxonomy: parsing and loading release files, picking candidate leaves, and working out
where each category went between two releases."""

import asyncio
import hashlib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api.db import TaxonomyNode
from shelfsense_api.embeddings import embed_passages

VERSION_HEADER = "# Google_Product_Taxonomy_Version: "


@dataclass(frozen=True)
class Node:
    node_id: int
    parent_id: int | None
    name: str
    full_path: str
    depth: int
    is_leaf: bool


def read_release(path: Path) -> tuple[str, list[Node]]:
    """The version and nodes of one release file ("<id> - A > B > C" per line). Refuses a file whose checksum
    doesn't match the `.sha256` written next to it by `make taxonomy`."""
    expected = path.with_name(path.name + ".sha256").read_text().split()[0]
    actual = hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise ValueError(f"{path} checksum {actual} does not match {expected}")

    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines[0].startswith(VERSION_HEADER):
        raise ValueError(f"{path} has no version header")
    version = lines[0].removeprefix(VERSION_HEADER).strip()

    rows = []
    for line in lines[1:]:
        node_id, _, full_path = line.partition(" - ")
        rows.append((int(node_id), full_path.strip()))
    id_by_path = {full_path: node_id for node_id, full_path in rows}
    parents = set()
    nodes = []
    for node_id, full_path in rows:
        segments = full_path.split(" > ")
        parent_id = id_by_path[" > ".join(segments[:-1])] if len(segments) > 1 else None
        if parent_id is not None:
            parents.add(parent_id)
        nodes.append(Node(node_id, parent_id, segments[-1], full_path, len(segments), is_leaf=False))
    return version, [Node(**{**n.__dict__, "is_leaf": n.node_id not in parents}) for n in nodes]


async def nearest_leaves(session: AsyncSession, version: str, query: list[float], k: int) -> list[TaxonomyNode]:
    """The k leaf categories whose path is closest to the query, nearest first (exact cosine scan)."""
    result = await session.scalars(
        select(TaxonomyNode)
        .where(TaxonomyNode.version == version, TaxonomyNode.is_leaf)
        .order_by(TaxonomyNode.embedding.cosine_distance(query))
        .limit(k)
    )
    return list(result)


async def load_release(session: AsyncSession, path: Path) -> tuple[str, int]:
    """Load a release file into taxonomy_nodes with each full path embedded, beside any releases already there.
    Returns its version and how many nodes were added (0 if it was loaded already)."""
    version, nodes = read_release(path)
    loaded = await session.scalar(select(func.count()).where(TaxonomyNode.version == version))
    if loaded == len(nodes):
        return version, 0
    vectors = await asyncio.to_thread(embed_passages, [n.full_path for n in nodes])
    # Parents come before children in the file, so inserting in file order satisfies the parent foreign key.
    rows = [{"version": version, **n.__dict__, "embedding": v} for n, v in zip(nodes, vectors, strict=True)]
    for start in range(0, len(rows), 1000):
        await session.execute(insert(TaxonomyNode).values(rows[start:start + 1000]).on_conflict_do_nothing())
    await session.commit()
    return version, len(nodes)


@dataclass(frozen=True)
class Remap:
    old_node_id: int
    new_node_id: int | None
    kind: str  # same, renamed, split, merged, deleted
    needs_review: bool
    note: str


def diff_releases(old: list[Node], new: list[Node]) -> list[Remap]:
    """Where each category of `old` went in `new`, matching by ID first (Google keeps IDs across renames), then by
    path. A leaf that gained children is split: its products need a new pick among them. Several old categories
    landing on one new one are merged. Anything matched only by path, or not at all, is flagged for review."""
    new_by_id = {n.node_id: n for n in new}
    new_by_path = {n.full_path: n for n in new}
    remaps = []
    for o in old:
        n = new_by_id.get(o.node_id)
        if n is not None:
            if o.is_leaf and not n.is_leaf:
                children = [c.name for c in new if c.parent_id == n.node_id]
                remaps.append(Remap(o.node_id, None, "split", False, f"now split into {', '.join(children)}"))
            elif n.full_path == o.full_path:
                remaps.append(Remap(o.node_id, n.node_id, "same", False, ""))
            else:
                remaps.append(Remap(o.node_id, n.node_id, "renamed", False, f"{o.full_path} -> {n.full_path}"))
        elif (n := new_by_path.get(o.full_path)) is not None:
            remaps.append(Remap(o.node_id, n.node_id, "renamed", True, f"ID {o.node_id} -> {n.node_id}, same path"))
        elif any(c.full_path.startswith(o.full_path + " > ") for c in new):
            remaps.append(Remap(o.node_id, None, "split", True, "ID removed; its path now has subcategories"))
        else:
            remaps.append(Remap(o.node_id, None, "deleted", True, f"{o.full_path} is gone"))

    targets = Counter(r.new_node_id for r in remaps if r.new_node_id is not None)
    return [Remap(r.old_node_id, r.new_node_id, "merged", True, f"one of {targets[r.new_node_id]} merged into "
                  f"{new_by_id[r.new_node_id].full_path}")
            if r.new_node_id is not None and targets[r.new_node_id] > 1 else r for r in remaps]
