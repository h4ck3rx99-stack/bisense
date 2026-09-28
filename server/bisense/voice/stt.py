"""Speech-to-text through an OpenAI-compatible /audio/transcriptions endpoint (Groq Whisper by default).

Checked against Groq's documentation on 2026-09-28: models whisper-large-v3-turbo / whisper-large-v3;
formats flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm; 25 MB free-tier limit; `language` is ISO-639-1;
`response_format=verbose_json` returns duration and per-segment no_speech_prob.

Fallback chain: primary model -> fallback model (on provider/model errors) -> the browser's own speech
recognition (decided by the UI when this raises).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from bisense.config import Settings
from bisense.voice import VoiceError, stt_config

# MIME types browsers produce with MediaRecorder, plus common upload types. Parameters (";codecs=opus")
# are stripped before the check.
ALLOWED_TYPES = {
    "audio/webm": "webm",
    "video/webm": "webm",  # some browsers label audio-only WebM as video/webm
    "audio/ogg": "ogg",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/wave": "wav",
    "audio/mpeg": "mp3",
    "audio/mp3": "mp3",
    "audio/mp4": "m4a",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
    "audio/aac": "m4a",
    "audio/flac": "flac",
    "audio/x-flac": "flac",
}
MIN_BYTES = 1000  # anything smaller cannot hold a spoken word
LANGS = {"en": "en", "hi": "hi", "kn": "kn"}
# Words Whisper often mishears in this domain; only used for English (a Latin prompt can pull Hindi or
# Kannada output into the wrong script).
EN_PROMPT = "BIS, Bureau of Indian Standards, Indian Standard, IS 14543, ISI mark, QCO, hallmarking, licence."
NO_SPEECH_PROB = 0.6
# Whisper invents these on silence or noise (measured: 2 s of digital silence -> "Thank you." with
# no_speech_prob 0). Alone, they are never a question about standards, so they count as "no speech".
HALLUCINATIONS = {"thank you", "thank you.", "thanks for watching!", "thanks for watching.", "you", ".", "bye.", "bye", "thank you very much."}
SILENT_PEAK = 300  # 16-bit PCM peak below this (about -40 dBFS) is treated as silence

# Tests replace this with an httpx.MockTransport; None means real network.
_transport: httpx.BaseTransport | None = None


@dataclass
class Transcript:
    text: str
    language: str | None
    duration_s: float | None
    model: str
    provider: str
    no_speech: bool
    ms: float


def audio_extension(content_type: str | None, filename: str | None = None) -> str:
    base = (content_type or "").split(";")[0].strip().lower()
    if base in ALLOWED_TYPES:
        return ALLOWED_TYPES[base]
    if base in ("", "application/octet-stream") and filename and "." in filename:
        ext = filename.rsplit(".", 1)[1].lower()
        if ext in set(ALLOWED_TYPES.values()) | {"mpga", "mpeg", "mp4"}:
            return ext
    raise VoiceError(415, "audio_unsupported_type", base or "unknown")


def validate_audio(data: bytes, content_type: str | None, filename: str | None, settings: Settings) -> str:
    ext = audio_extension(content_type, filename)
    if len(data) < MIN_BYTES:
        raise VoiceError(400, "audio_empty")
    if len(data) > settings.stt_max_bytes:
        raise VoiceError(413, "audio_too_large")
    if ext == "wav" and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        seconds = _wav_seconds(data)
        if seconds is not None and seconds > settings.stt_max_seconds + 1:
            raise VoiceError(413, "audio_too_long")
    return ext


def _wav_seconds(data: bytes) -> float | None:
    """Duration from the WAV header (fmt byte rate + data chunk size)."""
    i, byte_rate = 12, 0
    while i + 8 <= len(data):
        cid, size = data[i : i + 4], int.from_bytes(data[i + 4 : i + 8], "little")
        if cid == b"fmt ":
            byte_rate = int.from_bytes(data[i + 16 : i + 20], "little")
        elif cid == b"data":
            return size / byte_rate if byte_rate else None
        i += 8 + size + (size & 1)
    return None


def wav_is_silent(data: bytes) -> bool:
    """True for a 16-bit PCM WAV whose loudest sample is below SILENT_PEAK (other formats: unknown -> False)."""
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return False
    i, bits = 12, 0
    while i + 8 <= len(data):
        cid, size = data[i : i + 4], int.from_bytes(data[i + 4 : i + 8], "little")
        if cid == b"fmt ":
            bits = int.from_bytes(data[i + 22 : i + 24], "little")
        elif cid == b"data":
            if bits != 16:
                return False
            pcm = memoryview(data[i + 8 : i + 8 + size - (size % 2)]).cast("h")
            return max((abs(v) for v in pcm), default=0) < SILENT_PEAK
        i += 8 + size + (size & 1)
    return False


def transcribe(data: bytes, ext: str, lang: str | None, settings: Settings) -> Transcript:
    cfg = stt_config(settings)
    if cfg is None:
        raise VoiceError(503, "stt_unavailable")
    if ext == "wav" and wav_is_silent(data):
        return Transcript(text="", language=LANGS.get(lang or ""), duration_s=_wav_seconds(data), model="", provider="local-check", no_speech=True, ms=0.0)
    base_url, key = cfg
    language = LANGS.get(lang or "")
    models = [m for m in (settings.stt_model, settings.stt_fallback_model) if m]
    last: VoiceError | None = None
    for model in dict.fromkeys(models):
        try:
            return _call(base_url, key, model, data, ext, language, settings)
        except VoiceError as exc:
            last = exc
            # A bad request (our audio) or an auth problem will not improve with another model.
            if exc.code in ("audio_unreadable", "stt_auth", "audio_too_large"):
                raise
    assert last is not None
    raise last


def _call(base_url: str, key: str, model: str, data: bytes, ext: str, language: str | None, settings: Settings) -> Transcript:
    form = {"model": model, "response_format": "verbose_json", "temperature": "0"}
    if language:
        form["language"] = language
    if language == "en":
        form["prompt"] = EN_PROMPT
    t0 = time.perf_counter()
    try:
        with httpx.Client(timeout=settings.stt_timeout_s, transport=_transport) as client:
            r = client.post(
                f"{base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {key}"},
                data=form,
                files={"file": (f"speech.{ext}", data, f"audio/{ext}")},
            )
    except httpx.TimeoutException as exc:
        raise VoiceError(504, "stt_timeout") from exc
    except httpx.HTTPError as exc:
        raise VoiceError(502, "stt_failed", type(exc).__name__) from exc
    ms = round((time.perf_counter() - t0) * 1000, 1)
    if r.status_code in (401, 403):
        raise VoiceError(502, "stt_auth")
    if r.status_code == 429:
        raise VoiceError(503, "stt_busy")
    if r.status_code == 413:
        raise VoiceError(413, "audio_too_large")
    if r.status_code == 400:
        raise VoiceError(422, "audio_unreadable", _error_message(r))
    if r.status_code >= 300:
        raise VoiceError(502, "stt_failed", f"HTTP {r.status_code}")
    try:
        body = r.json()
    except ValueError as exc:
        raise VoiceError(502, "stt_failed", "invalid JSON") from exc
    text = " ".join(str(body.get("text") or "").split())
    segments = body.get("segments") or []
    no_speech = not text or text.lower() in HALLUCINATIONS or (bool(segments) and all(float(s.get("no_speech_prob") or 0) > NO_SPEECH_PROB for s in segments))
    duration = body.get("duration")
    if isinstance(duration, int | float) and duration > settings.stt_max_seconds + 1:
        raise VoiceError(413, "audio_too_long")
    return Transcript(
        text="" if no_speech else text,
        language=_iso(body.get("language")) or language,
        duration_s=round(float(duration), 2) if isinstance(duration, int | float) else None,
        model=model,
        provider="groq" if "groq.com" in base_url else "openai_compatible",
        no_speech=no_speech,
        ms=ms,
    )


# verbose_json reports the language as a name ("english", "hindi", "kannada").
_LANG_NAMES = {"english": "en", "hindi": "hi", "kannada": "kn"}


def _iso(value: object) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    v = value.strip().lower()
    return v if len(v) == 2 else _LANG_NAMES.get(v, v)


def _error_message(r: httpx.Response) -> str:
    try:
        return str(r.json().get("error", {}).get("message", ""))[:200]
    except ValueError:
        return ""
