"""
Tests pentru detectia deviz mismatch.

Deviz mismatch = deviz din oferta cu cod diferit fata de referinta,
dar cu articole similare (ofertantul a numerotat diferit categoriile).

Exemplu real: 226113 (oferta) = 226118 (referinta)
  - Articole identice: RPCE29A, CK25A, CE23A1, $2941123, ...
  - Denumiri similare: 'ARHITECTURA -teren tenis acoperit'
  - Overlap coduri: 100%

Aceasta situatie genereaza false LIPSA (din ref) si false EXTRA (din oferta).
Raportul trebuie sa semnaleze: 'Devizul 226113 pare echivalentul lui 226118'.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.deviz_mismatch_detector import detect_deviz_mismatches


def _art(cod, deviz, cant=1.0, um='buc', deviz_den=''):
    return {'cod': cod, 'deviz': deviz, 'cantitate': cant, 'um': um,
            'denumire': f'TEST {cod}', 'deviz_denumire': deviz_den}


def test_identical_articles_different_deviz_detected():
    """226113 (oferta) cu articole identice cu 226118 (ref) → MISMATCH detectat."""
    ref = [
        _art('RPCE29A', '226118', 1256.0, 'mp', 'ARHITECTURA teren tenis'),
        _art('CK25A',   '226118', 7.0,    'mp', 'ARHITECTURA teren tenis'),
        _art('CE23A1',  '226118', 1256.0, 'mp', 'ARHITECTURA teren tenis'),
    ]
    oferta = [
        _art('RPCE29A', '226113', 1256.0, 'mp', 'ARHITECTURA -teren tenis acoperit'),
        _art('CK25A',   '226113', 7.0,    'mp', 'ARHITECTURA -teren tenis acoperit'),
        _art('CE23A1',  '226113', 1256.0, 'mp', 'ARHITECTURA -teren tenis acoperit'),
    ]
    mismatches = detect_deviz_mismatches(ref, oferta)

    assert len(mismatches) == 1, f"Expected 1 mismatch, got {len(mismatches)}: {mismatches}"
    m = mismatches[0]
    assert m['oferta_deviz'] == '226113'
    assert m['ref_deviz'] == '226118'
    assert m['overlap_score'] == 1.0


def test_no_mismatch_when_deviz_exists_in_ref():
    """226118 exista in ambele → nu e mismatch."""
    ref    = [_art('RPCE29A', '226118')]
    oferta = [_art('RPCE29A', '226118')]
    mismatches = detect_deviz_mismatches(ref, oferta)
    assert len(mismatches) == 0, f"Expected 0 mismatches, got {len(mismatches)}"


def test_no_mismatch_below_threshold():
    """Overlap < 50% → nu e mismatch (probabil deviz genuinely extra)."""
    ref = [
        _art('RPCE29A', '226118'),
        _art('CK25A',   '226118'),
        _art('CE23A1',  '226118'),
        _art('TRB05B',  '226118'),
    ]
    oferta = [
        _art('RPCE29A', '226999'),  # doar 1 din 4 = 25% overlap → sub threshold
        _art('XY01A1',  '226999'),
        _art('ZZ02B3',  '226999'),
        _art('WW04C5',  '226999'),
    ]
    mismatches = detect_deviz_mismatches(ref, oferta)
    assert len(mismatches) == 0, \
        f"Expected 0 (overlap too low), got {len(mismatches)}"


def test_partial_overlap_above_threshold():
    """Overlap 70% → detectat ca mismatch cu overlap_score correct."""
    ref = [
        _art('A', '226118'), _art('B', '226118'), _art('C', '226118'),
        _art('D', '226118'), _art('E', '226118'), _art('F', '226118'),
        _art('G', '226118'), _art('H', '226118'), _art('I', '226118'),
        _art('J', '226118'),
    ]
    oferta = [
        # 7 din 10 comune
        _art('A', '226113'), _art('B', '226113'), _art('C', '226113'),
        _art('D', '226113'), _art('E', '226113'), _art('F', '226113'),
        _art('G', '226113'),
        # 3 extra
        _art('X', '226113'), _art('Y', '226113'), _art('Z', '226113'),
    ]
    mismatches = detect_deviz_mismatches(ref, oferta)
    assert len(mismatches) == 1
    m = mismatches[0]
    assert m['oferta_deviz'] == '226113'
    assert m['ref_deviz'] == '226118'
    # 7 comune / (10 ref + 3 extra in oferta = 13 unique) ≈ 53.8%
    assert m['overlap_score'] > 0.5


def test_mismatch_result_fields():
    """Rezultatul contine campurile necesare raportului."""
    ref    = [_art('A', '226118'), _art('B', '226118')]
    oferta = [_art('A', '226113'), _art('B', '226113')]
    mismatches = detect_deviz_mismatches(ref, oferta)
    assert len(mismatches) == 1
    m = mismatches[0]
    assert 'oferta_deviz' in m
    assert 'ref_deviz' in m
    assert 'overlap_score' in m
    assert 'oferta_art_count' in m
    assert 'ref_art_count' in m


def test_genuinely_extra_deviz_not_flagged():
    """
    226728 cu CHELT 30000 LEI nu e similar niciunui deviz din referinta → nu e mismatch.
    """
    ref = [
        _art('RPCE29A', '226118'),
        _art('CK25A',   '226118'),
        _art('TRA01A',  '226708'),
    ]
    oferta = [
        _art('$226728',  '226728', 0,     '',    'CHELTUIELI CONEXE'),
        _art('CHELT',    '226728', 30000, 'lei', 'CHELTUIELI CONEXE'),
    ]
    mismatches = detect_deviz_mismatches(ref, oferta)
    assert len(mismatches) == 0, \
        f"226728 with 0 overlap should not be flagged, got {mismatches}"
