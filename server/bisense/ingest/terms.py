"""Terms, references and amendments extracted from the clause tree.

- terms: from terminology clauses written as "3.1 Term - Definition" (or with an em dash).
- references: Indian Standard numbers mentioned in the References clause and elsewhere.
- amendments: clauses of kind "amendment" (label, date, excerpt), only when present in the source.
"""

from __future__ import annotations

import re

from bisense import stdnum
from bisense.ingest.types import ClauseDraft

_MONTHS = r"(January|February|March|April|May|June|July|August|September|October|November|December)"


def extract_terms(clauses: list[ClauseDraft]) -> list[tuple[int, str, str]]:
    """(clause index, term, verbatim definition) for terminology sub-clauses."""
    out = []
    for i, c in enumerate(clauses):
        if c.kind != "terminology" or c.level < 2:
            continue
        if c.heading and c.text:
            out.append((i, c.heading.strip(), c.text.strip()))
            continue
        m = re.match(r"^(?P<term>[^—–:-]{2,80}?)\s*[—–:-]\s+(?P<def>.+)$", c.text, re.S)
        if m:
            out.append((i, m.group("term").strip(), m.group("def").strip()))
    return out


def extract_references(clauses: list[ClauseDraft], own_number: str | None) -> list[tuple[int, str]]:
    """(clause index, canonical standard number) for every standard mentioned, excluding the document itself."""
    own_base = stdnum.base_number(own_number) if own_number else None
    seen: set[str] = set()
    out = []
    for i, c in enumerate(clauses):
        text = f"{c.heading}\n{c.text}"
        for sn in stdnum.find_all(text):
            if own_base and sn.base == own_base:
                continue
            key = sn.base
            if key in seen:
                continue
            seen.add(key)
            out.append((i, sn.canonical))
    return out


def extract_amendments(clauses: list[ClauseDraft]) -> list[dict]:
    out = []
    for c in clauses:
        if c.kind != "amendment" or c.level != 1:
            continue
        date = None
        m = re.search(_MONTHS + r"\s+(\d{4})", f"{c.heading} {c.text}")
        if m:
            date = f"{m.group(1)} {m.group(2)}"
        out.append({"label": c.number, "date": date, "text_excerpt": c.text[:500], "page": c.page_start})
    return out
