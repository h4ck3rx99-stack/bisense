"""Reciprocal Rank Fusion (RRF) plus small, explainable boosts.

RRF: score(d) = sum over ranked lists of 1 / (k + rank(d)), k = 60.
It needs no score calibration between BM25 and cosine similarity, which is why it is the standard
way to combine lexical and semantic results.

Boosts (added after RRF, all small and logged in the debug drawer):
  - the chunk belongs to a standard named explicitly in the query
  - the chunk's clause kind matches the intent (e.g. requirements -> requirement/test_method clauses)
"""

from __future__ import annotations

RRF_K = 60

INTENT_KIND_PRIORS: dict[str, dict[str, float]] = {
    "discover": {"scope": 0.012, "front": 0.004, "list": 0.010, "faq": 0.004},
    "applicability": {"scope": 0.010, "list": 0.010, "requirement": 0.004},
    "requirements": {"requirement": 0.010, "test_method": 0.010, "table": 0.006, "marking": 0.004, "packing": 0.003, "sampling": 0.003},
    "define": {"terminology": 0.014, "faq": 0.006},
    "summarize": {"scope": 0.010, "foreword": 0.006, "requirement": 0.003},
    "compare": {"scope": 0.004, "requirement": 0.004, "table": 0.004},
}


def rrf(lists: list[list[tuple[int, float]]], k: int = RRF_K) -> dict[int, float]:
    scores: dict[int, float] = {}
    for ranked in lists:
        for rank, (doc_id, _) in enumerate(ranked, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return scores


def apply_boosts(
    scores: dict[int, float],
    chunk_meta: dict[int, dict],
    intent: str,
    explicit_ids: list[int],
) -> dict[int, dict[str, float]]:
    """Return per-chunk breakdown {rrf, kind_boost, number_boost, total}."""
    priors = INTENT_KIND_PRIORS.get(intent, {})
    out: dict[int, dict[str, float]] = {}
    for cid, base in scores.items():
        meta = chunk_meta.get(cid, {})
        kind_boost = priors.get(meta.get("kind", ""), 0.0)
        number_boost = 0.02 if meta.get("standard_id") in explicit_ids else 0.0
        out[cid] = {"rrf": base, "kind_boost": kind_boost, "number_boost": number_boost, "total": base + kind_boost + number_boost}
    return out
