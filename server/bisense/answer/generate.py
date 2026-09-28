"""Prompt assembly and the LLM call for grounded answers.

Instruction channels are strictly separated (prompt-injection defence):
  - system message: fixed, versioned instructions only (prompts/answer_v2.txt);
  - user message: three delimited blocks -- <user_question>, <sources> (untrusted retrieved text,
    one <source id="C1" ...> per passage) and <context> (resolved scope ids only).
Retrieved text never goes into the system message, and the model has no tools.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

from bisense.answer.llm_client import LLMResult, extract_json
from bisense.retrieval.query import QueryPlan
from bisense.retrieval.search import Candidate

PROMPTS = Path(__file__).with_name("prompts")
ANSWER_SYSTEM = (PROMPTS / "answer_v2.txt").read_text(encoding="utf-8")
REWRITE_SYSTEM = (PROMPTS / "rewrite_v1.txt").read_text(encoding="utf-8")

_TAG_RE = re.compile(r"</?\s*(source|sources|user_question|context|intent|system)\b[^>]*>", re.I)


def _clean(text: str) -> str:
    """Neutralise anything in untrusted text that looks like our delimiter tags."""
    return _TAG_RE.sub(" ", text)


def _attr(v: str | None) -> str:
    return html.escape(v or "", quote=True)


def _document_kind(c: Candidate) -> str:
    if c.synthetic:
        return "sample data, not official"
    if c.text_scope == "product_manual":
        return f"BIS product manual for {c.number} (not the text of the standard)"
    return {"government_notification": "government notification", "official_website": "official BIS web page"}.get(c.source_type or "", "official BIS document")


def build_sources_block(context: list[Candidate]) -> str:
    parts = []
    for c in context:
        parts.append(
            f'<source id="{c.citation_id}" standard="{_attr(c.number or "")}" title="{_attr(c.title)}" '
            f'clause="{_attr(f"{c.clause_number} {c.clause_heading}".strip())}" page="{c.page_start}" '
            f'type="{_attr(c.std_kind)}" document="{_attr(_document_kind(c))}" synthetic="{str(c.synthetic).lower()}">\n{_clean(c.text)}\n</source>'
        )
    return "<sources>\n" + "\n".join(parts) + "\n</sources>"


def build_messages(plan: QueryPlan, context: list[Candidate], question: str | None = None) -> list[dict]:
    q = _clean(question or plan.english_query)
    scope = ", ".join(f"{s.number or s.title}" for s in plan.scope) or "none"
    user = (
        f"<user_question>{q}</user_question>\n"
        f"<intent>{plan.intent}</intent>\n"
        f"{build_sources_block(context)}\n"
        f"<context>resolved scope: {_clean(scope)}</context>"
    )
    return [{"role": "system", "content": ANSWER_SYSTEM}, {"role": "user", "content": user}]


def correction_message(drops: list) -> dict:
    reasons = "; ".join(f"{d.field}: {d.reason} ({d.text[:80]})" for d in drops[:10])
    return {
        "role": "user",
        "content": (
            "Your previous JSON contained statements that failed verification against the SOURCES: "
            f"{reasons}. Rewrite the JSON using only facts, numbers, standard numbers and quotes that appear "
            "verbatim in the cited SOURCES. Output JSON only."
        ),
    }


def generate(llm, messages: list[dict]) -> tuple[dict, LLMResult]:
    """Call the LLM and parse its JSON. Raises ValueError on unparseable output (caller retries once)."""
    res = llm.chat(messages, json_mode=True, temperature=0.1)
    return extract_json(res.text), res


def rewrite_query(llm, masked_query: str, recent: list[str]) -> dict:
    user = json.dumps({"question": _clean(masked_query), "previous_questions": [_clean(q) for q in recent[-2:]]}, ensure_ascii=False)
    res = llm.chat([{"role": "system", "content": REWRITE_SYSTEM}, {"role": "user", "content": user}], json_mode=True, max_tokens=300, temperature=0.0)
    return extract_json(res.text)
