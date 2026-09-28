"""Pydantic models: the single source of truth for the HTTP API contract.

The frontend never hand-writes API types: `npm run gen:types` generates web/src/api/types.gen.ts
from FastAPI's OpenAPI schema, which is built from these classes.

Input models enforce limits (query length, languages, slug formats, context size) so bad input is
rejected with a 422 before it reaches any pipeline code.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel as _PydanticBase
from pydantic import ConfigDict, Field


class BaseModel(_PydanticBase):
    # Response fields that have defaults are always present in JSON; mark them required in the
    # serialization schema so the generated TypeScript types are not needlessly optional.
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


Lang = Literal["en", "hi", "kn"]
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]{0,120}$"
Slug = Field(pattern=SLUG_PATTERN)

StandardKind = Literal["standard", "guidance", "order", "catalogue"]
EvidenceStrength = Literal["strong", "moderate", "limited", "none"]
AnswerMode = Literal["live", "cached", "extractive", "none"]
AnswerType = Literal[
    "answer",
    "standards_list",
    "requirements",
    "comparison",
    "summary",
    "definition",
    "clarification",
    "insufficient_evidence",
    "out_of_scope",
]
Modality = Literal["shall", "shall_not", "should", "should_not", "may", "must"]


# ---------------------------------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------------------------------


class AskContext(BaseModel):
    """What the client remembers about the conversation. Only questions and standard ids -- never answers."""

    recent_questions: list[str] = Field(default_factory=list, max_length=2)
    focus_slugs: list[str] = Field(default_factory=list, max_length=6)
    open_slug: str | None = Field(default=None, pattern=SLUG_PATTERN)

    def model_post_init(self, __context: object) -> None:
        self.recent_questions = [q[:1000] for q in self.recent_questions]
        self.focus_slugs = [s for s in self.focus_slugs if len(s) <= 120][:6]


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    lang: Lang = "en"
    context: AskContext | None = None


class SearchFilters(BaseModel):
    kinds: list[StandardKind] = Field(default_factory=list, max_length=4)
    slugs: list[str] = Field(default_factory=list, max_length=10)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    lang: Lang = "en"
    filters: SearchFilters | None = None
    context: AskContext | None = None


class CompareRequest(BaseModel):
    a: str = Field(pattern=SLUG_PATTERN)
    b: str = Field(pattern=SLUG_PATTERN)
    lang: Lang = "en"


class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    lang: Lang = "en"


class STTOut(BaseModel):
    text: str  # empty when no speech was heard
    no_speech: bool
    language: str | None  # language the provider detected/used (ISO-639-1)
    requested_language: str | None
    duration_s: float | None
    provider: str
    model: str
    ms: float


class VoiceStatus(BaseModel):
    stt_available: bool
    stt_provider: str | None
    stt_model: str | None
    stt_languages: list[str]
    tts_available: bool
    tts_provider: str | None
    tts_languages: list[str]
    tts_problem: str | None = None  # last provider error code, e.g. "tts_terms_required"
    max_seconds: int
    max_bytes: int


# ---------------------------------------------------------------------------------------------------
# Evidence and answers
# ---------------------------------------------------------------------------------------------------


class Scores(BaseModel):
    lexical_rank: int | None = None
    vector: float | None = None
    fused: float | None = None
    rerank: float | None = None
    boosts: dict[str, float] = Field(default_factory=dict)


class Citation(BaseModel):
    id: str  # "C1"
    n: int  # display number [1]
    slug: str
    standard_number: str | None
    standard_title: str
    standard_kind: StandardKind
    clause_number: str
    clause_heading: str
    clause_kind: str
    clause_path: str
    page_start: int
    page_end: int
    snippet: str
    scores: Scores
    synthetic: bool
    tier: str
    doc_type: str
    url: str | None
    has_page_image: bool
    # Provenance, for human-readable citations and source badges.
    text_scope: str = "full_text"  # full_text | product_manual | page | metadata_only | sample
    document_title: str | None = None
    source_org: str | None = None
    source_type: str | None = None  # official_document | official_website | government_notification | sample
    source_label: str = ""  # "Bureau of Indian Standards · IS 4151:2015 product manual · Section 2.1 · Page 7"


class Point(BaseModel):
    kind: Literal["source_fact", "interpretation"]
    text: str
    citations: list[str] = Field(default_factory=list)
    quote: str | None = None


class StandardRef(BaseModel):
    slug: str
    number: str | None
    title: str
    kind: StandardKind
    why: str | None = None
    citations: list[str] = Field(default_factory=list)
    compulsory: str = "unknown"
    compulsory_source: str | None = None
    catalogue_only: bool = False
    synthetic: bool = False
    via: str = "full_text"
    matched_row: str | None = None


class Drop(BaseModel):
    field: str
    text: str
    reason: str


class OriginalAnswer(BaseModel):
    summary: str
    points: list[Point]
    gaps: list[str]
    follow_ups: list[str]


class CoverageNote(BaseModel):
    slug: str
    number: str | None
    title: str
    text_scope: str  # metadata_only | product_manual


class Answer(BaseModel):
    answer_type: AnswerType
    summary: str = ""
    points: list[Point] = Field(default_factory=list)
    standards: list[StandardRef] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    clarifying_question: str | None = None
    clarifying_options: list[str] = Field(default_factory=list)
    follow_ups: list[str] = Field(default_factory=list)
    evidence_strength: EvidenceStrength = "none"
    strength_basis: str = ""
    mode: AnswerMode = "live"
    provider: str | None = None
    generated_at: str | None = None
    dropped_count: int = 0
    drops: list[Drop] = Field(default_factory=list)
    lang: Lang = "en"
    translated: bool = False
    translation_failed: bool = False
    original: OriginalAnswer | None = None
    notice: str | None = None  # message key, e.g. "notice.llm_unavailable"
    searched_summary: str = ""  # "Searched 34 sources (4 full-text standards ...)"
    library_note: str = ""
    synthetic_used: bool = False
    # Standards named in the question whose full text BISense does not hold.
    coverage: list[CoverageNote] = Field(default_factory=list)


class ScopeItemOut(BaseModel):
    slug: str
    number: str | None
    title: str
    kind: StandardKind


class QueryInfo(BaseModel):
    interpreted_query: str
    intent: str
    lang: Lang  # answer language (the selected language)
    query_lang: Lang = "en"  # language the question was asked in
    resolved_scope: list[ScopeItemOut]
    scope_source: str
    rewritten: bool
    notes: list[str] = Field(default_factory=list)


class SearchResponse(BaseModel):
    query: QueryInfo
    citations: list[Citation]
    standards: list[StandardRef]
    timings: dict[str, float]
    total_candidates: int


class Timings(BaseModel):
    stages: dict[str, float]
    total_ms: float


class StageEvent(BaseModel):
    stage: Literal["understanding", "searching", "drafting", "verifying", "translating"]
    detail: dict[str, int | str] = Field(default_factory=dict)


class EvidenceEvent(BaseModel):
    citations: list[Citation]
    standards: list[StandardRef]


class ErrorEvent(BaseModel):
    code: str
    message_key: str


class DoneEvent(BaseModel):
    request_id: str
    timings: Timings


class AskTrace(BaseModel):
    """Everything the Retrieval details drawer shows (also served by /api/debug/trace when DEBUG=true)."""

    request_id: str
    query: QueryInfo
    candidates: list[Citation]
    cited_ids: list[str]
    drops: list[Drop]
    mode: AnswerMode
    provider: str | None
    timings: Timings
    top_rerank: float | None
    gate_threshold: float
    tokens: dict[str, int] = Field(default_factory=dict)


# ---------------------------------------------------------------------------------------------------
# Library and standards
# ---------------------------------------------------------------------------------------------------


class CategoryCount(BaseModel):
    category: str
    count: int
    kind: StandardKind


class LibraryOut(BaseModel):
    coverage: str  # "BISense currently covers N standards (full text available for M; ...)"
    dataset_mode: str
    index_version: str
    built_at: str
    counts: dict[str, int]
    categories: list[CategoryCount]
    languages: list[Lang]
    sources: list[dict[str, str | None]]


class StandardSummary(BaseModel):
    slug: str
    kind: StandardKind
    number: str | None
    title: str
    year: int | None
    category: str | None
    status: str
    compulsory: str
    catalogue_only: bool
    synthetic: bool
    needs_review: bool
    tier: str
    text_scope: str = "full_text"  # full_text | product_manual | page | metadata_only | sample
    source_type: str | None = None
    clause_count: int = 0
    requirement_count: int = 0


class StandardListOut(BaseModel):
    items: list[StandardSummary]
    total: int
    page: int
    page_size: int
    facets: dict[str, list[CategoryCount]]


class SuggestItem(BaseModel):
    slug: str
    number: str | None
    title: str
    kind: StandardKind


class ClauseNode(BaseModel):
    id: int
    number: str
    heading: str
    kind: str
    level: int
    page_start: int
    page_end: int
    children: list[ClauseNode] = Field(default_factory=list)


class ClauseOut(BaseModel):
    id: int
    number: str
    heading: str
    kind: str
    path: str
    level: int
    page_start: int
    page_end: int
    text: str
    is_table: bool
    children: list[ClauseNode] = Field(default_factory=list)


class AmendmentOut(BaseModel):
    label: str
    date: str | None
    text_excerpt: str | None
    page: int | None


class ReferenceOut(BaseModel):
    number: str
    slug: str | None
    title: str | None
    clause_number: str | None


class RelatedOut(BaseModel):
    slug: str
    number: str | None
    title: str
    kind: StandardKind
    similarity: float


class Provenance(BaseModel):
    tier: str
    doc_type: str | None
    file_name: str | None
    source_url: str | None
    obtained_on: str | None
    pages: int | None
    language: str | None
    warnings: list[str] = Field(default_factory=list)
    document_title: str | None = None
    source_org: str | None = None
    source_type: str | None = None
    verification_status: str = "unverified"  # verified | unverified | sample
    access_note: str | None = None
    text_scope: str = "full_text"


class CompulsoryEvidence(BaseModel):
    status: str  # yes | denotified | no | unknown
    source: str | None
    slug: str | None
    clause_number: str | None


class StandardDetail(BaseModel):
    summary: StandardSummary
    revision_label: str | None
    status_verified_on: str | None
    committee: str | None
    ics: str | None
    industries: list[str]
    products: list[str]
    provenance: Provenance
    compulsory: CompulsoryEvidence
    scope_text: str | None
    scope_clause: str | None
    clauses: list[ClauseNode]
    amendments: list[AmendmentOut]
    references: list[ReferenceOut]
    referenced_by: list[ReferenceOut]
    related: list[RelatedOut]
    terms: list[dict[str, str | int]]
    counts: dict[str, int]
    product_mentions: list[dict[str, str | None]]


class RequirementOut(BaseModel):
    id: int
    clause_number: str
    clause_heading: str
    clause_kind: str
    modality: Modality
    text: str
    page: int
    topic: str


class RequirementsOut(BaseModel):
    slug: str
    number: str | None
    title: str
    synthetic: bool
    items: list[RequirementOut]
    counts: dict[str, int]


class SummaryOut(BaseModel):
    slug: str
    answer: Answer
    citations: list[Citation]


class CompareCell(BaseModel):
    text: str | None
    citations: list[str] = Field(default_factory=list)
    found: bool


class CompareRow(BaseModel):
    aspect: str
    a: CompareCell
    b: CompareCell


class NumericRow(BaseModel):
    parameter: str
    unit: str | None
    a_value: str | None
    b_value: str | None
    a_citation: str | None
    b_citation: str | None


class CompareResponse(BaseModel):
    a: StandardSummary
    b: StandardSummary
    rows: list[CompareRow]
    numeric: list[NumericRow]
    key_differences: list[Point]
    citations: list[Citation]
    mode: AnswerMode
    notice: str | None = None
    dropped_count: int = 0


class HealthOut(BaseModel):
    status: Literal["ok", "degraded", "no_index"]
    dataset_mode: str
    index_version: str | None
    counts: dict[str, int]
    llm: dict[str, bool | str | None]
    models_loaded: bool
    demo_mode: bool
    version: str
    features: dict[str, bool]
    voice: VoiceStatus | None = None
    translation: dict[str, bool | str | None] = Field(default_factory=dict)
    languages: dict[str, dict[str, bool]] = Field(default_factory=dict)
