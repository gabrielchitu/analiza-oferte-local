import json
import pytest
from pathlib import Path
from shared.f3_knowledge import F3Knowledge
from shared.f3_page_classifier import _apply_end_detection


@pytest.fixture
def knowledge(tmp_path):
    data = {
        "version": 1,
        "start_markers": [
            {"pattern": "Formular F3", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "STADIUL FIZIC:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
        "end_markers": [
            {"pattern": "TOTAL CHELT. DIRECTE", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "TOTAL GENERAL pe categorie", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
    }
    p = tmp_path / "k.json"
    p.write_text(json.dumps(data))
    return F3Knowledge(path=p)


def _make_page(lines, is_f3=True, page_number=1):
    return {"is_f3": is_f3, "lines": lines, "page_number": page_number,
            "deviz_cod": "1-01", "deviz_den": "test", "header_only": False}


def test_no_end_marker_no_change(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "2 CA01A mp 10.0"], page_number=1),
        _make_page(["3 CB01A mc 5.0"], page_number=2),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert "f3_line_end" not in result[0]
    assert "f3_line_end" not in result[1]


def test_end_marker_sets_f3_line_end(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"], page_number=3),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["f3_line_end"] == 1


def test_page_after_end_becomes_non_f3(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE"], page_number=1),
        {"is_f3": True, "lines": ["text fara F3"], "page_number": 2,
         "deviz_cod": "", "header_only": False, "extraction_method": "inherited"},
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[1]["is_f3"] == False


def test_same_page_restart_detected(knowledge):
    pages = [
        _make_page([
            "1 EA02A1 buc 1.0",
            "TOTAL CHELT. DIRECTE",
            "STADIUL FIZIC: oferta 226108 CUPOLA",
            "2 CB01A mc 5.0",
        ], page_number=4),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["f3_line_end"] == 1
    assert "f3_restart_line" in result[0]
    assert result[0]["f3_restart_line"] == 2


def test_non_f3_page_unchanged(knowledge):
    pages = [
        {"is_f3": False, "lines": ["pagina titlu"], "page_number": 1,
         "deviz_cod": "", "header_only": False},
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["is_f3"] == False
    assert "f3_line_end" not in result[0]
