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


def extractive_points(context: list[Candidate], limit: int = 6) -> list[Point]:
    points: list[Point] = []
    for c in context[:limit]:
        excerpt = first_sentences(c.text)
        if not excerpt:
            continue
        label = f"{c.label()} — {c.clause_number} {c.clause_heading}".strip()
        points.append(Point(kind="source_fact", text=f"{label}: {excerpt}", citations=[c.citation_id or ""], quote=excerpt))
    return points
