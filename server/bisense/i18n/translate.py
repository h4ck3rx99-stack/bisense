"""Translate validated English answers into Hindi or Kannada (English-pivot pipeline).

Validation happens in English (auditable, language-independent). Only after validation are the
user-facing strings translated, in one LLM call, with protected placeholders. Verbatim quotes are
never translated in place -- the UI shows the original and offers a labelled machine translation.

If placeholders do not round-trip exactly, we retry once, then return English with a notice.
"""

from __future__ import annotations

import json
from pathlib import Path

from bisense.answer.llm_client import LLMUnavailable, extract_json
from bisense.i18n.languages import LANGUAGES
from bisense.i18n.protect import protect, restore

PROMPT = (Path(__file__).parents[1] / "answer" / "prompts" / "translate_v1.txt").read_text(encoding="utf-8")


def translate_strings(llm, strings: dict[str, str], lang: str) -> dict[str, str] | None:
    """Translate a flat {key: English text} map. Returns None when translation is unavailable/invalid."""
    if lang == "en" or not strings:
        return dict(strings)
    if llm is None:
        return None
    masked: dict[str, str] = {}
    originals: dict[str, list[str]] = {}
    for k, v in strings.items():
        masked[k], originals[k] = protect(v)
    system = PROMPT.replace("{language}", LANGUAGES[lang].name)
    for _attempt in range(2):
        try:
            res = llm.chat(
                [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(masked, ensure_ascii=False)}],
                json_mode=True,
                max_tokens=1600,
                temperature=0.0,
            )
            data = extract_json(res.text)
            out = {}
            for k in strings:
                if k not in data:
                    raise ValueError(f"missing key {k}")
                out[k] = restore(str(data[k]), originals[k])
            return out
        except (ValueError, LLMUnavailable):
            continue
    return None


def translate_text(llm, text: str, lang: str) -> str | None:
    res = translate_strings(llm, {"t": text}, lang)
    return res["t"] if res else None
