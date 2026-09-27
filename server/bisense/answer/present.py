"""Convert internal retrieval objects into API models (Citation, StandardRef, QueryInfo)."""

from __future__ import annotations

import re
import sqlite3

from bisense import stdnum
from bisense.models import Citation, QueryInfo, ScopeItemOut, Scores, StandardRef
from bisense.retrieval.query import QueryPlan
from bisense.retrieval.search import Candidate, StandardHit


def snippet(text: str, limit: int = 600) -> str:
    t = text.strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + " …"


def to_citation(c: Candidate, n: int) -> Citation:
    return Citation(
        id=c.citation_id or f"R{n}",
        n=n,
        slug=c.slug,
        standard_number=c.number,
        standard_title=c.title,
        standard_kind=c.std_kind,  # type: ignore[arg-type]
        clause_number=c.clause_number,
        clause_heading=c.clause_heading,
        clause_kind=c.clause_kind,
        clause_path=c.clause_path,
        page_start=c.page_start,
        page_end=c.page_end,
        snippet=snippet(c.text),
        scores=Scores(
            lexical_rank=c.lexical_rank,
            vector=round(c.vector_score, 4) if c.vector_score is not None else None,
            fused=round(c.fused, 5),
            rerank=round(c.rerank_score, 3) if c.rerank_score is not None else None,
            boosts={k: round(v, 4) for k, v in c.boosts.items() if k not in ("total",)},
        ),
        synthetic=c.synthetic,
        tier=c.tier,
        doc_type=c.doc_type,
        url=c.source_url,
        has_page_image=c.has_pdf,
    )


def to_standard_ref(h: StandardHit, why: str | None = None, citations: list[str] | None = None) -> StandardRef:
    return StandardRef(
        slug=h.slug,
        number=h.number,
        title=h.title,
        kind=h.kind,  # type: ignore[arg-type]
        why=why,
        citations=citations or [],
        compulsory=h.compulsory,
        compulsory_source=h.compulsory_source,
        catalogue_only=h.catalogue_only,
        synthetic=h.synthetic,
        via=h.via,
        matched_row=h.matched_row,
    )


def query_info(plan: QueryPlan) -> QueryInfo:
    return QueryInfo(
        interpreted_query=plan.english_query,
        intent=plan.intent,
        lang=plan.lang,  # type: ignore[arg-type]
        resolved_scope=[ScopeItemOut(slug=s.slug, number=s.number, title=s.title, kind=s.kind) for s in plan.scope],  # type: ignore[arg-type]
        scope_source=plan.scope_source,
        rewritten=plan.rewritten,
        notes=plan.notes,
    )


def standard_ref_for_number(conn: sqlite3.Connection, number: str) -> StandardRef | None:
    sn = stdnum.parse(number)
    if not sn:
        return None
    r = conn.execute(
        "SELECT slug, number_canonical, title, kind, compulsory_certification, compulsory_source, catalogue_only, synthetic "
        "FROM standards WHERE base_number = ? ORDER BY (kind = 'catalogue'), year DESC LIMIT 1",
        (sn.base,),
    ).fetchone()
    if not r:
        return None
    return StandardRef(
        slug=r["slug"],
        number=r["number_canonical"],
        title=r["title"],
        kind=r["kind"],
        compulsory=r["compulsory_certification"],
        compulsory_source=r["compulsory_source"],
        catalogue_only=bool(r["catalogue_only"]),
        synthetic=bool(r["synthetic"]),
    )


def searched_summary(counts: dict) -> str:
    return (
        f"Searched {counts.get('standards_full_text', 0)} full-text standards, "
        f"{counts.get('guidance', 0)} BIS guidance pages and official orders, and "
        f"{counts.get('catalogue', 0)} catalogue entries from official BIS lists."
    )


def summary_context(conn: sqlite3.Connection, standard_id: int, limit: int = 8) -> list[int]:
    """Chunk ids for a whole-document summary: scope first, then the first chunk of each key section
    (requirements, tests, marking, packing, sampling), then key tables. Map-reduce over sections,
    reduced to what fits the context budget."""
    rows = conn.execute(
        "SELECT ch.id, cl.kind, cl.number, cl.level, cl.heading FROM chunks ch JOIN clauses cl ON cl.id = ch.clause_id "
        "WHERE ch.standard_id = ? ORDER BY cl.ord, ch.ord",
        (standard_id,),
    ).fetchall()
    picked: list[int] = []
    seen_kinds: dict[str, int] = {}
    order = ["scope", "requirement", "table", "test_method", "marking", "sampling", "conformity", "packing", "faq", "other", "front", "foreword"]
    per_kind = {
        "scope": 2,
        "requirement": 2,
        "table": 1,
        "test_method": 1,
        "marking": 1,
        "sampling": 1,
        "conformity": 1,
        "packing": 1,
        "faq": 4,
        "other": 3,
        "front": 1,
        "foreword": 1,
    }
    for kind in order:
        for r in rows:
            if len(picked) >= limit:
                break
            if r["kind"] != kind or seen_kinds.get(kind, 0) >= per_kind.get(kind, 1):
                continue
            # prefer clauses with body text over bare section headings
            if kind in ("requirement", "test_method") and re.fullmatch(r"\d+", r["number"] or ""):
                continue
            picked.append(r["id"])
            seen_kinds[kind] = seen_kinds.get(kind, 0) + 1
    return picked
