"""Local speech-to-text (Whisper on this computer, no key): real audio through /api/voice/stt.

Skipped unless the local model is already downloaded (`npm run setup` does it; ~460 MB), so CI never
downloads it. Measured quality decided the languages offered locally: English and Hindi, not Kannada.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bisense.config import REPO_ROOT, get_settings
from bisense.voice import local_stt_installed

AUDIO = Path(__file__).parent / "fixtures" / "audio"
MODEL_DIR = REPO_ROOT / "data" / "models" / "whisper"

pytestmark = pytest.mark.skipif(
    not local_stt_installed() or not any(MODEL_DIR.glob("models--Systran--faster-whisper-small")),
    reason="local Whisper model not downloaded (npm run setup)",
)


@pytest.fixture()
def local(monkeypatch, built_index):
    monkeypatch.setenv("STT_PROVIDER", "local")
    monkeypatch.setenv("MODEL_CACHE_DIR", str(REPO_ROOT / "data" / "models"))
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def _stt(client, name: str, ctype: str, lang: str):
    return client.post("/api/voice/stt", files={"audio": (name, (AUDIO / name).read_bytes(), ctype)}, data={"lang": lang})


def test_status_reports_local_languages(client, local):
    v = client.get("/api/voice/status").json()
    assert v["stt_available"] and v["stt_provider"] == "local" and v["stt_languages"] == ["en", "hi"]


def test_english_browser_recording(client, local):
    r = _stt(client, "en_helmet.webm", "audio/webm;codecs=opus", "en")
    assert r.status_code == 200, r.text
    body = r.json()
    text = body["text"].lower().replace("-", " ")  # Whisper writes "two wheeler" or "two-wheeler"
    assert body["provider"] == "local" and "helmet" in text and "two wheeler" in text


def test_hindi_in_devanagari(client, local):
    body = _stt(client, "hi_fleurs.wav", "audio/wav", "hi").json()
    assert "प्लांट" in body["text"] or "प्लाँट" in body["text"]
    assert any("ऀ" <= ch <= "ॿ" for ch in body["text"])


def test_kannada_refused_locally_instead_of_garbage(client, local):
    r = _stt(client, "kn_fleurs.wav", "audio/wav", "kn")
    assert r.status_code == 422 and r.json()["code"] == "stt_language_unsupported"


def test_silence_is_no_speech(client, local):
    body = _stt(client, "silence.wav", "audio/wav", "en").json()
    assert body["no_speech"] and body["text"] == ""
