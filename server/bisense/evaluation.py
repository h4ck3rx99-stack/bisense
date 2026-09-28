"""Evaluation harness: `bisense eval` (writes docs/EVAL.md and docs/eval/latest.json).

Two phases:
  1. Retrieval (always, no LLM needed except the Hindi/Kannada rewrite when an LLM is configured):
     recall@5, MRR@10, exact-number hit@1, gate refusal/false-refusal, retrieval latency. Also used to
     calibrate the evidence gate threshold (rerank score below which BISense refuses without an LLM).
  2. Answers (when an LLM is configured and --no-llm is not given): runs every question through the full
     /api/ask pipeline and measures refusal accuracy, false refusals, validator drop rate, fact hits,
     latency and tokens.
Real numbers only: whatever the run produces is written, including misses against the targets.
"""

from __future__ import annotations

import json
import os
import statistics
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import yaml

from bisense.config import REPO_ROOT, get_settings

EVAL_FILE = REPO_ROOT / "server" / "eval" / "questions.yaml"
OUT_JSON = REPO_ROOT / "docs" / "eval" / "latest.json"
OUT_MD = REPO_ROOT / "docs" / "EVAL.md"
OUT_NO_LLM = REPO_ROOT / "docs" / "eval" / "no_llm.json"
TARGETS = {"recall_at_5": 0.85, "exact_number_hit_at_1": 1.0, "refusal_accuracy": 0.9, "false_refusal_rate": 0.1}
ANSWERABLE_TYPES = {"answerable", "exact", "compare", "followup"}


@dataclass
class QResult:
    id: str
    type: str
    lang: str
    q: str
    rank: int | None = None  # 1-based rank of the first expected hit in the evidence list
    top_standard: str | None = None
    exact_hit: bool | None = None
    top_rerank: float | None = None
    retrieval_ms: float = 0.0
    scope_explicit: bool = False
    gate_refused: bool = False  # the real no-LLM evidence gate decision (works with or without the reranker)
    reranked: bool = False
    answer_type: str | None = None
    mode: str | None = None
    points: int = 0
    dropped: int = 0
    fact_hit: bool | None = None
    answer_ms: float | None = None
    tokens: int = 0
    notes: list[str] = field(default_factory=list)


def load_questions(path: Path = EVAL_FILE) -> list[dict]:
    return list(yaml.safe_load(path.read_text(encoding="utf-8"))["questions"])


def _matches(c, exp: dict) -> bool:
    if c.slug != exp["slug"]:
        return False
    clause = exp.get("clause")
    if not clause:
        return True
    return c.clause_number == clause or c.clause_number.startswith(clause + ".") or c.clause_path.startswith(clause + " ")


def _ctx(q: dict):
    from bisense.retrieval.query import ClientContext

    c = q.get("context") or {}
    return ClientContext(recent_questions=c.get("recent_questions", []), focus_slugs=c.get("focus_slugs", []), open_slug=c.get("open_slug"))


def run_retrieval(questions: list[dict], use_llm_rewrite: bool = True, rerank: bool | None = None, log=print) -> list[QResult]:
    from bisense.answer.ask import _gate_fails, prepare_plan, retrieve
    from bisense.answer.llm_client import get_llm
    from bisense.retrieval import search as search_mod
    from bisense.retrieval.index import db_conn

    llm = get_llm() if use_llm_rewrite else None
    conn = db_conn()
    out = []
    s = get_settings()
    old = s.rerank_enabled
    if rerank is not None:
        s.rerank_enabled = rerank
    search_mod._cache.clear()
    try:
        for q in questions:
            r = QResult(id=q["id"], type=q["type"], lang=q.get("lang", "en"), q=q["q"])
            t0 = time.perf_counter()
            plan = prepare_plan(conn, q["q"], q.get("lang", "en"), _ctx(q), llm)
            res = retrieve(conn, plan)
            r.retrieval_ms = round((time.perf_counter() - t0) * 1000, 1)
            r.top_rerank = res.top_rerank
            r.scope_explicit = plan.scope_source in ("explicit", "context")  # these bypass the gate
            r.gate_refused = _gate_fails(res, plan, llm_available=False)
            r.reranked = res.reranked
            ordered = list(res.context) + [c for c in res.candidates if c not in res.context]
            exp = q.get("expect") or []
            for i, c in enumerate(ordered[:10], start=1):
                if any(_matches(c, e) for e in exp):
                    r.rank = i
                    break
            # Catalogue-only standards have no text of their own; their evidence is an official list row,
            # so a hit is the standard appearing in the grouped results (position = rank).
            for i, h in enumerate(res.standards[:10], start=1):
                if any(e["slug"] == h.slug and not e.get("clause") for e in exp) and h.catalogue_only:
                    r.rank = min(r.rank or 99, i)
                    break
            if res.standards:
                r.top_standard = res.standards[0].slug
            if q["type"] == "exact":
                r.exact_hit = bool(res.standards) and res.standards[0].slug in {e["slug"] for e in exp}
            out.append(r)
    finally:
        s.rerank_enabled = old
        conn.close()
    return out


def run_answers(questions: list[dict], results: dict[str, QResult], log=print) -> None:
    from bisense.answer.ask import run_ask
    from bisense.models import AskContext, AskRequest

    s = get_settings()
    # Free-tier providers limit tokens per minute (Groq: ~8k/min per model, ~3-4k per answer). Pace the run
    # so the metrics measure the model, not the rate limit; a fallback caused by a provider failure is
    # retried once after a pause and recorded in the notes.
    live = s.llm_provider not in ("fake", "none") and s.llm_configured
    pace = float(os.environ.get("EVAL_PACE_S", "15" if live else "0"))

    def ask_once(req):
        answer = trace = None
        for ev, data in run_ask(req):
            if ev == "answer":
                answer = data
            elif ev == "trace":
                trace = data
        return answer, trace

    for i, q in enumerate(questions, start=1):
        c = q.get("context") or {}
        req = AskRequest(query=q["q"], lang=q.get("lang", "en"), context=AskContext(**c) if c else None)
        if pace and i > 1:
            time.sleep(pace)
        t0 = time.perf_counter()
        answer, trace = ask_once(req)
        r = results[q["id"]]
        if live and answer is not None and answer.notice == "notice.extractive_llm_quota" and (answer.retry_after_s or 0) <= 1800:
            # Free-tier daily limit: wait for it rather than scoring a fallback as the model's answer.
            wait = (answer.retry_after_s or 60) + 5
            r.notes.append(f"daily provider limit reached; waited {wait} s and retried")
            log(f"  daily provider limit reached; waiting {wait} s ...")
            time.sleep(wait)
            t0 = time.perf_counter()
            answer, trace = ask_once(req)
        elif live and answer is not None and answer.notice == "notice.extractive_llm_failed":
            r.notes.append("provider failed once (rate limit?); retried after 45 s")
            time.sleep(45)
            t0 = time.perf_counter()
            answer, trace = ask_once(req)
        r.answer_ms = round((time.perf_counter() - t0) * 1000, 1)
        if answer is None:
            r.notes.append("no answer event")
            continue
        r.answer_type = answer.answer_type
        r.mode = answer.mode
        r.points = len(answer.points)
        r.dropped = sum(1 for d in answer.drops if d.field == "point")
        if trace:
            r.tokens = sum(trace.tokens.values())
        if q.get("fact") and answer.answer_type not in ("insufficient_evidence", "out_of_scope"):
            text = " ".join(
                [answer.summary]
                + [p.text + " " + (p.quote or "") for p in (answer.original.points if answer.original else answer.points)]
                + [(s.number or "") + " " + (s.why or "") + " " + (s.matched_row or "") for s in answer.standards]
            ).lower()
            r.fact_hit = q["fact"].lower() in text
        log(f"  [{i}/{len(questions)}] {q['id']} {answer.answer_type} ({answer.mode}) {r.answer_ms / 1000:.1f}s")


def calibrate_gate(results: list[QResult]) -> dict:
    """Pick the rerank threshold that best separates answerable from unanswerable questions."""
    ans = [r.top_rerank for r in results if r.type in ANSWERABLE_TYPES and not r.scope_explicit and r.top_rerank is not None]
    una = [r.top_rerank for r in results if r.type == "unanswerable" and r.top_rerank is not None]
    if not ans or not una:
        return {}
    candidates = sorted(set([round(x, 2) for x in ans + una] + [-8.0, -6.0, -4.0, -2.0, 0.0]))
    best = None
    for t in candidates:
        refusal = sum(1 for x in una if x < t) / len(una)
        false_ref = sum(1 for x in ans if x < t) / len(ans)
        score = refusal - 2 * max(0.0, false_ref - 0.1) - false_ref * 0.5
        if best is None or score > best[0]:
            best = (score, t, refusal, false_ref)
    assert best is not None
    return {
        "threshold": best[1],
        "gate_refusal_accuracy": round(best[2], 3),
        "gate_false_refusal_rate": round(best[3], 3),
        "answerable_scores": sorted(round(x, 2) for x in ans),
        "unanswerable_scores": sorted(round(x, 2) for x in una),
    }


def _pct(values: list[float], p: float) -> float | None:
    if not values:
        return None
    v = sorted(values)
    k = min(len(v) - 1, max(0, round(p / 100 * (len(v) - 1))))
    return v[k]


def summarize(results: list[QResult], gate: float, with_answers: bool) -> dict:
    ans = [r for r in results if r.type in ANSWERABLE_TYPES]
    una = [r for r in results if r.type == "unanswerable"]
    recall5 = sum(1 for r in ans if r.rank and r.rank <= 5) / len(ans) if ans else None
    mrr = sum(1 / r.rank for r in ans if r.rank) / len(ans) if ans else None
    exact = [r for r in results if r.exact_hit is not None]
    m: dict[str, float | None] = {
        "recall_at_5": round(recall5, 3) if recall5 is not None else None,
        "mrr_at_10": round(mrr, 3) if mrr is not None else None,
        "exact_number_hit_at_1": round(sum(r.exact_hit for r in exact) / len(exact), 3) if exact else None,
        "retrieval_p50_ms": _pct([r.retrieval_ms for r in results], 50),
        "retrieval_p95_ms": _pct([r.retrieval_ms for r in results], 95),
    }
    refused = lambda r: r.answer_type in ("insufficient_evidence", "out_of_scope")  # noqa: E731
    if with_answers:
        m["refusal_accuracy"] = round(sum(1 for r in una if refused(r)) / len(una), 3) if una else None
        m["false_refusal_rate"] = round(sum(1 for r in ans if refused(r)) / len(ans), 3) if ans else None
        pts = sum(r.points + r.dropped for r in results)
        m["drop_rate"] = round(sum(r.dropped for r in results) / pts, 3) if pts else None
        facts = [r for r in results if r.fact_hit is not None]
        m["fact_hit_rate"] = round(sum(r.fact_hit for r in facts) / len(facts), 3) if facts else None  # type: ignore[misc]
        times = [r.answer_ms for r in results if r.answer_ms and r.mode == "live"]
        m["answer_p50_ms"] = _pct(times, 50)
        m["answer_p95_ms"] = _pct(times, 95)
        toks = [r.tokens for r in results if r.tokens]
        m["tokens_per_answer_median"] = statistics.median(toks) if toks else None
    else:
        # Without an LLM, refusal is decided by the evidence gate alone.
        gate_refused = lambda r: r.gate_refused  # noqa: E731
        m["refusal_accuracy"] = round(sum(1 for r in una if gate_refused(r)) / len(una), 3) if una else None
        m["false_refusal_rate"] = round(sum(1 for r in ans if gate_refused(r)) / len(ans), 3) if ans else None
    return m


def write_report(results: list[QResult], metrics: dict, calib: dict, meta: dict, comparisons: list[dict]) -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    data = {
        **meta,
        "metrics": metrics,
        "targets": TARGETS,
        "calibration": calib,
        "comparisons": comparisons,
        "counts": {
            "questions": len(results),
            "answerable": sum(1 for r in results if r.type in ANSWERABLE_TYPES),
            "unanswerable": sum(1 for r in results if r.type == "unanswerable"),
            "multilingual": sum(1 for r in results if r.lang != "en"),
        },
        "results": [r.__dict__ for r in results],
    }
    OUT_JSON.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    def fmt(v):
        return "—" if v is None else (f"{v:.3f}" if isinstance(v, float) else str(v))

    lines = [
        "# Evaluation",
        "",
        f"Generated {meta['generated_at']} by `npm run eval` ({'full pipeline with LLM' if meta['llm'] else 'retrieval + evidence gate only, no LLM'}).",
        "",
        f"- Dataset mode: **{meta['dataset_mode']}** (tiers {meta['tiers']}); corpus: {meta['corpus']}",
        f"- Questions: {data['counts']['questions']} ({data['counts']['answerable']} answerable incl. exact/compare/follow-up, "
        f"{data['counts']['unanswerable']} unanswerable, {data['counts']['multilingual']} Hindi/Kannada); source: `server/eval/questions.yaml`",
        f"- Embedding model: `{meta['embedding_model']}`; reranker: `{meta['reranker']}` (enabled: {meta['rerank_enabled']}); LLM: `{meta['llm'] or 'none'}`",
        "",
        "## Results",
        "",
        "| Metric | Value | Target |",
        "|---|---|---|",
    ]
    for k, v in metrics.items():
        lines.append(f"| {k} | {fmt(v)} | {TARGETS.get(k, '')} |")
    lines += [
        "",
        "Definitions: recall@5 = share of answerable questions with an expected source (document + clause) among the first 5 evidence passages; "
        "MRR@10 = mean reciprocal rank of the first expected passage; exact-number hit@1 = the named standard is the first standard listed; "
        'refusal accuracy = share of unanswerable questions answered with "not in the indexed sources"; false-refusal rate = share of answerable '
        "questions refused; drop rate = share of drafted statements removed by the validator; fact hit = the expected verbatim fragment appears in the answer.",
        "",
        "## Evidence gate calibration",
        "",
    ]
    if calib:
        lines += [
            f"Cross-encoder score of the best passage, answerable questions: {calib['answerable_scores']}",
            "",
            f"Unanswerable questions: {calib['unanswerable_scores']}",
            "",
            f"Recommended `GATE_RERANK_MIN` = **{calib['threshold']}** (gate alone: refusal accuracy {calib['gate_refusal_accuracy']}, "
            f"false refusals {calib['gate_false_refusal_rate']}). Method: sweep every observed score and pick the threshold that maximises "
            "refusals of unanswerable questions while penalising false refusals above 10%. Questions naming a standard explicitly bypass the gate.",
        ]
    else:
        lines.append("Not calibrated (reranker disabled).")
    if comparisons:
        lines += [
            "",
            "## Configuration comparison (retrieval only)",
            "",
            "| Configuration | recall@5 | MRR@10 | exact hit@1 | p50 ms | p95 ms |",
            "|---|---|---|---|---|---|",
        ]
        for c in comparisons:
            lines.append(
                f"| {c['name']} | {fmt(c['recall_at_5'])} | {fmt(c['mrr_at_10'])} | {fmt(c['exact_number_hit_at_1'])} | {fmt(c['retrieval_p50_ms'])} | {fmt(c['retrieval_p95_ms'])} |"
            )
    if OUT_NO_LLM.exists():
        nl = json.loads(OUT_NO_LLM.read_text(encoding="utf-8"))
        lines += ["", f"## Without an LLM (extractive mode, run {nl['generated_at']})", "", "| Metric | Value |", "|---|---|"]
        lines += [f"| {k} | {fmt(v)} |" for k, v in nl["metrics"].items()]
        lines += ["", "In this mode refusals come only from the stricter evidence gate (`GATE_RERANK_MIN_NO_LLM`); answers are verbatim passages."]
    lines += [
        "",
        "## Per-question results",
        "",
        "| id | type | lang | rank | top standard | top rerank | answer | mode | fact | ms |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        lines.append(
            f"| {r.id} | {r.type} | {r.lang} | {r.rank or '—'} | {r.top_standard or '—'} | {fmt(r.top_rerank)} | {r.answer_type or '—'} | {r.mode or '—'} | "
            f"{'' if r.fact_hit is None else ('yes' if r.fact_hit else 'no')} | {r.answer_ms or r.retrieval_ms} |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- All answerable questions were auto-drafted from ingested clauses (`origin: auto_drafted`) and should be spot-checked by the team.",
        "- The Tier C demo documents are synthetic; numbers on them measure the pipeline, not coverage of real Indian Standards.",
        "- Latency is measured on the build laptop (CPU embeddings/reranker; local LLM on an 8 GB laptop GPU when used).",
    ]
    OUT_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(no_llm: bool = False, smoke: bool = False, compare: bool = False, log=print) -> dict:
    from bisense.answer.llm_client import get_llm
    from bisense.retrieval.index import get_index

    s = get_settings()
    idx = get_index()
    questions = load_questions()
    if smoke:
        questions = [q for i, q in enumerate(questions) if i % 4 == 0]
    llm = None if no_llm else get_llm()
    log(f"Evaluating {len(questions)} questions (llm={'yes' if llm else 'no'}, rerank={s.rerank_enabled}) ...")
    results = run_retrieval(questions, use_llm_rewrite=llm is not None, log=log)
    calib = calibrate_gate(results) if s.rerank_enabled else {}
    comparisons = []
    if compare:
        for name, rr in (("hybrid + reranker", True), ("hybrid, no reranker", False)):
            rs = run_retrieval(questions, use_llm_rewrite=llm is not None, rerank=rr, log=log)
            mm = summarize(rs, s.gate_rerank_min, with_answers=False)
            comparisons.append(
                {
                    "name": f"{name} ({s.embedding_model})",
                    **{k: mm.get(k) for k in ("recall_at_5", "mrr_at_10", "exact_number_hit_at_1", "retrieval_p50_ms", "retrieval_p95_ms")},
                }
            )
    if llm is not None:
        log("Running the full answer pipeline ...")
        run_answers(questions, {r.id: r for r in results}, log=log)
    metrics = summarize(results, s.gate_rerank_min_no_llm, with_answers=llm is not None)
    meta = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "dataset_mode": idx.dataset_mode,
        "tiers": "A+B+C+D (D = sample data)" if idx.dataset_mode == "sample" else "A+B+C",
        "corpus": {k: v for k, v in idx.counts.items()},
        "embedding_model": s.embedding_model,
        "reranker": s.reranker_model,
        "rerank_enabled": s.rerank_enabled,
        "llm": s.llm_model if llm is not None else None,
        "smoke": smoke,
    }
    if smoke:
        pass
    elif llm is None:
        # Extractive-only mode: its own file, so the main (LLM) report is not overwritten.
        OUT_NO_LLM.parent.mkdir(parents=True, exist_ok=True)
        OUT_NO_LLM.write_text(json.dumps({**meta, "metrics": metrics, "calibration": calib}, indent=1, ensure_ascii=False), encoding="utf-8")
    else:
        write_report(results, metrics, calib, meta, comparisons)
    return {"metrics": metrics, "calibration": calib, "comparisons": comparisons, "results": results}
