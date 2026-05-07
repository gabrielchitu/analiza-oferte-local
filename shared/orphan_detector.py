"""
Detecta coduri orphane: cod care apare în deviz diferit în ref vs oferta.
Exemplu: CK25A categoria 226118 în ref, dar 226113 în oferta → orphan.
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def detect_orphans(ref_articole: list, oferta_articole: list) -> list:
    """
    Detecta articole cu cod identical dar deviz diferit.
    
    Returns: lista de {cod, ref_deviz, oferta_deviz, ref_cant, oferta_cant}
    """
    # Map: cod -> set of deviz în referință
    ref_cod_deviz = defaultdict(set)
    ref_cod_data = {}
    
    for art in ref_articole:
        cod = (art.get('cod') or '').upper()
        deviz = art.get('deviz', '')
        if cod and deviz:
            ref_cod_deviz[cod].add(deviz)
            key = (cod, deviz)
            if key not in ref_cod_data:
                ref_cod_data[key] = art
    
    # Map: cod -> set of deviz în oferta
    oferta_cod_deviz = defaultdict(set)
    oferta_cod_data = {}
    
    for art in oferta_articole:
        cod = (art.get('cod') or '').upper()
        deviz = art.get('deviz', '')
        if cod and deviz:
            oferta_cod_deviz[cod].add(deviz)
            key = (cod, deviz)
            if key not in oferta_cod_data:
                oferta_cod_data[key] = art
    
    # Gaseste orphane: cod care apare în ambele dar cu deviz diferit
    orphans = []
    
    for cod in ref_cod_deviz:
        if cod not in oferta_cod_deviz:
            continue  # Cod nu e în oferta deloc
        
        ref_devizes = ref_cod_deviz[cod]
        oferta_devizes = oferta_cod_deviz[cod]
        
        # Verifica fiecare combinație
        for ref_dv in ref_devizes:
            for oferta_dv in oferta_devizes:
                if ref_dv != oferta_dv:
                    # Orphan: cod identical, deviz diferit
                    ref_key = (cod, ref_dv)
                    oferta_key = (cod, oferta_dv)
                    
                    if ref_key in ref_cod_data and oferta_key in oferta_cod_data:
                        ref_art = ref_cod_data[ref_key]
                        oferta_art = oferta_cod_data[oferta_key]
                        
                        # Verifica daca cantitate + UM sunt identice (confirma aceeasi lucrare)
                        if (ref_art.get('cantitate') == oferta_art.get('cantitate') and
                            ref_art.get('um') == oferta_art.get('um')):
                            
                            orphans.append({
                                'cod': cod,
                                'ref_deviz': ref_dv,
                                'ref_denom': ref_art.get('denumire', '')[:50],
                                'ref_cant': ref_art.get('cantitate', 0),
                                'ref_um': ref_art.get('um', ''),
                                'oferta_deviz': oferta_dv,
                                'oferta_denom': oferta_art.get('denumire', '')[:50],
                                'oferta_cant': oferta_art.get('cantitate', 0),
                                'oferta_um': oferta_art.get('um', ''),
                            })
    
    # Deduplica
    seen = set()
    unique_orphans = []
    for orphan in orphans:
        key = (orphan['cod'], orphan['ref_deviz'], orphan['oferta_deviz'])
        if key not in seen:
            unique_orphans.append(orphan)
            seen.add(key)
    
    if unique_orphans:
        logger.info(f"[ORPHAN] Detectate {len(unique_orphans)} coduri orphane (cod identical, deviz diferit)")
    
    return unique_orphans
