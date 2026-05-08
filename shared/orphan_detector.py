"""
Detecta coduri orphane: cod din REF neacoperit in O2 sub acelasi deviz,
DAR care exista in O2 sub un deviz diferit.

Semantica: ofertantul a clasificat articolul la alta categorie de lucrari.

API:
    detect_orphans(ref_articole, oferta_articole, matched_ref_keys=None) -> list
    matched_ref_keys: set de (deviz, cod) deja match-uite — excluse din detectie.
                      Daca None, se considera nimic matched (backward compat).
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def detect_orphans(
    ref_articole: list,
    oferta_articole: list,
    matched_ref_keys: set = None,
) -> list:
    """
    Detecta articole din REF nematch-uite al caror cod apare in oferta
    sub un deviz diferit.

    Algoritm (fara produs cartezian):
      1. Porneste de la articolele REF NEacoperite: (deviz, cod) not in matched_ref_keys
      2. Verifica daca codul exista in oferta sub orice alt deviz
      3. Daca da → ORFAN (deviz gresit in oferta)
      4. Daca nu → ramane LIPSA (gestionat de matcher principal)

    matched_ref_keys: set((deviz, cod)) deja match-uite. Default=None = nimic matched.
    """
    if matched_ref_keys is None:
        matched_ref_keys = set()

    # Index oferta: cod -> set(deviz)
    oferta_cod_to_devize: dict[str, set] = defaultdict(set)
    oferta_cod_to_art: dict[tuple, dict] = {}
    for art in oferta_articole:
        cod = (art.get('cod') or '').upper()
        deviz = art.get('deviz', '')
        if cod and deviz:
            oferta_cod_to_devize[cod].add(deviz)
            key = (cod, deviz)
            if key not in oferta_cod_to_art:
                oferta_cod_to_art[key] = art

    orphans = []
    seen: set[tuple] = set()

    for art in ref_articole:
        cod = (art.get('cod') or '').upper()
        ref_deviz = art.get('deviz', '')
        if not cod or not ref_deviz:
            continue

        ref_key = (ref_deviz, cod)

        # Sari articolele deja match-uite
        if ref_key in matched_ref_keys:
            continue

        # Codul exista in oferta sub alt deviz?
        oferta_devize = oferta_cod_to_devize.get(cod, set())
        # Excludem devizele ofertă deja consumate de alte match-uri (acelasi cod, alt deviz ref)
        consumed_devize = {k[0] for k in matched_ref_keys if k[1] == cod}
        wrong_devize = oferta_devize - {ref_deviz} - consumed_devize
        if not wrong_devize:
            continue  # Cod absent total din oferta → LIPSA (nu ORFAN)

        # Genereaza un orfan per deviz gresit (nu produs cartezian)
        for oferta_dv in sorted(wrong_devize):
            orphan_key = (cod, ref_deviz, oferta_dv)
            if orphan_key in seen:
                continue
            seen.add(orphan_key)

            oferta_art = oferta_cod_to_art.get((cod, oferta_dv), {})
            orphans.append({
                'cod': cod,
                'ref_deviz': ref_deviz,
                'ref_denom': art.get('denumire', '')[:50],
                'ref_cant': art.get('cantitate', 0),
                'ref_um': art.get('um', ''),
                'oferta_deviz': oferta_dv,
                'oferta_denom': oferta_art.get('denumire', '')[:50],
                'oferta_cant': oferta_art.get('cantitate', 0),
                'oferta_um': oferta_art.get('um', ''),
            })

    if orphans:
        logger.info(f"[ORPHAN] Detectate {len(orphans)} coduri orphane (deviz gresit in oferta)")

    return orphans
