"""Extractive fallback: useful answers with zero LLM calls.

Used when no LLM key is configured, the provider errors/times out/runs out of quota, or validation
fails twice. Returns the most relevant passages grouped by standard, each as a verbatim
source_fact (its first sentences), so every statement is trivially grounded.
The UI heads it with "AI summary unavailable. Here are the most relevant clauses."
"""

from __future__ import annotations

import re

from bisense.models import Point
from bisense.retrieval.search import Candidate


def first_sentences(text: str, max_chars: int = 320) -> str:
    text = " ".join(text.split())
    if text.startswith("|") or "| ---" in text or "|---" in text:
        # tables: show the caption/first rows instead of a sentence
        return text[:max_chars]
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(•])", text)
    out = ""
    for p in parts:
        if len(out) + len(p) > max_chars and out:
            break
        out = f"{out} {p}".strip()
    return out[:max_chars]


# How far below the best passage a passage may score and still be shown (reranker logit / cosine).
RERANK_MARGIN = 5.0
VECTOR_MARGIN = 0.07


def strong_context(context: list[Candidate]) -> list[Candidate]:
    """Drop passages much weaker than the best one, so an extractive answer about helmets does not also
    list a steel-bar clause that only shares the word "marked". Keeps at least the best passage."""
    if not context:
        return []
    reranked = [c.rerank_score for c in context if c.rerank_score is not None]
    if reranked:
        top = max(reranked)
        return [c for c in context if c.rerank_score is None or c.rerank_score >= top - RERANK_MARGIN] or context[:1]
    vecs = [c.vector_score for c in context if c.vector_score is not None]
    if not vecs:
        return context
    best = max(vecs)
    keep = [
        c for c in context if (c.vector_score is not None and c.vector_score >= best - VECTOR_MARGIN) or (c.lexical_rank is not None and c.lexical_rank <= 2)
    ]
    return keep or context[:1]


def extractive_points(context: list[Candidate], limit: int = 6) -> list[Point]:
    points: list[Point] = []
    for c in strong_context(context)[:limit]:
        excerpt = first_sentences(c.text)
        if not excerpt:
            continue
        label = f"{c.label()} — {c.clause_number} {c.clause_heading}".strip()
        points.append(Point(kind="source_fact", text=f"{label}: {excerpt}", citations=[c.citation_id or ""], quote=excerpt))
    return points
