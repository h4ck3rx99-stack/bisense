"""Optional OCR support detection.

OCR is only needed for scanned pages that have no text layer. It requires Tesseract (eng + hin),
which is not a Python package and may not be installed. Ingestion must work without it: pages
without text are reported as warnings in the ingest report, never silently indexed as empty.
"""

from __future__ import annotations

import shutil


def available() -> bool:
    return shutil.which("tesseract") is not None
