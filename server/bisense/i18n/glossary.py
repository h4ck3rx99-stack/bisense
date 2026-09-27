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
