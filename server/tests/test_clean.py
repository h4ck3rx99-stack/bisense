from bisense.ingest.clean import (
    find_repeated_lines,
    is_watermark_line,
    join_wrapped,
    looks_like_legacy_font,
    normalize_text,
    page_is_garbled,
    strip_repeated_lines,
)


def test_watermark_lines_with_personal_data_are_detected():
    assert is_watermark_line("Supplied by Book Supply Bureau under the licence from BIS for RAM KUMAR on 12/03/2026 10.20.33 (202.54.1.2)")
    assert is_watermark_line("Licensed to: Asha Rao (asha.rao@example.com) downloaded on 2026-09-01")
    assert is_watermark_line("Supplied by the BISense demo pack to demo.user@example.com on 2026-09-27 (simulated licence line)")
    assert not is_watermark_line("The water shall be packed in clean containers.")


def test_strip_repeated_headers_footers_and_watermarks():
    pages = [
        ["IS 14543 : 2016", "4.1 The water shall be clear.", "Licensed to X (x@y.in) on 01-01-2026 1.2.3.4", "Page 1"],
        ["IS 14543 : 2016", "5.1 Containers shall be sealed.", "Licensed to X (x@y.in) on 01-01-2026 1.2.3.4", "Page 2"],
        ["IS 14543 : 2016", "6.1 Each container shall be marked.", "Licensed to X (x@y.in) on 01-01-2026 1.2.3.4", "Page 3"],
    ]
    cleaned, removed = strip_repeated_lines(pages)
    assert cleaned == [["4.1 The water shall be clear."], ["5.1 Containers shall be sealed."], ["6.1 Each container shall be marked."]]
    assert removed == 9


def test_repeated_line_detection_treats_page_numbers_alike():
    pages = [["Header", f"Page {i}", "text"] for i in range(1, 5)]
    rep = find_repeated_lines(pages)
    assert "header" in rep and "page #" in rep


def test_demo_pdf_watermark_never_reaches_the_index(built_index):
    from bisense.config import get_settings
    from bisense.db import connect

    conn = connect(get_settings().db_path, readonly=True)
    hits = conn.execute("SELECT COUNT(*) FROM chunks WHERE text LIKE '%demo.user@example.com%' OR text LIKE '%simulated licence%'").fetchone()[0]
    conn.close()
    assert hits == 0


def test_normalize_zero_width_and_ligatures():
    assert normalize_text("Grant​​of​Licence") == "Grant of Licence"
    assert normalize_text("ﬁlter  ﬂow") == "filter flow"


def test_join_wrapped_repairs_hyphenation():
    assert join_wrapped(["hermeti-", "cally sealed containers"]) == "hermetically sealed containers"
    assert join_wrapped(["The water", "shall be clear."]) == "The water shall be clear."


def test_legacy_hindi_font_detection():
    assert looks_like_legacy_font("jftLVªh laö Mhö ,yö&33004@99")
    assert looks_like_legacy_font("vlk/kj.k Hkkx II—[k.M 3")
    assert not looks_like_legacy_font("The Bureau shall be the certifying authority.")
    assert page_is_garbled(["jftLVªh laö Mhö ,yö&33004@99", "izkf/dkj ls izdkf'kr vlk/kj.k", "Hkkx II—[k.M 3—mi -[k.M (ii)"])
    assert not page_is_garbled(["This Order may be called the Helmet (Quality Control) Order.", "It shall come into force on 1 June 2021."])
