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


def local_stt_installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except Exception:
        return False
    return True


def stt_mode(settings: Settings) -> str | None:
    """ "remote" (OpenAI-compatible API, e.g. Groq), "local" (Whisper on this computer) or None."""
    if settings.stt_provider == "none":
        return None
    if settings.stt_provider == "local":
        return "local" if local_stt_installed() else None
    if stt_config(settings) is not None:
        return "remote"
    # auto without a key: local Whisper (not in tests with the fake LLM, which must never load a model)
    if settings.stt_provider == "auto" and settings.llm_provider != "fake" and local_stt_installed():
        return "local"
    return None


def stt_languages(settings: Settings) -> list[str]:
    mode = stt_mode(settings)
    if mode == "remote":
        return ["en", "hi", "kn"]
    if mode == "local":
        return [x.strip() for x in settings.stt_local_languages.split(",") if x.strip()]
    return []


def stt_config(settings: Settings) -> tuple[str, str] | None:
    """(base_url, key) when server STT is usable, else None."""
    # With the fake test LLM, "auto" never reaches a real provider; an explicit provider still does
    # (the fake-microphone e2e test sets STT_PROVIDER=openai_compatible).
    if settings.stt_provider in ("none", "local") or (settings.stt_provider == "auto" and settings.llm_provider == "fake" and not settings.stt_api_key):
        return None
    key = resolve_key(settings, settings.stt_base_url, settings.stt_api_key)
    return (settings.stt_base_url.rstrip("/"), key) if key and settings.stt_base_url else None


def tts_config(settings: Settings) -> tuple[str, str] | None:
    if settings.tts_provider == "none" or (settings.tts_provider == "auto" and settings.llm_provider == "fake" and not settings.tts_api_key):
        return None
    key = resolve_key(settings, settings.tts_base_url, settings.tts_api_key)
    return (settings.tts_base_url.rstrip("/"), key) if key and settings.tts_base_url else None


def tts_languages(settings: Settings) -> list[str]:
    return [x.strip() for x in settings.tts_languages.split(",") if x.strip()] if tts_config(settings) else []
