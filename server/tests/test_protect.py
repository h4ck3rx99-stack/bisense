import pytest

from bisense.i18n.protect import protect, restore


def test_round_trip_example_from_brief():
    s = "IS 302 (Part 1):2008 clause 5.2.3 requires ≤ 0.5 mg/l"
    masked, originals = protect(s)
    assert "302" not in masked and "5.2.3" not in masked and "0.5" not in masked
    assert restore(masked, originals) == s


def test_protects_citations_tables_and_glossary_terms():
    s = "Table 1 of DEMO-101:2026 lists pH 6.5 to 8.5 [C2]; BIS grants the Standard Mark."
    masked, originals = protect(s)
    for token in ["Table 1", "DEMO-101:2026", "[C2]", "BIS", "Standard Mark"]:
        assert token in originals or any(token in o for o in originals)
    assert restore(masked, originals) == s


def test_restore_rejects_missing_or_duplicated_placeholders():
    masked, originals = protect("IS 14543 limits TDS to 500 mg/l")
    assert len(originals) >= 2
    with pytest.raises(ValueError):
        restore(masked.replace("⟦0⟧", ""), originals)
    with pytest.raises(ValueError):
        restore(masked + " ⟦0⟧", originals)


def test_translated_text_keeps_western_digits():
    masked, originals = protect("Coliform bacteria shall be absent in any 250 ml sample")
    hindi = masked.replace("Coliform bacteria shall be absent in any", "किसी भी").replace("sample", "नमूने में कोलीफॉर्म बैक्टीरिया अनुपस्थित होंगे")
    assert "250 ml" in restore(hindi, originals)
