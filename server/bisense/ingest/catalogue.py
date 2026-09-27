"""Parse BIS "Products under Compulsory Certification" pages (Tier B official lists).

These pages are the only *official* source in the library for "is certification compulsory for my
product?". Each table row links a product to an Indian Standard and to the Quality Control Order
(or registration order) that made certification compulsory, or marks it as de-notified.

Output:
  - one clause per product category ("§n <category>"), holding a Markdown table of its rows, so
    retrieval can cite the exact list section;
  - `catalogue_rows`: structured rows used to create product -> standard mappings and
    catalogue-only standard entries (number + title known, full text not indexed).

HTML tables here use rowspan (the order cell spans many rows) and colspan (category header rows), so
we expand the table into a full grid first.
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import Tag

from bisense import stdnum
from bisense.ingest.clean import normalize_text
from bisense.ingest.html_parse import _last_updated, content_root, load_soup
from bisense.ingest.pdf_parse import IngestError
from bisense.ingest.types import ClauseDraft, ParsedDoc

PARSER_VERSION = "catalogue-1.1"


def _cell_text(td: Tag) -> str:
    for br in td.find_all("br"):
        br.replace_with(" ")
    return normalize_text(td.get_text(" "))


def expand_table(table: Tag) -> list[list[str]]:
    """Expand rowspan/colspan into a rectangular grid of strings."""
    grid: list[list[str]] = []
    carry: dict[int, tuple[int, str]] = {}  # column -> (rows remaining, text)
    for tr in table.find_all("tr"):
        row: list[str] = []
        cells = tr.find_all(["td", "th"], recursive=False)
        col = 0
        ci = 0
        while ci < len(cells) or col in carry:
            if col in carry:
                remaining, text = carry[col]
                row.append(text)
                if remaining <= 1:
                    del carry[col]
                else:
                    carry[col] = (remaining - 1, text)
                col += 1
                continue
            td = cells[ci]
            ci += 1
            text = _cell_text(td)
            colspan = int(td.get("colspan", 1) or 1)
            rowspan = int(td.get("rowspan", 1) or 1)
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    carry[col] = (rowspan - 1, text)
                col += 1
        if any(c for c in row):
            grid.append(row)
    return grid


def _find_col(header: list[str], *names: str) -> int | None:
    for i, h in enumerate(header):
        hl = h.lower()
        if any(n in hl for n in names):
            return i
    return None


def parse_catalogue_document(path: Path) -> ParsedDoc:
    soup = load_soup(path)
    updated = _last_updated(soup)
    root = content_root(soup)
    h1 = root.find("h1")
    title = normalize_text(h1.get_text(" ")) if h1 else None

    clauses: list[ClauseDraft] = []
    rows_out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    section_n = 0

    for table in root.find_all("table"):
        grid = expand_table(table)
        if len(grid) < 2:
            continue
        header = grid[0]
        c_is = _find_col(header, "is no", "आईएस")
        if c_is is None:
            continue
        c_prod = _find_col(header, "product category", "product", "उत्पाद")
        c_title = _find_col(header, "title")
        c_order = _find_col(header, "notification", "order", "अधिसूचना")
        # Heading text just before the table (Scheme-II uses numbered headings per ministry).
        prev = table.find_previous(["h1", "h2", "h3", "h4", "p", "strong"])
        table_heading = normalize_text(prev.get_text(" ")) if prev else ""

        category = table_heading if c_title is not None else ""
        group_rows: list[list[str]] = []
        pending_meta: list[dict] = []
        for row in grid[1:]:
            distinct = {c for c in row if c}
            # Category header rows: one distinct value spanning the whole row, no IS number.
            if len(distinct) == 1 and not stdnum.parse(next(iter(distinct))):
                _flush(clauses, group_rows, pending_meta, rows_out, category, table_heading, section_counter := [section_n])
                section_n = section_counter[0]
                category = next(iter(distinct))
                continue
            row = [" ".join(c.split()) for c in row]
            is_raw = row[c_is] if c_is < len(row) else ""
            numbers = stdnum.find_all(is_raw)
            if not numbers:
                continue
            product = row[c_prod] if c_prod is not None and c_prod < len(row) else ""
            std_title = row[c_title] if c_title is not None and c_title < len(row) else ""
            order = row[c_order] if c_order is not None and c_order < len(row) else ""
            sl = row[0] if row and re.match(r"^\d+\.?$", row[0]) else ""
            full = " ".join(row)
            status = "denotified" if re.search(r"de-?notified", full, re.I) else "compulsory"
            if status == "denotified" and "de-notified" in product.lower():
                product = re.sub(r"\s*De-?notified.*$", "", product, flags=re.I).strip()
                order = "De-notified from compulsory BIS certification"
            order = _shorten_order(order)
            key = (numbers[0].canonical, product or std_title)
            if key in seen:
                continue
            seen.add(key)
            group_rows.append([sl, is_raw, product, std_title, order])
            for sn in numbers:
                pending_meta.append(
                    {
                        "standard_number": sn.canonical,
                        "product": product or std_title,
                        "title": std_title or product,
                        "order": order,
                        "status": status,
                        "category": category or table_heading,
                    }
                )
        _flush(clauses, group_rows, pending_meta, rows_out, category, table_heading, section_counter := [section_n])
        section_n = section_counter[0]

    if not rows_out:
        raise IngestError(f"{path.name}: no product/standard rows found in the list")
    return ParsedDoc(clauses=clauses, pages=1, language="en", detected_title=title, last_updated=updated, catalogue_rows=rows_out)


def _shorten_order(order: str, limit: int = 260) -> str:
    """Keep a verbatim prefix of very long notification histories (some list 30+ amendment orders)."""
    if len(order) <= limit:
        return order
    cut = order[:limit].rsplit(" ", 1)[0]
    return f"{cut} … (further amendment and extension orders are listed on the source page)"


def _flush(
    clauses: list[ClauseDraft],
    group_rows: list[list[str]],
    pending_meta: list[dict],
    rows_out: list[dict],
    category: str,
    table_heading: str,
    counter: list[int],
) -> None:
    """Close the current category group: add its clause and record which clause each row lives in."""
    if not group_rows:
        return
    counter[0] += 1
    number = f"§{counter[0]}"
    header = ["Sl No.", "IS No.", "Product", "Title of standard", "Notification / status"]
    # Drop the title column when the list has none (Scheme-I).
    has_title = any(r[3] for r in group_rows)
    rows = [header] + group_rows
    if not has_title:
        rows = [[c for i, c in enumerate(r) if i != 3] for r in rows]
    clauses.append(
        ClauseDraft(
            number=number,
            heading=(category or table_heading or "Products")[:200],
            level=1,
            kind="list",
            page_start=1,
            page_end=1,
            table_rows=rows,
        )
    )
    for meta in pending_meta:
        meta["clause_number"] = number
        rows_out.append(meta)
    group_rows.clear()
    pending_meta.clear()
