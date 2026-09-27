"""Lexical search with SQLite FTS5 (BM25).

User text is NEVER passed to FTS5 as query syntax. Each term is turned into a double-quoted string
(inner quotes doubled), so characters like `"`, `*`, `:`, `(`, `NEAR`, `AND` are just text.
Terms are joined with OR; multi-word glossary phrases become quoted phrases.

Note: SQLite's bm25() returns lower-is-better scores (more negative = more relevant). We negate it so
higher is better everywhere else in the code.
Column weights: text 1.0, heading 1.5, number 4.0, title 1.2.
"""

from __future__ import annotations

import re
import sqlite3


def fts_escape(term: str) -> str:
    return '"' + term.replace('"', '""') + '"'


def build_fts_query(terms: list[str]) -> str:
    """OR-joined quoted terms/phrases; returns '' if there is nothing searchable."""
    parts: list[str] = []
    seen: set[str] = set()
    for t in terms:
        t = " ".join(re.findall(r"[\wऀ-ॿಀ-೿]+", t))
        if not t or t.lower() in seen:
            continue
        seen.add(t.lower())
        parts.append(fts_escape(t))
    return " OR ".join(parts[:40])


def lexical_search(conn: sqlite3.Connection, terms: list[str], limit: int = 40, standard_ids: list[int] | None = None) -> list[tuple[int, float]]:
    q = build_fts_query(terms)
    if not q:
        return []
    sql = (
        "SELECT chunks_fts.rowid AS id, -bm25(chunks_fts, 1.0, 1.5, 4.0, 1.2) AS score "
        "FROM chunks_fts JOIN chunks ON chunks.id = chunks_fts.rowid "
        "WHERE chunks_fts MATCH ?"
    )
    params: list = [q]
    if standard_ids:
        sql += f" AND chunks.standard_id IN ({','.join('?' for _ in standard_ids)})"
        params += list(standard_ids)
    sql += " ORDER BY score DESC LIMIT ?"
    params.append(limit)
    try:
        return [(int(r["id"]), float(r["score"])) for r in conn.execute(sql, params)]
    except sqlite3.OperationalError:
        # Defensive: a malformed query must degrade to "no lexical hits", never a 500.
        return []
