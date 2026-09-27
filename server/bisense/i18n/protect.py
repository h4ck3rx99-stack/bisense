"""Placeholder protection for machine translation.

Before an English answer is translated, anything that must survive exactly -- standard numbers,
clause/table/annex references, numbers with units, chemical formulas, citation markers, verbatim
quotes and do-not-translate glossary terms -- is replaced by ⟦0⟧, ⟦1⟧, ... . After translation every
placeholder must come back exactly once; otherwise the translation is rejected (retry once, then
show English with a notice).
"""

from __future__ import annotations

import re

from bisense import stdnum
from bisense.i18n.glossary import do_not_translate

PLACEHOLDER_RE = re.compile(r"⟦(\d+)⟧")

_UNITS = r"(?:mg/l|mg/L|mg/kg|g/l|µg/l|ml|mL|l|L|kg|g|mg|mm|cm|m|km|°C|degrees C|%|percent|NTU|Hazen units|ppm|ppt|N/mm2|N|kN|V|W|kW|kVA|A|Hz|MPa|K|hours?|days?|months?|years?)"
_PATTERNS = [
    re.compile(r"\[C\d{1,2}\]"),  # citation markers
    re.compile(r"\b(?:clause|cl\.|section|sub-clause)\s+(?:[A-H]-\d+(?:\.\d+)*|\d+(?:\.\d+)*)", re.I),
    re.compile(r"\bTable\s+\d+[A-Z]?\b"),
    re.compile(r"\bAnnex(?:ure)?[\s-]+[A-Z]{1,4}\b"),
    re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:to|-|–)\s*\d+(?:[.,]\d+)?\s*" + _UNITS + r"?(?![\w])"),  # ranges
    re.compile(r"[≤≥<>]?\s*\b\d+(?:[.,]\d+)?\s*" + _UNITS + r"(?![\w])"),  # quantities with units
    re.compile(r"\b(?:[A-Z][a-z]?\d*){2,}\b(?=[^a-z]|$)"),  # chemical formulas like NO3, CaCO3
    re.compile(r"\b\d+(?:\.\d+)+\b"),  # bare decimals / clause-like numbers
    re.compile(r"\b\d+\b"),  # any remaining number (keeps Western digits exactly)
]


def protect(text: str, extra_literals: list[str] | None = None) -> tuple[str, list[str]]:
    """Replace protected spans with ⟦n⟧; returns (masked text, originals)."""
    spans: list[tuple[int, int]] = []

    def taken(a: int, b: int) -> bool:
        return any(not (b <= s or a >= e) for s, e in spans)

    # Standard numbers first (so "DEMO-101:2026" is one span, not "DEMO" + digits), then literals.
    for s, e, _ in stdnum.find_spans(text):
        if not taken(s, e):
            spans.append((s, e))
    literals = sorted(set((extra_literals or []) + do_not_translate()), key=len, reverse=True)
    for lit in literals:
        if not lit:
            continue
        for m in re.finditer(re.escape(lit), text):
            if not taken(m.start(), m.end()):
                spans.append((m.start(), m.end()))
    for pat in _PATTERNS:
        for m in pat.finditer(text):
            a, b = m.start(), m.end()
            # trim surrounding whitespace from the span
            while a < b and text[a].isspace():
                a += 1
            while b > a and text[b - 1].isspace():
                b -= 1
            if a < b and not taken(a, b):
                spans.append((a, b))
    spans.sort()
    originals: list[str] = []
    out = []
    last = 0
    for s, e in spans:
        out.append(text[last:s])
        out.append(f"⟦{len(originals)}⟧")
        originals.append(text[s:e])
        last = e
    out.append(text[last:])
    return "".join(out), originals


def restore(text: str, originals: list[str]) -> str:
    """Put originals back. Raises ValueError unless every placeholder appears exactly once."""
    found = [int(m.group(1)) for m in PLACEHOLDER_RE.finditer(text)]
    if sorted(found) != list(range(len(originals))):
        raise ValueError(f"placeholder mismatch: expected {len(originals)}, got {found}")
    return PLACEHOLDER_RE.sub(lambda m: originals[int(m.group(1))], text)
