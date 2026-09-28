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


def _table_rows_text(text: str, max_chars: int) -> str:
    """Readable rows from a Markdown table: "IS 17790:2022 — Insulated Flask for Domestic Use — … Order, 2023".
    Header and separator rows are dropped, as is a leading serial-number cell."""
    rows = []
    for line in text.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|") if c.strip()]
        if "|" not in line or not cells or all(set(c) <= set("-: ") for c in cells) or cells[0].lower().startswith(("sl no", "s. no", "sl. no")):
            continue
        if re.fullmatch(r"\d+\.?", cells[0]):
            cells = cells[1:]
        if cells:
            rows.append(" — ".join(" ".join(c.split()) for c in cells))
    out = "; ".join(rows) or text
    return out if len(out) <= max_chars else out[:max_chars].rsplit(" ", 1)[0].rstrip(" …") + " …"


def _is_table(text: str) -> bool:
    """Rows are reformatted for reading, so they are not the source's exact wording (no quote)."""
    return "|---" in text or "| ---" in text


def first_sentences(text: str, max_chars: int = 320) -> str:
    if _is_table(text):
        return _table_rows_text(text, max_chars)
    text = " ".join(text.split())
    if text.startswith("|"):
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


def strong_context(context: list[Candidate], margin: float = RERANK_MARGIN, keep_lists: bool = False) -> list[Candidate]:
    """Drop passages much weaker than the best one, so an extractive answer about helmets does not also
    list a steel-bar clause that only shares the word "mark". Keeps at least the best passage.
    keep_lists: official product-list rows always stay (for "which standard applies" they are the evidence,
    and the cross-encoder scores table rows low)."""
    if not context:
        return []
    reranked = [c.rerank_score for c in context if c.rerank_score is not None]
    if reranked:
        top = max(reranked)
        keep = [c for c in context if c.rerank_score is None or c.rerank_score >= top - margin or (keep_lists and c.clause_kind == "list")]
        return keep or context[:1]
    vecs = [c.vector_score for c in context if c.vector_score is not None]
    if not vecs:
        return context
    best = max(vecs)
    keep = [
        c
        for c in context
        if (c.vector_score is not None and c.vector_score >= best - VECTOR_MARGIN)
        or (c.lexical_rank is not None and c.lexical_rank <= 2)
        or (keep_lists and c.clause_kind == "list")
    ]
    return keep or context[:1]


def _location(c: Candidate) -> str:
    """ "4.2 Mass", "§3.1", or just the heading for front matter (never "Front Front matter")."""
    if c.clause_number.startswith("Front"):
        return c.clause_heading if c.clause_heading and c.clause_heading != "Front matter" else ""
    return f"{c.clause_number} {c.clause_heading}".strip()


DISCOVER_MARGIN = 3.0


# Preference when showing one passage per standard: what the standard is about first; marking,
# packing, sampling and annex text (often boilerplate shared by every product manual) last.
_ABOUT_RANK = {"scope": 0, "front": 1, "foreword": 2, "terminology": 3, "requirement": 4, "test_method": 5, "table": 6}
_LAST = {"marking", "packing", "sampling", "annex"}


def _words(text: str) -> set[str]:
    from bisense.retrieval.query import STOPWORDS

    return {w[:4] for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2 and w not in STOPWORDS}


def one_per_standard(context: list[Candidate], limit: int = 6, query: str = "") -> list[Candidate]:
    """For "which standards apply" questions: official list rows first (up to 3), then one retrieved
    passage per standard, preferring its scope/title passage over a marking clause that happened to match.
    Only retrieved passages are used, so every point keeps a citation in the evidence panel."""
    rows = [c for c in context if c.clause_kind == "list"][:3]
    by_std: dict[int, list[Candidate]] = {}
    for c in context:
        if c.clause_kind != "list":
            by_std.setdefault(c.standard_id, []).append(c)
    out = [min(cands, key=lambda c: (c.clause_kind in _LAST, _ABOUT_RANK.get(c.clause_kind, 7))) for cands in by_std.values()]
    # A standard whose title shares no word with the question only matched boilerplate (e.g. the lab
    # annex every product manual repeats): leave it out.
    q = _words(query)
    if q:
        out = [c for c in out if q & _words(f"{c.title} {c.document_title or ''}")] or out[:1]
    return (rows + out)[:limit]


def extractive_points(context: list[Candidate], limit: int = 6, discover: bool = False, query: str = "") -> list[Point]:
    points: list[Point] = []
    if discover:
        chosen = one_per_standard(strong_context(context, DISCOVER_MARGIN, keep_lists=True), query=query)
    else:
        chosen = strong_context(context)[:limit]
    for c in chosen:
        excerpt = first_sentences(c.text)
        if not excerpt:
            continue
        loc = _location(c)
        label = f"{c.label()} — {loc}" if loc else c.label()
        points.append(Point(kind="source_fact", text=f"{label}: {excerpt}", citations=[c.citation_id or ""], quote=None if _is_table(c.text) else excerpt))
    return points
