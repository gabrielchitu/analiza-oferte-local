"""F3 price extractor — parses articles with prices from classified F3 pages."""

import re
from typing import Optional

_UM_KNOWN = {
    'MP', 'MC', 'ML', 'BUC', 'KG', 'T', 'L', 'SET', 'PERECHE', 'M',
    'ORA', 'ZI', 'LUNA', 'AN', 'TONA', 'MII', 'DM3', 'CM2', 'KM', 'HA',
}

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

_NR_INT_RE = re.compile(r'^\d+$')
_NR_DEC_RE = re.compile(r'^\d+\.\d+$')
_COD_NAME_RE = re.compile(r'^([A-Z0-9$.*+#%^>@<]{2,}|\d{4,})\s*-\s*.+$')
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
    """All-caps line with no digit prefix and no dash — section header.

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
    if s != s.upper():
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
