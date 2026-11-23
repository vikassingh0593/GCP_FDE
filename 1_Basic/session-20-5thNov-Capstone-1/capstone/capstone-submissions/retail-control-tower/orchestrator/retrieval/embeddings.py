"""Embeddings with gemini-embedding-001 on Vertex AI (Gate 3).

Chunks use task type RETRIEVAL_DOCUMENT and questions RETRIEVAL_QUERY: the
model is trained to place a question near the passage that answers it
(session 8 _embed_one / embed_query). One model and one dimension per index:
every chunk row records both, and search only compares like with like.

Used by scripts/ingest_docs.py (documents) and orchestrator/retrieval/search.py
(questions), so both sides always embed the same way.
"""

from __future__ import annotations

from google.genai import types

from common import config
from common.clients import genai_client, with_retry
from orchestrator.retrieval.cache import TTLCache

_query_cache = TTLCache("query_embeddings", config.QUERY_EMBEDDING_CACHE_TTL_SECONDS)


def embed(text: str, task_type: str, *, dimension: int | None = None, title: str | None = None) -> list[float]:
    dimension = dimension or config.EMBEDDING_DIMENSION
    embed_config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=dimension)
    if title and task_type == "RETRIEVAL_DOCUMENT":
        embed_config.title = title
    client = genai_client(config.EMBEDDING_LOCATION)
    response = with_retry(lambda: client.models.embed_content(
        model=config.EMBEDDING_MODEL, contents=text, config=embed_config), f"embed:{task_type}")
    return list(response.embeddings[0].values)


def embed_document(text: str, *, title: str | None = None, dimension: int | None = None) -> list[float]:
    return embed(text, "RETRIEVAL_DOCUMENT", dimension=dimension, title=title)


def embed_query(text: str, *, dimension: int | None = None) -> tuple[list[float], bool]:
    """(vector, cache_hit). Cached for weeks: same text + same model + same dimension = same vector."""
    dimension = dimension or config.EMBEDDING_DIMENSION
    text = " ".join(text.split())
    key = TTLCache.key(text, config.EMBEDDING_MODEL, dimension, "RETRIEVAL_QUERY")
    cached = _query_cache.get(key)
    if cached is not None:
        return cached, True
    vector = embed(text, "RETRIEVAL_QUERY", dimension=dimension)
    _query_cache.put(key, vector)
    return vector, False


def cache_stats() -> dict:
    return _query_cache.stats()
