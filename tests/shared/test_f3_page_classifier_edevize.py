"""
Tests pentru clasificarea paginilor eDevize in f3_page_classifier.

Problema: paginile de date eDevize au in footer:
  'Deviz "001" - Formular F3 Formular generat cu programul @Devize'

Clasificatorul detecta _FORMULAR_F3_RE pe footer si extragea "001"
(numarul capitolului) in loc de deviz_cod-ul 6-cifre corect.

Fix: _SECTIUNEA_TEHNICA_RE trebuie verificata INAINTE de _FORMULAR_F3_RE.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.f3_page_classifier import classify_page_local


def _make_page(lines, page_number=1):
    return {
        "page_number": page_number,
        "lines": [{"content": l} for l in lines],
    }


# Pagina de date eDevize cu footer 'Deviz "001" - Formular F3'
_EDEVIZE_DATA_PAGE_LINES = [
    "Antet stanga",
    "eDevize",
    "SECTIUNEA TEHNICA",
    "SECTIUNEA FINANCIARA",
    "Nr.",
    "Capitol de lucrari",
    "U.M.",
    "Cantitatea",
    "Pretul unitar",
    "(fara TVA)",
    "- Lei -",
    "TOTALUL",
    "(fara TVA)",
    "- Lei -",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5 = 3 x 4",
    "7",
    "CA02A1 - TURNARE BETON ARMAT IN FUNDATII IZOLATE CU VOLUM < 3MC",
    "M.C.",
    "55.000",
    "111.92",
    "6,155.34",
    "material:",
    "0.99",
    "54.45",
    # Footer eDevize (sursa bug-ului)
    'Deviz "001" - Formular F3 Formular generat cu programul @Devize',
]


def test_edevize_data_page_classified_as_f3():
    """Pagina de date eDevize trebuie sa fie F3."""
    result = classify_page_local(_make_page(_EDEVIZE_DATA_PAGE_LINES))
    assert result["label"] == "F3", f"Expected F3, got {result['label']}"


def test_edevize_data_page_deviz_cod_empty():
    """Pagina de date eDevize (fara 'Stadiul fizic:') nu are deviz_cod propriu — propagat din cover."""
    result = classify_page_local(_make_page(_EDEVIZE_DATA_PAGE_LINES))
    assert result["deviz_cod"] == "", \
        f"Expected empty deviz_cod (propagat din cover), got '{result['deviz_cod']}'"


def test_edevize_data_page_not_extracting_chapter_number_as_cod():
    """Footer-ul 'Deviz \"001\"' NU trebuie sa devina deviz_cod."""
    result = classify_page_local(_make_page(_EDEVIZE_DATA_PAGE_LINES))
    assert result["deviz_cod"] != "001", \
        f"Footer chapter number '001' was incorrectly extracted as deviz_cod"


def test_edevize_data_page_not_header():
    """Pagina de date eDevize cu articole NU e header_only."""
    result = classify_page_local(_make_page(_EDEVIZE_DATA_PAGE_LINES))
    assert not result.get("is_header"), "Data page should not be header_only"
