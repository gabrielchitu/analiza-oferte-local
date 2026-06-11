# shared/lista_verifier.py
"""Autoverificare articole extrase: gaps nr_crt, total deviz, breakdown."""

from typing import Callable, Optional


def _check_count_devize(extracted: list[dict], deviz_headers: dict = None) -> dict:
    found = len(extracted)
    expected = len(deviz_headers) if deviz_headers else found
    return {'ok': found == expected, 'found': found, 'expected': expected}


def _check_nr_crt_gaps(extracted: list[dict]) -> dict:
    gaps = []
    for deviz in extracted:
        nrs = []
        for cap in deviz.get('capitole', []):
            for art in cap.get('articole', []):
                try:
                    nrs.append(int(art['nr_crt']))
                except (ValueError, TypeError):
                    pass
        nrs_sorted = sorted(set(nrs))
        for a, b in zip(nrs_sorted, nrs_sorted[1:]):
            if b - a > 1:
                gaps.extend(range(a + 1, b))
    return {'ok': len(gaps) == 0, 'gaps': gaps}


def _check_total_capitol(extracted: list[dict]) -> dict:
    failures = []
    for deviz in extracted:
        for cap in deviz.get('capitole', []):
            if cap.get('total_capitol') is None:
                continue
            computed = sum(a.get('total', 0.0) for a in cap.get('articole', []))
            diff = abs(computed - cap['total_capitol'])
            if diff > 0.05:
                failures.append({
                    'capitol': cap['titlu'],
                    'extracted': cap['total_capitol'],
                    'computed': computed,
                    'diff': diff,
                })
    return {'ok': len(failures) == 0, 'failures': failures}


def _check_total_deviz(extracted: list[dict]) -> dict:
    failures = []
    for deviz in extracted:
        computed = sum(
            cap.get('total_capitol') or sum(
                a.get('total', 0.0) for a in cap.get('articole', [])
            )
            for cap in deviz.get('capitole', [])
        )
        diff = abs(computed - deviz.get('total_deviz', 0.0))
        if diff > 0.05:
            failures.append({
                'deviz_key': deviz.get('deviz_key', ''),
                'extracted': deviz.get('total_deviz'),
                'computed': computed,
                'diff': diff,
            })
    return {
        'ok': len(failures) == 0,
        'failures': failures,
        'diff': failures[0]['diff'] if failures else 0.0,
    }


def _check_breakdown_control(extracted: list[dict]) -> dict:
    suspect = []
    for deviz in extracted:
        for cap in deviz.get('capitole', []):
            for art in cap.get('articole', []):
                if art.get('suspect', False):
                    suspect.append(art['nr_crt'])
    return {'ok': len(suspect) == 0, 'suspect_articles': suspect}


def verify(
    extracted: list[dict],
    deviz_headers: dict = None,
    max_iterations: int = 5,
    reextract_fn: Optional[Callable] = None,
) -> dict:
    """Run all checks, retry up to max_iterations if HIGH checks fail.

    Returns verification result dict: {status, iterations, checks}.
    status: 'OK' | 'WARN' | 'RED'
    """
    current = extracted

    for iteration in range(1, max_iterations + 1):
        checks = {
            'COUNT_DEVIZE':      _check_count_devize(current, deviz_headers),
            'NR_CRT_GAPS':       _check_nr_crt_gaps(current),
            'TOTAL_CAPITOL':     _check_total_capitol(current),
            'TOTAL_DEVIZ':       _check_total_deviz(current),
            'BREAKDOWN_CONTROL': _check_breakdown_control(current),
        }

        high_failures = [
            k for k in ('NR_CRT_GAPS', 'TOTAL_CAPITOL', 'TOTAL_DEVIZ')
            if not checks[k]['ok']
        ]

        if not high_failures:
            has_warn = not checks['BREAKDOWN_CONTROL']['ok']
            return {
                'status': 'WARN' if has_warn else 'OK',
                'iterations': iteration,
                'checks': checks,
            }

        if reextract_fn is None or iteration == max_iterations:
            break

        current = reextract_fn(current, checks, iteration)

    return {
        'status': 'RED',
        'iterations': max_iterations,
        'checks': checks,
    }
