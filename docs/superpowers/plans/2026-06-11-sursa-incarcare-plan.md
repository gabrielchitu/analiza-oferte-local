# Sursa de Încărcare — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pipeline care transformă un `di_*.json` în `Lista-proiect-XXX.docx/xlsx/pdf` — sursă F3 cu prețuri, verificare automată și retry loop.

**Architecture:** Abordare B — extractor dedicat (`f3_price_extractor.py`) rulează pe paginile deja clasificate de `f3_page_classifier` (existent, LLM-cached). Pipeline existent `local_run.py` / `f3_regex_parser.py` rămâne neatins. Trei module noi: extractor, verifier, writer. CLI orchestrează totul.

**Tech Stack:** `python-docx`, `openpyxl`, `LibreOffice CLI (optional)`, `anthropic` (refolosit din pipeline existent pentru page classifier)

**Spec:** `docs/superpowers/specs/2026-06-11-sursa-incarcare-design.md`

---

## File Structure

```
shared/f3_price_extractor.py      ← line parser + state machine + public API
shared/lista_verifier.py           ← 5 checks + retry loop
shared/sursa_incarcare_writer.py   ← make_acronym + write_docx + write_xlsx + write_pdf
gen_sursa_incarcare.py             ← CLI entry point + orchestration
tests/shared/test_f3_price_extractor.py
tests/shared/test_lista_verifier.py
tests/shared/test_sursa_incarcare_writer.py
```

Fișiere existente neatinse: `f3_regex_parser.py`, `f3_page_classifier.py`, `deviz_header_extractor.py`, `local_run.py`.

---

## Context critic pentru implementator

### Structura reală a liniilor din DI JSON (EuroProject)

Fiecare articol F3 din JSON este o secvență de linii individuale (nu o linie combinată):

```
'INFRASTRUCTURA'          ← capitol header (all-caps, singur pe linie)
'1'                        ← nr_crt articol (întreg singur)
'CF38A* - Tencuiala pe baza de ciment'  ← cod + " - " + denumire
'mp'                       ← UM
'225.000'                  ← cantitate (3 zecimale)
'33.22'                    ← pret_unitar (2 zecimale)
'7,473.71'                 ← total (2 zecimale, virgulă ca sep. mii)
'material:'                ← breakdown key (singur pe linie)
'13.22'                    ← breakdown pret
'2,973.71'                 ← breakdown total
'manopera:'
'20.00'
'4,500.00'
'utilaj:'
'0.00'
'0.00'
'transport:'
'0.00'
'0.00'
'TOTAL INFRASTRUCTURA'     ← total capitol (2 linii: header + valoare)
'24,220.05'
'3.1'                      ← sub-item nr (decimal singur pe linie)
'2101121 - Mortar de zidarie M 10 nisip S1030'
'mc'
'1.939'
'385.00'
'746.62'
```

Linii multi-linie pentru DENUMIRE lungă:
```
'5'
'RPCE31B+ - Hidroizolatie membrana bituminoasa cu'  ← prima parte
'armatura din poliester netesut - la contactul zidariei cu'   ← continuare
'placa de la cota +/- 0,00'                          ← continuare
'MP'
'34.000'
```

Zona de header pagină (SKIP — linii de la `'Antet stanga'` până la `'5 = 3 x 4'` inclusiv) apare la fiecare pagină. Zona de articole începe DUPĂ `'5 = 3 x 4'`.

### Interfețe existente relevante

```python
# f3_page_classifier.classify_pages() returnează:
page_classes: list[dict]  # fiecare dict are:
  {
    "is_f3": bool,
    "deviz_cod": str,      # ex: "3.1"
    "deviz_den": str,
    "lines": list[str],    # linii brute ale paginii
    "page_number": int,
    "header_only": bool,
  }

# deviz_header_extractor.extract_deviz_headers() returnează:
deviz_headers: dict[str, DevizHeader]  # keyed by deviz_key (md5 hash)
# DevizHeader are: .obiectivul, .obiectul, .categoria, .deviz_key, .is_valid

# ClientConfig (shared/client_config.py):
config.name, config.input_dir, config.output_dir, config.checkpoint_dir
config.reference_file  # Path la di_referinta.json
config.offer_files     # list[Path] la di_oferta_*.json
```

---

## Task 1: f3_price_extractor — Line Parser

**Files:**
- Create: `shared/f3_price_extractor.py`
- Create: `tests/shared/test_f3_price_extractor.py`

- [ ] **Step 1: Scrie testele pentru `_parse_number` și `_is_capitol_header`**

```python
# tests/shared/test_f3_price_extractor.py
import pytest
from shared.f3_price_extractor import _parse_number, _is_capitol_header, _is_cod_name, _is_um, _is_breakdown_key

def test_parse_number_simple():
    assert _parse_number("33.22") == pytest.approx(33.22)

def test_parse_number_with_thousands():
    assert _parse_number("7,473.71") == pytest.approx(7473.71)

def test_parse_number_zero():
    assert _parse_number("0.00") == pytest.approx(0.0)

def test_parse_number_invalid():
    assert _parse_number("material:") is None
    assert _parse_number("INFRASTRUCTURA") is None
    assert _parse_number("") is None

def test_is_capitol_header_yes():
    assert _is_capitol_header("INFRASTRUCTURA") is True
    assert _is_capitol_header("COMPARTIMENTARI") is True
    assert _is_capitol_header("FINISAJE EXTERIOARE") is True

def test_is_capitol_header_no():
    assert _is_capitol_header("TOTAL INFRASTRUCTURA") is False
    assert _is_capitol_header("1") is False
    assert _is_capitol_header("CF38A* - Tencuiala") is False
    assert _is_capitol_header("Nr.") is False

def test_is_cod_name_standard():
    assert _is_cod_name("CF38A* - Tencuiala pe baza de ciment") is True
    assert _is_cod_name("RPCE27A+ - Mastic bituminos") is True

def test_is_cod_name_numeric():
    assert _is_cod_name("2101121 - Mortar de zidarie M 10 nisip S1030") is True

def test_is_cod_name_no():
    assert _is_cod_name("mp") is False
    assert _is_cod_name("225.000") is False
    assert _is_cod_name("armatura din poliester") is False  # continuation line

def test_is_um():
    assert _is_um("mp") is True
    assert _is_um("MP") is True
    assert _is_um("mc") is True
    assert _is_um("buc") is True
    assert _is_um("ml") is True
    assert _is_um("kg") is True
    assert _is_um("33.22") is False
    assert _is_um("CF38A*") is False

def test_is_breakdown_key():
    assert _is_breakdown_key("material:") is True
    assert _is_breakdown_key("manopera:") is True
    assert _is_breakdown_key("utilaj:") is True
    assert _is_breakdown_key("transport:") is True
    assert _is_breakdown_key("material") is False
    assert _is_breakdown_key("TOTAL") is False
```

- [ ] **Step 2: Rulează testele să eșueze**

```bash
pytest tests/shared/test_f3_price_extractor.py -v
```
Expected: `ModuleNotFoundError: No module named 'shared.f3_price_extractor'`

- [ ] **Step 3: Implementează funcțiile utilitare**

```python
# shared/f3_price_extractor.py
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
```

- [ ] **Step 4: Rulează testele să treacă**

```bash
pytest tests/shared/test_f3_price_extractor.py -v
```
Expected: toate testele PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/f3_price_extractor.py tests/shared/test_f3_price_extractor.py
git commit -m "feat(sursa): f3_price_extractor — utility functions + tests"
```

---

## Task 2: f3_price_extractor — State Machine + Assembler + Public API

**Files:**
- Modify: `shared/f3_price_extractor.py` (adaugă `_parse_f3_page_lines`, `_assemble_deviz`, `extract_prices`)
- Modify: `tests/shared/test_f3_price_extractor.py`

- [ ] **Step 1: Scrie testele pentru state machine**

```python
# Adaugă în tests/shared/test_f3_price_extractor.py
from shared.f3_price_extractor import _parse_f3_page_lines, _assemble_deviz

_SAMPLE_LINES = [
    'Antet stanga', 'eDevize', 'SECTIUNEA TEHNICA', 'Nr.', 'Capitol de lucrari',
    'U.M.', 'Cantitatea', 'Pretul unitar', '(fara TVA)', '- Lei -',
    'TOTALUL', '(fara TVA)', '- Lei -', '0', '1', '2', '3', '4', '5 = 3 x 4',
    'INFRASTRUCTURA',
    '1',
    'CF38A* - Tencuiala pe baza de ciment',
    'mp',
    '225.000',
    '33.22',
    '7,473.71',
    'material:',
    '13.22',
    '2,973.71',
    'manopera:',
    '20.00',
    '4,500.00',
    'utilaj:',
    '0.00',
    '0.00',
    'transport:',
    '0.00',
    '0.00',
    '1.1',
    '2101121 - Mortar de zidarie M 10 nisip S1030',
    'mc',
    '1.939',
    '385.00',
    '746.62',
    'TOTAL INFRASTRUCTURA',
    '24,220.05',
    'Deviz "3.1" - Formular F3',
    'Pagina 1 din 14',
]

_MULTILINE_LINES = [
    '5 = 3 x 4',
    '5',
    'RPCE31B+ - Hidroizolatie membrana bituminoasa cu',
    'armatura din poliester netesut - la contactul zidariei cu',
    'placa de la cota +/- 0,00',
    'MP',
    '34.000',
    '63.16',
    '2,147.57',
    'material:',
    '50.94',
    '1,731.82',
    'manopera:',
    '12.22',
    '415.61',
    'utilaj:',
    '0.00',
    '0.00',
    'transport:',
    '0.00',
    '0.00',
]


def test_parse_f3_page_lines_basic():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    types = [e[0] for e in events]
    assert 'CAPITOL' in types
    assert 'ART_NR' in types
    assert 'COD_NAME' in types
    assert 'UM' in types
    assert 'BREAKDOWN' in types
    assert 'SUB_NR' in types
    assert 'TOTAL_CAPITOL' in types


def test_parse_f3_ignores_header_zone():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    # Antet stanga, eDevize etc. must not appear as events
    texts = [e[1].get('text', '') for e in events if e[0] == 'TEXT']
    assert 'Antet stanga' not in texts
    assert 'eDevize' not in texts


def test_parse_f3_breakdown_event():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    breakdowns = [e[1] for e in events if e[0] == 'BREAKDOWN']
    assert len(breakdowns) == 4  # material, manopera, utilaj, transport
    material = next(b for b in breakdowns if b['key'] == 'material')
    assert material['pret'] == pytest.approx(13.22)
    assert material['total'] == pytest.approx(2973.71)


def test_parse_f3_total_capitol_event():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    totals = [e[1] for e in events if e[0] == 'TOTAL_CAPITOL']
    assert len(totals) == 1
    assert totals[0]['titlu'] == 'INFRASTRUCTURA'
    assert totals[0]['total'] == pytest.approx(24220.05)


def test_parse_f3_multiline_denumire():
    events = _parse_f3_page_lines(_MULTILINE_LINES)
    cod_events = [e[1] for e in events if e[0] == 'COD_NAME']
    assert len(cod_events) == 1
    # denumire should include continuation
    assert 'armatura din poliester' in cod_events[0]['denumire']


def test_assemble_deviz_article_count():
    class MockHeader:
        obiectivul = "CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE"
        obiectul = "3 ARHITECTURA"
        categoria = "3.1 ARHITECTURA"
        deviz_key = "abc123"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    assert deviz['obiectivul'] == MockHeader.obiectivul
    assert len(deviz['capitole']) == 1
    capitol = deviz['capitole'][0]
    assert capitol['titlu'] == 'INFRASTRUCTURA'
    assert capitol['total_capitol'] == pytest.approx(24220.05)
    assert len(capitol['articole']) == 1
    art = capitol['articole'][0]
    assert art['nr_crt'] == '1'
    assert art['cod'] == 'CF38A*'
    assert art['cantitate'] == pytest.approx(225.0)
    assert art['pret_unitar'] == pytest.approx(33.22)
    assert art['total'] == pytest.approx(7473.71)


def test_assemble_deviz_breakdown():
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert art['breakdown'] is not None
    assert art['breakdown']['material']['pret'] == pytest.approx(13.22)
    assert art['breakdown']['control_ok'] is True


def test_assemble_deviz_sub_item():
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert len(art['sub_items']) == 1
    sub = art['sub_items'][0]
    assert sub['nr_crt'] == '1.1'
    assert sub['total'] == pytest.approx(746.62)
```

- [ ] **Step 2: Rulează testele să eșueze**

```bash
pytest tests/shared/test_f3_price_extractor.py -v -k "parse_f3 or assemble"
```
Expected: `ImportError: cannot import name '_parse_f3_page_lines'`

- [ ] **Step 3: Implementează `_parse_f3_page_lines`**

Adaugă în `shared/f3_price_extractor.py`:

```python
def _parse_f3_page_lines(lines: list[str]) -> list[tuple[str, dict]]:
    """Convert raw page lines to typed events. Skips page header zone.

    Events: CAPITOL, TOTAL_CAPITOL, ART_NR, SUB_NR, COD_NAME, UM, NUMBER,
            BREAKDOWN, TEXT
    """
    events: list[tuple[str, dict]] = []
    in_article_zone = False
    i = 0

    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        i += 1

        # Enter article zone after column header sentinel
        if line == '5 = 3 x 4':
            in_article_zone = True
            continue

        if not in_article_zone:
            continue

        # Page footer — stop
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
                    continue

        # CAPITOL HEADER
        if _is_capitol_header(line):
            events.append(('CAPITOL', {'titlu': line}))
            continue

        # SUB-ITEM NR (decimal like "3.1")
        if _NR_DEC_RE.match(line):
            events.append(('SUB_NR', {'nr_crt': line}))
            continue

        # ARTICLE NR (integer)
        if _NR_INT_RE.match(line):
            events.append(('ART_NR', {'nr_crt': line}))
            continue

        # BREAKDOWN KEY — consume next 2 lines as (pret, total)
        if _is_breakdown_key(line):
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

        # COD + DENUMIRE (possibly continued on next lines before UM)
        if _is_cod_name(line):
            # Gather continuation lines (not UM, not number, not cod-name, not breakdown)
            denumire_parts = [line]
            while i < len(lines):
                nxt = lines[i].strip()
                if (_is_um(nxt) or _NR_INT_RE.match(nxt) or _NR_DEC_RE.match(nxt)
                        or _is_cod_name(nxt) or _is_breakdown_key(nxt)
                        or _is_capitol_header(nxt) or _is_skip(nxt)
                        or _TOTAL_CAPITOL_RE.match(nxt)):
                    break
                if _parse_number(nxt) is not None:
                    break
                denumire_parts.append(nxt)
                i += 1
            full_line = denumire_parts[0]
            # Split COD from DENUMIRE
            dash_idx = full_line.index(' - ')
            cod = full_line[:dash_idx].strip()
            den_first = full_line[dash_idx + 3:].strip()
            denumire = ' '.join([den_first] + denumire_parts[1:]).strip()
            events.append(('COD_NAME', {'cod': cod, 'denumire': denumire}))
            continue

        # UM
        if _is_um(line):
            events.append(('UM', {'um': line.upper()}))
            continue

        # NUMBER (role determined by assembler based on position)
        num = _parse_number(line)
        if num is not None:
            events.append(('NUMBER', {'value': num, 'raw': line}))
            continue

        # Unknown text (continuation or noise)
        events.append(('TEXT', {'text': line}))

    return events
```

- [ ] **Step 4: Implementează `_assemble_deviz`**

```python
def _assemble_deviz(events: list[tuple[str, dict]], header) -> dict:
    """Assemble events from one deviz into structured dict."""
    capitole = []
    current_capitol = None
    current_article = None
    num_queue: list[float] = []  # pending numbers: [cant, pret, total]
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
        num_queue = []
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
                capitole.append(current_capitol)
                current_capitol = None

        elif etype == 'ART_NR':
            _flush_to_capitol()
            current_article = {
                'nr_crt': data['nr_crt'],
                'cod': '', 'denumire': '',
                'um': '', 'cantitate': 0.0,
                'pret_unitar': 0.0, 'total': 0.0,
                'breakdown': None, 'sub_items': [],
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
            num_queue = []  # reset number queue after UM

        elif etype == 'NUMBER':
            num_queue.append(data['value'])

        elif etype == 'BREAKDOWN':
            if current_article is not None:
                if current_article['breakdown'] is None:
                    current_article['breakdown'] = {
                        'material': {'pret': 0.0, 'total': 0.0},
                        'manopera': {'pret': 0.0, 'total': 0.0},
                        'utilaj': {'pret': 0.0, 'total': 0.0},
                        'transport': {'pret': 0.0, 'total': 0.0},
                        'control_ok': False,
                    }
                current_article['breakdown'][data['key']] = {
                    'pret': data['pret'],
                    'total': data['total'],
                }

    _flush_to_capitol()
    if current_capitol is not None:
        capitole.append(current_capitol)

    # Validate breakdown control_ok
    for cap in capitole:
        for art in cap['articole']:
            if art['breakdown'] and art['pret_unitar'] > 0:
                bd = art['breakdown']
                computed = sum(
                    bd[k]['pret'] for k in ('material', 'manopera', 'utilaj', 'transport')
                )
                art['breakdown']['control_ok'] = abs(computed - art['pret_unitar']) < 0.02

    return {
        'deviz_key': header.deviz_key,
        'obiectivul': header.obiectivul or '',
        'obiectul': header.obiectul or '',
        'categoria': header.categoria or '',
        'capitole': capitole,
        'total_deviz': sum(
            cap['total_capitol'] or 0.0 for cap in capitole
        ),
    }
```

- [ ] **Step 5: Implementează `extract_prices` (public API + checkpoint)**

```python
def extract_prices(
    page_classes: list[dict],
    deviz_headers: dict,
    checkpoint_path: Path | None = None,
    force: bool = False,
) -> list[dict]:
    """Extract articles+prices from classified F3 pages.

    Args:
        page_classes: output from f3_page_classifier.classify_pages()
        deviz_headers: dict[deviz_key, DevizHeader] from extract_deviz_headers()
        checkpoint_path: optional path to save/load extracted data
        force: if True, ignore existing checkpoint

    Returns: list of deviz dicts
    """
    if checkpoint_path and checkpoint_path.exists() and not force:
        return json.loads(checkpoint_path.read_text(encoding='utf-8'))

    # Group F3 pages by deviz_cod
    from collections import defaultdict
    pages_by_cod: dict[str, list[list[str]]] = defaultdict(list)
    for pc in page_classes:
        if pc.get('is_f3') and not pc.get('header_only'):
            cod = pc.get('deviz_cod', '')
            if cod:
                pages_by_cod[cod].append(pc.get('lines', []))

    # Map deviz_cod → DevizHeader
    cod_to_header: dict[str, object] = {}
    for header in deviz_headers.values():
        cod = (getattr(header, 'deviz_cod', '') or '').strip()
        if cod and cod not in cod_to_header:
            cod_to_header[cod] = header

    result = []
    for cod, page_lines_list in pages_by_cod.items():
        header = cod_to_header.get(cod)
        if header is None:
            # Fallback: use first available header
            header = next(iter(deviz_headers.values()), None)
        if header is None:
            continue

        # Merge all lines from all pages of this deviz
        all_lines: list[str] = []
        for page_lines in page_lines_list:
            all_lines.extend(page_lines)

        events = _parse_f3_page_lines(all_lines)
        deviz = _assemble_deviz(events, header)
        result.append(deviz)

    if checkpoint_path:
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding='utf-8',
        )

    return result
```

- [ ] **Step 6: Rulează toate testele extractor să treacă**

```bash
pytest tests/shared/test_f3_price_extractor.py -v
```
Expected: toate PASS.

- [ ] **Step 7: Commit**

```bash
git add shared/f3_price_extractor.py tests/shared/test_f3_price_extractor.py
git commit -m "feat(sursa): f3_price_extractor — state machine + assembler + public API"
```

---

## Task 3: lista_verifier

**Files:**
- Create: `shared/lista_verifier.py`
- Create: `tests/shared/test_lista_verifier.py`

- [ ] **Step 1: Scrie testele**

```python
# tests/shared/test_lista_verifier.py
import pytest
from shared.lista_verifier import verify, _check_nr_crt_gaps, _check_total_deviz

def _make_deviz(articole_per_capitol, total_deviz=None, capitole_totals=None):
    """Helper: build a minimal deviz dict."""
    capitole = []
    for idx, (nr_list, cap_total) in enumerate(
        zip(articole_per_capitol,
            capitole_totals or [None] * len(articole_per_capitol))
    ):
        arts = [
            {'nr_crt': str(nr), 'pret_unitar': 10.0, 'total': 10.0,
             'breakdown': None, 'sub_items': []}
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
    deviz = _make_deviz([[1, 2, 3]])  # 3 articles × 10.0 = 30.0
    result = _check_total_deviz([deviz])
    assert result['ok'] is True


def test_check_total_deviz_mismatch():
    deviz = _make_deviz([[1, 2, 3]], total_deviz=999.0)
    result = _check_total_deviz([deviz])
    assert result['ok'] is False
    assert result['diff'] == pytest.approx(999.0 - 30.0, abs=0.1)


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
    result = verify([deviz])
    assert result['status'] == 'WARN'
    assert result['checks']['BREAKDOWN_CONTROL']['ok'] is False
```

- [ ] **Step 2: Rulează testele să eșueze**

```bash
pytest tests/shared/test_lista_verifier.py -v
```

- [ ] **Step 3: Implementează `lista_verifier.py`**

```python
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
                bd = art.get('breakdown')
                if bd and not bd.get('control_ok', True):
                    suspect.append(art['nr_crt'])
    return {'ok': len(suspect) == 0, 'suspect_articles': suspect}


def verify(
    extracted: list[dict],
    deviz_headers: dict = None,
    max_iterations: int = 5,
    reextract_fn: Optional[Callable] = None,
) -> dict:
    """Run all checks, retry up to max_iterations if HIGH checks fail.

    Returns verification result dict with status (OK/WARN/RED), iterations, checks.
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
            k for k, v in checks.items()
            if k != 'BREAKDOWN_CONTROL' and k != 'COUNT_DEVIZE' and not v['ok']
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
```

- [ ] **Step 4: Rulează testele să treacă**

```bash
pytest tests/shared/test_lista_verifier.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/lista_verifier.py tests/shared/test_lista_verifier.py
git commit -m "feat(sursa): lista_verifier — 5 checks + retry loop"
```

---

## Task 4: sursa_incarcare_writer — Acronym + DOCX

**Files:**
- Create: `shared/sursa_incarcare_writer.py`
- Create: `tests/shared/test_sursa_incarcare_writer.py`

- [ ] **Step 1: Scrie testele pentru `make_acronym` și structura DOCX**

```python
# tests/shared/test_sursa_incarcare_writer.py
import pytest
from pathlib import Path
from docx import Document
from shared.sursa_incarcare_writer import make_acronym, write_docx, write_xlsx

def test_make_acronym_standard():
    assert make_acronym("CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE") == "CUCT"

def test_make_acronym_with_numeric_prefix():
    assert make_acronym("0232 000000232 DRUMURI TATARANI") == "DT"

def test_make_acronym_short():
    assert make_acronym("DRUMURI TATARANI") == "DT"

def test_make_acronym_max_6():
    result = make_acronym("CONSTRUIRE REABILITARE MODERNIZARE EXTINDERE CONSOLIDARE RENOVARE")
    assert len(result) <= 6


def _make_sample_deviz(status="OK"):
    return {
        'status': status,
        'deviz_key': 'test',
        'obiectivul': 'CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE',
        'obiectul': '3 ARHITECTURA',
        'categoria': '3.1 ARHITECTURA',
        'total_deviz': 24220.05,
        'capitole': [
            {
                'titlu': 'INFRASTRUCTURA',
                'total_capitol': 24220.05,
                'articole': [
                    {
                        'nr_crt': '1',
                        'cod': 'CF38A*',
                        'denumire': 'Tencuiala pe baza de ciment',
                        'um': 'MP',
                        'cantitate': 225.0,
                        'pret_unitar': 33.22,
                        'total': 7473.71,
                        'breakdown': {
                            'material': {'pret': 13.22, 'total': 2973.71},
                            'manopera': {'pret': 20.00, 'total': 4500.00},
                            'utilaj': {'pret': 0.00, 'total': 0.00},
                            'transport': {'pret': 0.00, 'total': 0.00},
                            'control_ok': True,
                        },
                        'sub_items': [],
                    },
                    {
                        'nr_crt': '2',
                        'cod': 'RPCE27A+',
                        'denumire': 'Mastic bituminos',
                        'um': 'MP',
                        'cantitate': 307.0,
                        'pret_unitar': 54.55,
                        'total': 16746.33,
                        'breakdown': None,
                        'sub_items': [],
                    },
                ],
            }
        ],
    }


def test_write_docx_creates_file(tmp_path):
    deviz = _make_sample_deviz()
    out = tmp_path / "test.docx"
    write_docx([deviz], out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_write_docx_has_rows(tmp_path):
    deviz = _make_sample_deviz()
    out = tmp_path / "test.docx"
    write_docx([deviz], out)
    doc = Document(str(out))
    # At least one table
    assert len(doc.tables) >= 1
    # Table should have: header(2) + capitol(1) + art1(1) + breakdown(4) + art2(1) + total_cap(1)
    tbl = doc.tables[0]
    assert len(tbl.rows) >= 8


def test_write_docx_no_breakdown_rows_when_none(tmp_path):
    deviz = _make_sample_deviz()
    # Remove breakdown from first article too
    deviz['capitole'][0]['articole'][0]['breakdown'] = None
    out = tmp_path / "test.docx"
    write_docx([deviz], out)
    doc = Document(str(out))
    tbl = doc.tables[0]
    # Without breakdown: header(2) + capitol(1) + art1(1) + art2(1) + total_cap(1) = 6
    assert len(tbl.rows) == 6


def test_write_docx_red_flag_when_red(tmp_path):
    deviz = _make_sample_deviz(status="RED")
    out = tmp_path / "test.docx"
    write_docx([deviz], out)
    doc = Document(str(out))
    # Find RED_FLAG text somewhere in document
    all_text = ' '.join(
        cell.text for tbl in doc.tables for row in tbl.rows for cell in row.cells
    )
    assert 'NECONFIRMAT' in all_text
```

- [ ] **Step 2: Rulează testele să eșueze**

```bash
pytest tests/shared/test_sursa_incarcare_writer.py -v
```

- [ ] **Step 3: Implementează `make_acronym` și `write_docx`**

```python
# shared/sursa_incarcare_writer.py
"""Generate F3 landscape DOCX, XLS and PDF from verified extracted data."""

import re
import subprocess
from pathlib import Path
from typing import Optional

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

# Column widths in cm: Nr | Denumire | UM | Cant | Pret | Total
_COL_W = [1.2, 9.0, 1.5, 2.5, 2.8, 3.0]

_STOPWORDS = {'DE', 'LA', 'PE', 'SI', 'IN', 'CU', 'DIN', 'A', 'AL', 'SA', 'O', 'UN'}

_GRAY_HEX = 'EEEEEE'
_YELLOW_HEX = 'FFF2CC'
_RED_HEX = 'FF0000'
_HEADER_GRAY = 'D9D9D9'


def make_acronym(obiectivul: str) -> str:
    """Generate max-6-char acronym from OBIECTIVUL.

    '0232 000000232 DRUMURI TATARANI' → 'DT'
    'CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE' → 'CUCT'
    """
    # Strip leading numeric codes
    text = re.sub(r'^\d[\d\s]+', '', obiectivul).strip()
    # Keep only letters and spaces
    text = re.sub(r'[^A-ZĂÂÎȘȚ ]', '', text.upper())
    words = text.split()
    letters = [w[0] for w in words if w and w not in _STOPWORDS and len(w) >= 2]
    return ''.join(letters[:6])


def _set_landscape(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)


def _set_tbl_grid(tbl) -> None:
    tblGrid = OxmlElement('w:tblGrid')
    for w_cm in _COL_W:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(int(round(w_cm * 567))))
        tblGrid.append(gc)
    tbl_el = tbl._tbl
    tbl_pr = tbl_el.find(qn('w:tblPr'))
    if tbl_pr is not None:
        tbl_pr.addnext(tblGrid)
    else:
        tbl_el.insert(0, tblGrid)


def _set_cell_margins(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    tblCellMar = OxmlElement('w:tblCellMar')
    for side, twips in [('top', 28), ('left', 57), ('bottom', 28), ('right', 57)]:
        elem = OxmlElement(f'w:{side}')
        elem.set(qn('w:w'), str(twips))
        elem.set(qn('w:type'), 'dxa')
        tblCellMar.append(elem)
    tblPr.append(tblCellMar)


def _repeat_header_rows(tbl, n_rows: int = 2) -> None:
    for row in tbl.rows[:n_rows]:
        tr = row._tr
        trPr = tr.find(qn('w:trPr'))
        if trPr is None:
            trPr = OxmlElement('w:trPr')
            tr.insert(0, trPr)
        trPr.append(OxmlElement('w:tblHeader'))


def _shade_cell(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _fmt_num(value: float, decimals: int = 2) -> str:
    if value == 0.0:
        return '0.00'
    s = f'{value:,.{decimals}f}'  # uses comma as thousands sep
    return s


def _cell_write(cell, text: str, bold: bool = False, size: int = 8,
                center: bool = False, color: str | None = None) -> None:
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT
    # No wrap for number columns
    tcPr = cell._tc.get_or_add_tcPr()
    noWrap = OxmlElement('w:noWrap')
    tcPr.append(noWrap)


def _add_header_rows(tbl, obiectivul: str, obiectul: str, categoria: str) -> None:
    """Row 0: deviz identity merged across 6 cols. Row 1: column headers."""
    row0 = tbl.rows[0]
    for i in range(1, 6):
        row0.cells[0].merge(row0.cells[i])
    header_text = f"{obiectivul} / {obiectul} / {categoria}"
    _cell_write(row0.cells[0], header_text, bold=True, size=9)

    row1 = tbl.rows[1]
    headers = ['Nr.', 'Capitol de lucrări', 'U.M.', 'Cantitatea',
               'Preț unitar (fără TVA) — Lei', 'TOTALUL (fără TVA) — Lei']
    for i, h in enumerate(headers):
        _shade_cell(row1.cells[i], _HEADER_GRAY)
        _cell_write(row1.cells[i], h, bold=True, size=7.5, center=True)


def _add_capitol_row(tbl, titlu: str) -> None:
    row = tbl.add_row()
    # Merge cols 1-5
    for i in range(2, 6):
        row.cells[1].merge(row.cells[i])
    _shade_cell(row.cells[0], _GRAY_HEX)
    _shade_cell(row.cells[1], _GRAY_HEX)
    _cell_write(row.cells[0], '', bold=True, size=8)
    _cell_write(row.cells[1], titlu, bold=True, size=8.5)


def _add_article_row(tbl, art: dict) -> None:
    row = tbl.add_row()
    cod_den = f"{art['cod']} - {art['denumire']}" if art['cod'] else art['denumire']
    vals = [
        art['nr_crt'], cod_den, art.get('um', ''),
        _fmt_num(art.get('cantitate', 0), 3),
        _fmt_num(art.get('pret_unitar', 0)),
        _fmt_num(art.get('total', 0)),
    ]
    for i, v in enumerate(vals):
        _cell_write(row.cells[i], v, size=8, center=(i in {0, 2, 3, 4, 5}))


def _add_breakdown_rows(tbl, breakdown: dict) -> None:
    for key in ('material', 'manopera', 'utilaj', 'transport'):
        bd = breakdown.get(key, {})
        row = tbl.add_row()
        _cell_write(row.cells[0], '', size=7)
        # Col 1: indented key label
        cell1 = row.cells[1]
        cell1.text = ''
        p = cell1.paragraphs[0]
        p.paragraph_format.left_indent = Cm(0.5)
        run = p.add_run(f"{key}:")
        run.font.size = Pt(7)
        run.font.italic = True
        _cell_write(row.cells[2], '', size=7)
        _cell_write(row.cells[3], '', size=7)
        _cell_write(row.cells[4], _fmt_num(bd.get('pret', 0)), size=7, center=True)
        _cell_write(row.cells[5], _fmt_num(bd.get('total', 0)), size=7, center=True)


def _add_sub_item_row(tbl, sub: dict) -> None:
    row = tbl.add_row()
    cod_den = f"{sub['cod']} - {sub['denumire']}" if sub['cod'] else sub['denumire']
    vals = [
        sub['nr_crt'], cod_den, sub.get('um', ''),
        _fmt_num(sub.get('cantitate', 0), 3),
        _fmt_num(sub.get('pret_unitar', 0)),
        _fmt_num(sub.get('total', 0)),
    ]
    for i, v in enumerate(vals):
        _cell_write(row.cells[i], v, size=7.5, center=(i in {0, 2, 3, 4, 5}))


def _add_total_capitol_row(tbl, titlu: str, total: float) -> None:
    row = tbl.add_row()
    for i in range(5):
        row.cells[0].merge(row.cells[1]) if i == 0 else None
    # Merge cols 0-4
    for i in range(1, 5):
        row.cells[0].merge(row.cells[i])
    _cell_write(row.cells[0], f'TOTAL {titlu}', bold=True, size=8)
    _cell_write(row.cells[5], _fmt_num(total), bold=True, size=8, center=True)


def _add_total_deviz_row(tbl, total: float, is_red: bool = False) -> None:
    row = tbl.add_row()
    for i in range(1, 5):
        row.cells[0].merge(row.cells[i])
    if is_red:
        for cell in row.cells:
            _shade_cell(cell, _RED_HEX)
        _cell_write(row.cells[0],
                    'TOTAL NECONFIRMAT — verificare manuală necesară',
                    bold=True, size=8, color='FFFFFF')
        _cell_write(row.cells[5], _fmt_num(total), bold=True, size=8,
                    center=True, color='FFFFFF')
    else:
        for cell in row.cells:
            _shade_cell(cell, _YELLOW_HEX)
        _cell_write(row.cells[0], 'TOTAL 1 (Cheltuieli directe)', bold=True, size=9)
        _cell_write(row.cells[5], _fmt_num(total), bold=True, size=9, center=True)


def _build_table(doc: Document, deviz: dict) -> None:
    tbl = doc.add_table(rows=2, cols=6)
    tbl.style = 'Table Grid'
    _set_tbl_grid(tbl)
    _set_cell_margins(tbl)
    _repeat_header_rows(tbl, n_rows=2)
    _add_header_rows(tbl,
                     deviz.get('obiectivul', ''),
                     deviz.get('obiectul', ''),
                     deviz.get('categoria', ''))

    for cap in deviz.get('capitole', []):
        _add_capitol_row(tbl, cap['titlu'])
        for art in cap.get('articole', []):
            _add_article_row(tbl, art)
            if art.get('breakdown'):
                _add_breakdown_rows(tbl, art['breakdown'])
            for sub in art.get('sub_items', []):
                _add_sub_item_row(tbl, sub)
        if cap.get('total_capitol') is not None:
            _add_total_capitol_row(tbl, cap['titlu'], cap['total_capitol'])

    is_red = deviz.get('status') == 'RED'
    _add_total_deviz_row(tbl, deviz.get('total_deviz', 0.0), is_red)


def write_docx(devize: list[dict], output_path: Path) -> None:
    """Write F3 landscape DOCX with all devize."""
    doc = Document()
    _set_landscape(doc)
    for idx, deviz in enumerate(devize):
        if idx > 0:
            doc.add_page_break()
        _build_table(doc, deviz)
    doc.save(str(output_path))
```

- [ ] **Step 4: Rulează testele să treacă**

```bash
pytest tests/shared/test_sursa_incarcare_writer.py -v -k "acronym or docx"
```

- [ ] **Step 5: Commit**

```bash
git add shared/sursa_incarcare_writer.py tests/shared/test_sursa_incarcare_writer.py
git commit -m "feat(sursa): sursa_incarcare_writer — acronym + DOCX generator"
```

---

## Task 5: sursa_incarcare_writer — XLS + PDF

**Files:**
- Modify: `shared/sursa_incarcare_writer.py` (adaugă `write_xlsx`, `write_pdf`)
- Modify: `tests/shared/test_sursa_incarcare_writer.py`

- [ ] **Step 1: Scrie testele pentru XLS și PDF**

```python
# Adaugă în tests/shared/test_sursa_incarcare_writer.py
from shared.sursa_incarcare_writer import write_xlsx, write_pdf
from openpyxl import load_workbook
import shutil


def test_write_xlsx_creates_file(tmp_path):
    deviz = _make_sample_deviz()
    out = tmp_path / "test.xlsx"
    write_xlsx([deviz], out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_write_xlsx_sheet_name(tmp_path):
    deviz = _make_sample_deviz()
    out = tmp_path / "test.xlsx"
    write_xlsx([deviz], out)
    wb = load_workbook(str(out))
    assert '3.1 ARHITECTURA' in wb.sheetnames[0]


def test_write_xlsx_has_rows(tmp_path):
    deviz = _make_sample_deviz()
    out = tmp_path / "test.xlsx"
    write_xlsx([deviz], out)
    wb = load_workbook(str(out))
    ws = wb.active
    # Should have at least header row + capitol + 2 articles + breakdown + total
    assert ws.max_row >= 8


def test_write_pdf_skips_gracefully_if_no_libreoffice(tmp_path, monkeypatch):
    deviz = _make_sample_deviz()
    docx_path = tmp_path / "test.docx"
    write_docx([deviz], docx_path)

    # Monkeypatch subprocess to simulate LibreOffice missing
    import subprocess
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("soffice not found")
    monkeypatch.setattr(subprocess, "run", fake_run)

    result = write_pdf(docx_path, tmp_path)
    assert result is False  # returns False, no exception
```

- [ ] **Step 2: Rulează testele să eșueze**

```bash
pytest tests/shared/test_sursa_incarcare_writer.py -v -k "xlsx or pdf"
```

- [ ] **Step 3: Implementează `write_xlsx` și `write_pdf`**

Adaugă în `shared/sursa_incarcare_writer.py`:

```python
_XLS_GRAY = PatternFill('solid', fgColor='EEEEEE')
_XLS_YELLOW = PatternFill('solid', fgColor='FFF2CC')
_XLS_RED = PatternFill('solid', fgColor='FF0000')
_XLS_HEADER = PatternFill('solid', fgColor='D9D9D9')
_XLS_BOLD = Font(bold=True)
_XLS_BOLD_WHITE = Font(bold=True, color='FFFFFF')
_XLS_SMALL = Font(size=8, italic=True)
_XLS_CENTER = Alignment(horizontal='center', vertical='center')


def write_xlsx(devize: list[dict], output_path: Path) -> None:
    """Write F3 XLS with same structure as DOCX (one sheet per deviz)."""
    wb = Workbook()
    wb.remove(wb.active)

    col_widths = [8, 55, 8, 14, 16, 16]  # approximate character widths

    for deviz in devize:
        sheet_name = (deviz.get('categoria') or 'Deviz')[:31]
        ws = wb.create_sheet(title=sheet_name)

        for ci, w in enumerate(col_widths, 1):
            ws.column_dimensions[ws.cell(1, ci).column_letter].width = w

        r = 1
        # Deviz header row
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        cell = ws.cell(r, 1,
                       value=f"{deviz.get('obiectivul','')} / {deviz.get('obiectul','')} / {deviz.get('categoria','')}")
        cell.font = _XLS_BOLD
        r += 1

        # Column headers
        headers = ['Nr.', 'Capitol de lucrări', 'U.M.', 'Cantitatea',
                   'Preț unitar (fără TVA)', 'TOTALUL (fără TVA)']
        for ci, h in enumerate(headers, 1):
            c = ws.cell(r, ci, value=h)
            c.fill = _XLS_HEADER
            c.font = _XLS_BOLD
            c.alignment = _XLS_CENTER
        r += 1

        for cap in deviz.get('capitole', []):
            # Capitol row
            ws.cell(r, 1, value='').fill = _XLS_GRAY
            c = ws.cell(r, 2, value=cap['titlu'])
            c.font = _XLS_BOLD
            c.fill = _XLS_GRAY
            for ci in range(3, 7):
                ws.cell(r, ci).fill = _XLS_GRAY
            r += 1

            for art in cap.get('articole', []):
                cod_den = f"{art['cod']} - {art['denumire']}" if art['cod'] else art['denumire']
                ws.cell(r, 1, value=art['nr_crt']).alignment = _XLS_CENTER
                ws.cell(r, 2, value=cod_den)
                ws.cell(r, 3, value=art.get('um', '')).alignment = _XLS_CENTER
                ws.cell(r, 4, value=art.get('cantitate', 0)).alignment = _XLS_CENTER
                ws.cell(r, 5, value=art.get('pret_unitar', 0)).alignment = _XLS_CENTER
                ws.cell(r, 6, value=art.get('total', 0)).alignment = _XLS_CENTER
                r += 1

                if art.get('breakdown'):
                    for key in ('material', 'manopera', 'utilaj', 'transport'):
                        bd = art['breakdown'].get(key, {})
                        ws.cell(r, 2, value=f"  {key}:").font = _XLS_SMALL
                        ws.cell(r, 5, value=bd.get('pret', 0)).font = _XLS_SMALL
                        ws.cell(r, 6, value=bd.get('total', 0)).font = _XLS_SMALL
                        r += 1

                for sub in art.get('sub_items', []):
                    cod_den_s = f"{sub['cod']} - {sub['denumire']}" if sub['cod'] else sub['denumire']
                    ws.cell(r, 1, value=sub['nr_crt']).alignment = _XLS_CENTER
                    ws.cell(r, 2, value=cod_den_s).font = Font(size=8)
                    ws.cell(r, 3, value=sub.get('um', '')).alignment = _XLS_CENTER
                    ws.cell(r, 4, value=sub.get('cantitate', 0)).alignment = _XLS_CENTER
                    ws.cell(r, 5, value=sub.get('pret_unitar', 0)).alignment = _XLS_CENTER
                    ws.cell(r, 6, value=sub.get('total', 0)).alignment = _XLS_CENTER
                    r += 1

            # Total capitol row
            if cap.get('total_capitol') is not None:
                for ci in range(1, 6):
                    ws.cell(r, ci, value=f'TOTAL {cap["titlu"]}' if ci == 1 else '').font = _XLS_BOLD
                ws.cell(r, 6, value=cap['total_capitol']).font = _XLS_BOLD
                r += 1

        # Total deviz row
        is_red = deviz.get('status') == 'RED'
        total_label = 'TOTAL NECONFIRMAT — verificare manuală' if is_red else 'TOTAL 1 (Cheltuieli directe)'
        fill = _XLS_RED if is_red else _XLS_YELLOW
        font = _XLS_BOLD_WHITE if is_red else _XLS_BOLD
        for ci in range(1, 7):
            ws.cell(r, ci).fill = fill
        ws.cell(r, 1, value=total_label).font = font
        ws.cell(r, 6, value=deviz.get('total_deviz', 0)).font = font
        r += 1

    wb.save(str(output_path))


def write_pdf(docx_path: Path, output_dir: Path) -> bool:
    """Convert DOCX to PDF via LibreOffice CLI. Returns True on success."""
    import subprocess
    try:
        result = subprocess.run(
            ['soffice', '--headless', '--convert-to', 'pdf',
             '--outdir', str(output_dir), str(docx_path)],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
```

- [ ] **Step 4: Rulează toate testele writer să treacă**

```bash
pytest tests/shared/test_sursa_incarcare_writer.py -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/sursa_incarcare_writer.py tests/shared/test_sursa_incarcare_writer.py
git commit -m "feat(sursa): sursa_incarcare_writer — XLS + PDF output"
```

---

## Task 6: gen_sursa_incarcare.py — CLI + Integration

**Files:**
- Create: `gen_sursa_incarcare.py`

- [ ] **Step 1: Implementează CLI-ul**

```python
#!/usr/bin/env python3
"""Generate F3 Lista-proiect-XXX.docx/xlsx/pdf from a single di_*.json.

Usage:
    python3 gen_sursa_incarcare.py                                  # interactive
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --no-pdf
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --force
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from shared.client_config import ClientConfig
from shared.f3_price_extractor import extract_prices
from shared.lista_verifier import verify
from shared.sursa_incarcare_writer import make_acronym, write_docx, write_xlsx, write_pdf
from anthropic_adapter import AnthropicAdapter

INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")
MODEL = "claude-sonnet-4-6"


def _make_llm_client():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)
    return AnthropicAdapter(anthropic.Anthropic(api_key=api_key), model=MODEL), MODEL


def _pick_client(args_client: str | None) -> str:
    clients = ClientConfig.detect_clients(INPUT_BASE)
    if not clients:
        print("No clients found in input_AO/")
        sys.exit(1)
    if args_client:
        if args_client not in clients:
            print(f"Client '{args_client}' not found. Available: {clients}")
            sys.exit(1)
        return args_client
    print("\nClienți disponibili:")
    for i, c in enumerate(clients, 1):
        print(f"  {i}. {c}")
    choice = input("Client [număr]: ").strip()
    try:
        return clients[int(choice) - 1]
    except (ValueError, IndexError):
        print("Selecție invalidă.")
        sys.exit(1)


def _pick_json(client_name: str, args_json: str | None) -> Path:
    input_dir = INPUT_BASE / client_name
    json_files = sorted(input_dir.glob("di_*.json"))
    if not json_files:
        print(f"No di_*.json files found in {input_dir}")
        sys.exit(1)
    if args_json:
        name = args_json if args_json.endswith(".json") else args_json + ".json"
        path = input_dir / name
        if not path.exists():
            print(f"File {path} not found.")
            sys.exit(1)
        return path
    print(f"\nFișiere JSON disponibile în {input_dir}:")
    for i, f in enumerate(json_files, 1):
        print(f"  {i}. {f.name}")
    choice = input("JSON [număr]: ").strip()
    try:
        return json_files[int(choice) - 1]
    except (ValueError, IndexError):
        print("Selecție invalidă.")
        sys.exit(1)


def _run_pipeline(
    client_name: str,
    json_path: Path,
    no_pdf: bool = False,
    force: bool = False,
) -> None:
    from shared.f3_page_classifier import classify_pages, build_deviz_groups
    from shared.deviz_header_extractor import extract_deviz_headers
    from shared.group_extractor import extract_groups_as_headers

    config = ClientConfig.from_folder(client_name, INPUT_BASE, OUTPUT_BASE)
    config.ensure_output_dirs()

    json_stem = json_path.stem  # "di_referinta"
    print(f"\nProcesare {client_name} / {json_path.name}...")

    # Step 1: Page classification
    ckpt_pages = config.checkpoint_dir / f"{json_stem}_page_classes.json"
    di = json.loads(json_path.read_text(encoding="utf-8"))
    pages = di.get("pages", [])

    if ckpt_pages.exists() and not force:
        print(f"  [1/4] Clasificare pagini (cached)...", end="")
        ckpt = json.loads(ckpt_pages.read_text(encoding="utf-8"))
        page_classes = ckpt.get("page_classes", ckpt) if isinstance(ckpt, dict) else ckpt
    else:
        print(f"  [1/4] Clasificare pagini (LLM, poate dura 2-5 min)...", end="")
        llm_client, model = _make_llm_client()
        page_classes, ckpt_data = classify_pages(
            pages, llm_client, model, document_type="reference", source_path=str(json_path)
        )
        ckpt_pages.write_text(
            json.dumps({"page_classes": page_classes, "metadata": ckpt_data},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    f3_count = sum(1 for pc in page_classes if pc.get("is_f3"))
    print(f" ✓ {f3_count} pagini F3")

    # Step 2: Deviz headers
    print(f"  [2/4] Extragere devize...", end="")
    deviz_headers = extract_deviz_headers(page_classes)
    valid = sum(1 for h in deviz_headers.values() if h.is_valid)
    print(f" ✓ {valid} deviz(e)")

    # Step 3: Extract prices
    print(f"  [3/4] Extragere articole + prețuri...", end="")
    ckpt_extracted = config.output_dir / f"sursa_extracted_{json_stem}.json"
    extracted = extract_prices(
        page_classes, deviz_headers,
        checkpoint_path=ckpt_extracted,
        force=force,
    )
    total_arts = sum(
        len(cap['articole'])
        for deviz in extracted
        for cap in deviz.get('capitole', [])
    )
    bd_count = sum(
        1 for deviz in extracted
        for cap in deviz.get('capitole', [])
        for art in cap['articole']
        if art.get('breakdown')
    )
    print(f" ✓ {total_arts} articole, {bd_count} cu breakdown")

    # Step 4: Verify
    print(f"  [4/4] Verificare...", end="")
    verification = verify(extracted, deviz_headers)

    # Attach status to each deviz for writer
    # Single deviz case: all devize get the same status
    for deviz in extracted:
        deviz['status'] = verification['status']

    ckpt_verified = config.output_dir / f"sursa_verified_{json_stem}.json"
    ckpt_verified.write_text(
        json.dumps(verification, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    status_symbol = "✓" if verification['status'] == "OK" else ("⚠" if verification['status'] == "WARN" else "✗")
    print(f" {status_symbol} {verification['status']} (iterații: {verification['iterations']})")

    # Generate output files
    obiectivul = extracted[0].get('obiectivul', '') if extracted else ''
    acronym = make_acronym(obiectivul) if obiectivul else 'PRJ'
    base_name = f"Lista-proiect-{acronym}-{json_stem}"

    docx_path = config.output_dir / f"{base_name}.docx"
    xlsx_path = config.output_dir / f"{base_name}.xlsx"
    pdf_path = config.output_dir / f"{base_name}.pdf"

    write_docx(extracted, docx_path)
    print(f"\nOutput generat:")
    print(f"  {docx_path}  ✓")

    write_xlsx(extracted, xlsx_path)
    print(f"  {xlsx_path}  ✓")

    if not no_pdf:
        ok = write_pdf(docx_path, config.output_dir)
        print(f"  {pdf_path}  {'✓' if ok else '⚠ (LibreOffice indisponibil — PDF omis)'}")
    else:
        print(f"  PDF omis (--no-pdf)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generează Lista-proiect din di_*.json")
    parser.add_argument("--client", help="Numele clientului")
    parser.add_argument("--json", help="Numele fișierului JSON (fără .json)")
    parser.add_argument("--no-pdf", action="store_true", help="Skip generare PDF")
    parser.add_argument("--force", action="store_true", help="Ignoră checkpoint")
    args = parser.parse_args()

    client_name = _pick_client(args.client)
    json_path = _pick_json(client_name, getattr(args, "json"))
    _run_pipeline(client_name, json_path, no_pdf=args.no_pdf, force=args.force)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Rulează smoke test pe EuroProject**

```bash
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --no-pdf
```

Expected output:
```
Procesare EuroProject / di_referinta.json...
  [1/4] Clasificare pagini (LLM sau cached)... ✓ 13 pagini F3
  [2/4] Extragere devize... ✓ 1 deviz(e)
  [3/4] Extragere articole + prețuri... ✓ ~90 articole, ~38 cu breakdown
  [4/4] Verificare... ✓ OK (iterații: 1)

Output generat:
  output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.docx  ✓
  output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.xlsx  ✓
  PDF omis (--no-pdf)
```

- [ ] **Step 3: Verifică fișierele generate vizual**

Deschide `output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.docx` și verifică:
- Header deviz: `CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE / 3 ARHITECTURA / 3.1 ARHITECTURA`
- Capitol separator: `INFRASTRUCTURA` (gri)
- Articol 1: `CF38A* - Tencuiala pe baza de ciment | mp | 225.000 | 33.22 | 7,473.71`
- Rânduri breakdown (material/manopera/utilaj/transport) cu font mai mic
- `TOTAL INFRASTRUCTURA` bold la finalul capitolului
- `TOTAL 1 (Cheltuieli directe)` galben la finalul tabelului

- [ ] **Step 4: Rulează toate testele suite**

```bash
pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py
```

Expected: nu mai puțin de 214 PASS (baseline). Orice scădere = BLOCKER.

- [ ] **Step 5: Commit final**

```bash
git add gen_sursa_incarcare.py
git commit -m "feat(sursa): gen_sursa_incarcare CLI — full pipeline orchestration"
```

---

## Self-Review Checklist

✅ **Spec coverage:**
- f3_price_extractor: `_parse_f3_page_lines` + `_assemble_deviz` + `extract_prices` → Task 1+2
- lista_verifier: 5 checks + retry loop → Task 3
- sursa_incarcare_writer: acronym + DOCX + XLS + PDF → Task 4+5
- CLI: interactive + `--client`/`--json`/`--no-pdf`/`--force` → Task 6
- Naming `Lista-proiect-{ACRONIM}-{json_stem}` → Task 5+6
- Checkpoint pentru extragere → Task 2
- RED flag în DOCX când status=RED → Task 4

✅ **Consistență tipuri:**
- `extract_prices()` returnează `list[dict]` — consumat de `verify()` și `write_docx/xlsx()`
- `verify()` returnează `dict` cu cheile `status`, `iterations`, `checks`
- `write_docx(devize: list[dict], output_path: Path)` — deviz dict are cheia `status` adăugată de CLI

✅ **Fișiere existente neatinse:** `f3_regex_parser.py`, `f3_page_classifier.py`, `deviz_header_extractor.py`, `local_run.py`, `AgentComparator_local.py`
