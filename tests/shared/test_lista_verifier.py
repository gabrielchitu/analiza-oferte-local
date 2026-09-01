import pytest
from shared.lista_verifier import verify, _check_nr_crt_gaps, _check_total_deviz, _check_total_capitol


def _make_deviz(articole_per_capitol, total_deviz=None, capitole_totals=None):
    capitole = []
    for idx, (nr_list, cap_total) in enumerate(
        zip(articole_per_capitol,
            capitole_totals or [None] * len(articole_per_capitol))
    ):
        arts = [
            {'nr_crt': str(nr), 'cod': f'C{nr}', 'denumire': f'Art {nr}',
             'pret_unitar': 10.0, 'total': 10.0,
             'breakdown': None, 'suspect': False, 'sub_items': []}
            for nr in nr_list
        ]
        cap_sum = sum(a['total'] for a in arts)
        capitole.append({
            'titlu': f'CAP{idx}',
            'articole': arts,
            'total_capitol': cap_total if cap_total is not None else cap_sum,
        })
    total = total_deviz if total_deviz is not None else sum(
        c['total_capitol'] for c in capitole
    )
    return {'deviz_key': 'test', 'capitole': capitole, 'total_deviz': total}


def test_check_nr_crt_gaps_no_gaps():
    deviz = _make_deviz([[1, 2, 3, 4, 5]])
    result = _check_nr_crt_gaps([deviz])
    assert result['ok'] is True
    assert result['gaps'] == []


def test_check_nr_crt_gaps_with_gap():
    deviz = _make_deviz([[1, 2, 4, 5]])  # missing 3
    result = _check_nr_crt_gaps([deviz])
    assert result['ok'] is False
    assert 3 in result['gaps']


def test_check_total_deviz_match():
    deviz = _make_deviz([[1, 2, 3]])  # 3 articles x 10.0 = 30.0
    result = _check_total_deviz([deviz])
    assert result['ok'] is True


def test_check_total_deviz_mismatch():
    deviz = _make_deviz([[1, 2, 3]], total_deviz=999.0)
    result = _check_total_deviz([deviz])
    assert result['ok'] is False
    assert result['failures'][0]['diff'] == pytest.approx(969.0, abs=0.1)


def test_verify_ok_status():
    deviz = _make_deviz([[1, 2, 3]])
    result = verify([deviz])
    assert result['status'] == 'OK'
    assert result['iterations'] == 1


def test_verify_red_status_no_retry():
    deviz = _make_deviz([[1, 2, 4]], total_deviz=999.0)
    result = verify([deviz], max_iterations=1)
    assert result['status'] == 'RED'


def test_verify_warn_status_breakdown():
    deviz = _make_deviz([[1, 2, 3]])
    # Inject suspect article
    deviz['capitole'][0]['articole'][0]['breakdown'] = {
        'material': {'pret': 5.0, 'total': 50.0},
        'manopera': {'pret': 1.0, 'total': 10.0},
        'utilaj': {'pret': 0.0, 'total': 0.0},
        'transport': {'pret': 0.0, 'total': 0.0},
        'control_ok': False,
    }
    deviz['capitole'][0]['articole'][0]['suspect'] = True
    result = verify([deviz])
    assert result['status'] == 'WARN'
    assert result['checks']['BREAKDOWN_CONTROL']['ok'] is False


def test_check_total_capitol_mismatch():
    deviz = _make_deviz([[1, 2, 3]], capitole_totals=[999.0])  # sum=30, declared=999
    result = _check_total_capitol([deviz])
    assert result['ok'] is False
    assert len(result['failures']) == 1
    assert result['failures'][0]['diff'] == pytest.approx(969.0, abs=0.1)


def test_verify_max_iterations_zero():
    deviz = _make_deviz([[1, 2, 3]])
    result = verify([deviz], max_iterations=0)
    # Should not crash; 0 iterations means no checks ran → RED
    assert result['status'] == 'RED'
    assert result['iterations'] == 0


def test_verify_retry_loop():
    """reextract_fn called on HIGH failure; second pass returns fixed data."""
    bad_deviz = _make_deviz([[1, 2, 4]])  # gap at 3
    good_deviz = _make_deviz([[1, 2, 3]])  # fixed

    call_count = [0]
    def reextract_fn(data, checks, iteration):
        call_count[0] += 1
        return [good_deviz]

    result = verify([bad_deviz], reextract_fn=reextract_fn)
    assert result['status'] == 'OK'
    assert call_count[0] == 1
    assert result['iterations'] == 2


# --- Regression: raw last-article-nr scan (EuroProject short devize) ---

def _page(lines):
    return {'is_f3': True, 'lines': lines}


def test_max_nr_ignores_table_column_numbers():
    """'0' '1' '2' '3' '4' above the '5 = 3 x 4' header are column labels."""
    from shared.lista_verifier import max_nr_crt_in_page_classes

    page = _page(['Formular F3', '0', '1', '2', '3', '4', '5 = 3 x 4',
                  '1', 'OS - Organizare de santier', 'buc', '1.000'])
    assert max_nr_crt_in_page_classes([page]) == 1


def test_max_nr_counts_inline_nr_cod_articles():
    """'4 ACD03A01> - Bazin ...' carries article nr 4 on the code line."""
    from shared.lista_verifier import max_nr_crt_in_page_classes

    page = _page(['5 = 3 x 4',
                  '1', 'IB05A01> - Montare ventiloconvector', 'buc',
                  '4 ACD03A01> - Bazin ecologic vidanjabil', 'buc',
                  '7 CP14C# - Montare ventilatie cu recuperare', 'buc'])
    assert max_nr_crt_in_page_classes([page]) == 7


def test_numbering_skips_are_not_gaps_when_absent_from_raw():
    """A 'situatie de lucrari' lists only the articles executed in the period,
    so its numbering skips by design."""
    from shared.lista_verifier import _check_nr_crt_gaps

    extracted = [{'capitole': [{'articole': [{'nr_crt': '3'}, {'nr_crt': '7'}]}]}]
    # 4, 5, 6 are not printed anywhere in the document
    res = _check_nr_crt_gaps(extracted, raw_nrs={3, 7})
    assert res['ok'] is True
    assert res['gaps'] == []
    assert res['numbering_skips'] == [4, 5, 6]


def test_gap_still_reported_when_the_number_is_printed():
    from shared.lista_verifier import _check_nr_crt_gaps

    extracted = [{'capitole': [{'articole': [{'nr_crt': '3'}, {'nr_crt': '5'}]}]}]
    res = _check_nr_crt_gaps(extracted, raw_nrs={3, 4, 5})
    assert res['ok'] is False
    assert res['gaps'] == [4]


def test_gaps_without_raw_keep_the_old_behaviour():
    from shared.lista_verifier import _check_nr_crt_gaps

    extracted = [{'capitole': [{'articole': [{'nr_crt': '3'}, {'nr_crt': '5'}]}]}]
    assert _check_nr_crt_gaps(extracted) == {'ok': False, 'gaps': [4]}


def test_article_nrs_collects_every_printed_number():
    from shared.lista_verifier import article_nrs_in_page_classes

    page = {'is_f3': True, 'lines': ['0', '1', '2', '3', '4', '5 = 3 x 4',
                                     '3', 'CD08C2 - Pereti', 'mc',
                                     '7 CP14C# - Ventilatie', 'buc']}
    assert article_nrs_in_page_classes([page]) == {3, 7}


# --- TOTAL 1 (Cheltuieli directe) cross-check against the printed value ---

def test_check_total_1_doc_match():
    from shared.lista_verifier import _check_total_1_doc

    deviz = _make_deviz([[1, 2, 3]])  # 3 x 10.0 = 30.0
    result = _check_total_1_doc([deviz], 30.0)
    assert result['ok'] is True


def test_check_total_1_doc_mismatch():
    from shared.lista_verifier import _check_total_1_doc

    deviz = _make_deviz([[1, 2, 3]])  # 30.0 extracted
    result = _check_total_1_doc([deviz], 40.0)
    assert result['ok'] is False
    assert result['computed'] == pytest.approx(30.0)
    assert result['doc'] == pytest.approx(40.0)
    assert result['diff'] == pytest.approx(10.0)


def test_check_total_1_doc_skipped_when_not_printed():
    from shared.lista_verifier import _check_total_1_doc

    deviz = _make_deviz([[1, 2, 3]])
    result = _check_total_1_doc([deviz], None)
    assert result['ok'] is None
    assert result['skipped'] is True


def test_verify_red_when_doc_total_1_disagrees():
    """A lost article changes the sum; the printed TOTAL 1 must catch it."""
    deviz = _make_deviz([[1, 2, 3]])
    result = verify([deviz], doc_total_1=40.0)
    assert result['status'] == 'RED'
    assert result['checks']['TOTAL_1_DOC']['ok'] is False


def test_verify_ok_when_doc_total_1_agrees():
    deviz = _make_deviz([[1, 2, 3]])
    result = verify([deviz], doc_total_1=30.0)
    assert result['status'] == 'OK'


# --- Footer coherence (TOTAL GENERAL / TVA) ---

def test_check_footer_coherent_ok():
    from shared.lista_verifier import _check_footer

    result = _check_footer({
        'total_general_fara_tva': 1433031.11,
        'tva_pct': 21.0,
        'tva_val': 300936.53,
        'total_cu_tva': 1733967.64,
    })
    assert result['ok'] is True


def test_check_footer_flags_lost_tva_value():
    """A wrapped TVA label loses the value; the totals alone still look fine."""
    from shared.lista_verifier import _check_footer

    result = _check_footer({
        'total_general_fara_tva': 1433031.11,
        'total_cu_tva': 1733967.64,
    })
    assert result['ok'] is False
    assert 'tva_val' in result['missing']


def test_check_footer_flags_arithmetic_mismatch():
    from shared.lista_verifier import _check_footer

    result = _check_footer({
        'total_general_fara_tva': 1000.0,
        'tva_pct': 21.0,
        'tva_val': 210.0,
        'total_cu_tva': 9999.0,
    })
    assert result['ok'] is False
    assert result['sum_diff'] == pytest.approx(8789.0)


def test_check_footer_skipped_when_document_prints_none():
    from shared.lista_verifier import _check_footer

    result = _check_footer({})
    assert result['ok'] is None
    assert result['skipped'] is True


def test_verify_red_when_footer_incoherent():
    deviz = _make_deviz([[1, 2, 3]])
    result = verify([deviz], footer={
        'total_general_fara_tva': 1433031.11,
        'total_cu_tva': 1733967.64,
    })
    assert result['status'] == 'RED'
    assert result['checks']['FOOTER']['ok'] is False
