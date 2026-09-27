"""Shared API helpers: error type with stable codes, rate limiting, database dependency.

Errors never expose stack traces. Each error has a stable `code` and an i18n `message_key` that the
frontend maps to a translated message.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from collections import deque
from collections.abc import Iterator

from fastapi import Request

from bisense.retrieval.index import IndexMissing, db_conn


class ApiError(Exception):
    def __init__(self, status: int, code: str, message_key: str | None = None):
        self.status = status
        self.code = code
        self.message_key = message_key or f"error.{code}"


def get_db() -> Iterator[sqlite3.Connection]:
    try:
        conn = db_conn()
    except IndexMissing as exc:
        raise ApiError(503, "no_index") from exc
    try:
        yield conn
    finally:
        conn.close()


class RateLimiter:
    """Sliding-window limit per client IP, e.g. "20/minute". In-memory: fine for one process."""

    def __init__(self, spec: str):
        count, _, unit = spec.partition("/")
        self.limit = int(count)
        self.window = {"second": 1, "minute": 60, "hour": 3600}.get(unit.strip().lower(), 60)
        self.hits: dict[str, deque[float]] = {}
        self.lock = threading.Lock()

    def check(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            q = self.hits.setdefault(ip, deque())
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise ApiError(429, "rate_limited")
            q.append(now)
