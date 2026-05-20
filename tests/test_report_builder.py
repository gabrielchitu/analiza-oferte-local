# tests/test_report_builder.py
import pytest
from shared.report_builder import build_raport_ierarhic

REF_ARTICOLE = [
    {'cod': 'TF24A', 'denumire': 'Beton C25', 'um': 'mp', 'cantitate': 34.2,
     'deviz': '226108', 'deviz_denumire': 'Structura', 'is_component': False,
     'nr_ordine': 1, 'parent_nr_ordine': None},
    {'cod': '$3274270', 'denumire': 'Cofraj', 'um': 'mp', 'cantitate': 102.6,
     'deviz': '226108', 'deviz_denumire': 'Structura', 'is_component': True,
     'nr_ordine': '1.1', 'parent_nr_ordine': 1, 'parent_cod': 'TF24A'},
    {'cod': 'TF26A', 'denumire': 'Beton C30', 'um': 'mc', 'cantitate': 12.5,
     'deviz': '226108', 'deviz_denumire': 'Structura', 'is_component': False,
     'nr_ordine': 2, 'parent_nr_ordine': None},
]

NECONFORMITATI = [
    {'tip': 'DIFERENTA_CAMP', 'deviz': '226108', 'ref_cod': 'TF26A',
     'oferta_cod': 'TF26A', 'nr_ordine_ref': 2, 'parent_cod_ref': None},
]

MATCHES = [
    {'ref_cod': 'TF24A', 'oferta_cod': 'TF24A', 'deviz': '226108'},
    {'ref_cod': '$3274270', 'oferta_cod': '$3274270', 'deviz': '226108'},
]

def test_raport_has_devize_section():
    r = build_raport_ierarhic(REF_ARTICOLE, NECONFORMITATI, MATCHES)
    assert 'devize' in r
    assert len(r['devize']) == 1
    assert r['devize'][0]['cod_deviz'] == '226108'

def test_deviz_preserves_ref_order():
    r = build_raport_ierarhic(REF_ARTICOLE, NECONFORMITATI, MATCHES)
    deviz = r['devize'][0]
    nrs = [a['nr_ordine'] for a in deviz['articole']]
    assert nrs == [1, 2]

def test_subarticole_nested_under_parent():
    r = build_raport_ierarhic(REF_ARTICOLE, NECONFORMITATI, MATCHES)
    tf24a = r['devize'][0]['articole'][0]
    assert tf24a['cod'] == 'TF24A'
    assert len(tf24a['subarticole']) == 1
    assert tf24a['subarticole'][0]['cod'] == '$3274270'

def test_status_match_correctly_set():
    r = build_raport_ierarhic(REF_ARTICOLE, NECONFORMITATI, MATCHES)
    deviz = r['devize'][0]
    tf24a = deviz['articole'][0]
    tf26a = deviz['articole'][1]
    assert tf24a['status_match'] == 'MATCHED'
    assert tf26a['status_match'] == 'NECONFORMITATE'

def test_sumar_deviz_counts():
    r = build_raport_ierarhic(REF_ARTICOLE, NECONFORMITATI, MATCHES)
    sumar = r['devize'][0]['sumar_deviz']
    assert sumar['matched'] == 1
    assert sumar['neconformitati'] == 1

def test_erori_extractie_collected():
    ref_cu_orfan = REF_ARTICOLE + [
        {'cod': '$9999', 'denumire': 'Fara parinte', 'um': 'mp', 'cantitate': 1.0,
         'deviz': '226108', 'deviz_denumire': 'Structura', 'is_component': True,
         'nr_ordine': None, 'parent_nr_ordine': None, 'parent_cod': None}
    ]
    r = build_raport_ierarhic(ref_cu_orfan, NECONFORMITATI, MATCHES)
    assert 'erori_extractie' in r
    assert any(e['cod'] == '$9999' for e in r['erori_extractie'])
