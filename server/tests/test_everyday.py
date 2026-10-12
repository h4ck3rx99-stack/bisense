"""Everyday questions (server/eval/everyday.yaml) get a useful answer from the official data.

Usability audit 2026-10-12: 13 of 30 everyday questions got a useful answer (12 when re-measured without an
AI model). Causes fixed: whole category tables as one chunk (rows past ~512 tokens invisible), everyday words
not matching official product names, a no-AI evidence gate that refused weak-scoring but exact official rows,
FAQ/FMCS pages ranked above list rows, and romanised Hindi refused.

Runs on an official-only index built in a temporary folder (skipped until `npm run fetch-public` has run).
Without an AI model always; with the configured AI model only when BISENSE_LIVE_EVERYDAY=1 (it uses about
100k tokens of a free-tier daily allowance).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from test_rag_proof import MANUAL, PUBLIC, _activate, _build

from bisense.answer.llm_client import set_llm
from bisense.everyday import load, run

pytestmark = pytest.mark.skipif(
    not (PUBLIC / MANUAL).exists() or not (PUBLIC / "fetch_log.yaml").exists(),
    reason="official documents not fetched (run: npm run fetch-public)",
)

MUST = {
    "e01": "IS 4151",  # helmets
    "e02": "IS 2347",  # pressure cooker
    "e03": "IS 16102",  # LED bulbs
    "e04": "IS 269",  # OPC cement
    "e05": "IS 1786",  # TMT bars
    "e06": "IS 9873",  # toys
    "e07": "IS/IEC 62368",  # mobile charger
    "e08": "IS 302",  # room heater
    "e09": "IS 374",  # ceiling fan
    "e10": "IS 15410",  # plastic water bottle
    "e11": "IS 14286",  # solar panels
}


@pytest.fixture(scope="module")
def official(built_index, tmp_path_factory):
    saved = {k: os.environ.get(k) for k in ("DATA_DIR", "DATASET")}
    try:
        yield _build(tmp_path_factory.mktemp("everyday"))
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        _activate(Path(os.environ["DATA_DIR"]))
        set_llm(None, override=False)


def _check(outcomes) -> None:
    by_id = {o.id: o for o in outcomes}
    for qid, number in MUST.items():
        assert by_id[qid].good, f"{qid} {by_id[qid].q!r}: {by_id[qid].why} (expected {number})"
    for qid in ("e12", "e13", "e14"):  # complaint page, domestic licence (not FMCS), Hinglish kettle
        assert by_id[qid].good, f"{qid} {by_id[qid].q!r}: {by_id[qid].why}"
    for qid in ("e15", "e16"):  # fine for fake helmets, cotton t-shirts: must still refuse
        assert by_id[qid].good, f"{qid} {by_id[qid].q!r} must be refused, got {by_id[qid].answer_type}"
    good = sum(o.good for o in outcomes)
    assert good >= 24, f"only {good}/30 everyday questions answered usefully"


def test_everyday_questions_without_an_ai_model(official):
    _activate(official)
    set_llm(None)  # evidence-only answers
    outcomes = run(load(), log=lambda *_: None)
    _check(outcomes)


@pytest.mark.skipif(os.environ.get("BISENSE_LIVE_EVERYDAY") != "1", reason="set BISENSE_LIVE_EVERYDAY=1 to spend ~100k tokens of the AI model's allowance")
def test_everyday_questions_with_the_ai_model(official):
    from bisense.answer.llm_client import LLMClient
    from bisense.config import Settings

    s = Settings(llm_provider="openai_compatible", data_dir=official)
    if not s.llm_configured:
        pytest.skip("no AI model configured in .env")
    _activate(official)
    set_llm(LLMClient(s))
    outcomes = run(load(), pace_s=8, log=print)
    assert not [o for o in outcomes if o.mode == "extractive" and "quota" in " ".join(o.notes)], "daily limit reached during the run"
    _check(outcomes)
