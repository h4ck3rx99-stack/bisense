"""Text-to-speech through an OpenAI-compatible /audio/speech endpoint (Groq Orpheus by default).

Groq's TTS models (checked 2026-09-28) speak English (canopylabs/orpheus-v1-english) and Saudi Arabic
only, so the server voice is offered for English; Hindi and Kannada use the browser's voices when the
device has them, and the UI says plainly when it does not.

The client sends one sentence group at a time (MAX_CHARS), so playback starts quickly and stop works
between chunks.
"""

from __future__ import annotations

import time

import httpx

from bisense.config import Settings
from bisense.voice import VoiceError, tts_config, tts_languages

MAX_CHARS = 400

_transport: httpx.BaseTransport | None = None  # tests only
# Last provider problem seen (e.g. "tts_terms_required"), reported by /api/health.
last_error: dict[str, str | float] = {}


def synthesize(text: str, lang: str, settings: Settings) -> tuple[bytes, str]:
    cfg = tts_config(settings)
    if cfg is None:
        raise VoiceError(503, "tts_unavailable")
    if lang not in tts_languages(settings):
        raise VoiceError(422, "tts_language_unsupported", lang)
    text = " ".join(text.split())
    if not text:
        raise VoiceError(400, "tts_empty")
    if len(text) > MAX_CHARS:
        raise VoiceError(413, "tts_text_too_long")
    base_url, key = cfg
    try:
        with httpx.Client(timeout=settings.tts_timeout_s, transport=_transport) as client:
            r = client.post(
                f"{base_url}/audio/speech",
                headers={"Authorization": f"Bearer {key}"},
                json={"model": settings.tts_model, "voice": settings.tts_voice, "input": text, "response_format": "wav"},
            )
    except httpx.TimeoutException as exc:
        raise _fail(504, "tts_timeout") from exc
    except httpx.HTTPError as exc:
        raise _fail(502, "tts_failed", type(exc).__name__) from exc
    if r.status_code == 200 and r.content:
        last_error.clear()
        return r.content, r.headers.get("content-type", "audio/wav").split(";")[0]
    code = _provider_code(r)
    if code == "model_terms_required":
        raise _fail(503, "tts_terms_required")
    if r.status_code in (401, 403):
        raise _fail(502, "tts_auth")
    if r.status_code == 429:
        raise _fail(503, "tts_busy")
    raise _fail(502, "tts_failed", f"HTTP {r.status_code}")


def _fail(status: int, code: str, detail: str = "") -> VoiceError:
    last_error.update({"code": code, "at": time.time()})
    return VoiceError(status, code, detail)


def _provider_code(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("code", ""))
    except ValueError:
        return ""
