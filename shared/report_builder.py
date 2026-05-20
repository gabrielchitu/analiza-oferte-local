"""Build hierarchical report structure from flat match/nonconformity lists."""
from collections import defaultdict


def build_raport_ierarhic(
    ref_articole: list,
    neconformitati: list,
    matches: list,
) -> dict:
    """Build hierarchical report JSON from flat matching results.

    Returns dict with keys: sumar, devize, erori_extractie.
    devize are in reference order; articles within each deviz are in nr_ordine order.
    """
    # Index matched ref codes per deviz
    matched_ref = set()
    for m in matches:
        matched_ref.add((m.get('deviz', ''), m.get('ref_cod', '')))

    # Index neconformitati per (deviz, ref_cod)
    nc_index = defaultdict(list)
    for nc in neconformitati:
        key = (nc.get('deviz', ''), nc.get('ref_cod', ''))
        nc_index[key].append(nc)

    # Collect subarticole fără parent (erori OCR/extracție)
    erori_extractie = []
    for art in ref_articole:
        if art.get('is_component') and not art.get('parent_cod') and not art.get('parent_nr_ordine'):
            erori_extractie.append({
                'cod': art.get('cod'),
                'denumire': art.get('denumire'),
                'deviz': art.get('deviz'),
                'deviz_denumire': art.get('deviz_denumire'),
                'nr_ordine': art.get('nr_ordine'),
            })

    # Separate main articles and subarticles
    main_arts = [a for a in ref_articole if not a.get('is_component')]
    sub_arts = [a for a in ref_articole if a.get('is_component') and a.get('parent_cod')]

    # Index subarticole per (deviz, parent_cod)
    sub_index = defaultdict(list)
    for sub in sub_arts:
        key = (sub.get('deviz', ''), sub.get('parent_cod', ''))
        sub_index[key].append(sub)

    # Build devize in reference order (preserve insertion order from ref_articole)
    deviz_order = []
    deviz_seen = set()
    for art in main_arts:
        dv = art.get('deviz', '')
        if dv not in deviz_seen:
            deviz_order.append((dv, art.get('deviz_denumire', '')))
            deviz_seen.add(dv)

    devize_out = []
    total_matched = 0
    total_lipsa = 0
    total_extra = len([nc for nc in neconformitati if nc.get('tip') == 'ARTICOL_EXTRA'])

    for dv_cod, dv_den in deviz_order:
        arts_in_deviz = [a for a in main_arts if a.get('deviz') == dv_cod]
        arts_in_deviz.sort(key=lambda a: (
            int(a['nr_ordine']) if isinstance(a.get('nr_ordine'), (int, float)) else 0
        ))

        dv_matched = 0
        dv_neconformitati = 0
        dv_lipsa = 0

        articole_out = []
        for art in arts_in_deviz:
            ref_cod = art.get('cod', '')
            ncs = nc_index.get((dv_cod, ref_cod), [])
            is_matched = (dv_cod, ref_cod) in matched_ref
            has_lipsa = any(nc.get('tip') == 'ARTICOL_LIPSA' for nc in ncs)

            if is_matched:
                status = 'MATCHED'
                dv_matched += 1
                total_matched += 1
            elif has_lipsa:
                status = 'LIPSA'
                dv_lipsa += 1
                total_lipsa += 1
            else:
                status = 'NECONFORMITATE'
                dv_neconformitati += 1

            # Subarticole ale acestui articol
            subs_ref = sub_index.get((dv_cod, ref_cod), [])
            subs_ref_sorted = sorted(subs_ref, key=lambda s: str(s.get('nr_ordine', '')))
            subarticole_out = []
            for sub in subs_ref_sorted:
                sub_cod = sub.get('cod', '')
                sub_ncs = nc_index.get((dv_cod, sub_cod), [])
                sub_matched = (dv_cod, sub_cod) in matched_ref
                sub_has_lipsa = any(nc.get('tip') == 'ARTICOL_LIPSA' for nc in sub_ncs)
                if sub_matched:
                    sub_status = 'MATCHED'
                elif sub_has_lipsa:
                    sub_status = 'LIPSA'
                else:
                    sub_status = 'NECONFORMITATE' if sub_ncs else 'MATCHED'

                subarticole_out.append({
                    'nr_ordine': sub.get('nr_ordine'),
                    'parent_cod': sub.get('parent_cod'),
                    'parent_nr_ordine': sub.get('parent_nr_ordine'),
                    'cod': sub_cod,
                    'denumire': sub.get('denumire'),
                    'um': sub.get('um'),
                    'cantitate': sub.get('cantitate'),
                    'cant_mostenita': sub.get('cant_mostenita', False),
                    'status_match': sub_status,
                    'neconformitati': sub_ncs,
                })

            articole_out.append({
                'nr_ordine': art.get('nr_ordine'),
                'cod': ref_cod,
                'denumire': art.get('denumire'),
                'um': art.get('um'),
                'cantitate': art.get('cantitate'),
                'status_match': status,
                'neconformitati': ncs,
                'subarticole': subarticole_out,
            })

        devize_out.append({
            'cod_deviz': dv_cod,
            'denumire_deviz': dv_den,
            'sumar_deviz': {
                'total': len(arts_in_deviz),
                'matched': dv_matched,
                'lipsa': dv_lipsa,
                'neconformitati': dv_neconformitati,
            },
            'articole': articole_out,
        })

    return {
        'sumar': {
            'total_articole_ref': len(main_arts),
            'matched': total_matched,
            'lipsa': total_lipsa,
            'extra': total_extra,
        },
        'devize': devize_out,
        'erori_extractie': erori_extractie,
    }
