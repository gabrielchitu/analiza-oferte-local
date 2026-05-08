"""
Tests pentru filtrarea paginilor dupa deviz_cod din referinta.

Problema: codul '226U08' (OCR: U in loc de 0) nu era in ref_deviz_codes
care contine '226008', deci paginile respective erau filtrate gresit.

Fix: normalizeaza deviz_cod cu U→0 inainte de comparare.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from local_run import _normalize_deviz_for_filter


def test_normal_deviz_passes_filter():
    ref_codes = {'226108', '226208', '226008'}
    assert _normalize_deviz_for_filter('226108') in ref_codes


def test_ocr_u_variant_passes_filter():
    """226U08 trebuie sa treaca filtrul deoarece 226008 e in referinta."""
    ref_codes = {'226008', '226018', '226028'}
    assert _normalize_deviz_for_filter('226U08') in ref_codes


def test_ocr_u28_variant_passes_filter():
    ref_codes = {'226028'}
    assert _normalize_deviz_for_filter('226U28') in ref_codes


def test_ocr_u38_variant_passes_filter():
    ref_codes = {'226038'}
    assert _normalize_deviz_for_filter('226U38') in ref_codes


def test_genuinely_missing_deviz_blocked():
    """Un deviz care chiar nu e in referinta trebuie blocat."""
    ref_codes = {'226108', '226208'}
    assert _normalize_deviz_for_filter('226999') not in ref_codes


def test_empty_deviz_blocked():
    ref_codes = {'226108'}
    assert _normalize_deviz_for_filter('') not in ref_codes
