"""PDF text extraction with PyMuPDF.

Produces, for each page, a list of `RawLine` objects (text, font size, bold flag, x position) and the
tables PyMuPDF's table finder detected (converted to Markdown). Lines that fall inside a detected
table are removed from the line stream and the table is inserted in their place, so the structure
builder sees the document in reading order.

Also validates the file first (magic bytes, size and page caps, encryption) so a corrupt or non-PDF
file fails with a clear message instead of a stack trace.

License note: PyMuPDF is AGPL-3.0 (see README).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from bisense.ingest.clean import normalize_text
from bisense.ingest.tables import rows_to_markdown

MAX_BYTES = 50 * 1024 * 1024
MAX_PAGES = 500


class IngestError(Exception):
    """A document could not be ingested; the message is shown to the user as-is."""


@dataclass
class RawLine:
    text: str
    page: int  # 1-based
    size: float
    bold: bool
    x0: float
    y0: float
    is_table: bool = False
    table_md: str = ""
    table_rows: list[list[str]] = field(default_factory=list)


@dataclass
class ParsedPdf:
    pages: list[list[RawLine]]
    page_count: int
    no_text_pages: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_pdf(path: Path) -> None:
    size = path.stat().st_size
    if size == 0:
        raise IngestError(f"{path.name}: file is empty")
    if size > MAX_BYTES:
        raise IngestError(f"{path.name}: file is larger than {MAX_BYTES // (1024 * 1024)} MB")
    with path.open("rb") as fh:
        head = fh.read(1024)
    if b"%PDF-" not in head:
        raise IngestError(f"{path.name}: not a PDF file (missing %PDF header)")


def _bbox_inside(inner: tuple[float, float, float, float], outer: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = inner
    ox0, oy0, ox1, oy1 = outer
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return ox0 - 1 <= cx <= ox1 + 1 and oy0 - 1 <= cy <= oy1 + 1


def extract_pdf(path: Path, find_tables: bool = True) -> ParsedPdf:
    validate_pdf(path)
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:  # PyMuPDF raises several exception types for corrupt files
        raise IngestError(f"{path.name}: could not open PDF ({exc.__class__.__name__})") from exc
    if doc.needs_pass:
        raise IngestError(f"{path.name}: PDF is encrypted/password-protected; export an unprotected copy")
    if doc.page_count > MAX_PAGES:
        raise IngestError(f"{path.name}: {doc.page_count} pages exceeds the {MAX_PAGES}-page cap")

    parsed = ParsedPdf(pages=[], page_count=doc.page_count)
    for pno, page in enumerate(doc, start=1):
        tables: list[tuple[tuple[float, float, float, float], list[list[str]]]] = []
        if find_tables:
            try:
                for tab in page.find_tables().tables:
                    rows = [[normalize_text(c or "") for c in row] for row in tab.extract()]
                    rows = [r for r in rows if any(c for c in r)]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        tables.append((tuple(tab.bbox), rows))  # type: ignore[arg-type]
            except Exception as exc:  # table finder failures must not stop ingestion
                parsed.warnings.append(f"page {pno}: table detection failed ({exc.__class__.__name__})")

        lines: list[RawLine] = []
        data = page.get_text("dict")
        for block in data.get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                spans = [s for s in line.get("spans", []) if s.get("text", "").strip()]
                if not spans:
                    continue
                text = normalize_text("".join(s["text"] for s in line["spans"]))
                if not text:
                    continue
                bbox = tuple(line["bbox"])
                if any(_bbox_inside(bbox, tb) for tb, _ in tables):  # type: ignore[arg-type]
                    continue
                size = max(s.get("size", 0) for s in spans)
                bold = any((s.get("flags", 0) & 16) or "bold" in s.get("font", "").lower() for s in spans)
                lines.append(RawLine(text=text, page=pno, size=round(size, 1), bold=bold, x0=bbox[0], y0=bbox[1]))

        for tb, rows in tables:
            lines.append(
                RawLine(
                    text="",
                    page=pno,
                    size=0,
                    bold=False,
                    x0=tb[0],
                    y0=tb[1],
                    is_table=True,
                    table_md=rows_to_markdown(rows),
                    table_rows=rows,
                )
            )
        lines.sort(key=lambda ln: (round(ln.y0, 0), ln.x0))
        if not any(not ln.is_table for ln in lines) and not tables:
            parsed.no_text_pages.append(pno)
        parsed.pages.append(lines)
    doc.close()
    return parsed


def render_page_png(path: Path, page_no: int, highlight: str | None = None, zoom: float = 1.6) -> bytes:
    """Render one page to PNG, optionally highlighting occurrences of `highlight` (used for page previews)."""
    doc = pymupdf.open(str(path))
    try:
        if not 1 <= page_no <= doc.page_count:
            raise IngestError(f"page {page_no} out of range")
        page = doc[page_no - 1]
        if highlight:
            needle = highlight.strip()[:120]
            rects = page.search_for(needle) if needle else []
            if not rects and len(needle) > 40:
                rects = page.search_for(needle[:40])
            for r in rects:
                annot = page.add_highlight_annot(r)
                annot.set_colors(stroke=(1.0, 0.85, 0.2))
                annot.update()
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
        return pix.tobytes("png")
    finally:
        doc.close()
