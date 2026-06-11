import pytest
from shared.lista_verifier import verify, _check_nr_crt_gaps, _check_total_deviz, _check_total_capitol


def _make_deviz(articole_per_capitol, total_deviz=None, capitole_totals=None):
    capitole = []
    for idx, (nr_list, cap_total) in enumerate(
        zip(articole_per_capitol,
            capitole_totals or [None] * len(articole_per_capitol))
    ):
        arts = [
            {'nr_crt': str(nr), 'pret_unitar': 10.0, 'total': 10.0,
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
