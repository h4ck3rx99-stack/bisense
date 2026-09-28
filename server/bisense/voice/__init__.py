"""Server-side speech: speech-to-text (Whisper via an OpenAI-compatible API, e.g. Groq) and text-to-speech.

Keys stay on the server. Every failure maps to a stable error code the UI can explain; the browser's own
speech features are the fallback where they exist.
"""

from __future__ import annotations

from urllib.parse import urlparse

from bisense.config import Settings

GROQ_HOST = "api.groq.com"


class VoiceError(Exception):
    """A voice failure with a stable code (e.g. "stt_unavailable") and an HTTP status for the API."""

    def __init__(self, status: int, code: str, detail: str = ""):
        super().__init__(detail or code)
        self.status = status
        self.code = code
        self.detail = detail


def resolve_key(settings: Settings, base_url: str, explicit_key: str) -> str:
    """The key for a voice endpoint: its own, or the LLM key when both point at the same host."""
    if explicit_key:
        return explicit_key
    if settings.llm_api_key and urlparse(settings.llm_base_url).hostname == urlparse(base_url).hostname:
        return settings.llm_api_key
    return ""


def stt_config(settings: Settings) -> tuple[str, str] | None:
    """(base_url, key) when server STT is usable, else None."""
    if settings.stt_provider == "none" or settings.llm_provider == "fake" and not settings.stt_api_key:
        return None
    key = resolve_key(settings, settings.stt_base_url, settings.stt_api_key)
    return (settings.stt_base_url.rstrip("/"), key) if key and settings.stt_base_url else None


def tts_config(settings: Settings) -> tuple[str, str] | None:
    if settings.tts_provider == "none" or settings.llm_provider == "fake" and not settings.tts_api_key:
        return None
    key = resolve_key(settings, settings.tts_base_url, settings.tts_api_key)
    return (settings.tts_base_url.rstrip("/"), key) if key and settings.tts_base_url else None


def tts_languages(settings: Settings) -> list[str]:
    return [x.strip() for x in settings.tts_languages.split(",") if x.strip()] if tts_config(settings) else []
