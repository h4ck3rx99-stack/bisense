"""Build a clause tree from cleaned PDF lines.

Heading detection uses, in order of trust:
  1. Unnumbered top-level headings: FOREWORD, INTRODUCTION, ANNEX X, AMENDMENT NO. N (upper case,
     bold or larger than body text).
  2. Numbered clauses: "4 REQUIREMENTS", "4.2 Chemical Requirements", "4.2.1 The water shall ...",
     "A-1.2 ...", "1. Short title and commencement.- (1) ...". Numbers are kept exactly as printed.
     Guards against false positives (wrapped lines starting with a number, e.g. "250 ml sample"):
       - a top-level number must follow the previous top-level number (n+1..n+3) or be bold/upper case,
       - a sub-clause's parent number must already be open,
       - the text after the number must start with a capital letter, '(' or a quote.
  3. "Table N ..." captions start a table clause; a detected table block becomes its Markdown text.
  4. Margin notes (short lines in a left column, used by BIS guideline documents) become the heading
     of the next numbered clause.
Everything else is paragraph text of the currently open clause.
"""

from __future__ import annotations

import re
from collections import Counter

from bisense.ingest.clean import join_wrapped
from bisense.ingest.pdf_parse import RawLine
from bisense.ingest.types import ClauseDraft, kind_for_heading

TOP_UNNUMBERED_RE = re.compile(
    r"^(FOREWORD|INTRODUCTION|ANNEX\s+[A-Z]\b.*|ANNEXURE\s*[-–]?\s*[IVXLC\d]+\b.*|AMENDMENT\s+NO\.?\s*\d+.*|CONTENTS)$",
    re.IGNORECASE,
)
# A margin note printed on the same line as a numbered paragraph: "Application 2. The application ..."
MARGIN_PREFIX_RE = re.compile(r"^(?P<note>[A-Z][A-Za-z/&' ]{2,30}?)\s+(?P<rest>\d{1,2}\.\s+\S.*)$")
NUMBERED_RE = re.compile(r"^(?P<num>\d{1,2}(?:\.\d{1,3}){0,5})(?P<dot>\.)?(?:\s+|(?=\())(?P<rest>.*)$")
ANNEX_NUM_RE = re.compile(r"^(?P<num>[A-H]-\d{1,2}(?:\.\d{1,3}){0,4})\s+(?P<rest>.*)$")
TABLE_CAPTION_RE = re.compile(r"^Table\s+(?P<n>[A-Z]?-?\d+[A-Z]?)\b\s*(?P<rest>.*)$")
LIST_ITEM_RE = re.compile(r"^(?:[a-z]\)|\([a-z0-9ivx]{1,4}\)|[ivx]{1,4}\)|•|–|-\s)")
HEAD_DASH_RE = re.compile(r"^(?P<head>[A-Za-z][^.]{0,60}?)\s*\.?\s*[-–—:]\s+(?P<body>\S.*)$")


def _body_size(lines: list[RawLine]) -> float:
    c: Counter[float] = Counter()
    for ln in lines:
        if not ln.is_table:
            c[ln.size] += len(ln.text)
    return c.most_common(1)[0][0] if c else 10.0


def _is_upperish(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    return bool(letters) and sum(ch.isupper() for ch in letters) / len(letters) > 0.8


def _left_margin(lines: list[RawLine]) -> float:
    xs = sorted(round(ln.x0) for ln in lines if not ln.is_table)
    if not xs:
        return 0.0
    c = Counter(xs)
    return float(c.most_common(1)[0][0])


def build_clauses(pages: list[list[RawLine]]) -> list[ClauseDraft]:
    all_lines = [ln for page in pages for ln in page]
    body = _body_size(all_lines)
    margin = _left_margin(all_lines)

    clauses: list[ClauseDraft] = []
    open_numbers: dict[str, int] = {}  # clause number -> index, for parent lookup
    current: int | None = None
    top_index: int | None = None  # current top-level section
    last_top = 0
    pending_margin: list[str] = []
    para_lines: list[str] = []
    table_counter = 0

    def flush_para() -> None:
        if current is not None and para_lines:
            clauses[current].paragraphs.append(join_wrapped(para_lines))
        para_lines.clear()

    def add_clause(c: ClauseDraft) -> int:
        clauses.append(c)
        return len(clauses) - 1

    # Merge "1." alone on a line with the following line (common in Gazette orders).
    # But a lone number right after an unfinished sentence ("... as prescribed in clause" / "8.") is the end
    # of that sentence, not a new clause.
    merged: list[RawLine] = []
    for ln in all_lines:
        if merged and re.fullmatch(r"\d{1,2}(\.\d{1,3})*\.?", ln.text) and len(merged) >= 1 and not merged[-1].is_table:
            prev_text = merged[-1].text
            if not re.search(r"[.:;)\]]$", prev_text) and re.search(r"\b(clause|clauses|table|annex|see|in|of|and|to|sub-clause)$", prev_text, re.I):
                p = merged.pop()
                merged.append(RawLine(f"{p.text} {ln.text}", p.page, p.size, p.bold, p.x0, p.y0))
                continue
        if merged and re.fullmatch(r"\d{1,2}\.?", merged[-1].text) and not ln.is_table and ln.page == merged[-1].page:
            prev = merged.pop()
            merged.append(RawLine(prev.text.rstrip(".") + ". " + ln.text, ln.page, max(prev.size, ln.size), prev.bold or ln.bold, prev.x0, prev.y0))
        else:
            merged.append(ln)

    line_on_page: dict[int, int] = {}
    for ln in merged:
        text = ln.text.strip()
        line_on_page[ln.page] = line_on_page.get(ln.page, 0) + 1
        near_page_top = line_on_page[ln.page] == 1

        # ---- tables ---------------------------------------------------------------------------
        if ln.is_table:
            flush_para()
            if current is not None and clauses[current].kind == "table" and clauses[current].table_rows is None:
                clauses[current].table_rows = ln.table_rows
                clauses[current].paragraphs = [ln.table_md]
                clauses[current].page_end = ln.page
            else:
                table_counter += 1
                parent = current if current is not None and clauses[current].kind != "table" else top_index
                idx = add_clause(
                    ClauseDraft(
                        number=f"Table (p. {ln.page})" if table_counter else "Table",
                        heading="",
                        level=(clauses[parent].level + 1) if parent is not None else 1,
                        kind="table",
                        page_start=ln.page,
                        page_end=ln.page,
                        parent=parent,
                        paragraphs=[ln.table_md],
                        table_rows=ln.table_rows,
                    )
                )
                current = idx
            continue

        if not text:
            continue

        # ---- margin notes (left column labels) --------------------------------------------------
        if margin and ln.x0 < margin - 15:
            mp = MARGIN_PREFIX_RE.match(text)
            if mp:
                pending_margin.append(mp.group("note"))
                text = mp.group("rest")
                ln = RawLine(text, ln.page, ln.size, ln.bold, margin, ln.y0)
            elif len(text) < 40 and not NUMBERED_RE.match(text):
                pending_margin.append(text)
                continue

        # ---- unnumbered top-level headings ------------------------------------------------------
        is_annexure = text.upper().startswith("ANNEXURE")
        if (
            TOP_UNNUMBERED_RE.match(text)
            and (ln.bold or ln.size > body + 0.5 or _is_upperish(text))
            and (not is_annexure or near_page_top)  # "refer Annexure-XI ..." inside text is not a heading
        ):
            flush_para()
            number, heading = _split_unnumbered(text)
            kind = kind_for_heading(text)
            current = add_clause(ClauseDraft(number=number, heading=heading, level=1, kind=kind, page_start=ln.page, page_end=ln.page))
            top_index = current
            open_numbers = {}
            pending_margin.clear()
            if number.startswith("Annexure"):
                last_top = 0  # numbering restarts inside annexures of guideline documents
            continue

        # ---- table captions ------------------------------------------------------------------------
        m_cap = TABLE_CAPTION_RE.match(text)
        if m_cap and (ln.bold or len(text) < 120) and not re.search(r"\b(shall|given in|of Table)\b", text):
            flush_para()
            parent = current
            while parent is not None and clauses[parent].kind == "table":
                parent = clauses[parent].parent
            level = (clauses[parent].level + 1) if parent is not None else 1
            number = f"Table {m_cap.group('n')}"
            current = add_clause(
                ClauseDraft(number=number, heading=m_cap.group("rest").strip(" -–—"), level=level, kind="table", page_start=ln.page, page_end=ln.page, parent=parent)
            )
            continue

        # ---- numbered clauses -------------------------------------------------------------------
        m = NUMBERED_RE.match(text) or ANNEX_NUM_RE.match(text)
        if m and margin - 30 < ln.x0 < margin + 60 and _accept_number(m, ln, last_top, open_numbers, body):
            num = m.group("num")
            rest = m.group("rest").strip()
            flush_para()
            depth = num.count(".") + 1
            is_annex_num = bool(re.match(r"^[A-H]-", num))
            if depth == 1 and not is_annex_num:
                last_top = int(num)
                parent = None
                # A numbered top-level section inside an annex belongs to the annex only if it is lettered.
                top_candidate = True
            else:
                parent_num = num.rsplit(".", 1)[0] if "." in num else None
                parent = open_numbers.get(parent_num) if parent_num else top_index
                if parent is None:
                    parent = top_index
                top_candidate = False
            heading, body_text = _split_heading(rest, ln, body)
            if not heading and pending_margin:
                heading = " ".join(pending_margin)
            pending_margin.clear()
            level = (clauses[parent].level + 1) if parent is not None else 1
            if parent is not None:
                kind = clauses[parent].kind if clauses[parent].kind not in ("table", "other", "front") else kind_for_heading(heading)
            else:
                kind = kind_for_heading(heading or rest)
            idx = add_clause(ClauseDraft(number=num, heading=heading, level=level, kind=kind, page_start=ln.page, page_end=ln.page, parent=parent))
            if body_text:
                para_lines.append(body_text)
            open_numbers[num] = idx
            current = idx
            if top_candidate:
                top_index = idx
            continue

        # ---- plain text -----------------------------------------------------------------------------
        if current is None:
            current = add_clause(ClauseDraft(number="Front", heading="Front matter", level=1, kind="front", page_start=ln.page, page_end=ln.page))
        if pending_margin:
            # A margin note next to plain text is part of that text's context; keep it as a lead-in.
            para_lines.append("[" + " ".join(pending_margin) + "]")
            pending_margin.clear()
        if para_lines and (LIST_ITEM_RE.match(text) or re.search(r"[.:;]$", para_lines[-1])):
            flush_para()
        para_lines.append(text)
        clauses[current].page_end = max(clauses[current].page_end, ln.page)
        # propagate page_end to ancestors
        p = clauses[current].parent
        while p is not None:
            clauses[p].page_end = max(clauses[p].page_end, ln.page)
            p = clauses[p].parent

    flush_para()
    return _finalize(clauses)


def _split_unnumbered(text: str) -> tuple[str, str]:
    t = text.strip()
    m = re.match(r"^ANNEX\s+([A-Z])\b\s*(.*)$", t, re.I)
    if m:
        return f"Annex {m.group(1).upper()}", m.group(2).strip()
    m = re.match(r"^ANNEXURE\s*[-–]?\s*([IVXLC\d]+)\b\s*(\([A-Z]\))?\s*(.*)$", t, re.I)
    if m:
        suffix = f" {m.group(2).upper()}" if m.group(2) else ""
        return f"Annexure-{m.group(1).upper()}{suffix}", m.group(3).strip(" -–:")
    m = re.match(r"^AMENDMENT\s+NO\.?\s*(\d+)\s*(.*)$", t, re.I)
    if m:
        return f"Amendment No. {m.group(1)}", m.group(2).strip().title() if m.group(2).isupper() else m.group(2).strip()
    return t.title(), ""


def _accept_number(m: re.Match[str], ln: RawLine, last_top: int, open_numbers: dict[str, int], body: float) -> bool:
    num = m.group("num")
    rest = m.group("rest").strip()
    parts = num.split(".")
    # Sub-clauses whose parent is open may start in lower case ("8.5 pH - ..."), but never with a unit.
    parent_open = len(parts) > 1 and ".".join(parts[:-1]) in open_numbers
    if rest and not re.match(r"^[A-Z(\"'“‘]", rest):
        if not parent_open or re.match(r"^(mg|ml|g|kg|mm|cm|m|l|percent|per)\b", rest):
            return False
    if re.match(r"^[A-H]-", num):
        return True
    if len(parts) == 1:
        n = int(parts[0])
        if n == 0 or n > 60:
            return False
        sequential = last_top < n <= last_top + 3
        strong = ln.bold or (rest and _is_upperish(rest)) or ln.size > body + 0.5
        # A bold/upper-case heading may skip a few numbers, but never jump far ahead (that is a wrapped line).
        return bool(sequential and (strong or m.group("dot") or rest)) or bool(strong and last_top < n <= last_top + 5)
    parent = ".".join(parts[:-1])
    if parent not in open_numbers and parts[0] != str(last_top):
        return False
    return True


def _split_heading(rest: str, ln: RawLine, body: float) -> tuple[str, str]:
    """Return (heading, body_text) for the text after a clause number."""
    if not rest:
        return "", ""
    short = len(rest) <= 80 and not rest.endswith((".", ":", ";")) and not rest.startswith("(")
    sentence_like = bool(re.search(r"\b(shall|should|may|must|will|is|are|has|have)\b", rest))
    if short and not sentence_like and (ln.bold or _is_upperish(rest) or ln.size > body + 0.5):
        heading = rest.title() if _is_upperish(rest) and len(rest) > 3 else rest
        return heading, ""
    m = HEAD_DASH_RE.match(rest)
    if m and len(m.group("head")) <= 60 and not re.search(r"\b(shall|should|may|is|are)\b", m.group("head")):
        return m.group("head").strip(), m.group("body").strip()
    return "", rest


def _finalize(clauses: list[ClauseDraft]) -> list[ClauseDraft]:
    """Drop empty unnamed table stubs and fix duplicate numbers (e.g. repeated 'Table (p. 3)')."""
    seen: Counter[str] = Counter()
    for c in clauses:
        seen[c.number] += 1
        if seen[c.number] > 1:
            c.number = f"{c.number} ({seen[c.number]})"
    return clauses
