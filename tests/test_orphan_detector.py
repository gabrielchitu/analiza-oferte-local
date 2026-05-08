"""
Tests pentru detectia corecta a orfanelor.

Problema actuala: detectorul face PRODUS CARTEZIAN al devizelor.
Daca cod X apare in REF sub [226108, 226208] si in O2 sub [226108, 226208],
genereaza orfane pentru toate perechile cross-deviz, desi totul e corect.

Comportamentul corect:
  Orfan = articol din REF (deviz D, cod C) care NU are pereche in O2 sub
          acelasi deviz D, dar codul C EXISTA in O2 sub un deviz diferit D'.
  Adica: orfanele se detecteaza NUMAI pe articolele nematch-uite, nu pe tot.

Context domeniu:
  - Acelasi cod poate aparea in multiple devize in ambele documente → NORMAL
  - Daca REF are (226108, CC03C) si O2 are si (226108, CC03C) → MATCHED, nu orfan
  - Daca REF are (226108, XY01A1) si O2 nu are (226108, XY01A1) dar are
    (226228, XY01A1) → ORFAN (ofertantul a clasificat gresit devizul)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.orphan_detector import detect_orphans


def _art(cod, deviz, cant=1.0, um='buc'):
    return {'cod': cod, 'deviz': deviz, 'cantitate': cant, 'um': um,
            'denumire': f'TEST {cod}', 'deviz_denumire': ''}


def test_no_orphan_when_code_matched_in_same_deviz():
    """
    CC03C in REF[226108] si O2[226108] → MATCHED → nu e orfan.
    Chiar daca CC03C apare si in alte devize.
    """
    ref = [
        _art('CC03C', '226108', cant=100.0),
        _art('CC03C', '226208', cant=50.0),
    ]
    o2 = [
        _art('CC03C', '226108', cant=100.0),
        _art('CC03C', '226208', cant=50.0),
    ]
    # Articolele matched sunt excluse din detectie
    matched_ref_keys = {('226108', 'CC03C'), ('226208', 'CC03C')}
    orphans = detect_orphans(ref, o2, matched_ref_keys=matched_ref_keys)
    assert len(orphans) == 0, \
        f"Expected 0 orphans (all matched), got {len(orphans)}: {orphans}"


def test_orphan_detected_when_code_in_different_deviz():
    """
    XY01A1 in REF[226108] dar O2 are XY01A1 in [226228] (nu in 226108) → ORFAN.
    """
    ref = [_art('XY01A1', '226108', cant=10.0)]
    o2  = [_art('XY01A1', '226228', cant=10.0)]
    # Nimic matched → matched_ref_keys gol
    orphans = detect_orphans(ref, o2, matched_ref_keys=set())
    assert len(orphans) == 1, f"Expected 1 orphan, got {len(orphans)}"
    assert orphans[0]['cod'] == 'XY01A1'
    assert orphans[0]['ref_deviz'] == '226108'
    assert orphans[0]['oferta_deviz'] == '226228'


def test_genuine_lipsa_not_reported_as_orphan():
    """
    AB01B1 in REF dar COMPLET ABSENT din O2 → LIPSA, nu orfan.
    """
    ref = [_art('AB01B1', '226108')]
    o2  = [_art('OTHER', '226108')]
    orphans = detect_orphans(ref, o2, matched_ref_keys=set())
    assert len(orphans) == 0, \
        f"Expected 0 orphans (code absent from O2), got {len(orphans)}"


def test_no_cartesian_product_inflation():
    """
    Cod in REF sub [A,B,C] si O2 sub [A,B,C] cu toate matched → 0 orfane.
    Detectorul vechi genera 3*2=6 orfane (produs cartezian).
    """
    devize = ['226108', '226208', '226308']
    ref = [_art('CC03C', d, cant=float(i*10)) for i, d in enumerate(devize, 1)]
    o2  = [_art('CC03C', d, cant=float(i*10)) for i, d in enumerate(devize, 1)]
    matched = {(d, 'CC03C') for d in devize}
    orphans = detect_orphans(ref, o2, matched_ref_keys=matched)
    assert len(orphans) == 0, \
        f"Expected 0 (all matched, no cartesian product), got {len(orphans)}: {orphans}"


def test_partial_match_generates_orphan_only_for_unmatched():
    """
    CC03C in REF[226108]=matched, REF[226208]=unmatched dar O2 are CC03C in 226308.
    Orfan NUMAI pentru (226208, CC03C) → (226308, CC03C).
    """
    ref = [
        _art('CC03C', '226108', cant=100.0),  # matched
        _art('CC03C', '226208', cant=50.0),   # unmatched
    ]
    o2 = [
        _art('CC03C', '226108', cant=100.0),  # matches ref 226108
        _art('CC03C', '226308', cant=50.0),   # wrong deviz for ref 226208
    ]
    matched = {('226108', 'CC03C')}  # doar 226108 matched
    orphans = detect_orphans(ref, o2, matched_ref_keys=matched)
    assert len(orphans) == 1, f"Expected 1 orphan, got {len(orphans)}: {orphans}"
    assert orphans[0]['ref_deviz'] == '226208'
    assert orphans[0]['oferta_deviz'] == '226308'
