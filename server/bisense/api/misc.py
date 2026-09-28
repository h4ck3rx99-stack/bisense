"""Health, compare, voice and debug endpoints.

Voice: the browser records audio (MediaRecorder) and posts it to /api/voice/stt, which transcribes it with
the configured server provider (Groq Whisper by default; key server-side only). /api/voice/tts speaks
text in the languages the server model supports. When a server provider is missing or fails, the error
code tells the UI to fall back to the browser's own speech features where they exist.
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response

from bisense.api.ask import check_rate
from bisense.api.common import ApiError, get_db
from bisense.config import get_settings
from bisense.models import AskTrace, CompareRequest, CompareResponse, HealthOut, STTOut, TranslateOut, TranslateRequest, TTSRequest, VoiceStatus
from bisense.retrieval.index import IndexMissing, get_index
from bisense.voice import VoiceError, stt_config, stt_languages, stt_mode, tts_config, tts_languages

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
        return HealthOut(
            status="no_index",
            dataset_mode="none",
            index_version=None,
            counts={},
            llm=llm_info,
            models_loaded=False,
            demo_mode=s.demo_mode,
            version=VERSION,
            features=_features(),
            **_capabilities(),
        )
    from bisense.retrieval import embed, rerank

    models_loaded = bool(embed._models) and (rerank._model is not None or not s.rerank_enabled)
    status = "ok" if (llm_info["reachable"] or not llm_info["configured"]) else "degraded"
    if not s.rerank_enabled:
        rr = {"reranker": "disabled", "fix": None}
    elif rerank._model is not None:
        rr = {"reranker": "ready", "fix": None}
    elif rerank.load_error():
        status = "degraded"
        rr = {
            "reranker": "unavailable",
            "fix": "Run `npm run setup` once with internet access to download the reranker model. Until then answers use keyword + meaning search only.",
        }
    else:
        rr = {"reranker": "not_loaded", "fix": None}
    return HealthOut(
        status=status,
        dataset_mode=idx.dataset_mode,
        index_version=idx.version,
        counts=idx.counts,
        llm=llm_info,
        models_loaded=models_loaded,
        demo_mode=s.demo_mode,
        version=VERSION,
        features=_features(),
        retrieval=rr,
        **_capabilities(),
    )


def _capabilities() -> dict:
    """Voice, translation and per-language support, so the UI and `bisense doctor` can be honest."""
    s = get_settings()
    voice = voice_status()
    llm_on = s.llm_configured and s.llm_provider != "none"
    translation = {"available": llm_on, "model": (s.translation_model or s.llm_model) if llm_on and s.llm_provider != "fake" else None}
    languages = {
        lang: {
            "ui": True,
            "answers": lang == "en" or llm_on,
            "stt_server": lang in voice.stt_languages,
            "tts_server": lang in voice.tts_languages,
        }
        for lang in ("en", "hi", "kn")
        if lang in s.language_list
    }
    return {"voice": voice, "translation": translation, "languages": languages}


def _features() -> dict[str, bool]:
    s = get_settings()
    return {
        "server_stt": stt_mode(s) is not None,
        "server_tts": tts_config(s) is not None,
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


_translation_cache: dict[tuple[str, str], str] = {}


@router.post("/translate", response_model=TranslateOut)
def translate(req: TranslateRequest, request: Request) -> TranslateOut:
    """Labelled machine translation shown UNDER a quoted source passage (the original is always shown).
    Identifiers (standard numbers, clauses, units, numbers) are protected; results are cached per language."""
    from bisense.answer.llm_client import get_translation_llm
    from bisense.i18n.translate import translate_strings

    check_rate(request)
    if req.lang == "en":
        return TranslateOut(available=True, translations=list(req.texts))
    missing = [t for t in req.texts if (req.lang, t) not in _translation_cache]
    if missing:
        out = translate_strings(get_translation_llm(), {f"t{i}": t for i, t in enumerate(missing)}, req.lang)
        if out is None:
            return TranslateOut(available=False)
        for i, t in enumerate(missing):
            if len(_translation_cache) > 2000:
                _translation_cache.clear()
            _translation_cache[(req.lang, t)] = out[f"t{i}"]
    return TranslateOut(available=True, translations=[_translation_cache[(req.lang, t)] for t in req.texts])


def voice_status() -> VoiceStatus:
    from bisense.voice import tts as tts_mod

    s = get_settings()
    stt = stt_config(s)
    mode = stt_mode(s)
    tts = tts_config(s)
    return VoiceStatus(
        stt_available=mode is not None,
        stt_provider=("local" if mode == "local" else ("groq" if stt and "groq.com" in stt[0] else "openai_compatible")) if mode else None,
        stt_model=(s.stt_local_model if mode == "local" else s.stt_model) if mode else None,
        stt_languages=stt_languages(s),
        tts_available=tts is not None,
        tts_provider=("groq" if "groq.com" in tts[0] else "openai_compatible") if tts else None,
        tts_languages=tts_languages(s),
        tts_problem=str(tts_mod.last_error.get("code")) if tts_mod.last_error else None,
        max_seconds=s.stt_max_seconds,
        max_bytes=s.stt_max_bytes,
    )


@router.get("/voice/status", response_model=VoiceStatus)
def voice_status_endpoint() -> VoiceStatus:
    return voice_status()


@router.post("/voice/stt", response_model=STTOut)
async def voice_stt(request: Request, audio: UploadFile = File(...), lang: str | None = Form(None)) -> STTOut:
    """Transcribe one recording. `lang`: en | hi | kn, or empty to let the model detect it."""
    from starlette.concurrency import run_in_threadpool

    from bisense.voice.stt import transcribe, validate_audio

    check_rate(request)
    s = get_settings()
    if lang not in (None, "", "en", "hi", "kn"):
        raise ApiError(422, "invalid_request")
    declared = int(request.headers.get("content-length") or 0)
    if declared > s.stt_max_bytes + 64_000:
        raise ApiError(413, "audio_too_large")
    data = await audio.read(s.stt_max_bytes + 1)
    try:
        ext = validate_audio(data, audio.content_type, audio.filename, s)
        t = await run_in_threadpool(transcribe, data, ext, lang or None, s)
    except VoiceError as exc:
        raise ApiError(exc.status, exc.code) from exc
    return STTOut(
        text=t.text,
        no_speech=t.no_speech,
        language=t.language,
        requested_language=lang or None,
        duration_s=t.duration_s,
        provider=t.provider,
        model=t.model,
        ms=t.ms,
    )


@router.post("/voice/tts")
def voice_tts(req: TTSRequest, request: Request) -> Response:
    from bisense.voice.tts import synthesize

    check_rate(request)
    try:
        audio, media_type = synthesize(req.text, req.lang, get_settings())
    except VoiceError as exc:
        raise ApiError(exc.status, exc.code) from exc
    return Response(content=audio, media_type=media_type, headers={"Cache-Control": "no-store"})


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
