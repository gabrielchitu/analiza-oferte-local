"""F3 price extractor — parses articles with prices from classified F3 pages."""

import re
import json
import hashlib
from pathlib import Path
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
    """Parse Romanian-format number: '7,473.71' → 7473.71, '225.000' → 225.0."""
    s = s.strip()
    if not s:
        return None
    cleaned = s.replace(',', '')
    try:
        return float(cleaned)
    except ValueError:
        return None


def _is_capitol_header(line: str) -> bool:
    """All-caps line with no digit prefix and no dash — section header."""
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
