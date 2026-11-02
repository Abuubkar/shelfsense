"""The Google Product Taxonomy: parsing the release files, embedding paths, and picking candidate leaves."""

import hashlib
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from fastembed import TextEmbedding
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shelfsense_api.db import TaxonomyNode

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
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


@cache
def _embedder() -> TextEmbedding:
    # Downloads the model on first use (~130 MB, cached by fastembed), then runs on CPU.
    return TextEmbedding(model_name=EMBEDDING_MODEL)


def embed_paths(paths: list[str]) -> list[list[float]]:
    """Taxonomy paths are the documents searched over: bge's passage side."""
    return [v.tolist() for v in _embedder().passage_embed(paths)]


def embed_query(text: str) -> list[float]:
    """A product's text is the query: bge prefixes it with its retrieval instruction."""
    return next(iter(_embedder().query_embed(text))).tolist()


async def nearest_leaves(session: AsyncSession, version: str, query: list[float], k: int) -> list[TaxonomyNode]:
    """The k leaf categories whose path is closest to the query, nearest first (exact cosine scan)."""
    result = await session.scalars(
        select(TaxonomyNode)
        .where(TaxonomyNode.version == version, TaxonomyNode.is_leaf)
        .order_by(TaxonomyNode.embedding.cosine_distance(query))
        .limit(k)
    )
    return list(result)
