"""
Detecteaza devize din oferta cu cod diferit fata de referinta,
dar cu set de articole similar (ofertantul a numerotat diferit categoriile).

Exemplu: 226113 (oferta) = 226118 (referinta) — articole identice,
denumiri similare, doar codul devizului difera.

Aceasta situatie genereaza false LIPSA + false EXTRA in comparatia normala.
Raportul trebuie sa semnaleze inadvertenta pentru verificare manuala.

Public API:
    detect_deviz_mismatches(ref_articole, oferta_articole, threshold=0.5) -> list[dict]
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)

_DEFAULT_THRESHOLD = 0.5


def detect_deviz_mismatches(
    ref_articole: list,
    oferta_articole: list,
    threshold: float = _DEFAULT_THRESHOLD,
) -> list:
    """
    Detecteaza devize din oferta prezente in ref sub un alt cod.

    Algoritm:
      1. Gaseste devizele din oferta ABSENTE din referinta
      2. Pentru fiecare, calculeaza overlap Jaccard cu fiecare deviz din ref
         overlap = |cods_comune| / |cods_reunite|
      3. Daca best_overlap >= threshold → MISMATCH potential

    Returns: list[dict] cu campuri:
      oferta_deviz    — codul devizului din oferta
      ref_deviz       — codul devizului din referinta cu cel mai mare overlap
      overlap_score   — scor Jaccard [0..1]
      oferta_art_count — numarul de articole in oferta deviz
      ref_art_count    — numarul de articole in ref deviz
    """
    ref_devize_set = {a.get('deviz', '') for a in ref_articole if a.get('deviz')}

    ref_by_deviz: dict[str, set] = defaultdict(set)
    for a in ref_articole:
        d = a.get('deviz', '')
        c = (a.get('cod') or '').upper().strip()
        if d and c:
            ref_by_deviz[d].add(c)

    oferta_by_deviz: dict[str, set] = defaultdict(set)
    for a in oferta_articole:
        d = a.get('deviz', '')
        c = (a.get('cod') or '').upper().strip()
        if d and c:
            oferta_by_deviz[d].add(c)

    mismatches = []
    for o_deviz, o_cods in oferta_by_deviz.items():
        if o_deviz in ref_devize_set:
            continue  # deviz exista in ref → nu e mismatch
        if not o_cods:
            continue

        best_ref = None
        best_score = 0.0
        for r_deviz, r_cods in ref_by_deviz.items():
            reunite = o_cods | r_cods
            if not reunite:
                continue
            score = len(o_cods & r_cods) / len(reunite)
            if score > best_score:
                best_score = score
                best_ref = r_deviz

        if best_score >= threshold and best_ref:
            mismatches.append({
                'oferta_deviz': o_deviz,
                'ref_deviz': best_ref,
                'overlap_score': round(best_score, 3),
                'oferta_art_count': len(o_cods),
                'ref_art_count': len(ref_by_deviz[best_ref]),
            })
            logger.info(
                f"[MISMATCH] Deviz {o_deviz} (oferta) pare echivalentul lui "
                f"{best_ref} (ref) — overlap {best_score:.0%}"
            )

    return mismatches
