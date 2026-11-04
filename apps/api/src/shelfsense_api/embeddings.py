"""The one way Shelfsense embeds and reranks text: bge-small and a MiniLM cross-encoder through fastembed, on the CPU."""

from functools import cache

from fastembed import TextEmbedding
from fastembed.common.model_description import ModelSource
from fastembed.rerank.cross_encoder import TextCrossEncoder

from shelfsense_api.settings import settings

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
# ms-marco-MiniLM-L-6-v2 quantized to int8 (the same repo's onnx/model_int8.onnx): ~2x faster than its fp32 build on
# the CPU, ~20x faster than bge-reranker-base, and no worse on the golden set (docs/adr/0021).
RERANK_MODEL = "shelfsense/ms-marco-MiniLM-L-6-v2-int8"
TextCrossEncoder.add_custom_model(RERANK_MODEL, sources=ModelSource(hf="Xenova/ms-marco-MiniLM-L-6-v2"),
                                  model_file="onnx/model_int8.onnx", size_in_gb=0.023)
# Long descriptions add compute, not signal: what a product is shows in its title and first lines.
MAX_PRODUCT_TEXT_CHARS = 1500


@cache
def _embedder() -> TextEmbedding:
    # Downloads the model on first use (~130 MB, cached by fastembed).
    return TextEmbedding(model_name=EMBEDDING_MODEL)


@cache
def _reranker() -> TextCrossEncoder:
    # ~23 MB on first use.
    return TextCrossEncoder(model_name=RERANK_MODEL, threads=settings.rerank_threads)


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
