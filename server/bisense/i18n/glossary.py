"""Loads i18n/glossary.yaml and applies it.

expand_lexical(text)      -> extra English search terms from the synonym map (lexical query only)
keyword_translate(text)   -> offline Hindi/Kannada -> English keywords (used only without an LLM)
do_not_translate()        -> protected glossary terms for answer translation
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

GLOSSARY_PATH = Path(__file__).with_name("glossary.yaml")


@lru_cache
def _glossary() -> dict:
    return yaml.safe_load(GLOSSARY_PATH.read_text(encoding="utf-8")) or {}


def expand_lexical(text: str) -> list[str]:
    low = text.lower()
    extra: list[str] = []
    for key, values in (_glossary().get("synonyms") or {}).items():
        # tolerate a plural "s" on the last word ("motorcycle helmets" matches "motorcycle helmet")
        if re.search(r"(?<!\w)" + re.escape(key) + r"s?(?!\w)", low):
            extra.extend(values)
    return extra


def keyword_translate(text: str, lang: str) -> list[str]:
    table = _glossary().get(f"keywords_{lang}") or {}
    out: list[str] = []
    for token in re.findall(r"[\wऀ-ॿಀ-೿‌‍]+", text):
        if token in table:
            out.extend(table[token])
            continue
        # crude stemming: match the longest glossary key that prefixes the token (Indic inflections)
        best = max((k for k in table if token.startswith(k) and len(k) >= 3), key=len, default=None)
        if best:
            out.extend(table[best])
    # Latin tokens inside a Hindi/Kannada query (e.g. "BIS", "IS 14543") are kept as they are.
    out.extend(re.findall(r"[A-Za-z][A-Za-z0-9\-]+|\d+", text))
    seen: set[str] = set()
    return [w for w in out if not (w.lower() in seen or seen.add(w.lower()))]  # type: ignore[func-returns-value]


def do_not_translate() -> list[str]:
    return list(_glossary().get("do_not_translate") or [])


def product_phrases(text: str) -> list[tuple[str, str]]:
    """(everyday key, official product wording) for each product key in the text, longest keys first and
    without overlaps ("water heater" wins over "heater"; "mobile charger" over "charger")."""
    low = text.lower()
    table = _glossary().get("products") or {}
    taken: list[tuple[int, int]] = []
    out: list[tuple[str, str]] = []
    for key in sorted(table, key=len, reverse=True):
        for m in re.finditer(r"(?<![\w-])" + re.escape(key) + r"(?:e?s)?(?![\w-])", low):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            out.extend((key, v) for v in table[key])
            break
    return out


# Romanised Hindi function words: two or more in a Latin-script question => Hinglish.
_HINGLISH = set(
    "main mai mein hoon hun hu hai hain ka ki ke ko kya kaunsa konsa kaun kaise kahan chahiye banata banate banati "
    "bechta bechte bechti mera meri mere apna liye zaroori zaruri jaruri lagega lagta karna karta karte se par aur "
    "bhi nahi nahin kyun kab".split()
)


def is_hinglish(text: str) -> bool:
    if re.search(r"[^\x00-\x7F]", text):
        return False
    words = re.findall(r"[a-z]+", text.lower())
    hits = sum(1 for w in words if w in _HINGLISH)
    return hits >= 2 and hits >= len(words) * 0.25


def hinglish_translate(text: str) -> list[str]:
    """Offline Hinglish -> English keywords: mapped function words plus every other word kept as is
    (product names like "kettle" are usually English already)."""
    table = _glossary().get("keywords_hinglish") or {}
    out: list[str] = []
    for w in re.findall(r"[A-Za-z0-9][A-Za-z0-9\-]*", text):
        lw = w.lower()
        if lw in table:
            out.extend(table[lw])
        elif lw not in _HINGLISH:
            out.append(w)
    seen: set[str] = set()
    return [w for w in out if not (w.lower() in seen or seen.add(w.lower()))]  # type: ignore[func-returns-value]
