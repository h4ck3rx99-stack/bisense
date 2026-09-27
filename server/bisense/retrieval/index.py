"""In-memory handle on the built index (embedding matrix + chunk metadata).

The vector index is a normalised float32 NumPy matrix; cosine similarity is a matrix-vector product.
For a corpus under ~100k chunks this takes milliseconds and has no moving parts.

`get_index()` reloads automatically when `bisense ingest` produces a new index_version, so the
server never needs a restart after re-indexing. SQLite connections are opened per request, so the
database file can be replaced by ingest while the server is idle.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from bisense.config import get_settings
from bisense.db import connect, get_meta


class IndexMissing(Exception):
    pass


@dataclass
class LoadedIndex:
    version: str
    matrix: np.ndarray  # (n_chunks, dim), L2-normalised
    chunk_ids: np.ndarray  # (n_chunks,) int64
    chunk_standard: np.ndarray  # (n_chunks,) standard id per row
    row_of_chunk: dict[int, int]
    dataset_mode: str
    embedding_model: str
    built_at: str
    counts: dict = field(default_factory=dict)

    def rows_for_standards(self, standard_ids: list[int]) -> np.ndarray:
        return np.flatnonzero(np.isin(self.chunk_standard, np.asarray(standard_ids)))


_lock = threading.Lock()
_current: LoadedIndex | None = None
_last_check = 0.0


def db_conn() -> sqlite3.Connection:
    """Read-only connection for one request. Raises IndexMissing if ingest has not run."""
    path = get_settings().db_path
    if not path.exists():
        raise IndexMissing("The library index has not been built yet. Run: npm run ingest")
    return connect(path, readonly=True)


def _read_version(index_dir: Path) -> str | None:
    p = index_dir / "index_version.txt"
    return p.read_text(encoding="utf-8").strip() if p.exists() else None


def get_index(force: bool = False) -> LoadedIndex:
    global _current, _last_check
    settings = get_settings()
    now = time.monotonic()
    if _current is not None and not force and now - _last_check < 2.0:
        return _current
    with _lock:
        _last_check = now
        version = _read_version(settings.index_dir)
        if version is None or not settings.db_path.exists():
            raise IndexMissing("The library index has not been built yet. Run: npm run ingest")
        if _current is not None and _current.version == version and not force:
            return _current
        matrix = np.load(settings.index_dir / "embeddings.npy")
        chunk_ids = np.load(settings.index_dir / "chunk_ids.npy")
        conn = connect(settings.db_path, readonly=True)
        try:
            std_of = dict(conn.execute("SELECT id, standard_id FROM chunks").fetchall())
            counts = {
                "standards_full_text": conn.execute("SELECT COUNT(*) FROM standards WHERE kind = 'standard'").fetchone()[0],
                "guidance": conn.execute("SELECT COUNT(*) FROM standards WHERE kind IN ('guidance', 'order')").fetchone()[0],
                "catalogue": conn.execute("SELECT COUNT(*) FROM standards WHERE kind = 'catalogue'").fetchone()[0],
                "chunks": len(chunk_ids),
                "clauses": conn.execute("SELECT COUNT(*) FROM clauses").fetchone()[0],
                "requirements": conn.execute("SELECT COUNT(*) FROM requirements").fetchone()[0],
            }
            idx = LoadedIndex(
                version=get_meta(conn, "index_version") or version,
                matrix=matrix,
                chunk_ids=chunk_ids,
                chunk_standard=np.array([std_of.get(int(c), -1) for c in chunk_ids], dtype=np.int64),
                row_of_chunk={int(c): i for i, c in enumerate(chunk_ids)},
                dataset_mode=get_meta(conn, "dataset_mode") or "unknown",
                embedding_model=get_meta(conn, "embedding_model") or "",
                built_at=get_meta(conn, "built_at") or "",
                counts=counts,
            )
        finally:
            conn.close()
        _current = idx
        return idx
