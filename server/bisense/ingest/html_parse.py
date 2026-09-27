"""Parse official BIS web pages (Tier B) into the same clause structure as PDFs.

The BIS website (WordPress) puts the page body inside `div.who_we_area`. Inside it we find:
  - headings (h1..h4) and short bold-only paragraphs -> section clauses numbered "§1", "§2", ...
  - FAQ accordions: `div.accordion` (question) followed by `div.panel` (answer) -> clauses "Q1", "Q2" ...
  - paragraphs and list items -> text of the current clause
  - tables -> table clauses (Markdown)
Navigation, breadcrumbs, "Read More" links and file-size notes are dropped.

HTML pages have no page numbers; every clause is on "page 1" and citations show "web page".
"""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from bisense.ingest.clean import normalize_text
from bisense.ingest.pdf_parse import IngestError
from bisense.ingest.tables import rows_to_markdown
from bisense.ingest.types import ClauseDraft, ParsedDoc

PARSER_VERSION = "html-1.1"

_NOISE_RE = re.compile(
    r"^(Read More\s*»?|\(?\s*(size|आकार)\s*[–-].*\)?|Last Updated on .*|Skip Content|Home|/|»|Click here|पुराने दिशानिर्देश देखें)$",
    re.IGNORECASE,
)
_FAQ_NUM_RE = re.compile(r"^\s*(?:Q\s*\.?\s*)?(\d{1,3})(?:\s*[.):]\s*|\s+)")


def load_soup(path: Path) -> BeautifulSoup:
    raw = path.read_bytes()
    if len(raw) > 20 * 1024 * 1024:
        raise IngestError(f"{path.name}: HTML file too large")
    head = raw[:2048].lower()
    if b"<html" not in head and b"<!doctype" not in head:
        raise IngestError(f"{path.name}: not an HTML page")
    return BeautifulSoup(raw.decode("utf-8", errors="replace"), "html.parser")


def content_root(soup: BeautifulSoup) -> Tag:
    areas = soup.select("div.who_we_area")
    if areas:
        root = max(areas, key=lambda a: len(a.get_text()))
    else:
        root = soup.find("main") or soup.find("article") or soup.body  # type: ignore[assignment]
    if root is None:
        raise IngestError("no content area found in HTML page")
    for sel in (".fbc", "script", "style", "nav", "form", "iframe", "noscript"):
        for el in root.select(sel):
            el.decompose()
    return root


def _text(el: Tag | NavigableString) -> str:
    if isinstance(el, NavigableString):
        return normalize_text(str(el))
    for br in el.find_all("br"):
        br.replace_with("\n")
    return normalize_text(" ".join(t.strip() for t in el.get_text(" ").split("\n") if t.strip()))


def _last_updated(soup: BeautifulSoup) -> str | None:
    m = re.search(r"Last Updated on\s+([A-Z][a-z]+ \d{1,2}, \d{4})", soup.get_text(" "))
    return m.group(1) if m else None


def parse_html_document(path: Path, language: str = "en") -> ParsedDoc:
    soup = load_soup(path)
    updated = _last_updated(soup)
    root = content_root(soup)

    clauses: list[ClauseDraft] = []
    current: int | None = None
    section_n = 0
    faq_n = 0
    table_n = 0
    title: str | None = None

    def new_clause(number: str, heading: str, kind: str, level: int = 1, parent: int | None = None) -> int:
        clauses.append(ClauseDraft(number=number, heading=heading, level=level, kind=kind, page_start=1, page_end=1, parent=parent))
        return len(clauses) - 1

    def add_text(text: str) -> None:
        nonlocal current
        text = text.strip()
        if not text or _NOISE_RE.match(text):
            return
        if current is None:
            current = new_clause("§0", "Introduction", "other")
        clauses[current].paragraphs.append(text)

    # Walk block-level elements in document order, without descending into ones we consume whole.
    def walk(node: Tag) -> None:
        nonlocal current, section_n, faq_n, table_n, title
        for child in node.children:
            if isinstance(child, Comment):
                continue
            if isinstance(child, NavigableString):
                t = normalize_text(str(child))
                if len(t) > 2:
                    add_text(t)
                continue
            if not isinstance(child, Tag):
                continue
            name = child.name or ""
            classes = child.get("class") or []
            if "accordion" in classes:
                q = _text(child)
                faq_n += 1
                m = _FAQ_NUM_RE.match(q)
                q_clean = q[m.end() :] if m else q
                current = new_clause(f"Q{faq_n}", q_clean.strip(), "faq")
                continue
            if "panel" in classes:
                if current is None or clauses[current].kind != "faq":
                    current = new_clause(f"Q{faq_n + 1}", "", "faq")
                    faq_n += 1
                _collect_blocks(child, clauses[current].paragraphs)
                continue
            if name in ("h1", "h2", "h3", "h4", "h5"):
                t = _text(child)
                if not t or _NOISE_RE.match(t):
                    continue
                if name == "h1" and title is None:
                    title = t
                    continue
                section_n += 1
                current = new_clause(f"§{section_n}", t, "other")
                continue
            if name == "table":
                rows = _table_rows(child)
                if rows:
                    table_n += 1
                    parent = current
                    current_table = new_clause(f"Table {table_n}", "", "table", level=2 if parent is not None else 1, parent=parent)
                    clauses[current_table].table_rows = rows
                    clauses[current_table].paragraphs = [rows_to_markdown(rows)]
                continue
            if name in ("p", "li"):
                t = _text(child)
                strong = child.find(["strong", "b"])
                if strong and len(t) < 90 and _text(strong) == t and not t.endswith((".", ":")):
                    section_n += 1
                    current = new_clause(f"§{section_n}", t, "other")
                else:
                    add_text(("• " if name == "li" else "") + t)
                continue
            if name in ("ul", "ol", "div", "section", "span", "center", "tbody", "strong", "b", "a", "u", "em"):
                walk(child)
                continue

    walk(root)
    clauses = [c for c in clauses if c.paragraphs or c.heading]
    # Fix parent indexes after filtering (only tables have parents here).
    for c in clauses:
        c.parent = None if c.kind != "table" else None
    total = sum(len(c.text) + len(c.heading) for c in clauses)
    if not clauses or total < 150:
        raise IngestError(f"{path.name}: page has too little text to index ({total} characters)")
    return ParsedDoc(clauses=clauses, pages=1, language=language, detected_title=title, last_updated=updated)


def _collect_blocks(node: Tag, out: list[str]) -> None:
    items = node.find_all(["p", "li", "td"], recursive=True)
    if not items:
        t = _text(node)
        if t:
            out.append(t)
        return
    for it in items:
        if it.find(["p", "li"]):
            continue
        t = _text(it)
        if t and not _NOISE_RE.match(t):
            out.append(("• " if it.name == "li" else "") + t)


def _table_rows(table: Tag) -> list[list[str]]:
    rows = []
    for tr in table.find_all("tr"):
        cells = [_text(td) for td in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append(cells)
    return rows
