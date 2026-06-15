# shared/lista_verifier.py
"""Autoverificare articole extrase: gaps nr_crt, total deviz, breakdown."""

import re
from typing import Callable, Optional

_NR_ART_RAW_RE = re.compile(r'^\d{1,3}$')


def _check_count_devize(extracted: list[dict], deviz_headers: dict = None) -> dict:
    found = len(extracted)
    if deviz_headers is None:
        return {'ok': None, 'skipped': True, 'found': found, 'expected': None}
    expected = len(deviz_headers)
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
    }


def max_nr_crt_in_page_classes(page_classes: list[dict]) -> int | None:
    """Scan F3 page lines for the highest standalone integer (1-999) = raw last article nr."""
    best = None
    for pc in page_classes:
        if not pc.get('is_f3'):
            continue
        for line in pc.get('lines', []):
            s = line.strip()
            if _NR_ART_RAW_RE.match(s):
                n = int(s)
                if 1 <= n <= 999 and (best is None or n > best):
                    best = n
    return best


def _check_last_nr_crt(extracted: list[dict], raw_max_nr: int | None) -> dict:
    """Verify max extracted nr_crt == max nr_crt found in raw F3 lines."""
    if raw_max_nr is None:
        return {'ok': None, 'skipped': True, 'reason': 'raw_max_nr not provided'}
    extracted_max = None
    for deviz in extracted:
        for cap in deviz.get('capitole', []):
            for art in cap.get('articole', []):
                try:
                    n = int(art['nr_crt'])
                    if extracted_max is None or n > extracted_max:
                        extracted_max = n
                except (ValueError, TypeError):
                    pass
    if extracted_max is None:
        return {'ok': False, 'extracted_max': None, 'raw_max': raw_max_nr}
    return {
        'ok': extracted_max == raw_max_nr,
        'extracted_max': extracted_max,
        'raw_max': raw_max_nr,
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
    raw_max_nr: int | None = None,
) -> dict:
    """Run all checks, retry up to max_iterations if HIGH checks fail.

    Returns verification result dict: {status, iterations, checks}.
    status: 'OK' | 'WARN' | 'RED'
    """
    current = extracted
    checks: dict = {}
    last_iteration = 0

    for iteration in range(1, max_iterations + 1):
        last_iteration = iteration
        checks = {
            'COUNT_DEVIZE':      _check_count_devize(current, deviz_headers),
            'NR_CRT_GAPS':       _check_nr_crt_gaps(current),
            'LAST_NR_CRT':       _check_last_nr_crt(current, raw_max_nr),
            'TOTAL_CAPITOL':     _check_total_capitol(current),
            'TOTAL_DEVIZ':       _check_total_deviz(current),
            'BREAKDOWN_CONTROL': _check_breakdown_control(current),
        }

        high_failures = [
            k for k in ('NR_CRT_GAPS', 'LAST_NR_CRT', 'TOTAL_CAPITOL', 'TOTAL_DEVIZ')
            if checks[k].get('ok') is False
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
        'iterations': last_iteration,
        'checks': checks,
    }
