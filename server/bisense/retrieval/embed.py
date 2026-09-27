"""Local text embeddings with fastembed (ONNX runtime, no PyTorch, works offline once downloaded).

Two entry points:
  - embed_passages(texts): for chunks at ingest time
  - embed_query(text):     for user queries (cached in an LRU; some models add a query prefix)
Vectors are L2-normalised float32 so cosine similarity is a plain dot product.
"""

from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

from bisense.config import get_settings

_lock = threading.Lock()
_models: dict[str, object] = {}


def get_model(name: str | None = None):
    from fastembed import TextEmbedding

    settings = get_settings()
    name = name or settings.embedding_model
    with _lock:
        if name not in _models:
            settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
            _models[name] = TextEmbedding(model_name=name, cache_dir=str(settings.model_cache_dir))
        return _models[name]


def _normalize(m: np.ndarray) -> np.ndarray:
    m = m.astype(np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


def embed_passages(texts: list[str], model_name: str | None = None, batch_size: int = 64) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)
    model = get_model(model_name)
    vecs = list(model.passage_embed(texts, batch_size=batch_size))  # type: ignore[attr-defined]
    return _normalize(np.vstack(vecs))


@lru_cache(maxsize=512)
def _embed_query_cached(text: str, model_name: str) -> bytes:
    model = get_model(model_name)
    vec = next(iter(model.query_embed([text])))  # type: ignore[attr-defined]
    return _normalize(np.asarray([vec]))[0].tobytes()


def embed_query(text: str, model_name: str | None = None) -> np.ndarray:
    name = model_name or get_settings().embedding_model
    return np.frombuffer(_embed_query_cached(text, name), dtype=np.float32)
