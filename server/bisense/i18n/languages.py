"""Language registry: the single place that lists supported languages.

Adding Tamil, Telugu or Marathi = one entry here + one UI strings file (web/src/i18n/<code>.json)
+ optional keyword entries in glossary.yaml.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # English name
    native: str  # name in its own script
    script: str
    font: str
    speech_locale: str  # BCP-47 tag for browser STT/TTS
    unicode_range: tuple[int, int] | None  # script block used for detection


LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "English", "Latin", "Inter", "en-IN", None),
    "hi": Language("hi", "Hindi", "हिन्दी", "Devanagari", "Noto Sans Devanagari", "hi-IN", (0x0900, 0x097F)),
    "kn": Language("kn", "Kannada", "ಕನ್ನಡ", "Kannada", "Noto Sans Kannada", "kn-IN", (0x0C80, 0x0CFF)),
}


def detect_language(text: str, fallback: str = "en") -> str:
    """Detect by script: Devanagari -> hi, Kannada -> kn, otherwise the fallback (UI language or en).

    Romanized Hindi ("kaunsa standard lagu hota hai") is left to the LLM rewrite step.
    """
    counts: dict[str, int] = {}
    for ch in text:
        o = ord(ch)
        for code, lang in LANGUAGES.items():
            if lang.unicode_range and lang.unicode_range[0] <= o <= lang.unicode_range[1]:
                counts[code] = counts.get(code, 0) + 1
    if counts:
        return max(counts, key=lambda k: counts[k])
    return fallback if fallback in LANGUAGES else "en"
