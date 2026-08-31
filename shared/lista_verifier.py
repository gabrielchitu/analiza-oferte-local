# shared/lista_verifier.py
"""Autoverificare articole extrase: gaps nr_crt, total deviz, breakdown."""

import re
from typing import Callable, Optional

_NR_ART_RAW_RE = re.compile(r'^\d{1,3}$')

# 'NR COD - denumire' pe o singura linie — acelasi format pe care il accepta
# f3_price_extractor._NR_COD_INLINE_RE
_NR_COD_INLINE_RAW_RE = re.compile(r'^(\d{1,3})\s+(?:[A-Z0-9$.*+#%^>@<-]{2,}|\d{4,})\s+-\s+')

# Randul de antet al tabelului F3; numerele de coloana de dinaintea lui
# ('0' '1' '2' '3' '4') nu sunt numere de articol
_TABLE_HEADER_LINE = '5 = 3 x 4'


def _check_count_devize(extracted: list[dict], deviz_headers: dict = None) -> dict:
    found = len(extracted)
    if deviz_headers is None:
        return {'ok': None, 'skipped': True, 'found': found, 'expected': None}
    expected = len(deviz_headers)
    return {'ok': found == expected, 'found': found, 'expected': expected}


def _check_nr_crt_gaps(extracted: list[dict], raw_nrs: set[int] | None = None) -> dict:
    """Missing article numbers.

    A hole only means an article was lost if that number is actually printed in
    the document. A 'situatie de lucrari' lists just the articles executed in
    the period, so its numbering skips by design — pass `raw_nrs` to tell the
    two apart.
    """
    gaps = []
    skipped = []
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
                for n in range(a + 1, b):
                    if raw_nrs is not None and n not in raw_nrs:
                        skipped.append(n)
                    else:
                        gaps.append(n)
    if skipped:
        return {'ok': len(gaps) == 0, 'gaps': gaps, 'numbering_skips': skipped}
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


def _check_total_1_doc(extracted: list[dict], doc_total_1: float | None) -> dict:
    """Cross-check the extracted grand total against the one the document prints.

    `total_deviz` is *derived* from what was extracted, so TOTAL_DEVIZ can only
    confirm the sum is self-consistent. 'TOTAL 1 (Cheltuieli directe)' is read
    straight off the recapitulation, which makes it the one figure that can
    reveal a whole capitol or article silently missing from the extraction.
    """
    if doc_total_1 is None:
        return {'ok': None, 'skipped': True, 'reason': 'TOTAL 1 not found in document'}
    computed = sum(d.get('total_deviz', 0.0) or 0.0 for d in extracted)
    diff = abs(computed - doc_total_1)
    return {
        'ok': diff <= 0.05,
        'computed': computed,
        'doc': doc_total_1,
        'diff': diff,
    }


def article_nrs_in_page_classes(page_classes: list[dict]) -> set[int]:
    """Every article number printed in the raw F3 pages.

    Only the article zone counts: on a page that opens the table, the column
    numbers ('0' '1' '2' '3' '4') printed just above the '5 = 3 x 4' header
    would otherwise be read as article numbers.  Article numbers appear either
    standalone or glued to the code ('4 ACD03A01> - Bazin ...').
    """
    found: set[int] = set()
    for pc in page_classes:
        if not pc.get('is_f3'):
            continue
        lines = [line.strip() for line in pc.get('lines', [])]
        if _TABLE_HEADER_LINE in lines:
            lines = lines[lines.index(_TABLE_HEADER_LINE) + 1:]
        for s in lines:
            m = _NR_COD_INLINE_RAW_RE.match(s)
            n = int(m.group(1)) if m else (int(s) if _NR_ART_RAW_RE.match(s) else None)
            if n is not None and 1 <= n <= 999:
                found.add(n)
    return found


def max_nr_crt_in_page_classes(page_classes: list[dict]) -> int | None:
    """Highest article nr printed in the raw F3 pages."""
    found = article_nrs_in_page_classes(page_classes)
    return max(found) if found else None


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


def _check_hollow_articles(extracted: list[dict]) -> dict:
    """Detect articles that have prices but no cod/denumire — extraction bug."""
    hollow = []
    for deviz in extracted:
        for cap in deviz.get('capitole', []):
            for art in cap.get('articole', []):
                if (not art.get('cod') and not art.get('denumire')
                        and (art.get('total') or art.get('cantitate'))):
                    hollow.append({
                        'nr_crt': art.get('nr_crt'),
                        'cantitate': art.get('cantitate'),
                        'total': art.get('total'),
                    })
    return {'ok': len(hollow) == 0, 'hollow_articles': hollow}


def verify(
    extracted: list[dict],
    deviz_headers: dict = None,
    max_iterations: int = 5,
    reextract_fn: Optional[Callable] = None,
    raw_max_nr: int | None = None,
    raw_nrs: set[int] | None = None,
    doc_total_1: float | None = None,
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
            'NR_CRT_GAPS':       _check_nr_crt_gaps(current, raw_nrs),
            'LAST_NR_CRT':       _check_last_nr_crt(current, raw_max_nr),
            'HOLLOW_ARTICLES':   _check_hollow_articles(current),
            'TOTAL_CAPITOL':     _check_total_capitol(current),
            'TOTAL_DEVIZ':       _check_total_deviz(current),
            'TOTAL_1_DOC':       _check_total_1_doc(current, doc_total_1),
            'BREAKDOWN_CONTROL': _check_breakdown_control(current),
        }

        high_failures = [
            k for k in ('NR_CRT_GAPS', 'LAST_NR_CRT', 'TOTAL_CAPITOL', 'TOTAL_DEVIZ',
                       'TOTAL_1_DOC')
            if checks[k].get('ok') is False
        ]

        if not high_failures:
            has_warn = any(
                not checks[k]['ok']
                for k in ('BREAKDOWN_CONTROL', 'HOLLOW_ARTICLES')
                if checks[k].get('ok') is not None
            )
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
