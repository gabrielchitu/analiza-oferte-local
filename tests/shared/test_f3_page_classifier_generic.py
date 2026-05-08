"""
Tests pentru robustete generica a clasificatorului de pagini.

Doua probleme independente de format:

1. Recapitulatia mixta: ultima pagina de date a unui deviz contine
   atat articole CAT SI o sectiune 'Recapitulatia:' la final.
   Clasificatorul marcheaza gresit pagina ca NON_F3.
   Fix generic: Recapitulatia => NON_F3 NUMAI daca NU are coduri articol.

2. STADIUL FIZIC cu linii OCR intercalate: OCR poate insera linii extra
   (ex: 'Beneficiar:', 'Executant:') intre 'STADIUL FIZIC:' si codul deviz.
   Regex-ul exact nu mai gaseste codul => pagina devine AMBIGUOUS.
   Fix generic: cauta codul deviz in fereastra de N linii dupa STADIUL FIZIC.
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


# ─── Test 1: Recapitulatia pe ultima pagina de date ─────────────────────────

_LAST_DATA_PAGE_WITH_RECAPITULATIE = [
    "Pag 50",
    "STADIUL FIZIC: oferta 226288 SISTEM SUPRAVEGHEREA VIDEO",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5 = 3 x 4",
    "6",
    "TCB40D1",
    "APARAT TELEGR. RECEPTOR PERFORATOR",
    "buc",
    "1,00",
    "580,93",
    "580,93",
    "material:",
    "53,49",
    "53,49",
    "manopera:",
    "527,44",
    "527,44",
    "utilaj:",
    "0,00",
    "0,00",
    "transport:",
    "0,00",
    "0,00",
    # Sectiunea Recapitulatia la finalul paginii
    "Recapitulatia:",
    "Valoare",
    "Material",
    "Manopera",
    "Cheltuieli directe:",
    "580,93",
    "53,49",
    "527,44",
    "0,00",
    "0,00",
]


def test_data_page_with_trailing_recapitulatia_is_f3():
    """O pagina cu articole SI Recapitulatia la final trebuie sa fie F3."""
    result = classify_page_local(_make_page(_LAST_DATA_PAGE_WITH_RECAPITULATIE))
    assert result["label"] == "F3", \
        f"Expected F3 (page has article codes), got {result['label']}"


def test_data_page_with_trailing_recapitulatia_has_deviz_cod():
    """Deviz codul trebuie extras chiar daca pagina are si Recapitulatia."""
    result = classify_page_local(_make_page(_LAST_DATA_PAGE_WITH_RECAPITULATIE))
    assert result["deviz_cod"] == "226288", \
        f"Expected '226288', got '{result['deviz_cod']}'"


def test_pure_recapitulatia_page_is_non_f3():
    """O pagina NUMAI cu Recapitulatia (fara articole) ramane NON_F3."""
    lines = [
        "Pag 17",
        "STADIUL FIZIC: oferta 226108 STRUCTURA",
        "Recapitulatia:",
        "Total cheltuieli directe:",
        "557.633,01",
        "Cheltuieli indirecte 5%:",
        "27.881,65",
        "Total:",
        "585.514,66",
    ]
    result = classify_page_local(_make_page(lines))
    assert result["label"] == "NON_F3", \
        f"Expected NON_F3 (pure summary, no article codes), got {result['label']}"


# ─── Test 2: STADIUL FIZIC cu linii OCR intercalate ─────────────────────────

_COVER_WITH_OCR_JUNK_BETWEEN_STADIUL_AND_COD = [
    "Pag 51",
    "OBIECTIV:",
    "SCN1164693 - 0226 45000000 EXTINDERE SI",
    "MODERNIZARE BAZA SPORTIVA RACARI",
    "OBIECTUL:",
    "0002 45000000 VESTIAR TEREN TENIS SI GRUPURI SANITARE",
    "STADIUL FIZIC:",          # ← STADIUL FIZIC pe o linie
    "Beneficiar:",             # ← OCR junk intercalat
    "oferta 226268 INSTALATII ELECTRICE curenti",  # ← codul e 2 linii mai jos
    "Proiectant:",
    "Executant:",
    "SC Street Lighting SRL",
    "F3 - LISTA cu cantitati de lucrari pe categorii de lucrari",
    "SECTIUNEA TEHNICA",
    "SECTIUNEA FINANCIARA",
    "Nr.",
    "Capitolul de lucrari",
    "1",
    "EF03D1",
    "INSTALATIE ELECTRICA EXTERIOARA",
    "buc",
    "1,00",
    "1.500,00",
    "1.500,00",
]


def test_stadiul_fizic_with_ocr_junk_classified_as_f3():
    """Pagina cu OCR junk intre STADIUL FIZIC si cod trebuie sa fie F3."""
    result = classify_page_local(_make_page(_COVER_WITH_OCR_JUNK_BETWEEN_STADIUL_AND_COD))
    assert result["label"] == "F3", \
        f"Expected F3, got {result['label']}"


def test_stadiul_fizic_with_ocr_junk_extracts_correct_deviz():
    """Codul deviz trebuie extras corect chiar cu OCR junk intre STADIUL FIZIC si cod."""
    result = classify_page_local(_make_page(_COVER_WITH_OCR_JUNK_BETWEEN_STADIUL_AND_COD))
    assert result["deviz_cod"] == "226268", \
        f"Expected '226268', got '{result['deviz_cod']}'"
