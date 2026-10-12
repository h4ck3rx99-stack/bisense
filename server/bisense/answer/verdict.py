"""The verdict card: one line a first-time user can act on.

    "Yes — BIS certification is compulsory for <product>"     (official list row, Scheme-I or CRS)
    "Not compulsory, but a standard exists"                   (de-notified, or not on the official lists)
    "We couldn't find this in official BIS sources"           (refusal)

Built only from official evidence that was retrieved for the question: the matching row of the BIS
"Products under Compulsory Certification" lists, the standard's own entry (which records that list evidence),
or the first cited official page for service questions. Model text is never used, so the verdict is the
same with or without an AI model, and it can be checked against the source line it shows.
"""

from __future__ import annotations

import json
import re
import sqlite3

from bisense import stdnum
from bisense.listrow import ListRow, order_short, parse_row, scheme_of
from bisense.models import Answer, Citation, StandardRef, Verdict, VerdictSource
from bisense.retrieval.search import APPLIES_RE, LEGAL_QUESTION_RE, SearchResult, product_match, product_terms

REFUSED = ("insufficient_evidence", "out_of_scope")


def _source(c: Citation) -> VerdictSource:
    return VerdictSource(label=c.source_label, url=c.url, citation_id=c.id, page=c.page_start if c.has_page_image else None, source_type=c.source_type)


def _std_row(conn: sqlite3.Connection, number: str) -> sqlite3.Row | None:
    sn = stdnum.parse(number)
    if not sn:
        return None
    return conn.execute(
        "SELECT * FROM standards WHERE base_number = ? AND kind IN ('standard','catalogue') AND synthetic = 0 ORDER BY (kind = 'catalogue'), year DESC LIMIT 1",
        (sn.base,),
    ).fetchone()


def _list_scheme(conn: sqlite3.Connection, s: sqlite3.Row) -> str | None:
    """ISI or CRS, from the official list that records the standard's compulsory status."""
    try:
        ev = json.loads(s["compulsory_evidence_json"] or "{}")
    except ValueError:
        return None
    r = conn.execute("SELECT title FROM standards WHERE slug = ?", (ev.get("slug"),)).fetchone() if ev.get("slug") else None
    return scheme_of(r["title"]) if r else None


def _short_product(text: str, limit: int = 70) -> str:
    t = re.split(r"\s+[-–—:]\s+|\.\s|\(Part", text)[0].strip(" .,")
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def is_product_question(plan) -> bool:
    return plan.intent in ("discover", "applicability") or bool(APPLIES_RE.search(plan.english_query)) or bool(LEGAL_QUESTION_RE.search(plan.english_query))


def build_verdict(conn: sqlite3.Connection, plan, answer: Answer, res: SearchResult, citations: list[Citation]) -> Verdict | None:
    if answer.answer_type in REFUSED:
        return Verdict(kind="not_found")
    if answer.answer_type == "clarification":
        return None
    possible = answer.notice == "notice.possible_match"
    by_id = {c.id: c for c in citations}
    cited = [by_id[i] for p in answer.points for i in p.citations if i in by_id]

    if is_product_question(plan) or any(s.via == "official_list" for s in answer.standards[:1]):
        # The matching official row: first list row in the evidence (search puts it first for these questions).
        row: ListRow | None = None
        row_cite: Citation | None = None
        pq = product_terms(plan)
        explicit = {s.base for s in map(stdnum.parse, plan.explicit_numbers) if s}
        for c in citations:
            if c.clause_kind == "list":
                r = parse_row(c.snippet)
                # only a row for the product asked about (a neighbouring row in the evidence is not the answer)
                nums = stdnum.find_all(r.numbers) if r else []
                if r and (product_match(f"{r.product} {r.title}", pq) > 0 or (explicit and any(n.base in explicit for n in nums))):
                    row, row_cite = r, c
                    break
        std = None
        if row:
            std = _std_row(conn, stdnum.find_all(row.numbers)[0].canonical) if stdnum.find_all(row.numbers) else None
        if std is None:
            # No list row: the first standard in the answer (manual or catalogue entry).
            for s in answer.standards:
                if s.kind in ("standard", "catalogue") and s.number:
                    std = _std_row(conn, s.number)
                    if std is not None:
                        break
        if std is not None:
            status = std["compulsory_certification"]
            denotified = (row.denotified if row else False) or status == "denotified"
            compulsory = not denotified and (status == "yes" or (row is not None and not row.denotified))
            scheme = row.scheme if row else _list_scheme(conn, std)
            order = row.order if row else (std["compulsory_source"] or "").split("—", 1)[-1].strip()
            src_cite = row_cite or next((c for c in cited if c.slug == std["slug"]), None) or next((c for c in citations if c.slug == std["slug"]), None)
            product = _short_product(row.product) if row else _short_product(std["title"])
            return Verdict(
                kind="compulsory" if compulsory else "not_compulsory" if denotified else "standard_only",
                possible=possible,
                product=product,
                standard_slug=std["slug"],
                standard_number=std["number_canonical"],
                standard_title=std["title"],
                scheme=scheme if compulsory else None,  # type: ignore[arg-type]
                order_short=order_short(order) if compulsory else None,
                denotified=denotified,
                source=_source(src_cite) if src_cite else None,
            )

    first = cited[0] if cited else (citations[0] if citations else None)
    return Verdict(kind="info", possible=possible, source=_source(first) if first else None)


def lead_with_verdict(answer: Answer, verdict: Verdict | None, conn: sqlite3.Connection) -> None:
    """Make the verdict's standard the first standard listed (the answer page shows one standard chip)."""
    if not verdict or not verdict.standard_slug:
        return
    rest = [s for s in answer.standards if s.slug != verdict.standard_slug]
    first = next((s for s in answer.standards if s.slug == verdict.standard_slug), None)
    if first is None:
        r = conn.execute("SELECT * FROM standards WHERE slug = ?", (verdict.standard_slug,)).fetchone()
        if r is None:
            return
        first = StandardRef(
            slug=r["slug"],
            number=r["number_canonical"],
            title=r["title"],
            kind=r["kind"],
            compulsory=r["compulsory_certification"],
            compulsory_source=r["compulsory_source"],
            catalogue_only=bool(r["catalogue_only"]),
            via="official_list" if verdict.kind in ("compulsory", "not_compulsory") else "full_text",
        )
    answer.standards = [first, *rest]


def suggestions(conn: sqlite3.Connection, plan, limit: int = 2) -> list[str]:
    """Two rephrasings for a question nothing was found for: the official product wording from the glossary,
    else official product names that share a key word with the question."""
    from bisense.i18n.glossary import product_phrases
    from bisense.retrieval.search import _GENERIC_STEMS, _stems

    out: list[str] = []
    for _, phrase in product_phrases(plan.english_query):
        out += [f"Which Indian Standard applies to {phrase}?", f"Is BIS certification compulsory for {phrase}?"]
    if not out:
        # words that name a product, not a measurement ("boiling POINT" must not suggest a "3 point sling")
        words = {w for t in plan.content_terms for w in _stems(t) if len(w) >= 5} - _GENERIC_STEMS - _NOT_PRODUCT_WORDS
        seen: set[str] = set()
        for r in conn.execute("SELECT DISTINCT product_term FROM product_mappings WHERE status = 'compulsory'"):
            name = _short_product(r["product_term"], 60)
            if words & _stems(name) and name.lower() not in seen:
                seen.add(name.lower())
                out.append(f"Is BIS certification compulsory for {name}?")
            if len(out) >= limit:
                break
    # Ways forward that always work: the product picker, and the official list itself.
    for fallback in ("Is BIS certification compulsory for my product?", "Which products need compulsory BIS certification?"):
        if len(out) < limit:
            out.append(fallback)
    return out[:limit]


_NOT_PRODUCT_WORDS = set(
    "point level value speed limit limits range rate price prices penalty penalties fine fines number numbers "
    "kelvin celsius degree degrees boiling melting weight height length width maximum minimum temperature".split()
)
