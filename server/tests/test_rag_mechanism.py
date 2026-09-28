"""RAG mechanism proof that runs everywhere, including a fresh clone with no network.

tests/test_rag_proof.py proves the same things on the OFFICIAL data, but it is skipped until
`npm run fetch-public` has downloaded the BIS documents. This file uses the sample pack that ships in
the repository (data/demo, Tier D, "Sample data, not official") so the retrieval -> answer -> citation
mechanism is always proven by CI. It says nothing about the official data itself.

  known-answer  a fact present in exactly one document is answered and cited to that document
  ablation      the same index without that document -> the fact is gone, even if a model "knows" it
  refusal       unrelated questions are refused before any LLM call
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from bisense.answer.llm_client import FakeLLM, set_llm
from bisense.models import AskRequest

REPO = Path(__file__).resolve().parents[2]
DOC = "DEMO-301"  # sample steel-bar document; the only one that talks about bundles of bars
KNOWN_Q = "How many places must bundles of reinforcement bars be tied with steel wire?"
KNOWN_FACT = "three places"


def _build(root: Path, exclude: str | None = None) -> Path:
    from bisense.config import get_settings
    from bisense.ingest.pipeline import run_ingest

    data = root / "data"
    shutil.copytree(REPO / "data" / "demo", data / "demo")
    if exclude:
        (data / "demo" / f"{exclude}.md").unlink()
        (data / "demo" / "pdf" / f"{exclude}.pdf").unlink(missing_ok=True)
    os.environ["DATA_DIR"] = str(data)
    get_settings.cache_clear()
    run_ingest(get_settings(), dataset="demo", log=lambda *_: None)
    return data


def _activate(data: Path) -> None:
    from bisense.config import get_settings
    from bisense.retrieval import index as index_mod
    from bisense.retrieval import search as search_mod

    os.environ["DATA_DIR"] = str(data)
    get_settings.cache_clear()
    index_mod.get_index(force=True)
    search_mod._cache.clear()


@pytest.fixture(scope="module")
def indexes(built_index, tmp_path_factory):
    saved = os.environ.get("DATA_DIR")
    try:
        yield {"full": Path(built_index["data_dir"]), "ablated": _build(tmp_path_factory.mktemp("ablated"), exclude=DOC)}
    finally:
        _activate(Path(saved or built_index["data_dir"]))
        set_llm(None, override=False)


def _ask(query: str):
    from bisense.answer.ask import run_ask

    events = dict(run_ask(AskRequest(query=query)))
    return events["answer"], events["evidence"]


def _text(answer) -> str:
    parts = [answer.summary, *answer.gaps]
    for p in answer.points:
        parts += [p.text, p.quote or ""]
    return " ".join(parts)


def test_known_answer_is_cited_to_the_one_document_that_has_it(indexes):
    _activate(indexes["full"])
    set_llm(None)  # extractive: verbatim sentences from retrieved passages only
    answer, evidence = _ask(KNOWN_Q)
    assert answer.answer_type != "insufficient_evidence"
    assert KNOWN_FACT in _text(answer)
    by_id = {c.id: c for c in evidence.citations}
    cited = [by_id[c] for p in answer.points for c in p.citations if c in by_id]
    hit = [c for c in cited if KNOWN_FACT in c.snippet]
    assert hit and (hit[0].standard_number or "").startswith(DOC) and hit[0].slug.startswith("demo-301")


def test_ablation_without_the_document_the_fact_disappears(indexes):
    _activate(indexes["ablated"])
    set_llm(None)
    answer, evidence = _ask(KNOWN_Q)
    assert KNOWN_FACT not in _text(answer)
    assert all(KNOWN_FACT not in c.snippet for c in evidence.citations)


def test_ablation_with_a_model_that_knows_the_answer(indexes):
    """A model that 'remembers' the fact cannot put it in the answer when no source says it."""
    _activate(indexes["ablated"])

    def responder(_messages):
        return json.dumps(
            {
                "answer_type": "answer",
                "summary": "Bundles are tied at three places [C1].",
                "points": [
                    {"kind": "source_fact", "text": "Tie bundles at not less than three places.", "citations": ["C1"], "quote": "not less than three places"}
                ],
                "standards": [{"number": "DEMO-301:2026", "why": "steel bars", "citations": ["C1"]}],
                "gaps": [],
                "follow_ups": [],
            }
        )

    set_llm(FakeLLM(responder=responder))
    answer, _ = _ask(KNOWN_Q)
    assert KNOWN_FACT not in _text(answer)
    assert all(not (s.number or "").startswith(DOC) for s in answer.standards)


def test_refusal_before_any_llm_call(indexes):
    _activate(indexes["full"])
    llm = FakeLLM()
    set_llm(llm)
    for q in ("Who won the cricket world cup in 2011?", "What is the capital city of Australia?"):
        answer, _ = _ask(q)
        assert answer.answer_type in ("insufficient_evidence", "out_of_scope"), q
    assert llm.calls == []
