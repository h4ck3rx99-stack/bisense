"""Ingestion: structure, tables, chunking, requirements, idempotency, corrupt files."""

from pathlib import Path

import pytest

from bisense.ingest.chunk import MAX_TOKENS, chunk_clause, count_tokens
from bisense.ingest.pdf_parse import IngestError, RawLine, extract_pdf
from bisense.ingest.requirements import classify_modality, extract_requirements, split_sentences
from bisense.ingest.structure import build_clauses
from bisense.ingest.tables import markdown_to_rows, rows_to_markdown, split_table

DEMO = Path(__file__).resolve().parents[2] / "data" / "demo" / "pdf"


def L(text, bold=False, size=10.0, x0=56.0, page=1):  # noqa: N802 (test helper)
    return RawLine(text=text, page=page, size=size, bold=bold, x0=x0, y0=0)


def test_clause_tree_numbering_and_kinds():
    lines = [
        L("FOREWORD", bold=True, size=12),
        L("This is a foreword."),
        L("1 SCOPE", bold=True),
        L("1.1 This standard covers widgets."),
        L("4 REQUIREMENTS", bold=True),
        L("4.1 General", bold=True),
        L("4.1.1 The widget shall be blue."),
        L("4.2 Marking - Each widget shall be marked."),
    ]
    clauses = build_clauses([lines])
    nums = [c.number for c in clauses]
    assert nums == ["Foreword", "1", "1.1", "4", "4.1", "4.1.1", "4.2"]
    by = {c.number: c for c in clauses}
    assert by["1.1"].kind == "scope"
    assert by["4.1.1"].kind == "requirement"
    assert by["4.1"].heading == "General"
    assert by["4.2"].heading == "Marking" and by["4.2"].text == "Each widget shall be marked."
    assert clauses[by["4.1.1"].parent].number == "4.1"


def test_wrapped_line_number_is_not_a_new_clause():
    """Regression: "... as prescribed in clause" + "8." on the next line must not create clause 8."""
    lines = [
        L("4 REQUIREMENTS", bold=True),
        L("4.4 The helmet shall meet the requirements given in Table 1 when tested as prescribed in clause"),
        L("8."),
        L("5 PACKING", bold=True),
        L("5.1 Each helmet shall be packed in a carton."),
    ]
    nums = [c.number for c in build_clauses([lines])]
    assert "8" not in nums and "5" in nums and "5.1" in nums


def test_wrapped_number_with_unit_is_not_a_clause():
    lines = [L("4 REQUIREMENTS", bold=True), L("4.3 Coliform bacteria shall be absent in any"), L("250 ml sample of the water.")]
    nums = [c.number for c in build_clauses([lines])]
    assert nums == ["4", "4.3"]


def test_demo_pdf_structure_and_table_values_survive():
    parsed = extract_pdf(DEMO / "DEMO-101.pdf")
    tables = [ln for page in parsed.pages for ln in page if ln.is_table]
    md = "\n".join(t.table_md for t in tables)
    assert "| iv | Total dissolved solids, Max | mg/l | 500 | Clause 8.4 |" in md
    assert "6.5 to 8.5" in md


def test_table_markdown_round_trip_and_split_repeats_header():
    rows = [["Characteristic", "Requirement"], ["pH", "6.5 to 8.5"], ["Lead | Pb", "0.01"]]
    md = rows_to_markdown(rows)
    assert markdown_to_rows(md) == [["Characteristic", "Requirement"], ["pH", "6.5 to 8.5"], ["Lead / Pb", "0.01"]]
    big = [["h1", "h2"]] + [[str(i), "x"] for i in range(45)]
    parts = split_table(big, max_rows=20)
    assert len(parts) == 3 and all(p[0] == ["h1", "h2"] for p in parts)


def test_chunks_respect_size_and_never_cross_clauses():
    long = " ".join(f"Sentence {i} states that the product shall comply." for i in range(200))
    chunks = chunk_clause(long)
    assert len(chunks) > 1
    assert all(c.token_count <= MAX_TOKENS + 20 for c in chunks)
    short = chunk_clause("One clause only.")
    assert len(short) == 1 and short[0].text == "One clause only."
    assert count_tokens("a b c") == 4


def test_every_chunk_belongs_to_one_clause(built_index):
    from bisense.config import get_settings
    from bisense.db import connect

    conn = connect(get_settings().db_path, readonly=True)
    bad = conn.execute(
        "SELECT COUNT(*) FROM chunks ch JOIN clauses cl ON cl.id = ch.clause_id WHERE instr(cl.text, substr(ch.text, 1, 40)) = 0 AND cl.kind NOT IN ('table', 'list')"
    ).fetchone()[0]
    conn.close()
    assert bad == 0


@pytest.mark.parametrize(
    "sentence, expected",
    [
        ("The water shall not be treated with colour.", "shall_not"),
        ("The water shall comply with Table 1.", "shall"),
        ("Pouches should not be exposed to sunlight.", "should_not"),
        ("Pouches should be packed in cartons.", "should"),
        ("Containers may be reused after cleaning.", "may"),
        ("The applicant must submit Form V.", "must"),
        ("The shell shall not exceed 5 mm and may be coloured.", "shall_not"),
        ("This Order may be called the Helmet Order.", None),
        ("Colour is measured visually.", None),
    ],
)
def test_modality_precedence(sentence, expected):
    assert classify_modality(sentence) == expected


def test_requirement_extraction_skips_definitions_and_splits_sentences():
    text = "The water shall be clear. It should be cold; containers may be reused. Containers may be returned."
    # "should ...; ... may ..." is one sentence: precedence gives SHOULD.
    assert [m for _, m in extract_requirements(text, "requirement", "standard")] == ["shall", "should", "may"]
    assert extract_requirements("Batch means all containers that shall be packed.", "terminology", "standard") == []
    assert split_sentences("Sample No. 5 of Table 1 applies. The value shall be 2.") == ["Sample No. 5 of Table 1 applies.", "The value shall be 2."]


def test_ingest_is_idempotent(built_index):
    from bisense.config import get_settings
    from bisense.ingest.pipeline import run_ingest

    again = run_ingest(get_settings(), dataset="demo", log=lambda *_: None)
    assert again["index_version"] == built_index["report"]["index_version"]


def test_corrupt_and_non_pdf_files_fail_clearly(tmp_path):
    bad = tmp_path / "fake.pdf"
    bad.write_text("this is not a pdf", encoding="utf-8")
    with pytest.raises(IngestError, match="not a PDF"):
        extract_pdf(bad)
    empty = tmp_path / "empty.pdf"
    empty.write_bytes(b"")
    with pytest.raises(IngestError, match="empty"):
        extract_pdf(empty)
    broken = tmp_path / "broken.pdf"
    broken.write_bytes(b"%PDF-1.7\n garbage garbage")
    with pytest.raises(IngestError):
        extract_pdf(broken)


def test_short_category_names_from_official_list_headings():
    from bisense.ingest.catalogue import short_category

    qco_history = "Footwear made from all-Rubber and all Polymeric material and its components (Quality Control) Order, 2020 \n (S.O. No. 3858 (E) 27/10/2020) \n more orders ..."
    assert short_category(qco_history) == "Footwear made from all-Rubber and all Polymeric material and its components"
    assert short_category("Steel and Iron Products") == "Steel and Iron Products"
    long = short_category("1. List of Electronics and IT Goods under the Compulsory Registration Scheme for Self Declaration of conformity notified by MeitY")
    assert long.startswith("Electronics and IT Goods") and len(long) <= 81 and long.endswith("…")
