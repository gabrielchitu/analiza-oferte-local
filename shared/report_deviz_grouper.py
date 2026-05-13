from typing import Dict, List
from collections import defaultdict

def group_neconf_by_deviz(neconformitati: List[dict]) -> Dict:
    """
    Group non-conformities by deviz and calculate article counts.

    Returns:
    {
        'deviz_groups': [
            {
                'deviz_cod': '226108',
                'deviz_denumire': 'STRUCTURA...',
                'articole_ref_count': 45,
                'articole_oferta_count': 42,
                'neconformitati': [... all neconf for this deviz ...]
            },
            ...
        ],
        'deviz_map': {...}
    }
    """
    # Build deviz map and article counts
    deviz_map = {}
    deviz_groups_dict = defaultdict(list)
    ref_articles_by_deviz = defaultdict(set)
    offer_articles_by_deviz = defaultdict(set)

    # First pass: collect all neconf, build maps
    for nc in neconformitati:
        deviz_cod = nc.get('deviz_ref', '')
        deviz_den = nc.get('deviz_denumire', '')

        if deviz_cod and deviz_den:
            deviz_map[deviz_cod] = deviz_den

        deviz_groups_dict[deviz_cod].append(nc)

        # Track unique articles per deviz
        ref_cod = nc.get('ref_cod', '')
        oferta_cod = nc.get('oferta_cod', '')
        if ref_cod:
            ref_articles_by_deviz[deviz_cod].add(ref_cod)
        if oferta_cod:
            offer_articles_by_deviz[deviz_cod].add(oferta_cod)

    # Build result with deviz sorted numerically
    deviz_groups = []
    for deviz_cod in sorted(deviz_groups_dict.keys(),
                           key=lambda x: int(x) if x.isdigit() else float('inf')):
        deviz_groups.append({
            'deviz_cod': deviz_cod,
            'deviz_denumire': deviz_map.get(deviz_cod, ''),
            'articole_ref_count': len(ref_articles_by_deviz[deviz_cod]),
            'articole_oferta_count': len(offer_articles_by_deviz[deviz_cod]),
            'neconformitati': sorted(
                deviz_groups_dict[deviz_cod],
                key=lambda x: (x.get('tip', ''), x.get('ref_cod', ''))
            )
        })

    return {
        'deviz_groups': deviz_groups,
        'deviz_map': deviz_map
    }
