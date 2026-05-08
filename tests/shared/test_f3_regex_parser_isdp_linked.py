"""
Tests pentru extragerea articolelor legate (N.L) din formatul ISDP.

In ISDP, dupa un articol principal urmeaza sub-articole cu format:
  N.L
  COD_NUMERIC (5-8 cifre)
  DENUMIRE (multi-line)
  UM
  CANTITATE,00
  PRET_UNITAR
  VALOARE_TOTALA

Pot exista MULTIPLE N.L dupa acelasi articol principal (ex: 8.L, 8.L, 8.L).
Codul numeric devine $COD (prefix $).

Referinta (Design Studio) le listeaza ca articole separate cu prefix $.
Daca nu le extragem din ISDP => fals ARTICOL_LIPSA masiv.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.f3_regex_parser import extract_articles_regex


_ISDP_PAGE_WITH_LINKED = [
    "STADIUL FIZIC: oferta 226268 INSTALATII ELECTRICE curenti",
    "0",
    "1",
    "2",
    "3",
    "4",
    "5 = 3 x 4",
    "6",
    "EA02A2",
    "TUB IZOLANT DE PROTECTIE,",
    "ETANS IPE-PVC MONTAT INGROPAT",
    "CU D=20MM",
    "m",
    "650,00",
    "16,72",
    "10.868,00",
    "material:",
    "0,00",
    "0,00",
    "manopera:",
    "16,72",
    "10.868,00",
    "utilaj:",
    "0,00",
    "0,00",
    "transport:",
    "0,00",
    "0,00",
    "6.L",          # articol legat 1
    "2700015",
    "TUB DE PROTECTIE TIP",
    "IPEY/MONOFLEX D=20 MM",
    "ML.",
    "650,00",
    "1,75",
    "1.137,50",
    "7",
    "EA16D1",
    "DOZA DERIVATIE PT CABLURI SAU",
    "TEVI DE INSTALATII -NBU PG 21",
    "buc",
    "16,00",
    "9,92",
    "158,72",
    "material:",
    "0,80",
    "12,80",
    "manopera:",
    "9,12",
    "145,92",
    "utilaj:",
    "0,00",
    "0,00",
    "transport:",
    "0,00",
    "0,00",
    "7.L",          # articol legat 2
    "7318999",
    "DOZA DE DERIVATIE PENTRU",
    "CABLURI SAU TEVI INSTALATII",
    "TIP:NBU PG21",
    "BUC.",
    "16,00",
    "18,00",
    "288,00",
    "8",
    "EE09B#",
    "CORP DE ILUMINAT SPECIAL",
    "buc",
    "23,00",
    "82,39",
    "1.894,90",
    "material:",
    "25,22",
    "580,10",
    "manopera:",
    "57,00",
    "1.311,00",
    "utilaj:",
    "0,16",
    "3,79",
    "transport:",
    "0,00",
    "0,00",
    "8.L",          # articol legat 3a
    "7302109",
    "CORP DE ILUMINAT PLAFONIERA LED 20W",
    "BUC.",
    "15,00",
    "92,00",
    "1.380,00",
    "8.L",          # articol legat 3b (al doilea 8.L!)
    "7302111",
    "CORP ILUMINAT TIP PLAFONIERA LED SENZOR",
    "BUC.",
    "2,00",
    "194,00",
    "388,00",
]


def test_main_articles_still_extracted():
    """Articolele principale (EA02A2, EA16D1, EE09B) trebuie extrase ca inainte."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    cods = [a['cod'] for a in arts]
    assert 'EA02A2' in cods, f"EA02A2 missing from {cods}"
    assert 'EA16D1' in cods, f"EA16D1 missing from {cods}"
    assert 'EE09B' in cods or 'EE09B#' in cods, f"EE09B missing from {cods}"


def test_linked_article_extracted_with_dollar_prefix():
    """Articolul legat '6.L / 2700015' trebuie extras ca '$2700015'."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    cods = [a['cod'] for a in arts]
    assert '$2700015' in cods, \
        f"Linked article $2700015 not extracted. Got: {cods}"


def test_second_linked_article_extracted():
    """Al doilea articol legat '7.L / 7318999' trebuie extras ca '$7318999'."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    cods = [a['cod'] for a in arts]
    assert '$7318999' in cods, \
        f"Linked article $7318999 not extracted. Got: {cods}"


def test_multiple_linked_same_article_extracted():
    """Doua 8.L consecutive (7302109 si 7302111) ambele extrase."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    cods = [a['cod'] for a in arts]
    assert '$7302109' in cods, f"$7302109 missing from {cods}"
    assert '$7302111' in cods, f"$7302111 missing from {cods}"


def test_linked_article_quantity_correct():
    """Articolul legat $2700015 are cantitatea corecta (650.0)."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    art = next((a for a in arts if a['cod'] == '$2700015'), None)
    assert art is not None, "$2700015 not found"
    assert art['cantitate'] == 650.0, f"Expected 650.0, got {art['cantitate']}"


def test_linked_article_um_correct():
    """Articolul legat $2700015 are UM corect (ml)."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    art = next((a for a in arts if a['cod'] == '$2700015'), None)
    assert art is not None, "$2700015 not found"
    assert art['um'].lower() == 'ml', f"Expected 'ml', got '{art['um']}'"


def test_linked_article_denomination_not_contaminated():
    """Denominatia articolului legat nu contine 'N.L' sau alte artefacte."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    art = next((a for a in arts if a['cod'] == '$2700015'), None)
    assert art is not None, "$2700015 not found"
    den = art['denumire'].lower()
    assert '6.l' not in den, f"'6.L' leaked into denomination: '{art['denumire']}'"
    assert 'tub' in den, f"Expected 'TUB' in denomination: '{art['denumire']}'"


def test_total_articles_count():
    """Total 7 articole: 3 principale + 4 legate (2700015, 7318999, 7302109, 7302111)."""
    arts = extract_articles_regex(_ISDP_PAGE_WITH_LINKED, "226268", "INSTALATII ELECTRICE")
    assert len(arts) >= 7, f"Expected >=7 articles, got {len(arts)}: {[a['cod'] for a in arts]}"
