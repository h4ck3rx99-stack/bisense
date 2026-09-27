"""Turn one source file into a `ParsedDoc` (dispatches on file type).

PDF path:  extract lines/tables -> strip headers/footers/watermarks -> drop garbled or
           foreign-script lines -> build clause tree -> detect metadata.
HTML path: see html_parse.py (BIS web pages) and catalogue.py (official product lists).
"""

from __future__ import annotations

import re
from pathlib import Path

from bisense import stdnum
from bisense.ingest import ocr
from bisense.ingest.clean import (
    devanagari_ratio,
    is_broken_devanagari,
    looks_like_legacy_font,
    page_is_garbled,
    strip_repeated_lines,
)
from bisense.ingest.pdf_parse import IngestError, RawLine, extract_pdf
from bisense.ingest.structure import build_clauses
from bisense.ingest.types import ParsedDoc

PARSER_VERSION = "pdf-1.4"


def parse_pdf_document(path: Path, language: str = "en", ocr_mode: str = "auto") -> ParsedDoc:
    parsed = extract_pdf(path)
    warnings = list(parsed.warnings)

    # 1. Headers, footers, page numbers, watermarks (compare text lines across pages).
    page_texts = [[ln.text for ln in page if not ln.is_table] for page in parsed.pages]
    cleaned_texts, removed = strip_repeated_lines(page_texts)
    keep_sets = [set(map(id, [])) for _ in parsed.pages]  # placeholder for readability
    del keep_sets
    pages: list[list[RawLine]] = []
    for page, kept in zip(parsed.pages, cleaned_texts):
        kept_counter: dict[str, int] = {}
        for t in kept:
            kept_counter[t] = kept_counter.get(t, 0) + 1
        out = []
        for ln in page:
            if ln.is_table:
                out.append(ln)
            elif kept_counter.get(ln.text, 0) > 0:
                kept_counter[ln.text] -= 1
                out.append(ln)
        pages.append(out)

    # 2. Pages without a text layer -> OCR if available, else warn.
    ocr_pages: list[int] = []
    for pno in parsed.no_text_pages:
        if ocr_mode != "off" and ocr.available():
            ocr_pages.append(pno)
        else:
            warnings.append(f"page {pno}: no text layer (scanned image); OCR not available, page skipped")
    if ocr_pages:
        warnings.append(f"OCR pages detected {ocr_pages}; OCR text extraction is not enabled in this build")

    # 3. Garbled pages (legacy Hindi fonts) and, for English documents, Devanagari lines of bilingual
    #    Gazette notifications (the English half is indexed; the Hindi half is kept only if clean).
    garbled_pages: list[int] = []
    filtered: list[list[RawLine]] = []
    dropped_script = 0
    for pno, page in enumerate(pages, start=1):
        texts = [ln.text for ln in page if not ln.is_table]
        if language == "en":
            page_kept = []
            for ln in page:
                if ln.is_table:
                    cells = " ".join(c for row in ln.table_rows for c in row)
                    if devanagari_ratio(cells) > 0.3 or looks_like_legacy_font(cells[:400]):
                        dropped_script += 1
                        continue
                    page_kept.append(ln)
                    continue
                if devanagari_ratio(ln.text) > 0.3 or looks_like_legacy_font(ln.text) or is_broken_devanagari(ln.text):
                    dropped_script += 1
                    continue
                page_kept.append(ln)
            filtered.append(page_kept)
        else:
            if page_is_garbled(texts):
                garbled_pages.append(pno)
                warnings.append(f"page {pno}: text looks garbled (legacy font); excluded from the index")
                filtered.append([])
            else:
                filtered.append(page)
    if dropped_script:
        warnings.append(f"{dropped_script} non-English or garbled lines dropped (bilingual document, English text indexed)")

    clauses = build_clauses(filtered)
    if not clauses:
        raise IngestError(f"{path.name}: no text could be extracted")

    doc = ParsedDoc(
        clauses=clauses,
        pages=parsed.page_count,
        language=language,
        warnings=warnings,
        ocr_pages=ocr_pages,
        garbled_pages=garbled_pages,
        removed_lines=removed,
    )
    _detect_metadata(doc, filtered)
    return doc


def _detect_metadata(doc: ParsedDoc, pages: list[list[RawLine]]) -> None:
    """Best-effort number/title/year from page 1. The manifest always wins over these guesses."""
    first = [ln for ln in (pages[0] if pages else []) if not ln.is_table]
    head_text = " ".join(ln.text for ln in first[:15])
    sn = stdnum.parse(head_text)
    if sn:
        doc.detected_number = sn.canonical
        doc.detected_year = sn.year
    if first:
        biggest = max(ln.size for ln in first)
        title_lines = [ln.text for ln in first if ln.size >= biggest - 0.5 and not stdnum.parse(ln.text)]
        if not title_lines:
            second = sorted({ln.size for ln in first}, reverse=True)
            if len(second) > 1:
                title_lines = [ln.text for ln in first if abs(ln.size - second[1]) < 0.5][:3]
        if title_lines:
            doc.detected_title = " ".join(title_lines)[:300]
    m = re.search(r"Reaffirmed\s*(\d{4})", " ".join(ln.text for p in pages[:2] for ln in p if not ln.is_table), re.I)
    if m:
        doc.reaffirmed = m.group(1)
