import pytest
from docx import Document
from shared.report_word import _count_main_articles, _add_group_totals_row, GRAY_FILL


def test_count_main_articles_empty():
    assert _count_main_articles([]) == 0


def test_count_main_articles_all_main():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A02"},  # missing key → not a component
        {"cod": "A03", "is_component": False},
    ]
    assert _count_main_articles(articles) == 3


def test_count_main_articles_filters_components():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A01-sub1", "is_component": True},
        {"cod": "A01-sub2", "is_component": True},
        {"cod": "A02", "is_component": False},
    ]
    assert _count_main_articles(articles) == 2


def test_count_main_articles_all_components():
    articles = [
        {"cod": "X01", "is_component": True},
        {"cod": "X02", "is_component": True},
    ]
    assert _count_main_articles(articles) == 0


# ── Tests for _add_group_totals_row ────────────────────────────────────────


def _make_table(doc):
    """11-column table with one data row."""
    table = doc.add_table(rows=1, cols=11)
    return table


def _get_shading_fill(cell):
    """Extract fill hex from cell shading XML, or None."""
    tc = cell._tc
    tcPr = tc.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcPr"
    )
    if tcPr is None:
        return None
    shd = tcPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"
    )
    if shd is None:
        return None
    return shd.get(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill"
    )


def test_add_group_totals_row_matched_adds_one_row():
    doc = Document()
    table = _make_table(doc)
    initial_count = len(table.rows)
    _add_group_totals_row(table, ref_count=10, oferta_count=8)
    assert len(table.rows) == initial_count + 1


def test_add_group_totals_row_matched_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=10, oferta_count=8)
    row = table.rows[-1]
    # After merge, cell 0 = label, cell 2 = ref text, cell 6 = offer text
    label_text = row.cells[0].text
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert "TOTAL" in label_text
    assert "10" in ref_text
    assert "8" in offer_text


def test_add_group_totals_row_ref_only_no_offer_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=5, oferta_count=None)
    row = table.rows[-1]
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert "5" in ref_text
    assert offer_text.strip() == ""


def test_add_group_totals_row_oferta_only_no_ref_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=None, oferta_count=7)
    row = table.rows[-1]
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert ref_text.strip() == ""
    assert "7" in offer_text
