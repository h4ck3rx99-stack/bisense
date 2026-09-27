"""The /api/ask pipeline, written as a generator of (event, payload) pairs for Server-Sent Events.

    understand -> (rewrite) -> retrieve -> EVIDENCE EVENT -> gate -> generate -> validate
    -> (retry once | extractive fallback) -> translate -> evidence strength -> cache -> ANSWER EVENT

Evidence is streamed before the answer so the user sees sources first. Raw LLM tokens are never
streamed, because the answer must be validated as a whole before anyone sees it.

Runtime order when the LLM is unavailable (no key, timeout, quota, validation failing twice):
  cached answer for the same question (if any) -> extractive answer (verbatim passages).
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Generator, Iterator
from datetime import UTC, datetime
from typing import get_args

from pydantic import BaseModel

from bisense.answer import cache
from bisense.answer.confidence import evidence_strength
from bisense.answer.extractive import extractive_points
from bisense.answer.generate import build_messages, correction_message, generate, rewrite_query
from bisense.answer.llm_client import LLMUnavailable, get_llm
from bisense.answer.present import (
    query_info,
    searched_summary,
    standard_ref_for_number,
    summary_context,
    to_citation,
    to_standard_ref,
)
from bisense.answer.validate import SourceView, Validator
from bisense.config import get_settings
from bisense.i18n.protect import protect, restore
from bisense.i18n.translate import translate_strings
from bisense.models import (
    Answer,
    AnswerType,
    AskRequest,
    AskTrace,
    Citation,
    DoneEvent,
    EvidenceEvent,
    OriginalAnswer,
    Point,
    StageEvent,
    StandardRef,
    Timings,
)
from bisense.retrieval.index import db_conn, get_index
from bisense.retrieval.query import ClientContext, QueryPlan, apply_rewrite, understand
from bisense.retrieval.search import SearchResult, load_candidates, product_terms, search

Event = tuple[str, BaseModel | dict]
ANSWER_TYPES = set(get_args(AnswerType))

TRACES: dict[str, AskTrace] = {}  # last N traces for the debug endpoint / drawer
_TRACE_MAX = 50


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _sources(res: SearchResult) -> list[SourceView]:
    return [
        SourceView(
            cid=c.citation_id or "",
            text=c.text,
            clause_number=c.clause_number,
            standard_number=c.number,
            title=c.title,
            url=c.source_url,
            page_start=c.page_start,
            page_end=c.page_end,
        )
        for c in res.context
    ]


def run_ask(req: AskRequest) -> Iterator[Event]:
    settings = get_settings()
    request_id = uuid.uuid4().hex[:12]
    t_start = time.perf_counter()
    stages: dict[str, float] = {}

    def lap(name: str, t0: float) -> None:
        stages[name] = round((time.perf_counter() - t0) * 1000, 1)

    yield "stage", StageEvent(stage="understanding")
    t0 = time.perf_counter()
    conn = db_conn()
    try:
        index = get_index()
        ctx = req.context
        client_ctx = ClientContext(
            recent_questions=list(ctx.recent_questions) if ctx else [],
            focus_slugs=list(ctx.focus_slugs) if ctx else [],
            open_slug=ctx.open_slug if ctx else None,
        )
        llm = get_llm()
        plan = prepare_plan(conn, req.query, req.lang, client_ctx, llm)
        tokens = {"prompt": 0, "completion": 0}
        lap("understand", t0)
        yield "query", query_info(plan)

        # ---------------------------------------------------------------------------------------
        # Retrieval
        # ---------------------------------------------------------------------------------------
        yield "stage", StageEvent(stage="searching", detail={"sources": sum(index.counts.get(k, 0) for k in ("standards_full_text", "guidance", "catalogue"))})
        t0 = time.perf_counter()
        res = retrieve(conn, plan)
        lap("retrieve", t0)
        stages.update({f"retrieve.{k}": v for k, v in res.timings.items()})
        citations = [to_citation(c, i) for i, c in enumerate(res.context, start=1)]
        std_refs = [to_standard_ref(h) for h in res.standards[:8]]
        yield "evidence", EvidenceEvent(citations=citations, standards=std_refs)

        # _decide is a generator: stage events reach the browser while the LLM is working.
        decision = yield from _decide(conn, req, plan, res, citations, std_refs, llm, tokens, stages, index.version)
        final = decision.answer
        final.searched_summary = searched_summary(index.counts)
        final.synthetic_used = any(c.synthetic for c in res.context)

        total = round((time.perf_counter() - t_start) * 1000, 1)
        trace = AskTrace(
            request_id=request_id,
            query=query_info(plan),
            candidates=[to_citation(c, i) for i, c in enumerate(res.candidates[:20], start=1)],
            cited_ids=sorted({cid for p in final.points for cid in p.citations} | {cid for s in final.standards for cid in s.citations}),
            drops=final.drops,
            mode=final.mode,
            provider=final.provider,
            timings=Timings(stages=stages, total_ms=total),
            top_rerank=res.top_rerank,
            gate_threshold=settings.gate_rerank_min,
            tokens=tokens,
        )
        TRACES[request_id] = trace
        while len(TRACES) > _TRACE_MAX:
            TRACES.pop(next(iter(TRACES)))
        yield "answer", final
        yield "trace", trace
        yield "done", DoneEvent(request_id=request_id, timings=Timings(stages=stages, total_ms=total))
    finally:
        conn.close()


def prepare_plan(conn, query: str, ui_lang: str, client_ctx: ClientContext, llm) -> QueryPlan:
    """Understand the query; for Hindi/Kannada, one LLM call rewrites it to English (identifiers protected).
    Without an LLM the offline glossary keyword translation from `understand` is used."""
    plan = understand(conn, query, ui_lang=ui_lang, context=client_ctx)
    if plan.lang != "en" and llm is not None and plan.intent != "out_of_scope":
        try:
            masked, originals = protect(plan.raw)
            rw = rewrite_query(llm, masked, client_ctx.recent_questions)
            english = str(rw.get("english_query") or "")
            if "⟦" in english:
                english = restore(english, originals)
            kws = [str(k) for k in (rw.get("keywords") or []) if isinstance(k, str | int)][:8]
            apply_rewrite(plan, english, kws, rw.get("intent") if isinstance(rw.get("intent"), str) else None)
        except (LLMUnavailable, ValueError):
            plan.notes.append("rewrite unavailable; used offline keyword translation")
    return plan


def retrieve(conn, plan: QueryPlan) -> SearchResult:
    """Retrieval used by /api/ask (and the evaluation, so it measures exactly this path)."""
    if plan.intent == "summarize" and len(plan.scope) == 1 and plan.scope[0].kind != "catalogue":
        return _summary_search(conn, plan)
    if plan.scope_source == "context" and plan.scope:
        # Rerank follow-ups with the scoped standard's title so pronouns have something to refer to.
        titles = "; ".join(sc.title for sc in plan.scope)
        original = plan.english_query
        plan.english_query = f"{original} ({titles})"
        try:
            return search(conn, plan)
        finally:
            plan.english_query = original
    return search(conn, plan)


class _Decision:
    def __init__(self) -> None:
        self.events: list[Event] = []
        self.answer: Answer = Answer(answer_type="insufficient_evidence")


def _summary_search(conn, plan: QueryPlan) -> SearchResult:
    """Whole-document context for 'explain this standard' (scope + key sections), not query similarity."""
    ids = summary_context(conn, plan.scope[0].id)
    cands = load_candidates(conn, ids)
    ordered = [cands[i] for i in ids if i in cands]
    for i, c in enumerate(ordered, start=1):
        c.citation_id = f"C{i}"
    from bisense.retrieval.search import group_standards

    return SearchResult(
        plan=plan, candidates=ordered, context=ordered, standards=group_standards(conn, ordered, plan), timings={}, top_rerank=None, reranked=False
    )


def _gate_fails(res: SearchResult, plan: QueryPlan, llm_available: bool = True) -> bool:
    s = get_settings()
    # Without an LLM there is no model to say "not in the sources", so the gate is stricter.
    threshold = s.gate_rerank_min if llm_available else s.gate_rerank_min_no_llm
    if not res.context:
        return True
    # A named standard, or a follow-up about the standard in context: answer from that scope
    # (the reranker scores pronoun questions like "what must be marked on it?" poorly).
    if plan.scope_source in ("explicit", "context") or plan.intent == "summarize":
        return False
    if res.reranked and res.top_rerank is not None and res.top_rerank < threshold:
        return True
    return False


def _needs_product(plan: QueryPlan) -> bool:
    if plan.intent != "applicability" or plan.scope:
        return False
    orig, _ = product_terms(plan)
    return not orig


def _decide(
    conn,
    req: AskRequest,
    plan: QueryPlan,
    res: SearchResult,
    citations: list[Citation],
    std_refs: list[StandardRef],
    llm,
    tokens: dict,
    stages: dict,
    index_version: str,
) -> Generator[Event, None, _Decision]:
    d = _Decision()
    settings = get_settings()

    if plan.intent == "out_of_scope":
        d.answer = Answer(answer_type="out_of_scope", mode="none", lang=plan.lang, notice="notice.out_of_scope")  # type: ignore[arg-type]
        return d

    if _needs_product(plan):
        cats = [
            r["category"]
            for r in conn.execute(
                "SELECT category, COUNT(*) n FROM standards WHERE kind IN ('standard','catalogue') AND category IS NOT NULL GROUP BY category ORDER BY (kind='standard') DESC, n DESC LIMIT 6"
            )
        ]
        d.answer = Answer(
            answer_type="clarification",
            mode="none",
            lang=plan.lang,  # type: ignore[arg-type]
            clarifying_question="clarify.product",
            clarifying_options=["packaged drinking water", "two-wheeler helmet", "TMT steel bars", "electric iron", "gold jewellery"] + cats[:3],
        )
        return d

    if _gate_fails(res, plan, llm_available=llm is not None):
        d.answer = Answer(
            answer_type="insufficient_evidence",
            mode="none",
            lang=plan.lang,
            notice="notice.insufficient",
            evidence_strength="none",
            strength_basis="No indexed passage was relevant enough to answer.",
        )  # type: ignore[arg-type]
        return d

    key = cache.cache_key("ask", plan.english_query if plan.rewritten else plan.raw, plan.lang, [s.slug for s in plan.scope], plan.intent, index_version)
    cached = cache.get_cached(key)
    if cached and not settings.demo_mode:
        payload, source, created = cached
        a = Answer.model_validate(payload)
        a.mode = "cached"
        a.generated_at = created
        d.answer = a
        return d

    live: Answer | None = None
    if llm is not None:
        yield ("stage", StageEvent(stage="drafting", detail={"passages": len(res.context)}))
        t0 = time.perf_counter()
        live = _live_answer(llm, plan, res, citations, std_refs, tokens, d, conn)
        yield from d.events
        d.events.clear()
        stages["llm_and_validate"] = round((time.perf_counter() - t0) * 1000, 1)
        # Small models sometimes decline even when the best passage is a near-verbatim answer. With
        # evidence this strong, show the passages verbatim instead of a refusal (labelled as such).
        if (
            live is not None
            and live.answer_type == "insufficient_evidence"
            and res.top_rerank is not None
            and res.top_rerank >= settings.llm_refusal_override_min
        ):
            d.answer = _extractive(plan, res, std_refs, llm_configured=True)
            d.answer.notice = "notice.extractive_llm_declined"
            return d

    if live is not None:
        if plan.lang != "en" and live.answer_type not in ("insufficient_evidence",):
            yield ("stage", StageEvent(stage="translating"))
            t0 = time.perf_counter()
            live = _translate(llm, live, plan.lang)
            stages["translate"] = round((time.perf_counter() - t0) * 1000, 1)
        live.lang = plan.lang  # type: ignore[assignment]
        live.generated_at = _now()
        cache.put_cached(key, live.model_dump(), plan.lang, index_version, source="live")
        d.answer = live
        return d

    # LLM unavailable or failed: cached answer from the same pipeline, else extractive.
    if cached:
        payload, source, created = cached
        a = Answer.model_validate(payload)
        a.mode = "cached"
        a.generated_at = created
        a.notice = "notice.cached_used"
        d.answer = a
        return d
    d.answer = _extractive(plan, res, std_refs, llm_configured=llm is not None)
    return d


def _live_answer(
    llm, plan: QueryPlan, res: SearchResult, citations: list[Citation], std_refs: list[StandardRef], tokens: dict, d: _Decision, conn
) -> Answer | None:
    messages = build_messages(plan, res.context)
    sources = _sources(res)
    question = plan.raw if plan.lang == "en" else plan.english_query
    vr = None
    for attempt in range(2):
        try:
            draft, llm_res = generate(llm, messages)
            tokens["prompt"] += llm_res.prompt_tokens
            tokens["completion"] += llm_res.completion_tokens
            provider = llm_res.provider
        except LLMUnavailable:
            return None
        except ValueError:
            if attempt == 0:
                messages = messages + [{"role": "user", "content": "Your output was not valid JSON. Output only the JSON object."}]
                continue
            return None
        if attempt == 0:
            d.events.append(("stage", StageEvent(stage="verifying")))
        vr = Validator(sources, question, plan.intent).validate(draft)
        if vr.drop_fraction <= 0.3 or attempt == 1:
            if vr.drop_fraction > 0.3 and attempt == 1:
                return None  # validation failed twice -> extractive fallback
            break
        messages = messages + [{"role": "assistant", "content": str(draft)[:4000]}, correction_message(vr.drops)]
    if vr is None:
        return None

    strength, basis = evidence_strength(
        cited_count=len({c for p in vr.points for c in p.citations} | {c for s in vr.standards for c in s["citations"]}),
        top_score=res.top_rerank,
        survived_fraction=1 - vr.drop_fraction if vr.original_point_count else 1.0,
        reranked=res.reranked,
    )
    standards = _merge_standards(conn, vr.standards, std_refs)
    answer_type = vr.answer_type if vr.answer_type in ANSWER_TYPES else "answer"
    if answer_type == "insufficient_evidence":
        strength, basis = "none", "The sources retrieved do not answer this question."
    return Answer(
        answer_type=answer_type,  # type: ignore[arg-type]
        summary=vr.summary,
        points=vr.points,
        standards=standards,
        gaps=vr.gaps,
        clarifying_question=vr.clarifying_question,
        follow_ups=vr.follow_ups,
        evidence_strength=strength,  # type: ignore[arg-type]
        strength_basis=basis,
        mode="live",
        provider=provider,
        dropped_count=len([x for x in vr.drops if x.field in ("point", "summary", "standard", "quote")]),
        drops=vr.drops,
        notice="notice.insufficient" if answer_type == "insufficient_evidence" else None,
    )


def _merge_standards(conn, validated: list[dict], retrieved: list[StandardRef]) -> list[StandardRef]:
    """LLM-listed standards (validated, with 'why') first, then retrieval-grouped standards."""
    out: list[StandardRef] = []
    seen: set[str] = set()
    by_number = {r.number: r for r in retrieved if r.number}
    for v in validated:
        ref = by_number.get(v["number"]) or standard_ref_for_number(conn, v["number"])
        if not ref:
            continue
        ref = ref.model_copy(update={"why": v.get("why") or ref.why, "citations": v["citations"]})
        if ref.slug not in seen:
            out.append(ref)
            seen.add(ref.slug)
    for r in retrieved:
        if r.slug not in seen and r.kind in ("standard", "catalogue"):
            out.append(r)
            seen.add(r.slug)
    return out[:8]


def _extractive(plan: QueryPlan, res: SearchResult, std_refs: list[StandardRef], llm_configured: bool) -> Answer:
    points = extractive_points(res.context)
    return Answer(
        answer_type="answer",
        summary="",
        points=points,
        standards=[r for r in std_refs if r.kind in ("standard", "catalogue")][:8],
        evidence_strength="limited",
        strength_basis="Verbatim passages ranked by relevance; no AI summary was generated.",
        mode="extractive",
        lang=plan.lang,  # type: ignore[arg-type]
        notice="notice.extractive_no_key" if not llm_configured else "notice.extractive_llm_failed",
        generated_at=_now(),
    )


def _translate(llm, a: Answer, lang: str) -> Answer:
    strings: dict[str, str] = {}
    if a.summary:
        strings["summary"] = a.summary
    for i, p in enumerate(a.points):
        strings[f"p{i}"] = p.text
    for i, g in enumerate(a.gaps):
        strings[f"g{i}"] = g
    for i, f in enumerate(a.follow_ups):
        strings[f"f{i}"] = f
    for i, s in enumerate(a.standards):
        if s.why:
            strings[f"w{i}"] = s.why
    out = translate_strings(llm, strings, lang)
    original = OriginalAnswer(summary=a.summary, points=[p.model_copy() for p in a.points], gaps=list(a.gaps), follow_ups=list(a.follow_ups))
    if out is None:
        a.translation_failed = True
        a.notice = a.notice or "notice.translation_failed"
        return a
    a.original = original
    a.translated = True
    a.summary = out.get("summary", a.summary)
    a.points = [Point(kind=p.kind, text=out.get(f"p{i}", p.text), citations=p.citations, quote=p.quote) for i, p in enumerate(a.points)]
    a.gaps = [out.get(f"g{i}", g) for i, g in enumerate(a.gaps)]
    a.follow_ups = [out.get(f"f{i}", f) for i, f in enumerate(a.follow_ups)]
    a.standards = [s.model_copy(update={"why": out.get(f"w{i}", s.why)}) for i, s in enumerate(a.standards)]
    return a
