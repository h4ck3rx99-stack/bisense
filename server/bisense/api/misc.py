"""Health, compare, voice and debug endpoints.

Voice: speech-to-text and text-to-speech run in the browser (Web Speech API) by default. The server
endpoints exist so an optional provider (Sarvam, Bhashini, local Whisper) can be plugged in; when none
is configured they return 501 with a stable error code and the UI keeps using the browser.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Request

from bisense.api.ask import check_rate
from bisense.api.common import ApiError, get_db
from bisense.config import get_settings
from bisense.models import AskTrace, CompareRequest, CompareResponse, HealthOut, TTSRequest
from bisense.retrieval.index import IndexMissing, get_index

router = APIRouter(prefix="/api", tags=["misc"])
VERSION = "0.1.0"
_llm_reachable_cache: dict[str, tuple[float, bool]] = {}


def _llm_reachable() -> bool:
    import time

    from bisense.answer.llm_client import get_llm

    llm = get_llm()
    if llm is None:
        return False
    now = time.monotonic()
    hit = _llm_reachable_cache.get("v")
    if hit and now - hit[0] < 60:
        return hit[1]
    ok = llm.reachable()
    _llm_reachable_cache["v"] = (now, ok)
    return ok


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    s = get_settings()
    llm_info: dict[str, bool | str | None] = {"configured": s.llm_configured and s.llm_provider != "none", "reachable": False, "provider": s.llm_provider}
    if llm_info["configured"]:
        llm_info["reachable"] = _llm_reachable()
    try:
        idx = get_index()
    except IndexMissing:
        return HealthOut(status="no_index", dataset_mode="none", index_version=None, counts={}, llm=llm_info, models_loaded=False, demo_mode=s.demo_mode, version=VERSION, features=_features())
    from bisense.retrieval import embed, rerank

    models_loaded = bool(embed._models) and (rerank._model is not None or not s.rerank_enabled)
    status = "ok" if (llm_info["reachable"] or not llm_info["configured"]) else "degraded"
    return HealthOut(status=status, dataset_mode=idx.dataset_mode, index_version=idx.version, counts=idx.counts, llm=llm_info, models_loaded=models_loaded, demo_mode=s.demo_mode, version=VERSION, features=_features())


def _features() -> dict[str, bool]:
    s = get_settings()
    return {
        "server_stt": s.stt_provider not in ("browser", ""),
        "server_tts": s.tts_provider not in ("browser", ""),
        "uploads": s.allow_uploads,
        "debug": s.debug,
    }


@router.post("/compare", response_model=CompareResponse)
def compare(req: CompareRequest, request: Request, conn: sqlite3.Connection = Depends(get_db)) -> CompareResponse:
    from bisense.answer.compare import run_compare

    check_rate(request)
    if req.a == req.b:
        raise ApiError(422, "compare_same")
    return run_compare(conn, req.a, req.b, req.lang)


@router.post("/voice/stt")
def voice_stt(request: Request) -> None:
    check_rate(request)
    raise ApiError(501, "voice_provider_not_configured")


@router.post("/voice/tts")
def voice_tts(req: TTSRequest, request: Request) -> None:
    check_rate(request)
    raise ApiError(501, "voice_provider_not_configured")


@router.get("/eval")
def eval_summary() -> dict:
    """Latest evaluation results written by `bisense eval` (docs/eval/latest.json). Real numbers only."""
    import json

    from bisense.config import REPO_ROOT

    path = REPO_ROOT / "docs" / "eval" / "latest.json"
    if not path.exists():
        return {"available": False}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {"available": True, **{k: data.get(k) for k in ("generated_at", "dataset_mode", "corpus", "metrics", "targets", "counts", "llm")}}


@router.get("/debug/trace/{request_id}", response_model=AskTrace)
def debug_trace(request_id: str) -> AskTrace:
    from bisense.answer.ask import TRACES

    if not get_settings().debug:
        raise ApiError(404, "not_found")
    t = TRACES.get(request_id)
    if not t:
        raise ApiError(404, "not_found")
    return t
