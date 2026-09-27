"""Chunking: turn clauses into retrieval units.

Rules:
  - One clause = one chunk when it is at most ~450 tokens.
  - Longer clauses are split on paragraph, then sentence, boundaries into ~250-450 token chunks with
    ~15% overlap.
  - A chunk NEVER crosses a clause boundary (so every citation points to exactly one clause).
  - Tables are their own chunks; huge tables are split by row groups repeating the header row.
  - embed_text = "{number}: {title}\n{clause path}\n{text}" -- the contextual header tells the
    embedding model which standard and section the text comes from, which improves retrieval a lot.

Token counts are approximated as words * 1.3 (no tokenizer dependency).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bisense.ingest.tables import rows_to_markdown, split_table

MAX_TOKENS = 450
TARGET_TOKENS = 350
OVERLAP_FRACTION = 0.15
CHUNKER_VERSION = "chunk-1.2"


def count_tokens(text: str) -> int:
    return int(len(text.split()) * 1.3) + 1


@dataclass
class ChunkDraft:
    text: str
    token_count: int


def _split_long(text: str) -> list[str]:
    units: list[str] = []
    for para in re.split(r"\n{2,}", text):
        if count_tokens(para) <= MAX_TOKENS:
            units.append(para)
        else:
            units.extend(s for s in re.split(r"(?<=[.;:])\s+(?=[A-Z(•])", para) if s.strip())
    chunks: list[str] = []
    cur: list[str] = []
    cur_tokens = 0
    for u in units:
        t = count_tokens(u)
        if cur and cur_tokens + t > TARGET_TOKENS:
            chunks.append("\n\n".join(cur))
            # overlap: carry the tail units worth ~15% of the target
            overlap: list[str] = []
            ot = 0
            for prev in reversed(cur):
                pt = count_tokens(prev)
                if ot + pt > TARGET_TOKENS * OVERLAP_FRACTION:
                    break
                overlap.insert(0, prev)
                ot += pt
            cur, cur_tokens = overlap, ot
        # a single unit longer than MAX_TOKENS is hard-split by words
        if t > MAX_TOKENS:
            words = u.split()
            step = int(TARGET_TOKENS / 1.3)
            for i in range(0, len(words), step):
                piece = " ".join(words[i : i + step])
                chunks.append(piece)
            continue
        cur.append(u)
        cur_tokens += t
    if cur:
        chunks.append("\n\n".join(cur))
    return [c for c in chunks if c.strip()]


def chunk_clause(text: str, table_rows: list[list[str]] | None = None, heading: str = "", max_table_rows: int = 20) -> list[ChunkDraft]:
    if table_rows:
        groups = split_table(table_rows, max_rows=max_table_rows)
        out = []
        for g in groups:
            md = rows_to_markdown(g)
            if heading:
                md = f"{heading}\n{md}"
            out.append(ChunkDraft(md, count_tokens(md)))
        return out
    text = text.strip()
    if not text:
        return []
    if count_tokens(text) <= MAX_TOKENS:
        return [ChunkDraft(text, count_tokens(text))]
    return [ChunkDraft(t, count_tokens(t)) for t in _split_long(text)]


def build_embed_text(number: str | None, title: str, path: str, text: str) -> str:
    head = f"{number}: {title}" if number else title
    return f"{head}\n{path}\n{text}"
