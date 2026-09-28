"""Answer cache (SQLite table `answer_cache`).

Key = hash(normalised question, language, resolved scope, intent, index_version, PROMPT_VERSION),
so any change to the library or the prompt invalidates old answers automatically.

  source = "live"   -- stored after a successful live answer
  source = "warmed" -- produced by `npm run warm` running the same live pipeline ahead of a demo
Cached answers are always real pipeline outputs, never hand-written.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import UTC, datetime

from bisense.config import get_settings
from bisense.db import connect

PROMPT_VERSION = "answer_v2.1"

# Set by `bisense warm` so entries it produces are labelled "warmed" (still real pipeline outputs).
WARMING = False


def cache_key(kind: str, question: str, lang: str, scope: list[str], intent: str, index_version: str) -> str:
    raw = json.dumps([kind, " ".join(question.lower().split()), lang, sorted(scope), intent, index_version, PROMPT_VERSION])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def _conn() -> sqlite3.Connection:
    return connect(get_settings().db_path)


def _disabled() -> bool:
    # A FakeLLM's canned answers (tests, e2e) must never enter or be served from the real cache.
    return get_settings().llm_provider == "fake"


def get_cached(key: str) -> tuple[dict, str, str] | None:
    """(payload, source, created_at) or None."""
    if _disabled():
        return None
    try:
        conn = _conn()
        try:
            row = conn.execute("SELECT payload_json, source, created_at FROM answer_cache WHERE key = ?", (key,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return json.loads(row["payload_json"]), row["source"], row["created_at"]


def put_cached(key: str, payload: dict, lang: str, index_version: str, source: str = "live") -> None:
    if _disabled():
        return
    if WARMING:
        source = "warmed"
    try:
        conn = _conn()
        try:
            conn.execute(
                "INSERT INTO answer_cache(key, payload_json, lang, index_version, prompt_version, source, created_at) VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET payload_json = excluded.payload_json, source = excluded.source, created_at = excluded.created_at",
                (key, json.dumps(payload, ensure_ascii=False), lang, index_version, PROMPT_VERSION, source, datetime.now(UTC).isoformat(timespec="seconds")),
            )
            conn.commit()
        finally:
            conn.close()
    except sqlite3.Error:
        pass  # caching is best-effort; never fail a request because of it
