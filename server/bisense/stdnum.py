"""Indian Standard number parsing and normalization.

Users, PDFs and official lists write the same standard in many ways:
    "IS 302 (Part 1) : 2008", "IS302(Part1):2008", "IS 302 Part 1", "IS/IEC 60335-1",
    "IS 1786:2008 (Reaffirmed 2018)", "IS 1489 (Pt 1)", "DEMO-101:2026".
This module turns any of those into one canonical form so lookups, filters and citation checks
compare like with like.

Canonical form:  "<prefix> <number>[ (Part N)][ (Sec M)][:YYYY]"
    prefix is "IS", "IS/IEC", "IS/ISO", "IS/ISO/IEC" or "DEMO".
The *base* number is the canonical form without the year; when a user omits the year we match on it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Prefix alternatives, longest first so "IS/ISO/IEC" wins over "IS".
_PREFIX = r"(?P<prefix>IS\s*/\s*ISO\s*/\s*IEC|IS\s*/\s*IEC|IS\s*/\s*ISO|IS|DEMO)"
_NUMBER = r"(?P<num>\d{1,6}(?:[-.]\d{1,4})*)"
_PART = r"(?:\s*[:(]?\s*(?:Part|Pt\.?|भाग)\s*(?P<part>\d{1,3}[A-Z]?)\s*\)?)?"
# "(Sec 1)", "/Sec 3" (as in "Part 2/Sec 3"), "Section 2"
_SEC = r"(?:\s*[(/]?\s*(?:Sec(?:tion)?\.?)\s*(?P<sec>\d{1,3}[A-Z]?)\s*\)?)?"
_YEAR = r"(?:\s*[:：]\s*(?P<year>(?:19|20)\d{2}))?"

# Used for extraction from free text. "IS" must be a separate token (not the word "this").
STANDARD_RE = re.compile(
    r"(?<![A-Za-z0-9])" + _PREFIX + r"(?:\s*[-:]?\s*|\s+)" + _NUMBER + _PART + _SEC + _YEAR,
    re.IGNORECASE,
)

# Loose spoken/typed forms like "IS fourteen five four three" are handled in i18n/voice normalization;
# here we only deal with digits.


@dataclass(frozen=True)
class StdNumber:
    prefix: str
    number: str
    part: str | None = None
    section: str | None = None
    year: int | None = None

    @property
    def base(self) -> str:
        sep = "-" if self.prefix == "DEMO" else " "
        text = f"{self.prefix}{sep}{self.number}"
        if self.part:
            text += f" (Part {self.part})"
        if self.section:
            text += f" (Sec {self.section})"
        return text

    @property
    def canonical(self) -> str:
        return f"{self.base}:{self.year}" if self.year else self.base


def _clean_prefix(raw: str) -> str:
    p = re.sub(r"\s+", "", raw).upper()
    return p


def parse(text: str) -> StdNumber | None:
    """Parse the first standard number found in `text`; None if there is none."""
    if not text:
        return None
    m = STANDARD_RE.search(text.replace(" ", " "))
    if not m:
        return None
    return _from_match(m)


def _from_match(m: re.Match[str]) -> StdNumber | None:
    prefix = _clean_prefix(m.group("prefix"))
    num = m.group("num")
    # Guard: plain "IS" followed by a tiny number inside prose ("is 5 mg") is not a standard number.
    # Real IS numbers used alone are at least 2 digits in practice; accept 1-digit only with a Part.
    if prefix == "IS" and len(num) < 2 and not m.group("part"):
        return None
    # An "is" in lowercase prose ("the pH is 7") must not be treated as a standard.
    # Lowercase "is 14543" (typed queries) is accepted only for 3+ digit numbers not followed by a unit.
    raw_prefix = m.group("prefix")
    if raw_prefix.strip() == "is":
        after = m.string[m.end() : m.end() + 8].strip().lower()
        if len(num) < 3 or "." in num or re.match(r"^(mg|g|kg|ml|l|mm|cm|m|%|°|per|ppm|µ|n|kn|v|w|a)\b", after):
            return None
    year = int(m.group("year")) if m.group("year") else None
    part = m.group("part")
    sec = m.group("sec")
    return StdNumber(prefix=prefix, number=num, part=part, section=sec, year=year)


def find_all(text: str) -> list[StdNumber]:
    """All standard numbers in free text, in order, de-duplicated by canonical form."""
    out: list[StdNumber] = []
    seen: set[str] = set()
    for m in STANDARD_RE.finditer(text.replace(" ", " ")):
        sn = _from_match(m)
        if sn and sn.canonical not in seen:
            seen.add(sn.canonical)
            out.append(sn)
    return out


def find_spans(text: str) -> list[tuple[int, int, StdNumber]]:
    """Character spans of standard numbers (used for placeholder protection during translation)."""
    spans = []
    for m in STANDARD_RE.finditer(text):
        sn = _from_match(m)
        if sn:
            spans.append((m.start(), m.end(), sn))
    return spans


def normalize_standard_number(text: str) -> str | None:
    """Canonical string for a standard number, or None if `text` contains none.

    >>> normalize_standard_number("IS302(Part1):2008")
    'IS 302 (Part 1):2008'
    """
    sn = parse(text)
    return sn.canonical if sn else None


def base_number(text: str) -> str | None:
    sn = parse(text)
    return sn.base if sn else None


def slugify_number(canonical: str) -> str:
    """URL slug for a standard: 'IS 302 (Part 1):2008' -> 'is-302-part-1-2008'."""
    s = canonical.lower().replace("/", "-")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def same_standard(a: str, b: str) -> bool:
    """True if two references denote the same standard (year-insensitive when either omits it)."""
    pa, pb = parse(a), parse(b)
    if not pa or not pb:
        return False
    if pa.base != pb.base:
        return False
    return pa.year is None or pb.year is None or pa.year == pb.year
