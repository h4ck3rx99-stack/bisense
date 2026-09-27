"""Render the Tier C synthetic demo pack (data/demo/*.md) to PDF.

Why PDF and not just text: the demo documents must go through exactly the same path as real
standards (PDF parsing, heading detection, table finding, watermark stripping, page citations and
page previews). Rendering them to PDF guarantees that.

Each page carries:
  - a running header with the document number,
  - a footer "Synthetic demo document - not an Indian Standard - Page N",
  - a simulated downloader watermark line, like the per-page licence line on BIS-distributed PDFs.
The ingestion pipeline must strip all three before indexing (tested in tests/test_clean.py).

Source format (a small Markdown dialect):
  front matter between '---' lines (YAML), '# HEADING' for unnumbered top sections (FOREWORD, ANNEX A,
  AMENDMENT ...), '## 4 REQUIREMENTS' for numbered sections, lines starting with a clause number
  ('4.1 Source and Treatment') are sub-clauses, '| a | b |' lines form tables, 'Table N ...' captions.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from fpdf import FPDF
from fpdf.enums import XPos, YPos

WATERMARK = "Supplied by the BISense demo pack to demo.user@example.com on 2026-09-27 (simulated licence line)"
SUBCLAUSE_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+|[A-Z]-\d+(?:\.\d+)*)\s+([A-Z][^.]{0,70})$")


def read_demo_source(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8")
    if raw.startswith("---"):
        _, fm, body = raw.split("---", 2)
        return yaml.safe_load(fm) or {}, body.strip()
    return {}, raw


class _DemoPDF(FPDF):
    def __init__(self, number: str):
        super().__init__(format="A4")
        self.number = number
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(20, 20, 20)

    def header(self) -> None:
        self.set_font("Helvetica", "", 8)
        self.set_text_color(90, 90, 90)
        self.cell(0, 5, self.number, align="R", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.ln(3)
        self.set_text_color(0, 0, 0)

    def footer(self) -> None:
        self.set_y(-16)
        self.set_font("Helvetica", "", 7)
        self.set_text_color(120, 120, 120)
        self.cell(0, 4, WATERMARK, align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.cell(0, 4, f"Synthetic demo document - not an Indian Standard - Page {self.page_no()}", align="C")
        self.set_text_color(0, 0, 0)


def _latin1(text: str) -> str:
    # Core PDF fonts are Latin-1 only; demo sources are written to stay inside it.
    return text.encode("latin-1", "replace").decode("latin-1")


def render_pdf(src: Path, out: Path) -> None:
    meta, body = read_demo_source(src)
    pdf = _DemoPDF(meta["number"])
    pdf.add_page()

    # Title block
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 9, _latin1(meta["number"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 12)
    pdf.multi_cell(0, 6, _latin1(meta["title"]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 6, _latin1(f"{meta.get('revision', '')} - ICS {meta.get('ics', '')}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    table_rows: list[list[str]] = []

    def flush_table() -> None:
        if not table_rows:
            return
        pdf.set_font("Helvetica", "", 8.5)
        with pdf.table(first_row_as_headings=True, line_height=5, padding=1.2) as table:
            for r in table_rows:
                row = table.row()
                for cell in r:
                    row.cell(_latin1(cell))
        pdf.ln(3)
        table_rows.clear()

    for line in body.splitlines():
        s = line.strip()
        if s.startswith("|"):
            table_rows.append([c.strip() for c in s.strip("|").split("|")])
            continue
        flush_table()
        if not s:
            pdf.ln(1.5)
            continue
        if s.startswith("# "):
            pdf.ln(3)
            pdf.set_font("Helvetica", "B", 12)
            pdf.multi_cell(0, 7, _latin1(s[2:]), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif s.startswith("## "):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 11)
            pdf.multi_cell(0, 6, _latin1(s[3:]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        elif s.startswith("Table "):
            pdf.set_font("Helvetica", "B", 9.5)
            pdf.multi_cell(0, 5, _latin1(s), align="C", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(1)
        elif SUBCLAUSE_HEADING_RE.match(s):
            pdf.set_font("Helvetica", "B", 10)
            pdf.multi_cell(0, 5.5, _latin1(s), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        else:
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, _latin1(s), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    flush_table()

    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".pdf.tmp")
    pdf.output(str(tmp))
    tmp.replace(out)


def build_demo_pack(demo_dir: Path, force: bool = False) -> list[Path]:
    """Render every data/demo/*.md to data/demo/pdf/<name>.pdf if missing or older than its source."""
    outputs = []
    for src in sorted(demo_dir.glob("*.md")):
        out = demo_dir / "pdf" / (src.stem + ".pdf")
        if force or not out.exists() or out.stat().st_mtime < src.stat().st_mtime:
            render_pdf(src, out)
        outputs.append(out)
    return outputs
