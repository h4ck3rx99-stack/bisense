"""Semantic search: brute-force cosine similarity over the in-memory embedding matrix."""

from __future__ import annotations

import numpy as np

from bisense.retrieval.index import LoadedIndex


def vector_search(index: LoadedIndex, query_vec: np.ndarray, limit: int = 40, standard_ids: list[int] | None = None) -> list[tuple[int, float]]:
    if index.matrix.shape[0] == 0:
        return []
    if standard_ids:
        rows = index.rows_for_standards(standard_ids)
        if rows.size == 0:
            return []
        sims = index.matrix[rows] @ query_vec
        order = np.argsort(-sims)[:limit]
        return [(int(index.chunk_ids[rows[i]]), float(sims[i])) for i in order]
    sims = index.matrix @ query_vec
    k = min(limit, sims.shape[0])
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    return [(int(index.chunk_ids[i]), float(sims[i])) for i in top]
