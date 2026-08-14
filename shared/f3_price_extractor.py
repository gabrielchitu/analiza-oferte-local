"""F3 price extractor — parses articles with prices from classified F3 pages."""

import json
import re
from pathlib import Path
from typing import Optional

# Romanian lowercase conjunctions/prepositions allowed inside CAPITOL headers
_HEADER_LOWER_ALLOWED = {'si', 'de', 'cu', 'a', 'al', 'ale', 'din', 'la', 'pe', 'in', 'ca'}

_UM_KNOWN = {
    'MP', 'MC', 'ML', 'BUC', 'BUCATA', 'KG', 'T', 'L', 'SET', 'PERECHE', 'M',
    'ORA', 'ZI', 'LUNA', 'AN', 'ANS', 'TONA', 'MII', 'DM3', 'CM2', 'KM', 'HA',
    # eDevize prints a literal 'um' in the unit column of some material lines.
    # It still occupies the UM slot: without it the qty/price window never
    # opens and the following numbers are misread as sub-item markers.
    'UM',
}

# Spelling variants folded onto the canonical UM used in the output
_UM_NORMALIZE = {'BUCATA': 'BUC'}

_SKIP_EXACT = {
    'Antet stanga', 'eDevize', 'e', 'Beneficiar:', 'Executant:', 'Proiectant:',
    'Obiectivul:', 'Obiectul:', 'Stadiul fizic:', 'Devize', 'Formular F3',
    'Lista cu cantitati de lucrari pe categorii de lucrari',
    'SECTIUNEA TEHNICA', 'SECTIUNEA FINANCIARA',
    'Nr.', 'Capitol de lucrari', 'U.M.', 'Cantitatea', 'Pretul unitar',
    'TOTALUL', '(fara TVA)', '- Lei -', '5 = 3 x 4',
    'Director', 'Sef proiect', 'Ofertant',
}

_SKIP_RE = re.compile(
    r'^(Pagina\s+\d+\s+din\s+\d+|Deviz\s+"[^"]*"'
    r'|Formular\s+generat|www\.eDevize'
    r'|TOTAL\s+1\s+\(|TOTAL\s+GENERAL|T[234]\s*='
    r'|Recapitulatie|Greutate\s+Materiale|Ore\s+Manopera'
    r'|Alte\s+cheltuieli|Contributia|Cheltuieli\s+indirecte'
    r'|Beneficiu|Profit|TVA)',
    re.IGNORECASE
)

# Sfarsitul tabelului de articole — urmeaza blocul de recapitulatie. Etichetele
# lui sunt deja in _SKIP_RE, dar numerele dintre ele nu sunt, iar valorile pe
# care OCR-ul le rupe in doua ('1,081,909.0' + '6') lasa cifre izolate care
# altfel devin nr_crt de articol.
_END_OF_ARTICLES_RE = re.compile(
    r'^(TOTAL\s+1\s*\(Cheltuieli\s+directe|Recapitulati[ae]?\b)', re.IGNORECASE
)

_TG_FARA_TVA_RE = re.compile(r'TOTAL\s+GENERAL\s*\(fara\s+TVA\)', re.IGNORECASE)
_TVA_LINE_RE    = re.compile(r'\bTVA\b[^\d(]*\((\d+[\.,]\d+)\s*%\)', re.IGNORECASE)
_TG_CU_TVA_RE   = re.compile(r'TOTAL\s+GENERAL\s*\(inclusiv\s+TVA\)', re.IGNORECASE)


_PARTY_LABELS = {
    'Beneficiar:': 'beneficiar',
    'Executant:':  'executant',
    'Proiectant:': 'proiectant',
}


def extract_document_parties(raw_pages: list) -> dict:
    """Scan raw DI pages for Beneficiar/Executant/Proiectant (label on line N, value on N+1)."""
    parties: dict = {}
    for page in raw_pages:
        lines = [ln.get('content', '').strip() for ln in page.get('lines', [])]
        for i, line in enumerate(lines):
            key = _PARTY_LABELS.get(line)
            if key and key not in parties and i + 1 < len(lines):
                val = lines[i + 1].strip()
                if val:
                    parties[key] = val
        if len(parties) == 3:
            break
    return parties


def extract_footer_totals(page_classes: list) -> dict:
    """Scan every page for TOTAL GENERAL / TVA footer values.

    Non-F3 pages count too: in most devize the recapitulation sits on a page
    of its own, which the classifier correctly labels NON_F3 — restricting the
    scan to F3 pages loses the footer entirely.

    In eDevize OCR output the value for each footer row sits on a *different*
    line than the label:
      - TOTAL GENERAL (fara TVA):  value is on the line BEFORE the label
      - TVA (XX%):                 value is on the line AFTER the label
      - TOTAL GENERAL (inclusiv TVA): value is on the line AFTER the label
    """
    footer: dict = {}
    all_lines: list = []
    for pc in page_classes:
        all_lines.extend(line.strip() for line in pc.get('lines', []))

    for i, s in enumerate(all_lines):
        if _TG_FARA_TVA_RE.search(s):
            val = _parse_number(all_lines[i - 1]) if i > 0 else None
            if val is not None:
                footer['total_general_fara_tva'] = val
        elif _TVA_LINE_RE.search(s):
            m = _TVA_LINE_RE.search(s)
            pct = _parse_number(m.group(1)) if m else None
            if pct is not None:
                footer['tva_pct'] = pct
            val = _parse_number(all_lines[i + 1]) if i + 1 < len(all_lines) else None
            if val is not None:
                footer['tva_val'] = val
        elif _TG_CU_TVA_RE.search(s):
            val = _parse_number(all_lines[i + 1]) if i + 1 < len(all_lines) else None
            if val is not None:
                footer['total_cu_tva'] = val
    return footer


_NR_INT_RE = re.compile(r'^\d+$')
_NR_DEC_RE = re.compile(r'^\d+\.\d+$')
# Article code token: all-caps/symbolic, a bare numeric material code, or a
# mixed-case normative code ('AcD27A1*', 'eA10B1' — eDevize is not consistent
# about capitalisation). The mixed-case form must contain a digit so ordinary
# words ahead of a dash are not mistaken for codes.
_COD_TOKEN = r'[A-Z0-9$.*+#%^>@<-]{2,}|\d{4,}|[A-Za-z]{1,5}\d[A-Za-z0-9$.*+#%^>@<-]*'
_COD_NAME_RE = re.compile(rf'^({_COD_TOKEN})\s+-\s+(.+)$')
_NR_COD_INLINE_RE = re.compile(rf'^(\d{{1,3}})\s+({_COD_TOKEN})\s+-\s+(.+)$')
_TOTAL_CAPITOL_RE = re.compile(r'^TOTAL\s+(.+)$', re.IGNORECASE)
_BREAKDOWN_RE = re.compile(r'^(material|manopera|utilaj|transport):$', re.IGNORECASE)


def _parse_number(s: str) -> Optional[float]:
    """Parse a number in either US or EU format.

    US format: '7,473.71'  (comma=thousands, dot=decimal) → 7473.71
    EU format: '1.234,56'  (dot=thousands, comma=decimal) → 1234.56
    Ambiguous: '225.000' treated as dot=decimal → 225.0

    Detection rule: when both separators are present, the one that appears
    *last* (rightmost) is the decimal separator — identical logic to
    f3_regex_parser._parse_number so the two modules stay in sync.
    """
    s = s.strip().replace(' ', '')
    if not s:
        return None
    if '.' in s and ',' in s:
        if s.index('.') < s.index(','):
            # dot comes first → dot=thousands, comma=decimal  (EU)
            s = s.replace('.', '').replace(',', '.')
        else:
            # comma comes first → comma=thousands, dot=decimal  (US)
            s = s.replace(',', '')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return None


def _is_capitol_header(line: str) -> bool:
    """All-caps line with no digits and no dash — section header.

    Deliberately strict: a title missed here is recovered from the closing
    'TOTAL <name>' line, whereas a false positive swallows an article row.

    Note: callers must check `_is_cod_name` first — all-caps cod-name lines
    (e.g. ``RPCE27A+ - MASTIC BITUMINOS``) satisfy both predicates.
    """
    s = line.strip()
    if not s or len(s) < 3:
        return False
    if s.startswith('TOTAL'):
        return False
    if _NR_INT_RE.match(s) or _NR_DEC_RE.match(s):
        return False
    if re.search(r'\d', s) and '-' not in s:
        return False
    if re.fullmatch(r'\d+[-/]\d+', s):
        return False
    if not all(w.isupper() or w in _HEADER_LOWER_ALLOWED for w in s.split()):
        return False
    if s in _SKIP_EXACT:
        return False
    return True


def _is_cod_name(line: str) -> bool:
    """Line matching 'CODE - DENUMIRE' pattern."""
    return bool(_COD_NAME_RE.match(line.strip()))


def _is_um(line: str) -> bool:
    """Line is a known unit of measure."""
    return line.strip().upper() in _UM_KNOWN


def _match_um(line: str, next_line: str = '') -> Optional[tuple[str, int]]:
    """Match a UM starting at `line`, tolerating an OCR line-split.

    eDevize output sometimes wraps a UM across two lines ('BUCAT' + 'A').
    Returns ``(canonical_um, lines_consumed)`` or ``None``.
    """
    s = line.strip().upper()
    if s in _UM_KNOWN:
        return _UM_NORMALIZE.get(s, s), 1
    joined = s + next_line.strip().upper()
    if joined in _UM_KNOWN:
        return _UM_NORMALIZE.get(joined, joined), 2
    return None


def _is_breakdown_key(line: str) -> bool:
    """Line is 'material:', 'manopera:', etc."""
    return bool(_BREAKDOWN_RE.match(line.strip()))


def _is_skip(line: str) -> bool:
    """Line should be ignored."""
    s = line.strip()
    if s in _SKIP_EXACT:
        return True
    if _SKIP_RE.match(s):
        return True
    return False


def _parse_f3_page_lines(lines: list[str]) -> list[tuple[str, dict]]:
    """Convert raw page lines to typed events. Skips page header zone.

    Events: CAPITOL, TOTAL_CAPITOL, ART_NR, SUB_NR, COD_NAME, UM, NUMBER,
            BREAKDOWN, TEXT

    Note: callers should not expect CAPITOL + COD_NAME overlap since _is_cod_name
    is checked before _is_capitol_header in the dispatch order below.

    Sub-item detection: a decimal-looking token (e.g. "1.1") is only emitted as
    SUB_NR when we are *between* an article's BREAKDOWN block and the next
    top-level integer.  During the UM→NUMBER window (qty / unit-price / total
    still in flight) the same token is treated as a plain NUMBER so that
    quantities like "225.000" or prices like "33.22" are not mis-classified.
    """
    events: list[tuple[str, dict]] = []
    in_article_zone = False
    # State tracking for SUB_NR disambiguation
    # After a UM we collect up to 3 numbers (qty, pret, total) before
    # breakdowns. Once the 3-number window is exhausted and/or breakdowns
    # appear, decimal tokens are again eligible as sub-item markers.
    in_num_window = False  # True when UM seen and <3 NUMBERs collected yet
    num_window_count = 0
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        if line == '5 = 3 x 4':
            in_article_zone = True
            continue

        if line == 'Antet stanga':
            in_article_zone = False
            continue

        if _END_OF_ARTICLES_RE.match(line):
            in_article_zone = False
            continue

        if not in_article_zone:
            continue

        if _is_skip(line) or not line:
            continue

        # TOTAL CAPITOL: two-line pattern — consume next line as amount
        m = _TOTAL_CAPITOL_RE.match(line)
        if m and not re.search(r'^\d', m.group(1).strip()):
            if i < len(lines):
                amount = _parse_number(lines[i].strip())
                if amount is not None:
                    events.append(('TOTAL_CAPITOL', {
                        'titlu': m.group(1).strip(),
                        'total': amount,
                    }))
                    i += 1
                    in_num_window = False
                    num_window_count = 0
                    continue

        # NR + COD + DENUMIRE on same line (e.g. '10 CF17A01* - Amorsa...')
        m_nr_cod = _NR_COD_INLINE_RE.match(line)
        if m_nr_cod:
            in_num_window = False
            num_window_count = 0
            events.append(('ART_NR', {'nr_crt': m_nr_cod.group(1)}))
            events.append(('COD_NAME', {'cod': m_nr_cod.group(2), 'denumire': m_nr_cod.group(3).strip()}))
            continue

        # COD + DENUMIRE checked BEFORE capitol header (all-caps overlap)
        if _is_cod_name(line):
            denumire_parts = [line]
            while i < len(lines):
                nxt = lines[i].strip()
                nxt2 = lines[i + 1].strip() if (i + 1) < len(lines) else ''
                if (_match_um(nxt, nxt2) or _is_cod_name(nxt) or _is_breakdown_key(nxt)
                        or _is_skip(nxt) or _TOTAL_CAPITOL_RE.match(nxt)):
                    break
                last_part = denumire_parts[-1].strip()
                if _is_capitol_header(nxt) and not last_part.endswith('-'):
                    # A real section header is never followed by a UM; an all-caps
                    # line that is, is a wrapped denumire fragment
                    # ('... pt. instalatie' + 'CATV' + 'm').
                    nxt3 = lines[i + 2].strip() if (i + 2) < len(lines) else ''
                    if not _match_um(nxt2, nxt3):
                        break
                # Integer/decimal before UM = norm code in denomination (e.g. '2111' then 'kg')
                if _NR_INT_RE.match(nxt) or _NR_DEC_RE.match(nxt) or _parse_number(nxt) is not None:
                    next_next = lines[i + 1].strip() if (i + 1) < len(lines) else ''
                    if _is_um(next_next):
                        denumire_parts.append(nxt)
                        i += 1
                        continue
                    break
                denumire_parts.append(nxt)
                i += 1
            full_line = denumire_parts[0]
            m_cn = _COD_NAME_RE.match(full_line)
            cod = m_cn.group(1).strip()
            den_first = m_cn.group(2).strip()
            denumire = ' '.join([den_first] + denumire_parts[1:]).strip()
            events.append(('COD_NAME', {'cod': cod, 'denumire': denumire}))
            continue

        # CAPITOL HEADER — but a line-split UM ('BUCAT' + 'A') is not a header
        if _is_capitol_header(line) and not _match_um(line, lines[i].strip() if i < len(lines) else ''):
            in_num_window = False
            num_window_count = 0
            events.append(('CAPITOL', {'titlu': line}))
            continue

        # SUB-ITEM NR (decimal like "3.1") — only outside the qty/price window
        if _NR_DEC_RE.match(line) and not in_num_window:
            events.append(('SUB_NR', {'nr_crt': line}))
            # num window opens later when UM fires; no window state change here
            continue

        # ARTICLE NR (integer)
        if _NR_INT_RE.match(line):
            in_num_window = False
            num_window_count = 0
            events.append(('ART_NR', {'nr_crt': line}))
            continue

        # BREAKDOWN KEY — consume next 2 lines as (pret, total)
        # Breakdowns close the num window
        if _is_breakdown_key(line):
            in_num_window = False
            num_window_count = 0
            key = line.rstrip(':').lower()
            if i + 1 < len(lines):
                pret = _parse_number(lines[i].strip())
                total = _parse_number(lines[i + 1].strip())
                if pret is not None and total is not None:
                    events.append(('BREAKDOWN', {
                        'key': key,
                        'pret': pret,
                        'total': total,
                    }))
                    i += 2
                    continue

        # UM — opens the num window (next ≤3 decimal tokens are numbers)
        m_um = _match_um(line, lines[i].strip() if i < len(lines) else '')
        if m_um:
            um, consumed = m_um
            i += consumed - 1
            in_num_window = True
            num_window_count = 0
            events.append(('UM', {'um': um}))
            continue

        # NUMBER (plain float/int value)
        num = _parse_number(line)
        if num is not None:
            if in_num_window:
                num_window_count += 1
                if num_window_count >= 3:
                    in_num_window = False
                    num_window_count = 0
            events.append(('NUMBER', {'value': num, 'raw': line}))
            continue

        # Decimal-looking token inside num window was already handled above as NUMBER
        # (it didn't match _NR_DEC_RE path because in_num_window was True)
        events.append(('TEXT', {'text': line}))

    return events


def _assemble_deviz(events: list[tuple[str, dict]], header) -> dict:
    """Assemble events from one deviz into structured dict."""
    capitole = []
    current_capitol = None
    current_article = None
    num_queue: list[float] = []
    in_sub_item = False
    current_sub: dict | None = None

    def _flush_article():
        nonlocal current_article, num_queue, in_sub_item, current_sub
        if current_sub is not None and len(num_queue) >= 3:
            current_sub['cantitate'] = num_queue[0]
            current_sub['pret_unitar'] = num_queue[1]
            current_sub['total'] = num_queue[2]
            if current_article:
                current_article['sub_items'].append(current_sub)
            current_sub = None
        elif current_article is not None and len(num_queue) >= 3:
            current_article['cantitate'] = num_queue[0]
            current_article['pret_unitar'] = num_queue[1]
            current_article['total'] = num_queue[2]
        num_queue.clear()
        in_sub_item = False

    def _flush_to_capitol():
        nonlocal current_article
        _flush_article()
        if current_article is not None and current_capitol is not None:
            current_capitol['articole'].append(current_article)
        current_article = None

    for etype, data in events:
        if etype == 'CAPITOL':
            _flush_to_capitol()
            if current_capitol is not None:
                capitole.append(current_capitol)
            current_capitol = {
                'titlu': data['titlu'],
                'articole': [],
                'total_capitol': None,
            }

        elif etype == 'TOTAL_CAPITOL':
            _flush_to_capitol()
            if current_capitol is not None:
                current_capitol['total_capitol'] = data['total']
                # _is_capitol_header is intentionally strict and misses titles
                # carrying digits or dashes ('APARTAMENT 3 CAMERE',
                # 'INFRASTRUCTURA - TERASAMENTE'). The closing line names the
                # section, so recover it rather than leave the header blank.
                if not current_capitol['titlu'].strip():
                    current_capitol['titlu'] = data['titlu']
                capitole.append(current_capitol)
                current_capitol = None

        elif etype == 'ART_NR':
            _flush_to_capitol()
            if current_capitol is None:
                current_capitol = {'titlu': '', 'articole': [], 'total_capitol': None}
            current_article = {
                'nr_crt': data['nr_crt'],
                'cod': '', 'denumire': '',
                'um': '', 'cantitate': 0.0,
                'pret_unitar': 0.0, 'total': 0.0,
                'breakdown': None, 'sub_items': [],
                'suspect': False,
            }
            in_sub_item = False

        elif etype == 'SUB_NR':
            _flush_article()
            in_sub_item = True
            current_sub = {
                'nr_crt': data['nr_crt'],
                'cod': '', 'denumire': '',
                'um': '', 'cantitate': 0.0,
                'pret_unitar': 0.0, 'total': 0.0,
            }

        elif etype == 'COD_NAME':
            if in_sub_item and current_sub is not None:
                current_sub['cod'] = data['cod']
                current_sub['denumire'] = data['denumire']
            elif current_article is not None:
                current_article['cod'] = data['cod']
                current_article['denumire'] = data['denumire']

        elif etype == 'UM':
            if in_sub_item and current_sub is not None:
                current_sub['um'] = data['um']
            elif current_article is not None:
                current_article['um'] = data['um']
            num_queue.clear()

        elif etype == 'NUMBER':
            num_queue.append(data['value'])

        elif etype == 'BREAKDOWN':
            # Sub-items carry their own breakdown block in some devize; without
            # this branch the last sub-item's block overwrites the article's.
            target = current_sub if (in_sub_item and current_sub is not None) else current_article
            if target is not None:
                if target.get('breakdown') is None:
                    target['breakdown'] = {
                        'material': {'pret': 0.0, 'total': 0.0},
                        'manopera': {'pret': 0.0, 'total': 0.0},
                        'utilaj': {'pret': 0.0, 'total': 0.0},
                        'transport': {'pret': 0.0, 'total': 0.0},
                        'control_ok': False,
                    }
                target['breakdown'][data['key']] = {
                    'pret': data['pret'],
                    'total': data['total'],
                }

    _flush_to_capitol()
    if current_capitol is not None:
        capitole.append(current_capitol)

    for cap in capitole:
        for art in cap['articole']:
            if art['breakdown']:
                bd = art['breakdown']
                computed = sum(
                    bd[k]['pret'] for k in ('material', 'manopera', 'utilaj', 'transport')
                )
                art['breakdown']['control_ok'] = abs(computed - art['pret_unitar']) < 0.02
                art['suspect'] = not art['breakdown']['control_ok']

    return {
        'deviz_key': header.deviz_key,
        'obiectivul': header.obiectivul or '',
        'obiectul': header.obiectul or '',
        'categoria': header.categoria or '',
        'capitole': capitole,
        'total_deviz': sum(
            cap['total_capitol'] or sum(a.get('total', 0.0) for a in cap.get('articole', []))
            for cap in capitole
        ),
    }


def extract_prices(
    page_classes: list[dict],
    deviz_headers: dict,
    checkpoint_path=None,
    force: bool = False,
) -> list[dict]:
    """Extract articles+prices from classified F3 pages.

    Args:
        page_classes: output from f3_page_classifier.classify_pages()
        deviz_headers: dict[deviz_key, DevizHeader] from extract_deviz_headers()
        checkpoint_path: optional Path to save/load extracted data
        force: if True, ignore existing checkpoint

    Returns: list of deviz dicts
    """
    if checkpoint_path and Path(checkpoint_path).exists() and not force:
        return json.loads(Path(checkpoint_path).read_text(encoding='utf-8'))

    from collections import defaultdict
    pages_by_cod: dict[str, list[list[str]]] = defaultdict(list)
    for pc in page_classes:
        if pc.get('is_f3') and not pc.get('header_only'):
            cod = pc.get('deviz_cod', '')
            if cod:
                pages_by_cod[cod].append(pc.get('lines', []))

    cod_to_header: dict[str, object] = {}
    for header in deviz_headers.values():
        cod = (getattr(header, 'deviz_cod', '') or '').strip()
        if cod and cod not in cod_to_header:
            cod_to_header[cod] = header

    result = []
    for cod, page_lines_list in pages_by_cod.items():
        header = cod_to_header.get(cod)
        if header is None:
            header = next(iter(deviz_headers.values()), None)
        if header is None:
            continue

        all_lines: list[str] = []
        for page_lines in page_lines_list:
            all_lines.extend(page_lines)

        events = _parse_f3_page_lines(all_lines)
        deviz = _assemble_deviz(events, header)
        result.append(deviz)

    if checkpoint_path:
        p = Path(checkpoint_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')

    return result
