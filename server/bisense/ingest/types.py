"""Plain data types shared by the ingestion steps.

A parser (PDF or HTML) produces a `ParsedDoc`: document-level metadata plus an ordered list of
`ClauseDraft`s. Later steps (chunking, requirement extraction, database writing) only consume these
types, so adding a new input format means writing one new parser.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ClauseDraft:
    number: str  # exactly as printed: "4.2.1", "A-2", "Table 3", "Q4", "§2"
    heading: str
    level: int
    kind: str
    page_start: int
    page_end: int
    parent: int | None = None  # index into ParsedDoc.clauses
    paragraphs: list[str] = field(default_factory=list)
    table_rows: list[list[str]] | None = None  # set for kind == "table"

    @property
    def text(self) -> str:
        return "\n\n".join(p for p in self.paragraphs if p.strip())


@dataclass
class ParsedDoc:
    clauses: list[ClauseDraft]
    pages: int
    language: str = "en"
    detected_number: str | None = None
    detected_title: str | None = None
    detected_year: int | None = None
    reaffirmed: str | None = None
    warnings: list[str] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    garbled_pages: list[int] = field(default_factory=list)
    removed_lines: int = 0
    last_updated: str | None = None
    # For catalogue pages: product -> standard rows parsed from official lists.
    catalogue_rows: list[dict] = field(default_factory=list)


# Clause kinds used across the app (see schema.sql and the UI legend).
CLAUSE_KINDS = (
    "front",
    "foreword",
    "scope",
    "references",
    "terminology",
    "requirement",
    "test_method",
    "sampling",
    "marking",
    "packing",
    "conformity",
    "annex",
    "table",
    "amendment",
    "faq",
    "list",
    "other",
)

_KIND_KEYWORDS: list[tuple[str, str]] = [
    ("FOREWORD", "foreword"),
    ("INTRODUCTION", "foreword"),
    ("SCOPE", "scope"),
    ("REFERENCE", "references"),
    ("TERMINOLOGY", "terminology"),
    ("DEFINITION", "terminology"),
    ("TERMS", "terminology"),
    ("REQUIREMENT", "requirement"),
    ("TEST", "test_method"),
    ("METHOD", "test_method"),
    ("SAMPLING", "sampling"),
    ("CRITERIA FOR CONFORMITY", "conformity"),
    ("CONFORMITY", "conformity"),
    ("MARKING", "marking"),
    ("LABELLING", "marking"),
    ("LABELING", "marking"),
    ("PACKING", "packing"),
    ("PACKAGING", "packing"),
    ("ANNEX", "annex"),
    ("AMENDMENT", "amendment"),
]


def kind_for_heading(heading: str) -> str:
    h = heading.upper()
    for kw, kind in _KIND_KEYWORDS:
        if kw in h:
            return kind
    return "other"
