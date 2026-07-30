"""Regression tests for classify_page_local edge cases."""

from shared.f3_page_classifier import classify_page_local


def _page(lines):
    return {'lines': [{'content': line} for line in lines]}


_SINGLE_PAGE_DEVIZ = [
    'eDevize', 'Antet stanga',
    'Beneficiar:', 'EUROPROJECT PARTNER SRL',
    'Obiectivul:', 'CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE',
    'Obiectul:', '7 ORGANIZARE DE SANTIER',
    'Stadiul fizic:', '7.1 ORGANIZARE DE SANTIER',
    'Formular F3',
    'Lista cu cantitati de lucrari pe categorii de lucrari',
    'Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea',
    '0', '1', '2', '3', '4', '5 = 3 x 4',
    '1', 'OS - Organizare de santier', 'buc', '1.000', '26,383.18', '26,383.18',
    'material:', '26,300.00', '26,300.00',
    'Recapitulatie',
    'TOTAL GENERAL (fara TVA)', '26,383.18',
]


def test_single_page_deviz_with_recap_is_f3():
    """Table + Recapitulatie on one page: the codes are non-normative ('OS'),
    so only the '5 = 3 x 4' table header keeps the page out of the summary bin."""
    result = classify_page_local(_page(_SINGLE_PAGE_DEVIZ))
    assert result['label'] == 'F3'


def test_pure_recap_page_still_non_f3():
    """The same footer without the article table stays NON_F3."""
    lines = ['Antet stanga', 'eDevize', 'Recapitulatie',
             'Cheltuieli directe', 'TOTAL GENERAL (fara TVA)', '26,383.18']
    assert classify_page_local(_page(lines))['label'] == 'NON_F3'
