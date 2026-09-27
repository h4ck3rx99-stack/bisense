"""SQLite connection helpers and schema setup.

Why SQLite: a single file, zero operations, ships with Python, and FTS5 gives us BM25 lexical search.
All queries in the codebase use `?` parameters; never build SQL with user text.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path, readonly: bool = False) -> sqlite3.Connection:
    """Open the database. Read-only connections are used by the API so requests never write by accident
    (except the answer cache, which uses a normal connection)."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if readonly:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
    else:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.OperationalError:
        return default
    return row["value"] if row else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO meta(key, value) VALUES(?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def loads(value: str | None, default: Any) -> Any:
    """Decode a *_json column safely."""
    if not value:
        return default
    try:
        return json.loads(value)
    except ValueError:
        return default
