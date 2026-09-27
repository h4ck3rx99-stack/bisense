"""Cross-encoder reranking (local ONNX model via fastembed).

A cross-encoder reads the query and a candidate passage together and outputs a relevance score
(a logit: higher = more relevant; around 0 is "unsure", strongly negative is "irrelevant").
It is slower than embeddings, so we only rerank the top ~20 fused candidates.
The top rerank score also drives the evidence gate (see answer/gate thresholds in config).
"""

from __future__ import annotations

import threading

from bisense.config import get_settings

_lock = threading.Lock()
_model = None


def get_reranker():
    global _model
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    settings = get_settings()
    with _lock:
        if _model is None:
            settings.model_cache_dir.mkdir(parents=True, exist_ok=True)
            _model = TextCrossEncoder(model_name=settings.reranker_model, cache_dir=str(settings.model_cache_dir), threads=settings.onnx_threads)
        return _model


def rerank(query: str, passages: list[str]) -> list[float]:
    if not passages:
        return []
    model = get_reranker()
    return [float(s) for s in model.rerank(query, passages)]
