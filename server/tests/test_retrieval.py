"""Retrieval: FTS escaping, RRF, query understanding, context resolution, exact numbers, gate."""

import sqlite3

import pytest

from bisense.retrieval.fuse import apply_boosts, rrf
from bisense.retrieval.lexical import build_fts_query, fts_escape, lexical_search
from bisense.retrieval.query import ClientContext, classify_intent, understand


def test_fts_escaping_neutralises_syntax():
    assert fts_escape('a"b') == '"a""b"'
    q = build_fts_query(['") OR 1=1; DROP TABLE chunks; --', "NEAR(", "*", "col:val"])
    assert q.count('"') % 2 == 0
    assert "DROP" in q  # kept as a plain quoted term, not syntax


@pytest.mark.parametrize("evil", ['"', "NEAR(a b)", "a OR b AND", "*", "col:*", "'); DROP TABLE x; --", "(((", "^", "中文", ""])
def test_malicious_fts_input_never_errors(evil):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE VIRTUAL TABLE chunks_fts USING fts5(text, heading, number, title)")
    conn.execute("CREATE TABLE chunks (id INTEGER PRIMARY KEY, standard_id INTEGER)")
    conn.execute("INSERT INTO chunks VALUES (1, 1)")
    conn.execute("INSERT INTO chunks_fts(rowid, text, heading, number, title) VALUES (1, 'water shall be clear', '', '', '')")
    assert isinstance(lexical_search(conn, [evil, "water"]), list)


def test_rrf_rewards_agreement():
    s = rrf([[(1, 9.0), (2, 8.0), (3, 7.0)], [(3, 0.9), (1, 0.8)]])
    assert s[1] > s[3] > s[2]
    boosted = apply_boosts(s, {1: {"kind": "scope", "standard_id": 5}, 2: {"kind": "table", "standard_id": 6}, 3: {"kind": "requirement", "standard_id": 7}}, "discover", [7])
    assert boosted[1]["kind_boost"] > 0 and boosted[3]["number_boost"] > 0


@pytest.mark.parametrize(
    "q, intent",
    [
        ("Compare DEMO-101 and DEMO-102", "compare"),
        ("What does clause 4.2 say?", "clause_lookup"),
        ("What are the testing requirements?", "requirements"),
        ("Explain this standard in simple language", "summarize"),
        ("What is HUID?", "define"),
        ("Which standards apply to helmets?", "discover"),
        ("What requirements apply to my product?", "applicability"),
        ("hello", "out_of_scope"),
        ("पैकेज्ड पेयजल के लिए कौन-से BIS मानक लागू होते हैं?", "discover"),
        ("ಎರಡು ಮಾನದಂಡಗಳ ಹೋಲಿಕೆ", "compare"),
    ],
)
def test_intent_rules(q, intent):
    assert classify_intent(q) == intent


def test_context_resolution_follow_up_and_override(built_index):
    from bisense.retrieval.index import db_conn

    conn = db_conn()
    ctx = ClientContext(recent_questions=["What applies to packaged drinking water?"], focus_slugs=["demo-101-2026"])
    p = understand(conn, "What are the testing requirements?", context=ctx)
    assert p.scope_source == "context" and [s.slug for s in p.scope] == ["demo-101-2026"]
    p2 = understand(conn, "What are the testing requirements of DEMO-201?", context=ctx)
    assert p2.scope_source == "explicit" and [s.slug for s in p2.scope] == ["demo-201-2026"]
    p3 = understand(conn, "Which standards cover steel bars for concrete reinforcement in buildings?", context=ctx)
    assert p3.scope == []
    conn.close()


def test_exact_number_ranks_first(built_index):
    from bisense.retrieval.index import db_conn
    from bisense.retrieval.search import search

    conn = db_conn()
    for number, slug in [("DEMO-301", "demo-301-2026"), ("DEMO-102:2026", "demo-102-2026")]:
        res = search(conn, understand(conn, number))
        assert res.standards[0].slug == slug
    conn.close()


def test_clause_lookup_is_direct(built_index):
    from bisense.retrieval.index import db_conn
    from bisense.retrieval.search import search

    conn = db_conn()
    res = search(conn, understand(conn, "DEMO-201 clause 8.5"))
    assert res.context[0].clause_number == "8.5"
    conn.close()


def test_hindi_offline_keyword_translation(built_index):
    from bisense.retrieval.index import db_conn

    conn = db_conn()
    p = understand(conn, "पैकेज्ड पेयजल की परीक्षण आवश्यकताएँ")
    assert p.lang == "hi"
    assert "packaged drinking water" in p.english_query and "requirements" in p.english_query
    conn.close()
