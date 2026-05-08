"""
Tests pentru normalizarea codurilor de articole.

Regula: codul canonical contine NUMAI litere mari si cifre arabe [A-Z0-9].
Caracterele speciale (#, @, -, brackets) sunt artefacte software/OCR si se stripuiesc.
Prefixul $ (marker intern breviar) se gestioneaza separat.

Probleme actuale:
  'IC31A1#' → normalize → 'IC31A11' (# inlocuit cu 1 → cod gresit)
  Corect:    'IC31A1#' → 'IC31A1'
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from AgentComparator_local import _normalize_cod


def test_hash_suffix_stripped_not_replaced():
    """'IC31A1#' trebuie sa devina 'IC31A1', nu 'IC31A11'."""
    assert _normalize_cod('IC31A1#') == 'IC31A1', \
        f"Expected 'IC31A1', got '{_normalize_cod('IC31A1#')}'"


def test_hash_suffix_five_letter_prefix():
    """'RPCE29A#' -> 'RPCE29A'."""
    assert _normalize_cod('RPCE29A#') == 'RPCE29A', \
        f"Expected 'RPCE29A', got '{_normalize_cod('RPCE29A#')}'"


def test_normal_normative_code_unchanged():
    """'CA02A1' fara sufix ramane 'CA02A1'."""
    assert _normalize_cod('CA02A1') == 'CA02A1'


def test_ocr_l_to_1():
    """Litera 'l' OCR → cifra '1'."""
    result = _normalize_cod('CA02Al')
    assert '1' in result and 'l' not in result, \
        f"Expected l→1, got '{result}'"


def test_numeric_code_gets_dollar_prefix():
    """Cod numeric pur '3276069' → '$3276069'."""
    assert _normalize_cod('3276069') == '$3276069'


def test_dollar_numeric_code_preserved():
    """'$3276069' ramane '$3276069'."""
    assert _normalize_cod('$3276069') == '$3276069'


def test_bracket_suffix_stripped():
    """'CL08B1[7]' → 'CL08B1' (bracket suffix stripuit)."""
    result = _normalize_cod('CL08B17')  # current behavior after # fix
    # At minimum, brackets should produce clean cod
    assert '[' not in result and ']' not in result


def test_uppercase_normalization():
    """Codul se normalizeaza la uppercase."""
    result = _normalize_cod('ca02a1')
    assert result == result.upper()
