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


SOURCE_ORG_LABEL = {
    "official_document": "Bureau of Indian Standards",
    "official_website": "Official BIS website",
    "government_notification": "Government of India notification",
    "sample": "Sample data, not official",
}


def location_label(number: str, heading: str, kind: str, text_scope: str) -> str:
    """Human wording for where a passage sits: "Clause 5.2", "Section 2.1", "Table", "Annex B", or a heading."""
    if number in ("Front", "") or number.startswith("Front"):
        return ""
    if number.startswith("Table"):
        return "Table"
    if number.startswith("Annex"):
        return number
    if number.startswith("§"):
        if text_scope == "product_manual" or not heading:
            return f"Section {number[1:]}"
        return heading
    if re.fullmatch(r"Q\d+", number):
        return f"FAQ: {heading}" if heading else f"FAQ {number[1:]}"
    return f"Clause {number}"


def source_label(c: Candidate) -> str:
    """ "Bureau of Indian Standards · IS 14543:2016 · Clause 5.2 · Page 4" (no scores, no internal ids)."""
    org = SOURCE_ORG_LABEL.get(c.source_type or "", "Bureau of Indian Standards")
    if c.text_scope == "product_manual":
        doc = f"Product Manual for {c.number}" if c.number else (c.document_title or c.title)
    elif c.number and c.text_scope in ("full_text", "sample"):
        doc = c.number
    else:
        doc = c.document_title or c.title
    parts = [org, doc, location_label(c.clause_number, c.clause_heading, c.clause_kind, c.text_scope)]
    if c.has_pdf:
        parts.append(f"Page {c.page_start}" if c.page_end == c.page_start else f"Pages {c.page_start}–{c.page_end}")
    return " · ".join(p for p in parts if p)


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
        text_scope=c.text_scope,
        document_title=c.document_title,
        source_org=c.source_org,
        source_type=c.source_type,
        source_label=source_label(c),
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
        query_lang=plan.query_lang if plan.query_lang in ("en", "hi", "kn") else "en",  # type: ignore[arg-type]
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


def coverage_line(counts: dict) -> str:
    """The honest one-liner: how many standards BISense knows about and for how many it has text."""
    line = (
        f"BISense currently covers {counts.get('standards_total', 0)} standards "
        f"(full text available for {counts.get('standards_with_full_text', 0)}; "
        f"official BIS product manual for {counts.get('standards_with_manual', 0)}; "
        f"the rest by number and title from official BIS lists)"
    )
    if counts.get("sample_documents"):
        line += f", plus {counts['sample_documents']} sample documents (not official)"
    return line + "."


def searched_summary(counts: dict) -> str:
    return (
        f"Searched {counts.get('guidance', 0)} official BIS pages, documents and notifications, "
        f"{counts.get('standards_with_manual', 0)} BIS product manuals, {counts.get('standards_with_full_text', 0)} full-text standards "
        f"and {counts.get('catalogue', 0)} standards listed in official BIS lists."
    )


def scope_coverage(conn: sqlite3.Connection, slugs: list[str]) -> list[dict]:
    """For standards named in the question: what BISense holds for each (so the UI can say
    "Full text of this standard isn't available in BISense yet")."""
    out = []
    for slug in slugs:
        r = conn.execute("SELECT slug, number_canonical, title, text_scope FROM standards WHERE slug = ?", (slug,)).fetchone()
        if r and r["text_scope"] in ("metadata_only", "product_manual"):
            out.append({"slug": r["slug"], "number": r["number_canonical"], "title": r["title"], "text_scope": r["text_scope"]})
    return out


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
