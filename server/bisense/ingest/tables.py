"""Table helpers: convert extracted table rows to Markdown and split large tables.

Tables in standards carry the critical numeric limits, so values are copied cell-for-cell
(only whitespace is tidied). Large tables are split into row groups that repeat the header row,
so every chunk is self-explanatory when shown as evidence.
"""

from __future__ import annotations


def _cell(text: str) -> str:
    return " ".join(str(text or "").split()).replace("|", "/")


def rows_to_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    norm = [[_cell(c) for c in r] + [""] * (width - len(r)) for r in rows]
    header, body = norm[0], norm[1:]
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def markdown_to_rows(md: str) -> list[list[str]]:
    rows = []
    for line in md.splitlines():
        line = line.strip()
        if not line.startswith("|") or set(line) <= set("|-: "):
            continue
        rows.append([c.strip() for c in line.strip("|").split("|")])
    return rows


def split_table(rows: list[list[str]], max_rows: int = 25) -> list[list[list[str]]]:
    """Split a table (header + body rows) into groups of at most `max_rows` body rows, repeating the header."""
    if len(rows) <= max_rows + 1:
        return [rows]
    header, body = rows[0], rows[1:]
    return [[header] + body[i : i + max_rows] for i in range(0, len(body), max_rows)]
