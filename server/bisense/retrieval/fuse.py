"""Reciprocal Rank Fusion (RRF) plus small, explainable boosts.

RRF: score(d) = sum over ranked lists of 1 / (k + rank(d)), k = 60.
It needs no score calibration between BM25 and cosine similarity, which is why it is the standard
way to combine lexical and semantic results.

Boosts (added after RRF, all small and logged in the debug drawer):
  - the chunk belongs to a standard named explicitly in the query
  - the chunk's clause kind matches the intent (e.g. requirements -> requirement/test_method clauses)
  - the chunk's clause kind is the topic the question names ("what must be MARKED" -> marking clauses);
    this is larger than the intent prior so a generic requirement clause does not outrank it
"""

from __future__ import annotations

import re

RRF_K = 60

INTENT_KIND_PRIORS: dict[str, dict[str, float]] = {
    "discover": {"scope": 0.012, "front": 0.004, "list": 0.010, "faq": 0.004},
    "applicability": {"scope": 0.010, "list": 0.010, "requirement": 0.004},
    "requirements": {"requirement": 0.010, "test_method": 0.010, "table": 0.006, "marking": 0.004, "packing": 0.003, "sampling": 0.003},
    "define": {"terminology": 0.014, "faq": 0.006},
    "summarize": {"scope": 0.010, "foreword": 0.006, "requirement": 0.003},
    "compare": {"scope": 0.004, "requirement": 0.004, "table": 0.004},
}


TOPIC_BOOST = 0.015
TOPIC_KINDS: dict[str, re.Pattern[str]] = {
    "marking": re.compile(r"\b(mark|marked|marking|markings|label|labelled|labeled|labelling|labeling)\b", re.I),
    "packing": re.compile(r"\b(pack|packed|packing|packaging|bundles?)\b", re.I),
    "sampling": re.compile(r"\b(sample|samples|sampling)\b", re.I),
    "test_method": re.compile(r"\b(test method|tested|how to test|testing method)\b", re.I),
    "terminology": re.compile(r"\b(definition|define|meaning|what does .+ mean)\b", re.I),
}


def topic_kinds(query: str) -> set[str]:
    """Clause kinds the question is explicitly about, e.g. {"marking"} for "What must be marked on a helmet?"."""
    return {kind for kind, rx in TOPIC_KINDS.items() if rx.search(query)}


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
    topics: set[str] | None = None,
) -> dict[int, dict[str, float]]:
    """Return per-chunk breakdown {rrf, kind_boost, number_boost, total}."""
    priors = INTENT_KIND_PRIORS.get(intent, {})
    out: dict[int, dict[str, float]] = {}
    for cid, base in scores.items():
        meta = chunk_meta.get(cid, {})
        kind = meta.get("kind", "")
        kind_boost = TOPIC_BOOST if topics and kind in topics else priors.get(kind, 0.0)
        number_boost = 0.02 if meta.get("standard_id") in explicit_ids else 0.0
        out[cid] = {"rrf": base, "kind_boost": kind_boost, "number_boost": number_boost, "total": base + kind_boost + number_boost}
    return out
