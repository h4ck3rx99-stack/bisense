"""Deterministic answer validator (no LLM). Every model answer passes through here before a user sees it.

Checks, in order, for each point / summary sentence / listed standard:
  1. citation ids exist in the context set (C1..Cn); unknown ids are removed;
     a source_fact left with no valid citation is dropped;
  2. quotes must appear verbatim in a cited chunk (after normalising case, whitespace, hyphenation,
     quote marks and dashes); a failed quote is removed, and a point that depended on it is dropped;
  3. every number (with unit, percentage or range) must appear in a cited chunk (or its clause/standard
     metadata); otherwise the point is dropped;
  4. every standard number anywhere must appear in the context or the user's question;
  5. clause references ("clause 4.2", "Table 1") must exist among the cited chunks' clauses or text;
  6. URLs not present in source metadata or text are stripped;
  7. if no valid source fact survives for a factual question, the answer becomes insufficient_evidence.
Every removal is recorded as a `Drop(field, text, reason)` and shown in the Retrieval details drawer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from bisense import stdnum
from bisense.models import Drop, Point

CITE_MARKER_RE = re.compile(r"\[(C\d{1,2})\]")
URL_RE = re.compile(r"https?://[^\s)\]>\"']+")
CLAUSE_REF_RE = re.compile(
    r"\b(?:clause|cl\.|sub-clause|section)\s+([A-H]-\d+(?:\.\d+)*|\d+(?:\.\d+)*)|\b(Table\s+\d+[A-Z]?)|\b(Annex(?:ure)?[\s-]+[A-Z]{1,4}\b)", re.I
)
# numbers like 500, 0.01, 6.5, "5 000", 1,000 ; optional unit / percent afterwards is part of the match text
NUMBER_RE = re.compile(r"(?<![\w.])(\d{1,3}(?:[ ,]\d{3})+|\d+(?:\.\d+)?)(?![\w.]*\d)")
FACTUAL_INTENTS = {"ask", "discover", "requirements", "summarize", "define", "applicability", "compare", "clause_lookup"}


@dataclass
class SourceView:
    """What the validator knows about one context passage."""

    cid: str
    text: str
    clause_number: str
    standard_number: str | None
    title: str
    url: str | None = None
    page_start: int = 1
    page_end: int = 1


@dataclass
class ValidationResult:
    answer_type: str
    summary: str
    points: list[Point]
    standards: list[dict]
    gaps: list[str]
    follow_ups: list[str]
    clarifying_question: str | None
    drops: list[Drop] = field(default_factory=list)
    original_point_count: int = 0

    @property
    def drop_fraction(self) -> float:
        dropped_points = sum(1 for d in self.drops if d.field == "point")
        return dropped_points / self.original_point_count if self.original_point_count else 0.0

    @property
    def valid_fact_count(self) -> int:
        return sum(1 for p in self.points if p.kind == "source_fact") + sum(1 for s in self.standards if s.get("citations"))


# ---------------------------------------------------------------------------------------------------
# normalisation helpers
# ---------------------------------------------------------------------------------------------------

_QUOTE_MAP = str.maketrans({"“": '"', "”": '"', "„": '"', "‘": "'", "’": "'", "‛": "'", "–": "-", "—": "-", "‐": "-", "‑": "-", " ": " "})


def norm_text(s: str) -> str:
    s = s.translate(_QUOTE_MAP).casefold()
    s = re.sub(r"(\w)-\s+(\w)", r"\1\2", s)  # hyphenation across line breaks
    s = re.sub(r"[|*_`]", " ", s)  # markdown table pipes / emphasis
    s = re.sub(r"\s+", " ", s)
    return s.strip(" .;:")


def norm_number(tok: str) -> str:
    t = tok.replace(" ", "").replace(",", "")
    if "." in t:
        t = t.rstrip("0").rstrip(".") if re.fullmatch(r"\d+\.\d+", t) else t
    return t


def numbers_in(text: str) -> set[str]:
    """Numeric tokens in text, excluding digits that are part of standard numbers."""
    masked = text
    for start, end, _ in sorted(stdnum.find_spans(text), reverse=True):
        masked = masked[:start] + " " * (end - start) + masked[end:]
    masked = CITE_MARKER_RE.sub(" ", masked)
    return {norm_number(m.group(1)) for m in NUMBER_RE.finditer(masked)}


def source_numbers(src: SourceView) -> set[str]:
    nums = numbers_in(src.text)
    nums |= {norm_number(x) for x in re.findall(r"\d+(?:\.\d+)?", src.clause_number)}
    # clause numbers like 4.2.1 also allow their prefixes (4, 4.2) to be mentioned
    parts = src.clause_number.split(".")
    nums |= {".".join(parts[: i + 1]) for i in range(len(parts)) if parts[0].isdigit()}
    if src.standard_number:
        nums |= {norm_number(x) for x in re.findall(r"\d+", src.standard_number)}
    nums |= {str(src.page_start), str(src.page_end)}
    return nums


def standards_in(text: str) -> list[stdnum.StdNumber]:
    return stdnum.find_all(text)


# ---------------------------------------------------------------------------------------------------
# validator
# ---------------------------------------------------------------------------------------------------


class Validator:
    def __init__(self, sources: list[SourceView], question: str, intent: str):
        self.sources = {s.cid: s for s in sources}
        self.question = question
        self.intent = intent
        self.drops: list[Drop] = []
        corpus = " ".join(f"{s.text} {s.standard_number or ''} {s.title}" for s in sources) + " " + question
        self.known_bases = {sn.base for sn in stdnum.find_all(corpus)}
        self.known_urls = {u for s in sources for u in ([s.url] if s.url else []) + URL_RE.findall(s.text)}
        self.all_numbers: set[str] = set()
        for s in sources:
            self.all_numbers |= source_numbers(s)
        self.question_numbers = numbers_in(question)

    def drop(self, field_name: str, text: str, reason: str) -> None:
        self.drops.append(Drop(field=field_name, text=text[:300], reason=reason))

    # -- individual checks -------------------------------------------------------------------------

    def valid_citations(self, cites: list[str], where: str) -> list[str]:
        out = []
        for c in cites or []:
            c = str(c).strip().strip("[]")
            if c in self.sources:
                if c not in out:
                    out.append(c)
            else:
                self.drop(where, c, "citation id not in the provided sources")
        return out

    def quote_ok(self, quote: str, cites: list[str]) -> bool:
        q = norm_text(quote)
        if len(q) < 3:
            return False
        return any(q in norm_text(self.sources[c].text) for c in cites)

    def unknown_standard(self, text: str) -> str | None:
        for sn in standards_in(text):
            if sn.base not in self.known_bases:
                return sn.canonical
        return None

    def unsupported_number(self, text: str, cites: list[str]) -> str | None:
        allowed = set(self.question_numbers)
        pool = cites or list(self.sources)
        for c in pool:
            allowed |= source_numbers(self.sources[c])
        for n in numbers_in(text):
            if n not in allowed:
                return n
        return None

    def unsupported_clause(self, text: str, cites: list[str]) -> str | None:
        pool = cites or list(self.sources)
        for m in CLAUSE_REF_RE.finditer(text):
            ref = (m.group(1) or m.group(2) or m.group(3) or "").strip()
            ref_norm = norm_text(ref)
            ok = False
            for c in pool:
                s = self.sources[c]
                if (
                    norm_text(s.clause_number) == ref_norm
                    or norm_text(s.clause_number).startswith(ref_norm + ".")
                    or ref_norm.startswith(norm_text(s.clause_number) + ".")
                ):
                    ok = True
                elif ref_norm in norm_text(s.text) or ref_norm in norm_text(s.clause_number):
                    ok = True
                if ok:
                    break
            if not ok and m.group(1) and any(norm_text(self.sources[c].clause_number) == ref_norm for c in self.sources):
                ok = True  # exists in context, cited elsewhere
            if not ok:
                return ref
        return None

    def strip_urls(self, text: str, where: str) -> str:
        def repl(m: re.Match[str]) -> str:
            u = m.group(0).rstrip(".,;")
            if u in self.known_urls or any(u.startswith(k) for k in self.known_urls):
                return m.group(0)
            self.drop(where, u, "URL not present in the sources")
            return ""

        return URL_RE.sub(repl, text)

    # -- public ------------------------------------------------------------------------------------

    def validate(self, draft: dict) -> ValidationResult:
        answer_type = str(draft.get("answer_type") or "answer")
        raw_points = draft.get("points") or []
        points: list[Point] = []
        for rp in raw_points if isinstance(raw_points, list) else []:
            if not isinstance(rp, dict):
                continue
            p = self._validate_point(rp)
            if p:
                points.append(p)

        summary = self._validate_summary(str(draft.get("summary") or ""))
        standards = self._validate_standards(draft.get("standards") or [])
        gaps = self._validate_list(draft.get("gaps") or [], "gap")
        follow_ups = self._validate_list(draft.get("follow_ups") or [], "follow_up")
        cq = draft.get("clarifying_question")
        cq = str(cq) if cq else None
        if cq and self.unknown_standard(cq):
            cq = None

        result = ValidationResult(
            answer_type=answer_type,
            summary=summary,
            points=points,
            standards=standards,
            gaps=gaps,
            follow_ups=follow_ups,
            clarifying_question=cq,
            drops=self.drops,
            original_point_count=len(raw_points) if isinstance(raw_points, list) else 0,
        )
        if answer_type in ("clarification", "out_of_scope"):
            return result
        if self.intent in FACTUAL_INTENTS and result.valid_fact_count == 0:
            if answer_type != "insufficient_evidence":
                self.drop("answer", answer_type, "no statement survived validation; converted to insufficient evidence")
            result.answer_type = "insufficient_evidence"
            result.points = []
            result.summary = ""
            result.standards = []
        return result

    def _validate_point(self, rp: dict) -> Point | None:
        kind: Literal["source_fact", "interpretation"] = "interpretation" if rp.get("kind") == "interpretation" else "source_fact"
        text = " ".join(str(rp.get("text") or "").split())
        if not text:
            return None
        cites = self.valid_citations([str(c) for c in rp.get("citations") or []], "citation")
        if kind == "source_fact" and not cites:
            self.drop("point", text, "source fact without a valid citation")
            return None
        quote = rp.get("quote")
        quote = " ".join(str(quote).split()) if quote else None
        if quote and len(norm_text(quote)) < 12:
            quote = None  # a one-word "quote" adds nothing; the point's own citation still stands
        if quote and not self.quote_ok(quote, cites):
            self.drop("quote", quote, "quote not found verbatim in the cited source")
            # the point depended on the quote if the quote text is repeated inside the point
            if norm_text(quote)[:40] in norm_text(text):
                self.drop("point", text, "point relied on a quote that is not in the source")
                return None
            quote = None
        bad_std = self.unknown_standard(text)
        if bad_std:
            self.drop("point", text, f"standard number {bad_std} does not appear in the sources")
            return None
        bad_num = self.unsupported_number(text, cites)
        if bad_num:
            self.drop("point", text, f"number {bad_num} does not appear in the cited source")
            return None
        bad_clause = self.unsupported_clause(text, cites)
        if bad_clause:
            self.drop("point", text, f"reference '{bad_clause}' does not match the cited clauses")
            return None
        text = self.strip_urls(text, "point")
        return Point(kind=kind, text=text, citations=cites, quote=quote)

    def _validate_summary(self, summary: str) -> str:
        if not summary:
            return ""
        sentences = re.split(r"(?<=[.!?\]])\s+(?=[A-Z0-9\"'(])", summary.strip())
        kept = []
        for s in sentences:
            markers = CITE_MARKER_RE.findall(s)
            valid = [m for m in markers if m in self.sources]
            for m in markers:
                if m not in self.sources:
                    self.drop("summary", m, "citation marker not in the provided sources")
                    s = s.replace(f"[{m}]", "")
            bad_std = self.unknown_standard(s)
            if bad_std:
                self.drop("summary", s, f"standard number {bad_std} does not appear in the sources")
                continue
            bad_num = self.unsupported_number(s, valid)
            if bad_num:
                self.drop("summary", s, f"number {bad_num} does not appear in the cited source")
                continue
            if not valid and numbers_in(s) - self.question_numbers:
                self.drop("summary", s, "sentence with numbers but no valid citation")
                continue
            kept.append(self.strip_urls(s.strip(), "summary"))
        return " ".join(k for k in kept if k)

    def _validate_standards(self, items: list) -> list[dict]:
        out = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            number = str(it.get("number") or "").strip()
            sn = stdnum.parse(number)
            if not sn or sn.base not in self.known_bases:
                self.drop("standard", number or str(it)[:80], "standard not present in the sources")
                continue
            cites = self.valid_citations([str(c) for c in it.get("citations") or []], "citation")
            if not cites:
                self.drop("standard", number, "listed standard without a valid citation")
                continue
            why = " ".join(str(it.get("why") or "").split())
            if why and (self.unknown_standard(why) or self.unsupported_number(why, cites)):
                self.drop("standard_why", why, "reason contains an unsupported number or standard")
                why = ""
            out.append({"number": sn.canonical, "why": why, "citations": cites})
        return out

    def _validate_list(self, items: list, where: str) -> list[str]:
        out = []
        for it in items if isinstance(items, list) else []:
            t = " ".join(str(it).split())
            if not t:
                continue
            if self.unknown_standard(t):
                self.drop(where, t, "mentions a standard not present in the sources")
                continue
            out.append(self.strip_urls(t, where))
        return out[:6]
