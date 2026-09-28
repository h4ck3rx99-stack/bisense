"""Voice API: validation and error mapping (provider replaced by httpx.MockTransport), plus live
speech-to-text on real audio fixtures in English, Hindi and Kannada when a Groq key is configured."""

from __future__ import annotations

import json
import os
from pathlib import Path

import httpx
import pytest

from bisense.config import Settings, get_settings
from bisense.voice import stt as stt_mod
from bisense.voice import tts as tts_mod

AUDIO = Path(__file__).parent / "fixtures" / "audio"


@pytest.fixture()
def provider(monkeypatch, built_index):
    """Server STT/TTS 'configured' with a dummy key; every provider call goes to `handler`."""
    monkeypatch.setenv("STT_API_KEY", "test-key-not-real")
    monkeypatch.setenv("TTS_API_KEY", "test-key-not-real")
    get_settings.cache_clear()
    calls: list[httpx.Request] = []
    state: dict = {"handler": None}

    def dispatch(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return state["handler"](request)

    transport = httpx.MockTransport(dispatch)
    monkeypatch.setattr(stt_mod, "_transport", transport)
    monkeypatch.setattr(tts_mod, "_transport", transport)
    tts_mod.last_error.clear()
    yield state, calls
    get_settings.cache_clear()
    tts_mod.last_error.clear()


def _whisper(text: str, language: str = "english", duration: float = 3.2):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": text, "language": language, "duration": duration, "segments": [{"no_speech_prob": 0.01}]})

    return handler


def _post(client, name: str, content_type: str, lang: str | None = "en", data: bytes | None = None):
    body = data if data is not None else (AUDIO / name).read_bytes()
    form = {"lang": lang} if lang else {}
    return client.post("/api/voice/stt", files={"audio": (name, body, content_type)}, data=form)


def test_stt_unavailable_without_a_provider(client):
    r = _post(client, "en_helmet.wav", "audio/wav")
    assert r.status_code == 503 and r.json()["code"] == "stt_unavailable"


def test_stt_success_sends_language_model_and_file(client, provider):
    state, calls = provider
    state["handler"] = _whisper("Which Indian standard applies to helmets for two-wheeler riders?")
    r = _post(client, "en_helmet.webm", "audio/webm;codecs=opus", lang="en")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"].startswith("Which Indian standard") and body["language"] == "en" and not body["no_speech"]
    assert body["model"] == "whisper-large-v3-turbo"
    sent = calls[0].content
    assert b'name="language"\r\n\r\nen' in sent and b'name="model"\r\n\r\nwhisper-large-v3-turbo' in sent
    assert b'filename="speech.webm"' in sent
    assert calls[0].headers["authorization"] == "Bearer test-key-not-real"


def test_stt_hindi_and_kannada_language_mapping(client, provider):
    state, calls = provider
    state["handler"] = _whisper("नमस्ते", language="hindi")
    assert _post(client, "hi_fleurs.wav", "audio/wav", lang="hi").json()["language"] == "hi"
    state["handler"] = _whisper("ನಮಸ್ಕಾರ", language="kannada")
    assert _post(client, "kn_fleurs.wav", "audio/wav", lang="kn").json()["language"] == "kn"
    assert b'name="language"\r\n\r\nkn' in calls[-1].content


def test_stt_rejects_bad_input_before_calling_the_provider(client, provider):
    state, calls = provider
    state["handler"] = _whisper("x")
    assert _post(client, "a.txt", "text/plain", data=b"x" * 5000).json()["code"] == "audio_unsupported_type"
    assert _post(client, "tiny.webm", "audio/webm", data=b"x" * 10).json()["code"] == "audio_empty"
    big = _post(client, "big.webm", "audio/webm", data=b"x" * (get_settings().stt_max_bytes + 10))
    assert big.status_code == 413 and big.json()["code"] == "audio_too_large"
    assert _post(client, "en_helmet.wav", "audio/wav", lang="fr").status_code == 422
    # a WAV longer than the limit (header says 70 s)
    wav = bytearray((AUDIO / "silence.wav").read_bytes())
    data_at = wav.find(b"data")
    wav[data_at + 4 : data_at + 8] = (32000 * 70).to_bytes(4, "little")
    long = _post(client, "long.wav", "audio/wav", data=bytes(wav))
    assert long.status_code == 413 and long.json()["code"] == "audio_too_long"
    assert calls == []


def test_stt_silence_is_no_speech_without_a_provider_call(client, provider):
    state, calls = provider
    state["handler"] = _whisper("Thank you.")
    body = _post(client, "silence.wav", "audio/wav").json()
    assert body["no_speech"] is True and body["text"] == "" and calls == []


def test_stt_whisper_silence_hallucination_is_no_speech(client, provider):
    state, _ = provider
    state["handler"] = _whisper("Thank you.")
    body = _post(client, "en_helmet.webm", "audio/webm").json()
    assert body["no_speech"] is True and body["text"] == ""


@pytest.mark.parametrize(
    ("status", "payload", "code", "http"),
    [
        (401, {"error": {"message": "bad key"}}, "stt_auth", 502),
        (429, {"error": {"message": "slow down"}}, "stt_busy", 503),
        (400, {"error": {"message": "could not decode"}}, "audio_unreadable", 422),
        (500, {"error": {"message": "boom"}}, "stt_failed", 502),
    ],
)
def test_stt_provider_errors_map_to_stable_codes(client, provider, status, payload, code, http):
    state, _ = provider
    state["handler"] = lambda request: httpx.Response(status, json=payload)
    r = _post(client, "en_helmet.webm", "audio/webm")
    assert r.status_code == http and r.json()["code"] == code
    assert "bad key" not in r.text and "test-key" not in r.text


def test_stt_falls_back_to_the_second_model(client, provider):
    state, calls = provider

    def handler(request: httpx.Request) -> httpx.Response:
        if b"whisper-large-v3-turbo" in request.content:
            return httpx.Response(503, json={"error": {"message": "overloaded"}})
        return _whisper("fallback worked")(request)

    state["handler"] = handler
    body = _post(client, "en_helmet.webm", "audio/webm").json()
    assert body["text"] == "fallback worked" and body["model"] == "whisper-large-v3" and len(calls) == 2


def test_stt_timeout(client, provider):
    state, _ = provider

    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)

    state["handler"] = handler
    r = _post(client, "en_helmet.webm", "audio/webm")
    assert r.status_code == 504 and r.json()["code"] == "stt_timeout"


def test_tts_english_audio_and_unsupported_languages(client, provider):
    state, calls = provider
    state["handler"] = lambda request: httpx.Response(200, content=b"RIFF....WAVEfmt ", headers={"content-type": "audio/wav"})
    r = client.post("/api/voice/tts", json={"text": "BIS certification is compulsory for helmets.", "lang": "en"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav" and r.content.startswith(b"RIFF")
    assert json.loads(calls[0].content)["model"] == "canopylabs/orpheus-v1-english"
    for lang in ("hi", "kn"):
        r = client.post("/api/voice/tts", json={"text": "नमस्ते", "lang": lang})
        assert r.status_code == 422 and r.json()["code"] == "tts_language_unsupported"
    assert client.post("/api/voice/tts", json={"text": "x" * 401, "lang": "en"}).status_code == 422


def test_tts_terms_not_accepted_is_reported(client, provider):
    state, _ = provider
    state["handler"] = lambda request: httpx.Response(400, json={"error": {"code": "model_terms_required", "message": "accept terms"}})
    r = client.post("/api/voice/tts", json={"text": "Hello.", "lang": "en"})
    assert r.status_code == 503 and r.json()["code"] == "tts_terms_required"
    voice = client.get("/api/health").json()["voice"]
    assert voice["tts_problem"] == "tts_terms_required"


def test_health_reports_voice_translation_and_languages(client, provider):
    h = client.get("/api/health").json()
    assert h["voice"]["stt_available"] is True and h["voice"]["stt_languages"] == ["en", "hi", "kn"]
    assert h["voice"]["tts_languages"] == ["en"]
    assert h["languages"]["kn"] == {"ui": True, "answers": True, "stt_server": True, "tts_server": False}
    assert "test-key" not in json.dumps(h)


# ---------------------------------------------------------------------------------------------------
# Live: real audio -> Groq Whisper. Skipped without a key (CI, fresh clone).
# ---------------------------------------------------------------------------------------------------

_live = Settings(llm_provider="openai_compatible")
live = pytest.mark.skipif(os.environ.get("BISENSE_SKIP_LIVE") == "1" or stt_mod.stt_config(_live) is None, reason="no server STT key configured")


def _similar(a: str, b: str) -> float:
    """Character-level similarity (0..1) ignoring punctuation and spaces."""
    import difflib

    def norm(s: str) -> str:
        return "".join(ch for ch in s.lower() if ch.isalnum())

    return difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()


@live
@pytest.mark.parametrize(
    ("name", "lang", "expected"),
    [
        ("en_helmet.wav", "en", "Which Indian standard applies to helmets for two wheeler riders?"),
        ("en_helmet.webm", "en", "Which Indian standard applies to helmets for two wheeler riders?"),
        ("en_helmet.ogg", "en", "Which Indian standard applies to helmets for two wheeler riders?"),
        ("en_numbers.wav", "en", "What does IS 14543 say about packaged drinking water?"),
        ("hi_fleurs.wav", "hi", None),
        ("kn_fleurs.wav", "kn", None),
    ],
)
def test_live_transcription(name, lang, expected):
    data = (AUDIO / name).read_bytes()
    ext = stt_mod.validate_audio(data, None, name, _live)
    t = stt_mod.transcribe(data, ext, lang, _live)
    reference = expected or (AUDIO / name.replace(".wav", ".txt")).read_text(encoding="utf-8").strip()
    assert not t.no_speech and t.language == lang
    assert _similar(t.text, reference) >= 0.85, (t.text, reference)
    if name == "en_numbers.wav":
        assert "14543" in t.text


@live
def test_live_silence_is_no_speech():
    data = (AUDIO / "silence.wav").read_bytes()
    assert stt_mod.transcribe(data, "wav", "en", _live).no_speech
