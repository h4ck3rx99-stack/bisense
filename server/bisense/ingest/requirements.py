"""Deterministic requirement extraction (no LLM).

We split requirement-bearing clauses into sentences and classify each sentence's modality by the
verbal forms used in standards drafting:
    "shall"  -> a requirement of the document
    "should" -> a recommendation
    "may"    -> a permission
    "must"   -> treated like "shall" but kept distinct (appears in orders and guidelines)
Precedence when a sentence contains several: shall not > shall > should not > should > may > must.

This is a statement about what the *document* says. Whether the product is legally required to be
certified is a separate question answered only by official orders (see catalogue.py and the UI).
"""

from __future__ import annotations

import re

REQUIREMENT_KINDS = {"requirement", "test_method", "marking", "packing", "sampling", "conformity", "annex", "table", "other", "faq"}

_MODAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("shall_not", re.compile(r"\bshall\s+not\b|\bshall\s+neither\b", re.I)),
    ("shall", re.compile(r"\bshall\b", re.I)),
    ("should_not", re.compile(r"\bshould\s+not\b", re.I)),
    ("should", re.compile(r"\bshould\b", re.I)),
    ("may", re.compile(r"\bmay\b(?!\s+be\s+called)", re.I)),
    ("must", re.compile(r"\bmust\b", re.I)),
]

# Split after . ; or : followed by space + capital/bullet, but not after "No.", "e.g.", "i.e.", "Cl." etc.
_ABBREV = r"(?<!\bNo)(?<!\be\.g)(?<!\bi\.e)(?<!\bCl)(?<!\bSec)(?<!\bFig)(?<!\bvs)(?<!\bS\.O)(?<!\bdt)(?<!\bMax)(?<!\bMin)"
_SENT_SPLIT = re.compile(_ABBREV + r"(?<=[.;])\s+(?=[A-Z(•\"'])")


def classify_modality(sentence: str) -> str | None:
    for name, pat in _MODAL_PATTERNS:
        if pat.search(sentence):
            return name
    return None


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for para in re.split(r"\n{2,}", text):
        para = " ".join(para.split())
        if not para or para.startswith("|"):
            continue
        for s in _SENT_SPLIT.split(para):
            s = s.strip()
            if len(s) >= 12:
                out.append(s)
    return out


def extract_requirements(clause_text: str, clause_kind: str, doc_kind: str) -> list[tuple[str, str]]:
    """Return (sentence, modality) pairs for one clause.

    For standards we look at requirement-type clauses; for official orders and guidelines every
    clause may carry obligations, so all clauses are scanned. Definitions, forewords, scopes and
    reference lists never produce requirements.
    """
    if clause_kind in {"foreword", "terminology", "references", "scope", "front", "amendment", "list"}:
        return []
    if doc_kind == "standard" and clause_kind not in REQUIREMENT_KINDS:
        return []
    results = []
    for s in split_sentences(clause_text):
        modality = classify_modality(s)
        if modality:
            results.append((s, modality))
    return results
