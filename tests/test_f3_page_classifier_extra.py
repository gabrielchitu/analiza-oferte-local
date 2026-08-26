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


_F3NRZ_PAGE = [
    'eDevize', 'Antet stanga',
    'Obiectivul:', 'CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE',
    'Stadiul fizic:', '3.1 ARHITECTURA',
    'Formular F3nrz - Realizari la data de 17/08/2026',
    'Lista cu cantitati de lucrari pe categorii de lucrari',
    'SECTIUNEA TEHNICA',
    '0', '1', '2', '3', '4', '5 = 3 x 4',
    'COMPARTIMENTARI',
    '3', 'CD08C2 - Pereti compartimentare - BCA', 'mc', '34.630', '711.89', '24,652.74',
]


def test_f3nrz_progress_form_is_f3():
    """'Formular F3nrz' is the progress form — same table, still F3. The
    FORMULAR C6/F1/F2/F4 exclusion must not claim it."""
    assert classify_page_local(_page(_F3NRZ_PAGE))['label'] == 'F3'


def test_other_formulars_still_non_f3():
    for name in ('Formular F4', 'Formular C6', 'FORMULAR F1'):
        lines = ['Antet stanga', name, 'Lista cu cantitati de lucrari']
        assert classify_page_local(_page(lines))['label'] == 'NON_F3', name
