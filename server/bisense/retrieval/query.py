"""Query understanding (deterministic first; at most one LLM call, made by the caller).

Steps:
  1. detect language by script,
  2. extract standard numbers and clause references (they become HARD filters),
  3. merge the client context (last questions, focused standards, open standard) -- an explicit
     identifier in the query always overrides context,
  4. classify intent with keyword rules (English, Hindi, Kannada),
  5. (optional, done by the answer pipeline) LLM rewrite for non-English queries and follow-ups,
  6. glossary expansion for the lexical query.

The server is stateless: context arrives with each request and contains only previous *questions*
and *standard ids* -- never previous AI answers.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field

from bisense import stdnum
from bisense.i18n.glossary import expand_lexical, keyword_translate
from bisense.i18n.languages import detect_language

INTENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    (
        "out_of_scope",
        re.compile(r"^\s*(hi|hello|hey|namaste|thanks|thank you|how are you|who are you|good (morning|evening)|tell me a joke|what'?s up)\W*$", re.I),
    ),
    ("compare", re.compile(r"\b(compare|comparison|vs\.?|versus|difference|differences|differ)\b|तुलना|अंतर|ಹೋಲಿಕೆ|ವ್ಯತ್ಯಾಸ", re.I)),
    ("clause_lookup", re.compile(r"\b(clause|cl\.|section|annex|annexure)\s*[A-Z]?-?\d+(\.\d+)*|खंड\s*\d|ಖಂಡ\s*\d", re.I)),
    (
        "applicability",
        re.compile(
            r"\b(my product|my products|my business|my company|my factory|i make|i manufacture|we make|we manufacture|we produce|i produce|i sell|we sell|apply to my|for my)\b|मेरे उत्पाद|मेरा उत्पाद|ನನ್ನ ಉತ್ಪನ್ನ",
            re.I,
        ),
    ),
    (
        "summarize",
        re.compile(
            r"\b(explain|summari[sz]e|summary|simple language|simple terms|in simple|overview of|plain language|eli5)\b|सरल|समझा|सारांश|ವಿವರಿಸಿ|ಸರಳ|ಸಾರಾಂಶ", re.I
        ),
    ),
    (
        "requirements",
        re.compile(
            r"\b(requirements?|tests?|testing|test methods?|checklist|what must|must meet|limits?|specifications? for|criteria)\b|परीक्षण|आवश्यकता|ಪರೀಕ್ಷೆ|ಅವಶ್ಯಕತೆ|ಅಗತ್ಯ",
            re.I,
        ),
    ),
    (
        "discover",
        re.compile(
            r"\b(which (bis |indian )?standards?|what (bis |indian )?standards?|applicable|apply to|applies to|relevant standards?|standards? (for|on|covering)|is there a standard)\b|लागू|कौन.?से.{0,10}मानक|ಅನ್ವಯ|ಯಾವ.{0,20}ಮಾನದಂಡ",
            re.I,
        ),
    ),
    ("define", re.compile(r"^\s*(what is|what's|what are|meaning of|define|definition of|what does .* mean)\b|क्या है|का अर्थ|ಎಂದರೇನು|ಅರ್ಥ", re.I)),
]

CLAUSE_REF_RE = re.compile(
    r"\b(?:clause|cl\.|section|sec\.)\s*(?P<num>[A-H]-\d+(?:\.\d+)*|\d+(?:\.\d+)*)|\b(?P<table>Table\s+\d+)|\b(?P<annex>Annex(?:ure)?\s*-?\s*[A-Z]|Annex(?:ure)?\s*-?\s*[IVX]+)",
    re.I,
)
ANAPHORA_RE = re.compile(r"\b(this|that|these|those|it|its|they|them|the standard|the same|above|both)\b|यह|इस|इसके|ये|इन|ಈ|ಅದರ|ಇದು|ಇವು", re.I)
STOPWORDS = set(
    "a an the of for to in on at by with from and or is are was were be been being what which who whom whose how why when where "
    "do does did can could should would will shall may might must i me my we our you your it its this that these those there "
    "about as into than then so such any all some no not only also please tell give list show explain simple language "
    "bis standard standards indian apply applies applicable relevant".split()
)


@dataclass
class ClientContext:
    recent_questions: list[str] = field(default_factory=list)
    focus_slugs: list[str] = field(default_factory=list)
    open_slug: str | None = None


@dataclass
class ScopeItem:
    id: int
    slug: str
    number: str | None
    title: str
    kind: str


@dataclass
class QueryPlan:
    raw: str
    lang: str
    intent: str
    english_query: str
    keywords: list[str]
    lexical_terms: list[str]
    content_terms: list[str]  # the user's own content words (no glossary expansion)
    explicit_numbers: list[str]
    explicit_ids: list[int]
    clause_refs: list[str]
    scope: list[ScopeItem]
    scope_source: str  # "explicit" | "context" | "none"
    is_follow_up: bool
    rewritten: bool = False
    notes: list[str] = field(default_factory=list)
    query_lang: str = "en"  # language the question was written/spoken in (lang = the selected answer language)

    @property
    def scope_ids(self) -> list[int]:
        return [s.id for s in self.scope]


def classify_intent(text: str) -> str:
    for name, pat in INTENT_RULES:
        if pat.search(text):
            if name == "define" and re.search(r"\b(requirements?|tests?|testing|process|procedure|fee|steps)\b", text, re.I):
                continue
            return name
    return "ask"


def find_standards(conn: sqlite3.Connection, numbers: list[stdnum.StdNumber]) -> list[ScopeItem]:
    out: list[ScopeItem] = []
    for sn in numbers:
        rows = conn.execute(
            "SELECT id, slug, number_canonical, title, kind, year FROM standards WHERE base_number = ? ORDER BY (kind = 'catalogue'), year DESC",
            (sn.base,),
        ).fetchall()
        if sn.year:
            exact = [r for r in rows if r["year"] == sn.year]
            rows = exact or rows
        if rows:
            r = rows[0]
            out.append(ScopeItem(r["id"], r["slug"], r["number_canonical"], r["title"], r["kind"]))
    return out


def scope_from_slugs(conn: sqlite3.Connection, slugs: list[str]) -> list[ScopeItem]:
    out = []
    for slug in slugs:
        r = conn.execute("SELECT id, slug, number_canonical, title, kind FROM standards WHERE slug = ?", (slug,)).fetchone()
        if r:
            out.append(ScopeItem(r["id"], r["slug"], r["number_canonical"], r["title"], r["kind"]))
    return out


def tokenize_terms(text: str) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z0-9\-]*|\d+(?:\.\d+)?", text)
    return [w for w in words if w.lower() not in STOPWORDS and len(w) > 1]


def understand(conn: sqlite3.Connection, query: str, ui_lang: str = "en", context: ClientContext | None = None) -> QueryPlan:
    context = context or ClientContext()
    query = " ".join(query.split())
    lang = detect_language(query, fallback="en")
    intent = classify_intent(query)

    numbers = stdnum.find_all(query)
    explicit = find_standards(conn, numbers)
    clause_refs = []
    for m in CLAUSE_REF_RE.finditer(query):
        clause_refs.append(m.group("num") or m.group("table") or m.group("annex"))

    # Context: applies when the query has no explicit identifier and reads like a follow-up.
    words = len(query.split())
    is_follow_up = bool(context.recent_questions) and (
        bool(ANAPHORA_RE.search(query)) or words <= 6 or intent in ("requirements", "summarize", "compare", "clause_lookup")
    )
    scope: list[ScopeItem] = []
    scope_source = "none"
    if explicit:
        scope, scope_source = explicit, "explicit"
    else:
        wants_context = is_follow_up or bool(ANAPHORA_RE.search(query)) or intent in ("summarize", "clause_lookup")
        if wants_context:
            slugs = ([context.open_slug] if context.open_slug else []) + [s for s in context.focus_slugs if s != context.open_slug]
            scope = scope_from_slugs(conn, slugs[:4])
            if scope:
                scope_source = "context"

    english = query
    keywords: list[str] = []
    notes: list[str] = []
    if lang != "en":
        keywords = keyword_translate(query, lang)
        english = " ".join(keywords) if keywords else query
        notes.append("offline keyword translation")

    content = tokenize_terms(english)
    lexical = content + expand_lexical(english)
    return QueryPlan(
        raw=query,
        # One language context: answers are always in the language the user selected. The question may be
        # in another language (query_lang); the UI then says so and offers to switch.
        lang=ui_lang if ui_lang in ("en", "hi", "kn") else "en",
        query_lang=lang,
        intent=intent,
        english_query=english,
        keywords=keywords,
        lexical_terms=lexical,
        content_terms=content,
        explicit_numbers=[s.canonical for s in numbers],
        explicit_ids=[s.id for s in explicit],
        clause_refs=clause_refs,
        scope=scope,
        scope_source=scope_source,
        is_follow_up=is_follow_up,
        notes=notes,
    )


def apply_rewrite(plan: QueryPlan, english_query: str, keywords: list[str], intent: str | None) -> None:
    """Update a plan with the LLM rewrite result (English pivot for non-English queries/follow-ups)."""
    plan.english_query = english_query.strip() or plan.english_query
    plan.keywords = keywords or plan.keywords
    plan.content_terms = tokenize_terms(plan.english_query)
    plan.lexical_terms = plan.content_terms + [k for k in keywords if k] + expand_lexical(plan.english_query)
    # Re-classify with the same deterministic rules on the English text (the model's own label is
    # only a hint and is not trusted).
    if plan.intent == "ask":
        plan.intent = classify_intent(plan.english_query)
    plan.rewritten = True
    plan.notes = [n for n in plan.notes if n != "offline keyword translation"]
