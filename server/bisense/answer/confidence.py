"""Evidence strength: Strong / Moderate / Limited -- never a fake percentage.

Computed from three observable things, and explained to the user in plain words:
  1. how many distinct passages the answer cites,
  2. how relevant the best passage is (cross-encoder score vs calibrated thresholds; when the
     reranker is off, the fused retrieval score is used),
  3. what fraction of the drafted statements survived validation.
"""

from __future__ import annotations

from bisense.config import get_settings


def evidence_strength(cited_count: int, top_score: float | None, survived_fraction: float, reranked: bool) -> tuple[str, str]:
    s = get_settings()
    if cited_count == 0:
        return "none", "No passage from the indexed sources supports an answer."
    if reranked and top_score is not None:
        relevance = "high" if top_score >= s.strength_strong_min else "medium" if top_score >= s.strength_moderate_min else "low"
    else:
        relevance = "medium"
    if cited_count >= 2 and relevance == "high" and survived_fraction >= 0.8:
        level = "strong"
    elif relevance != "low" and survived_fraction >= 0.5:
        level = "moderate"
    else:
        level = "limited"
    basis = (
        f"Cites {cited_count} passage{'s' if cited_count != 1 else ''}; "
        f"best-match relevance is {relevance}; "
        f"{round(survived_fraction * 100)}% of drafted statements passed citation checks."
    )
    return level, basis
