"""Text cleaning for extracted document text.

What it does:
  - normalize_text: Unicode NFC, zero-width characters, ligatures, non-breaking spaces, whitespace.
  - repair_hyphenation / join_wrapped: undo PDF line wrapping inside a paragraph.
  - strip_repeated_lines: remove running headers, footers, page numbers and per-page watermarks.
  - is_watermark_line: licence/downloader lines that identify a person (never indexed or shown).
  - script ratios and garbled-text detection for legacy (non-Unicode) Hindi fonts.

Why: retrieval quality and citation accuracy depend on clean, stable text. Watermark lines on
BIS-distributed PDFs can contain a downloader's name, email and IP address; they must never reach
the index or the UI.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter

ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"), None)
LIGATURES = {"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl"}

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_IP_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_WATERMARK_WORDS = re.compile(
    r"\b(licen[cs]ed to|supplied by|downloaded by|downloaded on|for internal use|single user licence|"
    r"simulated licence line|printed by|purchased by)\b",
    re.IGNORECASE,
)
_PAGE_NUMBER_RE = re.compile(r"^\s*(?:page\s*)?[-–(\[]?\s*\d{1,4}\s*[-–)\]]?\s*(?:of\s*\d{1,4})?\s*$", re.IGNORECASE)

# Known boilerplate on Gazette of India notifications (bilingual orders).
_GAZETTE_NOISE = re.compile(
    r"(THE GAZETTE OF INDIA|REGD\.\s*No\.|^\s*\[?PART II\b|^\s*EXTRAORDINARY\s*$|PUBLISHED BY AUTHORITY|"
    r"GI/\d{4}|Uploaded by Dte\. of Printing|Digitally signed by|^\s*xxxGID\w*xxx\s*$|Signature Not Verified)",
    re.IGNORECASE,
)


def normalize_text(text: str) -> str:
    """NFC-normalize and tidy a string without changing its words."""
    # Zero-width spaces are used as word separators by some PDF producers ("Grant​​of").
    text = re.sub(r"[​⁠]+", " ", text)
    text = text.translate(ZERO_WIDTH)
    for k, v in LIGATURES.items():
        text = text.replace(k, v)
    text = text.replace(" ", " ").replace("­", "")
    text = unicodedata.normalize("NFC", text)
    text = re.sub(r"[ \t\f\v]+", " ", text)
    return text.strip()


def repair_hyphenation(prev: str, nxt: str) -> str | None:
    """If `prev` ends with a hyphenated word fragment continued on `nxt`, return the joined text."""
    if re.search(r"[a-z]-$", prev) and re.match(r"^[a-z]", nxt):
        return prev[:-1] + nxt
    return None


def join_wrapped(lines: list[str]) -> str:
    """Join lines of one paragraph, repairing end-of-line hyphenation."""
    out = ""
    for line in lines:
        line = line.strip()
        if not line:
            continue
        if not out:
            out = line
            continue
        joined = repair_hyphenation(out, line)
        out = joined if joined is not None else out + " " + line
    return out


def is_watermark_line(line: str) -> bool:
    """Lines that identify a downloader or licence holder (email, IP, 'licensed to ...')."""
    if _WATERMARK_WORDS.search(line):
        return True
    if _EMAIL_RE.search(line) and (_IP_RE.search(line) or re.search(r"\b(on|dated)\b", line, re.I)):
        return True
    return False


def is_page_number(line: str) -> bool:
    return bool(_PAGE_NUMBER_RE.match(line))


def is_gazette_noise(line: str) -> bool:
    return bool(_GAZETTE_NOISE.search(line))


def _repeat_key(line: str) -> str:
    # Treat "Page 3" and "Page 4" as the same repeated line.
    return re.sub(r"\d+", "#", line.strip().lower())


def find_repeated_lines(pages: list[list[str]], min_fraction: float = 0.5) -> set[str]:
    """Normalized keys of lines that appear on at least `min_fraction` of pages (headers/footers)."""
    if len(pages) < 2:
        return set()
    counts: Counter[str] = Counter()
    for lines in pages:
        counts.update({_repeat_key(line) for line in lines if line.strip()})
    threshold = max(2, int(len(pages) * min_fraction + 0.9999))
    return {k for k, c in counts.items() if c >= threshold and len(k) > 1}


def strip_repeated_lines(pages: list[list[str]]) -> tuple[list[list[str]], int]:
    """Remove headers, footers, page numbers and watermarks from per-page line lists.

    Returns the cleaned pages and the number of removed lines.
    """
    repeated = find_repeated_lines(pages)
    removed = 0
    cleaned: list[list[str]] = []
    for lines in pages:
        keep = []
        for line in lines:
            if _repeat_key(line) in repeated or is_page_number(line) or is_watermark_line(line) or is_gazette_noise(line):
                removed += 1
                continue
            keep.append(line)
        cleaned.append(keep)
    return cleaned, removed


# ---- script detection -------------------------------------------------------------------------


def script_counts(text: str) -> dict[str, int]:
    counts = {"latin": 0, "devanagari": 0, "kannada": 0, "other": 0}
    for ch in text:
        if not ch.isalpha():
            continue
        o = ord(ch)
        if o < 0x250:
            counts["latin"] += 1
        elif 0x0900 <= o <= 0x097F:
            counts["devanagari"] += 1
        elif 0x0C80 <= o <= 0x0CFF:
            counts["kannada"] += 1
        else:
            counts["other"] += 1
    return counts


def devanagari_ratio(text: str) -> float:
    c = script_counts(text)
    total = sum(c.values())
    return c["devanagari"] / total if total else 0.0


_LEGACY_CHARS = set("ªö@]^`~{}¡¢£¤¥¦§¨©«¬®¯°±²³´µ¶·¸¹º»¼½¾¿ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÐÑÒÓÔÕÖ×ØÙÚÛÜÝÞß")


def looks_like_legacy_font(line: str) -> bool:
    """Heuristic for ASCII-mapped legacy Hindi fonts (e.g. Kruti Dev): 'jftLVªh laö Mhö ,yö&33004@99'.

    Signals: odd symbols inside words, and words mixing lower→upper case mid-word ('jftLVªh', 'vlk/kj.k').
    """
    words = re.findall(r"\S+", line)
    if len(words) < 2:
        return False
    odd = 0
    for w in words:
        if any(ch in _LEGACY_CHARS for ch in w):
            odd += 1
        elif re.search(r"[a-z][A-Z]", w) and not re.match(r"^(?:[A-Z]?[a-z]+[A-Z][a-z]+)+$", w):
            odd += 1
        elif re.search(r"[a-zA-Z][/.;&][a-zA-Z]", w) and not re.search(r"(https?|www|\.pdf|\.in|\.com|e\.g|i\.e|and/or)", w, re.I):
            odd += 1
    return odd / len(words) >= 0.3


def is_broken_devanagari(line: str) -> bool:
    """Devanagari extracted from non-Unicode fonts often loses matras and yields stray Latin symbols.

    We flag lines where Devanagari letters are mixed with many stray symbols like '!', '"', '#', '$'.
    """
    dev = sum(1 for ch in line if 0x0900 <= ord(ch) <= 0x097F)
    if dev == 0:
        return False
    stray = sum(1 for ch in line if ch in "!\"#$%&'*+<=>?@[\\]^_`{|}~" or ch in "0123456789" and False)
    latin_caps_inside = len(re.findall(r"[ऀ-ॿ][A-Z]|[A-Z][ऀ-ॿ]", line))
    return (stray + latin_caps_inside) / max(dev, 1) > 0.08


def page_is_garbled(lines: list[str]) -> bool:
    """A page is garbled when most of its non-trivial lines look like legacy-font output."""
    content = [ln for ln in lines if len(ln.strip()) > 12]
    if not content:
        return False
    bad = sum(1 for ln in content if looks_like_legacy_font(ln) or is_broken_devanagari(ln))
    return bad / len(content) > 0.5


_DEVANAGARI_RUN = re.compile(r"[ऀ-ॿ꣠-ꣿ][ऀ-ॿ꣠-ꣿ‌‍\s/,:()-]*")
_LATIN = re.compile(r"[A-Za-z]")


def strip_parallel_devanagari(text: str) -> str:
    """Bilingual BIS documents print every label twice ("मानक संख्या IS No."). When a piece of text also
    has English, drop the Hindi half so the index is not doubled (the page image keeps the original).
    Text that is only Hindi is kept as it is."""
    if len(_LATIN.findall(text)) < 3 or not _DEVANAGARI_RUN.search(text):
        return text
    out = _DEVANAGARI_RUN.sub(" ", text)
    return re.sub(r"[ 	]{2,}", " ", out).strip()
