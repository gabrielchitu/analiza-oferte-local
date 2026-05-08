"""
Tests pentru clasificarea paginilor ISDP in f3_page_classifier.

Problema: Pagina de copertina ISDP are structura:
  ...
  STADIUL FIZIC:
  oferta 226108 STRUCTURA DE REZISTENTA CUPOLA

'oferta' apare pe o linie separata dupa 'STADIUL FIZIC:'.
_STADIUL_FIZIC_EDEVIZE_RE cu re.IGNORECASE captura 'oferta' (6 litere) ca
deviz_cod in loc de '226108'. Aceasta face ca pagina sa fie clasificata cu
deviz_cod='OFERTA' si sa fie filtrata (nu apare in referinta).

Fix: pattern-ul trebuie sa ceara cel putin 4 cifre in deviz_cod
(toate codurile valide au >= 4 cifre; 'oferta' nu are niciuna).
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


# Pagina cover ISDP cu STADIUL FIZIC pe doua linii separate
_ISDP_COVER_TWO_LINE_STADIUL = [
    "Pag 13",
    "OBIECTIV:",
    "SCN1164693 - 0226 45000000 EXTINDERE SI",
    "MODERNIZARE BAZA SPORTIVA RACARI",
    "OBIECTUL:",
    "0001 45000000 TEREN DE TENIS ACOPERIT",
    "STADIUL FIZIC:",           # ← linia 6: doar "STADIUL FIZIC:"
    "oferta 226108 STRUCTURA DE REZISTENTA CUPOLA",  # ← linia 7: codul pe urmatoarea linie
    "Beneficiar:",
    "Proiectant:",
    "Executant:",
    "F3 - LISTA cu cantitati de lucrari pe categorii de lucrari",
    "10.07.2025",
    "SECTIUNEA TEHNICA",
    "SECTIUNEA FINANCIARA",
    "Nr.",
    "Capitolul de lucrari",
    "U.M.",
    "Cantitatea",
    "Pretul unitar",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5 = 3 x 4",
    "8",             # articol 8 (pagina cover are si date)
    "CB01A1",
    "COFRAJE IN CUZINETI FUND PAHAR",
    "mp",
    "200,00",
    "62,44",
    "12.488,40",
]


def test_isdp_cover_two_line_stadiul_classified_as_f3():
    """Pagina ISDP cu STADIUL FIZIC pe doua linii trebuie clasificata ca F3."""
    result = classify_page_local(_make_page(_ISDP_COVER_TWO_LINE_STADIUL))
    assert result["label"] == "F3", f"Expected F3, got {result['label']}"


def test_isdp_cover_extracts_6digit_code_not_oferta():
    """deviz_cod trebuie sa fie '226108', NU 'OFERTA'."""
    result = classify_page_local(_make_page(_ISDP_COVER_TWO_LINE_STADIUL))
    assert result["deviz_cod"] == "226108", \
        f"Expected '226108', got '{result['deviz_cod']}'"


def test_isdp_cover_not_header_when_has_articles():
    """Pagina cu articole nu e header_only."""
    result = classify_page_local(_make_page(_ISDP_COVER_TWO_LINE_STADIUL))
    assert not result.get("is_header"), "Cover with articles should not be header_only"


def test_isdp_data_page_extracts_deviz_from_first_line():
    """Pagina de date ISDP cu 'STADIUL FIZIC: oferta 226108...' pe o singura linie."""
    lines = [
        "Pag 14",
        "STADIUL FIZIC: oferta 226108 STRUCTURA DE REZISTENTA CUPOLA",
        "0",
        "1",
        "2",
        "8",
        "CB01A1",
        "COFRAJE IN CUZINETI",
        "mp",
        "200,00",
    ]
    result = classify_page_local(_make_page(lines))
    assert result["label"] == "F3", f"Expected F3, got {result['label']}"
    assert result["deviz_cod"] == "226108", \
        f"Expected '226108', got '{result['deviz_cod']}'"
