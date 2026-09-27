import pytest

from bisense.stdnum import (
    base_number,
    find_all,
    normalize_standard_number,
    same_standard,
    slugify_number,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("IS 302 (Part 1) : 2008", "IS 302 (Part 1):2008"),
        ("IS302(Part1):2008", "IS 302 (Part 1):2008"),
        ("IS 302 Part 1", "IS 302 (Part 1)"),
        ("IS 302 (Pt 1)", "IS 302 (Part 1)"),
        ("IS 14543:2016", "IS 14543:2016"),
        ("IS 14543 : 2016", "IS 14543:2016"),
        ("is 14543", "IS 14543"),
        ("IS 14543", "IS 14543"),
        ("IS 1786:2008 (Reaffirmed 2018)", "IS 1786:2008"),
        ("IS/IEC 60335-1:2012", "IS/IEC 60335-1:2012"),
        ("IS / ISO 9001 : 2015", "IS/ISO 9001:2015"),
        ("IS/ISO/IEC 17025:2017", "IS/ISO/IEC 17025:2017"),
        ("IS 13252 (Part 1) : 2010", "IS 13252 (Part 1):2010"),
        ("IS 1293:2019", "IS 1293:2019"),
        ("IS 3043 (Part 2) (Sec 1)", "IS 3043 (Part 2) (Sec 1)"),
        ("DEMO-101:2026", "DEMO-101:2026"),
        ("DEMO 101", "DEMO-101"),
        ("demo-201", "DEMO-201"),
        ("See IS 4151:2015 for helmets", "IS 4151:2015"),
        ("IS 1489 (भाग 1)", "IS 1489 (Part 1)"),
    ],
)
def test_normalize(raw, expected):
    assert normalize_standard_number(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "the pH is 7", "This is 5 mg", "no numbers here", "ISO 9001"],
)
def test_no_standard(raw):
    assert normalize_standard_number(raw) is None


def test_base_number_drops_year():
    assert base_number("IS 302 (Part 1):2008") == "IS 302 (Part 1)"


def test_find_all_dedupes():
    text = "Compare IS 14543 and IS 13428:2005; IS 14543 again."
    assert [s.canonical for s in find_all(text)] == ["IS 14543", "IS 13428:2005"]


def test_same_standard_year_insensitive():
    assert same_standard("IS 1786", "IS 1786:2008")
    assert not same_standard("IS 1786:2008", "IS 1786:1985")
    assert not same_standard("IS 302 (Part 1)", "IS 302 (Part 2)")


def test_slug():
    assert slugify_number("IS 302 (Part 1):2008") == "is-302-part-1-2008"
    assert slugify_number("IS/IEC 60335-1:2012") == "is-iec-60335-1-2012"
