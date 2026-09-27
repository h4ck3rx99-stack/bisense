"""Library and standard explorer endpoints.

    GET /api/library                               counts by category, dataset mode, sources
    GET /api/standards                             filterable, paginated list with facets
    GET /api/standards/suggest?q=                  typeahead (<= 8)
    GET /api/standards/{slug}                      explorer detail (metadata, clause tree, refs, related ...)
    GET /api/standards/{slug}/clauses/{number}     verbatim clause
    GET /api/standards/{slug}/requirements         deterministic requirement statements
    GET /api/standards/{slug}/requirements.csv     checklist export
    GET /api/standards/{slug}/summary?lang=        cited plain-language summary (cached)
    GET /api/standards/{slug}/pages/{n}.png?q=     page image with highlighted quote (PDF sources only)
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import sqlite3
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response

from bisense import stdnum
from bisense.api.common import ApiError, get_db
from bisense.config import get_settings
from bisense.db import get_meta, loads
from bisense.models import (
    AmendmentOut,
    AskContext,
    AskRequest,
    CategoryCount,
    ClauseNode,
    ClauseOut,
    CompulsoryEvidence,
    LibraryOut,
    Provenance,
    ReferenceOut,
    RelatedOut,
    RequirementOut,
    RequirementsOut,
    StandardDetail,
    StandardListOut,
    StandardSummary,
    SuggestItem,
    SummaryOut,
)
from bisense.retrieval.index import get_index

router = APIRouter(prefix="/api", tags=["standards"])

_SUMMARY_COLS = (
    "s.id, s.slug, s.kind, s.number_canonical, s.title, s.year, s.category, s.status, s.compulsory_certification, "
    "s.catalogue_only, s.synthetic, s.needs_review, s.tier, "
    "(SELECT COUNT(*) FROM clauses c WHERE c.standard_id = s.id) AS clause_count, "
    "(SELECT COUNT(*) FROM requirements r WHERE r.standard_id = s.id) AS requirement_count"
)


def _summary(r: sqlite3.Row) -> StandardSummary:
    return StandardSummary(
        slug=r["slug"], kind=r["kind"], number=r["number_canonical"], title=r["title"], year=r["year"],
        category=r["category"], status=r["status"], compulsory=r["compulsory_certification"],
        catalogue_only=bool(r["catalogue_only"]), synthetic=bool(r["synthetic"]), needs_review=bool(r["needs_review"]),
        tier=r["tier"], clause_count=r["clause_count"], requirement_count=r["requirement_count"],
    )


def _get_standard(conn: sqlite3.Connection, slug: str) -> sqlite3.Row:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,120}", slug):
        raise ApiError(404, "not_found")
    r = conn.execute(f"SELECT {_SUMMARY_COLS}, s.* FROM standards s WHERE s.slug = ?", (slug,)).fetchone()  # noqa: S608
    if not r:
        raise ApiError(404, "not_found")
    return r


# ---------------------------------------------------------------------------------------------------

@router.get("/library", response_model=LibraryOut)
def library(conn: sqlite3.Connection = Depends(get_db)) -> LibraryOut:
    index = get_index()
    cats = [
        CategoryCount(category=r["category"] or "Uncategorised", count=r["n"], kind=r["kind"])
        for r in conn.execute("SELECT category, kind, COUNT(*) AS n FROM standards GROUP BY category, kind ORDER BY kind, n DESC")
    ]
    sources = [
        {"file": r["file_name"], "tier": r["tier"], "doc_type": r["doc_type"], "url": r["source_url"], "obtained_on": r["obtained_on"], "title": r["title"]}
        for r in conn.execute("SELECT d.file_name, d.tier, d.doc_type, d.source_url, d.obtained_on, s.title FROM documents d JOIN standards s ON s.document_id = d.id ORDER BY d.tier, s.title")
    ]
    return LibraryOut(
        dataset_mode=index.dataset_mode,
        index_version=index.version,
        built_at=get_meta(conn, "built_at") or "",
        counts=index.counts,
        categories=cats,
        languages=[x for x in get_settings().language_list if x in ("en", "hi", "kn")],  # type: ignore[misc]
        sources=sources,
    )


@router.get("/standards", response_model=StandardListOut)
def list_standards(
    conn: sqlite3.Connection = Depends(get_db),
    q: str | None = Query(None, max_length=200),
    kind: str | None = Query(None, pattern=r"^(standard|guidance|order|catalogue)(,(standard|guidance|order|catalogue))*$"),
    category: str | None = Query(None, max_length=200),
    compulsory: str | None = Query(None, pattern=r"^(yes|denotified|unknown|no)$"),
    tier: str | None = Query(None, pattern=r"^[ABC]$"),
    year_from: int | None = Query(None, ge=1900, le=2100),
    year_to: int | None = Query(None, ge=1900, le=2100),
    sort: str = Query("relevance", pattern=r"^(relevance|number|title|year)$"),
    page: int = Query(1, ge=1, le=1000),
    page_size: int = Query(25, ge=1, le=100),
) -> StandardListOut:
    where: list[str] = []
    params: list = []
    if kind:
        kinds = kind.split(",")
        where.append(f"s.kind IN ({','.join('?' for _ in kinds)})")
        params += kinds
    if category:
        where.append("s.category = ?")
        params.append(category)
    if compulsory:
        where.append("s.compulsory_certification = ?")
        params.append(compulsory)
    if tier:
        where.append("s.tier = ?")
        params.append(tier)
    if year_from:
        where.append("s.year >= ?")
        params.append(year_from)
    if year_to:
        where.append("s.year <= ?")
        params.append(year_to)
    if q and q.strip():
        sn = stdnum.parse(q)
        if sn:
            where.append("(s.base_number = ? OR s.number_canonical LIKE ?)")
            params += [sn.base, f"%{sn.number}%"]
        else:
            like_terms = [t for t in re.findall(r"\w+", q.lower()) if len(t) > 1][:6]
            for t in like_terms:
                where.append("(LOWER(s.title) LIKE ? OR LOWER(COALESCE(s.number_canonical, '')) LIKE ? OR LOWER(s.products_json) LIKE ? OR LOWER(COALESCE(s.category,'')) LIKE ?)")
                params += [f"%{t}%"] * 4
    clause = f"WHERE {' AND '.join(where)}" if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM standards s {clause}", params).fetchone()[0]  # noqa: S608
    order = {
        "relevance": "(s.kind = 'standard') DESC, (s.kind IN ('guidance','order')) DESC, s.number_canonical IS NULL, s.title",
        "number": "s.number_canonical IS NULL, s.base_number",
        "title": "s.title",
        "year": "s.year DESC",
    }[sort]
    rows = conn.execute(
        f"SELECT {_SUMMARY_COLS} FROM standards s {clause} ORDER BY {order} LIMIT ? OFFSET ?",  # noqa: S608
        params + [page_size, (page - 1) * page_size],
    ).fetchall()
    facets: dict[str, list[CategoryCount]] = {"category": [], "kind": []}
    for r in conn.execute(f"SELECT COALESCE(s.category, 'Uncategorised') AS c, s.kind AS k, COUNT(*) AS n FROM standards s {clause} GROUP BY c, k ORDER BY n DESC LIMIT 60", params):  # noqa: S608
        facets["category"].append(CategoryCount(category=r["c"], count=r["n"], kind=r["k"]))
    for r in conn.execute(f"SELECT s.kind AS k, COUNT(*) AS n FROM standards s {clause} GROUP BY k", params):  # noqa: S608
        facets["kind"].append(CategoryCount(category=r["k"], count=r["n"], kind=r["k"]))
    return StandardListOut(items=[_summary(r) for r in rows], total=total, page=page, page_size=page_size, facets=facets)


@router.get("/standards/suggest", response_model=list[SuggestItem])
def suggest(q: str = Query(..., min_length=1, max_length=100), conn: sqlite3.Connection = Depends(get_db)) -> list[SuggestItem]:
    sn = stdnum.parse(q)
    if sn:
        rows = conn.execute(
            "SELECT slug, number_canonical, title, kind FROM standards WHERE number_canonical LIKE ? ORDER BY (kind = 'catalogue'), length(number_canonical) LIMIT 8",
            (f"%{sn.number}%",),
        ).fetchall()
    else:
        t = q.strip().lower()
        rows = conn.execute(
            "SELECT slug, number_canonical, title, kind FROM standards WHERE LOWER(title) LIKE ? OR LOWER(COALESCE(number_canonical,'')) LIKE ? "
            "ORDER BY (kind = 'standard') DESC, (kind = 'catalogue'), (LOWER(title) LIKE ?) DESC, length(title) LIMIT 8",
            (f"%{t}%", f"%{t}%", f"{t}%"),
        ).fetchall()
    return [SuggestItem(slug=r["slug"], number=r["number_canonical"], title=r["title"], kind=r["kind"]) for r in rows]


def _clause_tree(conn: sqlite3.Connection, standard_id: int) -> list[ClauseNode]:
    rows = conn.execute("SELECT id, number, heading, kind, level, page_start, page_end, parent_id FROM clauses WHERE standard_id = ? ORDER BY ord", (standard_id,)).fetchall()
    nodes = {r["id"]: ClauseNode(id=r["id"], number=r["number"], heading=r["heading"], kind=r["kind"], level=r["level"], page_start=r["page_start"], page_end=r["page_end"]) for r in rows}
    roots: list[ClauseNode] = []
    for r in rows:
        node = nodes[r["id"]]
        if r["parent_id"] and r["parent_id"] in nodes:
            nodes[r["parent_id"]].children.append(node)
        else:
            roots.append(node)
    return roots


def _related(conn: sqlite3.Connection, standard_id: int, limit: int = 5) -> list[RelatedOut]:
    """'Similar scope (computed)': cosine similarity of scope/front chunk centroids. Labelled as computed in the UI."""
    index = get_index()
    rows = conn.execute(
        "SELECT ch.id, ch.standard_id FROM chunks ch JOIN clauses cl ON cl.id = ch.clause_id JOIN standards s ON s.id = ch.standard_id "
        "WHERE s.kind = 'standard' AND cl.kind IN ('scope', 'front') ORDER BY ch.standard_id, cl.ord LIMIT 2000"
    ).fetchall()
    by_std: dict[int, list[int]] = {}
    for r in rows:
        if r["id"] in index.row_of_chunk:
            by_std.setdefault(r["standard_id"], []).append(index.row_of_chunk[r["id"]])
    if standard_id not in by_std:
        return []
    cents = {sid: index.matrix[idx[:3]].mean(axis=0) for sid, idx in by_std.items()}
    me = cents[standard_id]
    me = me / (np.linalg.norm(me) or 1)
    sims = []
    for sid, v in cents.items():
        if sid == standard_id:
            continue
        sims.append((float(me @ (v / (np.linalg.norm(v) or 1))), sid))
    sims.sort(reverse=True)
    out = []
    for sim, sid in sims[:limit]:
        r = conn.execute("SELECT slug, number_canonical, title, kind FROM standards WHERE id = ?", (sid,)).fetchone()
        out.append(RelatedOut(slug=r["slug"], number=r["number_canonical"], title=r["title"], kind=r["kind"], similarity=round(sim, 3)))
    return out


@router.get("/standards/{slug}", response_model=StandardDetail)
def standard_detail(slug: str, conn: sqlite3.Connection = Depends(get_db)) -> StandardDetail:
    s = _get_standard(conn, slug)
    sid = s["id"]
    doc = conn.execute("SELECT * FROM documents WHERE id = ?", (s["document_id"],)).fetchone() if s["document_id"] else None
    scope = conn.execute("SELECT number, text FROM clauses WHERE standard_id = ? AND kind = 'scope' AND text != '' ORDER BY ord LIMIT 3", (sid,)).fetchall()
    scope_text = "\n\n".join(r["text"] for r in scope) or None
    if not scope_text:
        first = conn.execute("SELECT number, text FROM clauses WHERE standard_id = ? AND text != '' AND kind != 'table' ORDER BY ord LIMIT 1", (sid,)).fetchone()
        scope = [first] if first else []
        scope_text = first["text"][:800] if first else None
    refs = [
        ReferenceOut(number=r["to_number"], slug=r["slug"], title=r["title"], clause_number=r["number"])
        for r in conn.execute(
            "SELECT sr.to_number, t.slug, t.title, c.number FROM standard_refs sr LEFT JOIN standards t ON t.id = sr.to_standard_id "
            "LEFT JOIN clauses c ON c.id = sr.clause_id WHERE sr.from_standard_id = ?",
            (sid,),
        )
    ]
    referenced_by = [
        ReferenceOut(number=r["number_canonical"] or r["title"], slug=r["slug"], title=r["title"], clause_number=r["number"])
        for r in conn.execute(
            "SELECT f.number_canonical, f.slug, f.title, c.number FROM standard_refs sr JOIN standards f ON f.id = sr.from_standard_id "
            "LEFT JOIN clauses c ON c.id = sr.clause_id WHERE sr.to_standard_id = ?",
            (sid,),
        )
    ]
    ev = loads(s["compulsory_evidence_json"], {})
    mentions: list[dict[str, str | None]] = []
    if s["base_number"]:
        rows = conn.execute(
            "SELECT pm.product_term, pm.status, pm.note, pm.standard_number, st.slug, c.number FROM product_mappings pm "
            "JOIN standards st ON st.id = pm.source_standard_id LEFT JOIN clauses c ON c.id = pm.clause_id",
        ).fetchall()
        for r in rows:
            sn = stdnum.parse(r["standard_number"])
            if sn and sn.base == s["base_number"]:
                mentions.append({"product": r["product_term"], "status": r["status"], "order": r["note"], "slug": r["slug"], "clause_number": r["number"]})
    terms = [
        {"term": r["term"], "definition": r["definition_verbatim"], "clause_number": r["number"], "page": r["page"]}
        for r in conn.execute("SELECT t.term, t.definition_verbatim, t.page, c.number FROM terms t JOIN clauses c ON c.id = t.clause_id WHERE t.standard_id = ?", (sid,))
    ]
    counts = {
        "clauses": s["clause_count"],
        "requirements": s["requirement_count"],
        "tables": conn.execute("SELECT COUNT(*) FROM clauses WHERE standard_id = ? AND kind IN ('table','list')", (sid,)).fetchone()[0],
        "terms": len(terms),
        "chunks": conn.execute("SELECT COUNT(*) FROM chunks WHERE standard_id = ?", (sid,)).fetchone()[0],
    }
    return StandardDetail(
        summary=_summary(s),
        revision_label=s["revision_label"],
        status_verified_on=s["status_verified_on"],
        committee=s["committee"],
        ics=s["ics"],
        industries=loads(s["industries_json"], []),
        products=loads(s["products_json"], []),
        provenance=Provenance(
            tier=s["tier"], doc_type=doc["doc_type"] if doc else None, file_name=doc["file_name"] if doc else None,
            source_url=s["source_url"] or (doc["source_url"] if doc else None), obtained_on=doc["obtained_on"] if doc else None,
            pages=doc["pages"] if doc else None, language=doc["language"] if doc else None,
            warnings=loads(doc["warnings_json"], []) if doc else [],
        ),
        compulsory=CompulsoryEvidence(status=s["compulsory_certification"], source=s["compulsory_source"], slug=ev.get("slug"), clause_number=ev.get("clause_number")),
        scope_text=scope_text,
        scope_clause=scope[0]["number"] if scope else None,
        clauses=_clause_tree(conn, sid),
        amendments=[AmendmentOut(label=r["label"], date=r["date"], text_excerpt=r["text_excerpt"], page=r["page"]) for r in conn.execute("SELECT * FROM amendments WHERE standard_id = ?", (sid,))],
        references=refs,
        referenced_by=referenced_by,
        related=_related(conn, sid) if s["kind"] == "standard" else [],
        terms=terms,
        counts=counts,
        product_mentions=mentions[:20],
    )


@router.get("/standards/{slug}/clauses", response_model=list[ClauseOut])
def all_clauses(slug: str, conn: sqlite3.Connection = Depends(get_db)) -> list[ClauseOut]:
    """Every clause of a document, in order, with verbatim text (the explorer's clause viewer)."""
    s = _get_standard(conn, slug)
    return [
        ClauseOut(
            id=r["id"], number=r["number"], heading=r["heading"], kind=r["kind"], path=r["path"], level=r["level"],
            page_start=r["page_start"], page_end=r["page_end"], text=r["text"], is_table=r["kind"] in ("table", "list"), children=[],
        )
        for r in conn.execute("SELECT * FROM clauses WHERE standard_id = ? ORDER BY ord", (s["id"],))
    ]


@router.get("/standards/{slug}/clauses/{number:path}", response_model=ClauseOut)
def clause(slug: str, number: str, conn: sqlite3.Connection = Depends(get_db)) -> ClauseOut:
    s = _get_standard(conn, slug)
    if len(number) > 60:
        raise ApiError(404, "not_found")
    r = conn.execute("SELECT * FROM clauses WHERE standard_id = ? AND number = ?", (s["id"], number)).fetchone()
    if not r:
        raise ApiError(404, "clause_not_found")
    children = [
        ClauseNode(id=c["id"], number=c["number"], heading=c["heading"], kind=c["kind"], level=c["level"], page_start=c["page_start"], page_end=c["page_end"])
        for c in conn.execute("SELECT * FROM clauses WHERE parent_id = ? ORDER BY ord", (r["id"],))
    ]
    return ClauseOut(
        id=r["id"], number=r["number"], heading=r["heading"], kind=r["kind"], path=r["path"], level=r["level"],
        page_start=r["page_start"], page_end=r["page_end"], text=r["text"], is_table=r["kind"] in ("table", "list"), children=children,
    )


def _requirements(conn: sqlite3.Connection, s: sqlite3.Row, modality: str | None, kind: str | None, q: str | None) -> list[RequirementOut]:
    sql = (
        "SELECT r.id, r.modality, r.text_verbatim, r.page, r.topic, c.number, c.heading, c.kind FROM requirements r "
        "JOIN clauses c ON c.id = r.clause_id WHERE r.standard_id = ?"
    )
    params: list = [s["id"]]
    if modality:
        mods = modality.split(",")
        sql += f" AND r.modality IN ({','.join('?' for _ in mods)})"
        params += mods
    if kind:
        kinds = kind.split(",")
        sql += f" AND r.topic IN ({','.join('?' for _ in kinds)})"
        params += kinds
    if q:
        sql += " AND LOWER(r.text_verbatim) LIKE ?"
        params.append(f"%{q.lower()}%")
    sql += " ORDER BY c.ord, r.id"
    return [
        RequirementOut(id=r["id"], clause_number=r["number"], clause_heading=r["heading"], clause_kind=r["kind"], modality=r["modality"], text=r["text_verbatim"], page=r["page"], topic=r["topic"])
        for r in conn.execute(sql, params)
    ]


@router.get("/standards/{slug}/requirements", response_model=RequirementsOut)
def requirements(
    slug: str,
    conn: sqlite3.Connection = Depends(get_db),
    modality: str | None = Query(None, pattern=r"^(shall|shall_not|should|should_not|may|must)(,(shall|shall_not|should|should_not|may|must))*$"),
    kind: str | None = Query(None, max_length=200, pattern=r"^[a-z_,]+$"),
    q: str | None = Query(None, max_length=200),
) -> RequirementsOut:
    s = _get_standard(conn, slug)
    items = _requirements(conn, s, modality, kind, q)
    counts: dict[str, int] = {}
    for r in conn.execute("SELECT modality, COUNT(*) n FROM requirements WHERE standard_id = ? GROUP BY modality", (s["id"],)):
        counts[r["modality"]] = r["n"]
    return RequirementsOut(slug=slug, number=s["number_canonical"], title=s["title"], synthetic=bool(s["synthetic"]), items=items, counts=counts)


@router.get("/standards/{slug}/requirements/plain")
def requirements_plain(slug: str, request: Request, lang: str = Query("en", pattern=r"^(en|hi|kn)$"), conn: sqlite3.Connection = Depends(get_db)) -> dict[str, dict[str, str]]:
    """AI interpretations of requirement statements (labelled as such in the UI)."""
    from bisense.answer.plain import PlainUnavailable, plain_language
    from bisense.api.ask import check_rate

    s = _get_standard(conn, slug)
    check_rate(request)
    try:
        return {"items": plain_language(conn, s["id"], slug, lang)}
    except PlainUnavailable as exc:
        raise ApiError(503, "llm_unavailable") from exc


@router.get("/standards/{slug}/requirements.csv")
def requirements_csv(slug: str, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    s = _get_standard(conn, slug)
    items = _requirements(conn, s, None, None, None)
    buf = io.StringIO()
    w = csv.writer(buf)
    label = s["number_canonical"] or s["title"]
    w.writerow([f"Requirement statements extracted from {label}, with clause references. This checklist is a study aid, not a certification or compliance determination."])
    if s["synthetic"]:
        w.writerow(["Synthetic demo data, not an Indian Standard."])
    w.writerow(["standard", "clause", "page", "modality", "requirement_verbatim", "interpretation", "status", "notes"])
    for it in items:
        w.writerow([label, it.clause_number, it.page, it.modality.upper().replace("_", " "), it.text, "", "", ""])
    filename = re.sub(r"[^a-z0-9-]+", "-", slug) + "-requirements.csv"
    return Response(
        content="﻿" + buf.getvalue(),  # BOM so Excel opens UTF-8 correctly
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/standards/{slug}/summary", response_model=SummaryOut)
def summary(slug: str, request: Request, lang: str = Query("en", pattern=r"^(en|hi|kn)$"), conn: sqlite3.Connection = Depends(get_db)) -> SummaryOut:
    from bisense.answer.ask import run_ask
    from bisense.api.ask import check_rate

    s = _get_standard(conn, slug)
    if s["catalogue_only"]:
        raise ApiError(409, "catalogue_only")
    check_rate(request)
    label = s["number_canonical"] or s["title"]
    req = AskRequest(query=f"Explain {label} in simple language.", lang=lang, context=AskContext(open_slug=slug, focus_slugs=[slug], recent_questions=["summary"]))  # type: ignore[arg-type]
    answer = None
    citations = []
    for event, data in run_ask(req):
        if event == "evidence":
            citations = data.citations  # type: ignore[union-attr]
        elif event == "answer":
            answer = data
    if answer is None:
        raise ApiError(500, "internal")
    return SummaryOut(slug=slug, answer=answer, citations=citations)  # type: ignore[arg-type]


def _source_path(conn: sqlite3.Connection, s: sqlite3.Row) -> Path | None:
    if not s["document_id"]:
        return None
    d = conn.execute("SELECT file_name, tier FROM documents WHERE id = ?", (s["document_id"],)).fetchone()
    if not d or not d["file_name"].lower().endswith(".pdf"):
        return None
    data = get_settings().data_dir
    folder = {"A": data / "raw", "B": data / "public", "C": data / "demo" / "pdf"}.get(d["tier"])
    p = folder / d["file_name"] if folder else None
    return p if p and p.exists() else None


@router.get("/standards/{slug}/pages/{n}.png")
def page_image(slug: str, n: int, q: str | None = Query(None, max_length=200), conn: sqlite3.Connection = Depends(get_db)) -> Response:
    from bisense.ingest.pdf_parse import IngestError, render_page_png

    s = _get_standard(conn, slug)
    path = _source_path(conn, s)
    if path is None:
        raise ApiError(404, "page_unavailable")
    cache_dir = get_settings().data_dir / "cache" / "pages"
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([str(path), path.stat().st_mtime, n, q or ""]).encode()).hexdigest()[:20]
    cached = cache_dir / f"{key}.png"
    if cached.exists():
        png = cached.read_bytes()
    else:
        try:
            png = render_page_png(path, n, highlight=q)
        except IngestError as exc:
            raise ApiError(404, "page_unavailable") from exc
        cached.write_bytes(png)
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
