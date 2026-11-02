"""The one way Shelfsense embeds and reranks text: bge models through fastembed, on the CPU."""

from functools import cache

from fastembed import TextEmbedding
from fastembed.rerank.cross_encoder import TextCrossEncoder

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "BAAI/bge-reranker-base"
# Long descriptions add compute, not signal: what a product is shows in its title and first lines.
MAX_PRODUCT_TEXT_CHARS = 1500


@cache
def _embedder() -> TextEmbedding:
    # Downloads the model on first use (~130 MB, cached by fastembed).
    return TextEmbedding(model_name=EMBEDDING_MODEL)


@cache
def _reranker() -> TextCrossEncoder:
    # ~1.1 GB on first use.
    return TextCrossEncoder(model_name=RERANK_MODEL)


def product_text(title: str, brand: str | None, description: str | None) -> str:
    return " ".join(filter(None, [title, brand, description]))[:MAX_PRODUCT_TEXT_CHARS]


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Documents that get searched over (taxonomy paths, products): bge's passage side."""
    return [v.tolist() for v in _embedder().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    """What is searched for: bge prefixes it with its retrieval instruction."""
    return next(iter(_embedder().query_embed(text))).tolist()


def rerank(query: str, texts: list[str]) -> list[float]:
    """Cross-encoder relevance of each text to the query (higher is better; not a probability)."""
    return [float(s) for s in _reranker().rerank(query, texts)]
