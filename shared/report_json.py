import json
from typing import Dict, List

def generate_json_by_deviz(session: dict, comp: dict) -> dict:
    """
    Generate JSON report grouped by deviz with totals.

    Args:
        session: session dict with client_name, obiect_investitii
        comp: comparatie dict with neconformitati, oferta_nr, ref_articles, oferta_articles, etc.

    Returns:
        dict with structure:
        {
            'metadata': {...},
            'deviz_groups': [
                {
                    'deviz_cod': '226108',
                    'deviz_denumire': '...',
                    'articole_referinta_total': 45,
                    'articole_oferta_total': 42,
                    'articole_referinta_neconf': 5,
                    'neconformitati': [...]
                },
                ...
            ]
        }
    """
    from collections import defaultdict

    neconformitati = comp.get('neconformitati', [])

    # Build per-deviz TOTAL article counts from full article lists
    ref_total_by_deviz = defaultdict(int)
    offer_total_by_deviz = defaultdict(int)
    for art in comp.get('ref_articles', []):
        d = art.get('deviz', '')
        if d:
            ref_total_by_deviz[d] += 1
    for art in comp.get('oferta_articles', []):
        d = art.get('deviz', '')
        if d:
            offer_total_by_deviz[d] += 1

    # Build deviz map and groups
    deviz_map = {}
    deviz_groups_dict = defaultdict(list)
    ref_articles_by_deviz = defaultdict(set)
    offer_articles_by_deviz = defaultdict(set)

    for nc in neconformitati:
        deviz_cod = nc.get('deviz_ref', '')
        deviz_den = nc.get('deviz_denumire', '')

        if deviz_cod and deviz_den:
            deviz_map[deviz_cod] = deviz_den

        deviz_groups_dict[deviz_cod].append(nc)

        # Track unique articles with non-conformities
        if nc.get('ref_cod', ''):
            ref_articles_by_deviz[deviz_cod].add(nc.get('ref_cod', ''))
        if nc.get('oferta_cod', ''):
            offer_articles_by_deviz[deviz_cod].add(nc.get('oferta_cod', ''))

    # Build deviz groups sorted numerically
    deviz_groups = []
    for deviz_cod in sorted(deviz_groups_dict.keys(),
                           key=lambda x: int(x) if x.isdigit() else float('inf')):
        # Count EVERY non-conformity record (not unique articles)
        neconf_records = deviz_groups_dict[deviz_cod]
        neconf_count = len(neconf_records)
        deviz_groups.append({
            'deviz_cod': deviz_cod,
            'deviz_denumire': deviz_map.get(deviz_cod, ''),
            'articole_referinta_total': ref_total_by_deviz[deviz_cod],
            'articole_oferta_total': offer_total_by_deviz[deviz_cod],
            'neconformitati_count': neconf_count,
            'neconformitati': neconf_records
        })

    return {
        'metadata': {
            'client_name': session.get('client_name', ''),
            'obiect_investitii': session.get('obiect_investitii', ''),
            'oferta_nr': comp.get('oferta_nr', ''),
            'source_file': comp.get('source_file', ''),
            'matches': comp.get('matches', 0),
            'total_neconformitati': comp.get('total_neconformitati', 0),
            'ref_art_count': comp.get('ref_art_count', 0),
            'oferta_art_count': comp.get('oferta_art_count', 0)
        },
        'deviz_groups': deviz_groups
    }
