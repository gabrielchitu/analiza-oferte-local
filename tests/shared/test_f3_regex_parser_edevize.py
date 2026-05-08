"""
Tests pentru formatul eDevize în f3_regex_parser.

Formatul eDevize (eDevize.ro):
  NR
  COD - DENUMIRE (pe o singura linie)
  UM
  CANTITATE.decimale
  pret_unitar
  valoare_totala
  material:
  pret_mat
  valoare_mat
  manopera:
  pret_man
  valoare_man
  utilaj:
  pret_uti
  valoare_uti
  transport:
  pret_tra
  valoare_tra

Probleme verificate:
  1. Liniile 'material:', 'manopera:', 'utilaj:', 'transport:' NU trebuie sa apara in denumire
  2. Articolele cu format 'COD - DENUMIRE' pe o linie sunt extrase corect
  3. Mai multe articole consecutive sunt extrase toate
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.f3_regex_parser import extract_articles_regex


_EDEVIZE_PAGE = [
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
    "manopera:",
    "100.50",
    "5,527.50",
    "utilaj:",
    "10.43",
    "573.65",
    "transport:",
    "0.00",
    "0.00",
    "8",
    "CB01A1 - COFRAJE IN CUZINETI FUND PAHAR DIN PAN REF DIN SCINDURI",
    "MP",
    "200.000",
    "62.44",
    "12,488.40",
    "material:",
    "17.98",
    "3,596.40",
    "manopera:",
    "44.46",
    "8,892.00",
    "utilaj:",
    "0.00",
    "0.00",
    "transport:",
    "0.00",
    "0.00",
]


def test_edevize_label_lines_not_in_denomination():
    """Label lines 'material:', 'manopera:', 'utilaj:', 'transport:' nu apar in denumire."""
    articles = extract_articles_regex(_EDEVIZE_PAGE, "226108", "STRUCTURA DE REZISTENTA")

    assert len(articles) >= 1, f"Expected at least 1 article, got {len(articles)}"

    ca02 = next((a for a in articles if a['cod'] == 'CA02A1'), None)
    assert ca02 is not None, "Article CA02A1 not found"

    den = ca02['denumire']
    assert 'material' not in den.lower(), f"'material:' found in denomination: '{den}'"
    assert 'manopera' not in den.lower(), f"'manopera:' found in denomination: '{den}'"
    assert 'utilaj' not in den.lower(), f"'utilaj:' found in denomination: '{den}'"
    assert 'transport' not in den.lower(), f"'transport:' found in denomination: '{den}'"


def test_edevize_denomination_correct():
    """Denominatia articolului eDevize e extrasa corect din formatul 'COD - DENUMIRE'."""
    articles = extract_articles_regex(_EDEVIZE_PAGE, "226108", "STRUCTURA DE REZISTENTA")

    ca02 = next((a for a in articles if a['cod'] == 'CA02A1'), None)
    assert ca02 is not None, "Article CA02A1 not found"
    assert ca02['denumire'] == "TURNARE BETON ARMAT IN FUNDATII IZOLATE CU VOLUM < 3MC", \
        f"Denomination wrong: '{ca02['denumire']}'"
    assert ca02['um'] == 'mc', f"UM wrong: '{ca02['um']}'"
    assert ca02['cantitate'] == 55.0, f"Cantitate wrong: {ca02['cantitate']}"


def test_edevize_multiple_articles_extracted():
    """Toate articolele de pe o pagina eDevize sunt extrase."""
    articles = extract_articles_regex(_EDEVIZE_PAGE, "226108", "STRUCTURA DE REZISTENTA")

    cods = [a['cod'] for a in articles]
    assert 'CA02A1' in cods, f"CA02A1 missing from {cods}"
    assert 'CB01A1' in cods, f"CB01A1 missing from {cods}"


def test_edevize_second_article_denomination_clean():
    """Al doilea articol consecutiv are si el denominatie curata."""
    articles = extract_articles_regex(_EDEVIZE_PAGE, "226108", "STRUCTURA DE REZISTENTA")

    cb01 = next((a for a in articles if a['cod'] == 'CB01A1'), None)
    assert cb01 is not None, "Article CB01A1 not found"

    den = cb01['denumire']
    assert 'material' not in den.lower(), f"'material:' in denomination: '{den}'"
    assert cb01['um'] == 'mp', f"UM wrong: '{cb01['um']}'"
    assert cb01['cantitate'] == 200.0, f"Cantitate wrong: {cb01['cantitate']}"
