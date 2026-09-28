"""Cross-encoder reranking (local ONNX model via fastembed).

A cross-encoder reads the query and a candidate passage together and outputs a relevance score
(a logit: higher = more relevant; around 0 is "unsure", strongly negative is "irrelevant").
It is slower than embeddings, so we only rerank the top ~20 fused candidates.
The top rerank score also drives the evidence gate (see answer/gate thresholds in config).
"""

from __future__ import annotations

import logging
import threading

from bisense.config import get_settings

log = logging.getLogger("bisense.rerank")
_lock = threading.Lock()
_model = None
_load_error: str | None = None


class RerankerUnavailable(RuntimeError):
    """The cross-encoder model could not be loaded (e.g. first run offline). Search continues without it."""


def load_error() -> str | None:
    """Why the reranker failed to load, or None (used by /api/health and `bisense doctor`)."""
    return _load_error


def get_reranker():
    global _model, _load_error
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    with _lock:
        if _model is None:
            if _load_error is not None:
                raise RerankerUnavailable(_load_error)
            try:
                settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
                _model = TextCrossEncoder(model_name=settings.reranker_model, cache_dir=str(settings.model_cache_dir), threads=settings.onnx_threads)
            except Exception as e:  # download blocked, offline first run, corrupt cache
                _load_error = f"{type(e).__name__}: {str(e)[:200]}"
                log.warning("reranker unavailable, continuing with hybrid ranking only: %s", _load_error)
                raise RerankerUnavailable(_load_error) from e
        return _model


def rerank(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    model = get_reranker()
    return [float(s) for s in model.rerank(query, passages)]
