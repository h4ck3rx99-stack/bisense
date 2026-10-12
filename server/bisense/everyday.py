"""Everyday-question check: does a first-time user get a useful answer?

Runs server/eval/everyday.yaml through the real /api/ask pipeline and judges each answer the way the
answer page shows it: the verdict standard is the first standard listed (or, when none is listed, the
standard of the first cited passage). Used by tests/test_everyday.py and `bisense everyday`.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

import yaml

from bisense.config import REPO_ROOT

EVERYDAY_FILE = REPO_ROOT / "server" / "eval" / "everyday.yaml"
REFUSED = ("insufficient_evidence", "out_of_scope")


@dataclass
class Outcome:
    id: str
    q: str
    good: bool
    answer_type: str
    mode: str
    verdict: str  # what the user sees first: standard number or source title
    why: str = ""
    notes: list[str] = field(default_factory=list)


def load() -> list[dict]:
    return yaml.safe_load(EVERYDAY_FILE.read_text(encoding="utf-8"))["questions"]


def _base(number: str) -> str:
    return re.sub(r"\s*:\s*\d{4}.*$", "", number or "").strip()


def number_matches(number: str | None, expected: list[str]) -> bool:
    b = _base(number or "")
    return any(b == e or b.startswith(e + " ") or b.startswith(e + "(") for e in expected)


def judge(q: dict, answer, evidence) -> Outcome:
    cites = {c.id: c for c in (evidence.citations if evidence else [])}
    first_cited = next((cites[i] for p in answer.points for i in p.citations if i in cites), None)
    first_std = answer.standards[0].number if answer.standards else (first_cited.standard_number if first_cited else None)
    doc = " ".join(filter(None, [first_cited.document_title, first_cited.standard_title, first_cited.clause_heading])) if first_cited else ""
    refused = answer.answer_type in REFUSED
    out = Outcome(id=q["id"], q=q["q"], good=False, answer_type=answer.answer_type, mode=answer.mode, verdict=first_std or doc[:60])
    if q.get("refuse"):
        out.good, out.why = refused, "refused" if refused else "should refuse"
    elif refused:
        out.why = "refused"
    elif q.get("answer"):
        out.good, out.why = True, "answered"
    elif q.get("expect"):
        out.good = number_matches(first_std, q["expect"])
        out.why = "" if out.good else f"verdict {first_std!r}, expected {q['expect']}"
    elif q.get("expect_doc"):
        d = doc.lower()
        ok = any(w in d for w in q["expect_doc"]) and not any(w in d for w in q.get("avoid_doc", []))
        out.good, out.why = ok, "" if ok else f"first source {doc[:80]!r}"
    return out


def run(questions: list[dict] | None = None, pace_s: float = 0.0, log=print) -> list[Outcome]:
    from bisense.answer.ask import run_ask
    from bisense.models import AskRequest

    outcomes = []
    for i, q in enumerate(questions or load()):
        if pace_s and i:
            time.sleep(pace_s)
        events = dict(run_ask(AskRequest(query=q["q"], lang=q.get("lang", "en"))))
        o = judge(q, events["answer"], events.get("evidence"))
        outcomes.append(o)
        log(f"  {'OK ' if o.good else 'BAD'} {o.id} {o.answer_type:22} {o.mode:10} {o.verdict[:40]:40} {o.why}")
    log(f"good answers: {sum(o.good for o in outcomes)}/{len(outcomes)}")
    return outcomes
