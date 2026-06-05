# gen_lista_oferta — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standalone script that generates F3-format DOCX files listing all articles (with code, parent code, name, UM, qty, price breakdown) from holistic JSON, for both referința and each offer.

**Architecture:** Two files — `shared/lista_oferta_writer.py` handles all DOCX logic (entity name extraction, group iteration, table building), `gen_lista_oferta.py` is a thin CLI wrapper. Source data: `holistic_oferta_N.json` in `output_AO/<client>/`.

**Tech Stack:** `python-docx`, `shared/client_config.py`, `argparse`

---

## Data model (read before implementing)

### Holistic JSON structure

`holistic_oferta_N.json` keys: `matched_groups`, `ref_only_groups`, `oferta_only_groups`

**matched_groups[*]:**
```python
{
  "ref_articles": [...],     # use for Lista Referinta
  "oferta_articles": [...],  # use for Lista Oferta N
  "ref_header": "DevizHeader(...)",   # string repr — DO NOT parse
  "oferta_header": "DevizHeader(...)", # string repr — DO NOT parse
  "deviz_denumire": "OBIECTIVUL | Obiectul | Categoria",
}
```

**ref_only_groups[*] / oferta_only_groups[*]:**
```python
{
  "articles": [...],          # the articles
  "deviz_denumire": "A | B | C",
}
```

**Article fields used:**
```python
{
  "cod": "TSD06XA",
  "denumire": "Compactare cu placa...",
  "um": "mc",
  "cantitate": 1.76,
  "nr_ordine": 1,           # int for principals; "9.1" string for subcomponents
  "is_component": False,
  "parent_code": None,       # filled for subcomponents
  "pret_material": 0.0,      # unit price — material
  "pret_manopera": 0.0,
  "pret_utilaj": 0.0,
  "pret_transport": 0.0,
  "val_material": 0.0,       # value = qty * unit price — material
  "val_manopera": 0.0,
  "val_utilaj": 0.0,
  "val_transport": 0.0,
  "deviz_header": {          # dict — use this for group header, NOT ref_header string
    "obiectivul": "...",
    "obiectul": "...",
    "categoria": "...",
  }
}
```

### Source selection logic

| Document | `matched_groups` articles key | `*_only_groups` |
|---|---|---|
| Lista Referinta | `ref_articles` | `ref_only_groups[*]["articles"]` |
| Lista Oferta N | `oferta_articles` | `oferta_only_groups[*]["articles"]` |

### Entity name extraction

In `di_oferta_N.json` / `di_referinta.json`, pages are `pages[i]["lines"]`, each line is `{"content": "..."}`.

- For offers: find line containing `"CONTRACTANT (OFERTANT)"`, return next non-empty line that is not `"SRL"` alone.
- For referinta: find line containing `"PROIECTANT"`, return next non-empty line.
- Search only first 5 pages. Fallback: `"Necunoscut"`.

---

## File map

| File | Action | Responsibility |
|---|---|---|
| `shared/lista_oferta_writer.py` | Create | All DOCX logic |
| `gen_lista_oferta.py` | Create | CLI entry point |
| `tests/shared/test_lista_oferta_writer.py` | Create | Unit tests |

---

## Task 1: `extract_entity_name()` + tests

**Files:**
- Create: `shared/lista_oferta_writer.py`
- Create: `tests/shared/test_lista_oferta_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/shared/test_lista_oferta_writer.py
import pytest
from shared.lista_oferta_writer import extract_entity_name
import json, tempfile, os

def _make_di(pages_lines):
    """Helper: write temp di_*.json and return path."""
    data = {"pages": [{"page_number": i+1, "lines": lines} for i, lines in enumerate(pages_lines)], "tables": []}
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name

def test_extract_ofertant_found():
    path = _make_di([[
        {"content": "Formularul F3"},
        {"content": "CONTRACTANT (OFERTANT)"},
        {"content": "SC. KATO SERVICE SRL"},
    ]])
    try:
        assert extract_entity_name(path, is_referinta=False) == "SC. KATO SERVICE SRL"
    finally:
        os.unlink(path)

def test_extract_ofertant_skips_bare_srl():
    path = _make_di([[
        {"content": "CONTRACTANT (OFERTANT)"},
        {"content": "SRL"},
        {"content": "SC. REAL COMPANY SRL"},
    ]])
    try:
        assert extract_entity_name(path, is_referinta=False) == "SC. REAL COMPANY SRL"
    finally:
        os.unlink(path)

def test_extract_proiectant_found():
    path = _make_di([[
        {"content": "PROIECTANT"},
        {"content": "SC. ARHI DESIGN SRL"},
    ]])
    try:
        assert extract_entity_name(path, is_referinta=True) == "SC. ARHI DESIGN SRL"
    finally:
        os.unlink(path)

def test_extract_fallback_when_not_found():
    path = _make_di([[{"content": "Random text"}]])
    try:
        assert extract_entity_name(path, is_referinta=False) == "Necunoscut"
    finally:
        os.unlink(path)

def test_extract_searches_only_first_5_pages():
    # Marker on page 6 — should not be found
    pages = [[{"content": "nothing"}]] * 5 + [[
        {"content": "CONTRACTANT (OFERTANT)"},
        {"content": "SC. LATE SRL"},
    ]]
    path = _make_di(pages)
    try:
        assert extract_entity_name(path, is_referinta=False) == "Necunoscut"
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Implement `extract_entity_name()`**

```python
# shared/lista_oferta_writer.py
"""F3-format DOCX list generator for referinta and offer articles."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def extract_entity_name(di_json_path: str, is_referinta: bool) -> str:
    """Extract proiectant/ofertant name from raw DI JSON (first 5 pages)."""
    marker = "PROIECTANT" if is_referinta else "CONTRACTANT (OFERTANT)"
    try:
        with open(di_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return "Necunoscut"

    pages = data.get("pages", [])
    for page in pages[:5]:
        lines = [ln.get("content", "").strip() for ln in page.get("lines", [])]
        for i, line in enumerate(lines):
            if marker in line:
                for candidate in lines[i + 1:]:
                    if candidate and candidate.upper() != "SRL":
                        return candidate
    return "Necunoscut"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v 2>&1 | head -20
```
Expected: 5 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): extract_entity_name — ofertant/proiectant from DI pages"
```

---

## Task 2: `_iter_source_groups()` — iterate groups from holistic

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

Yields `(header: dict, articles: list)` tuples. `header` has keys `obiectivul`, `obiectul`, `categoria`.

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from shared.lista_oferta_writer import _iter_source_groups

def _make_article(cod="TST01", nr_ordine=1, is_component=False, parent_code=None, deviz_header=None):
    return {
        "cod": cod, "denumire": "Test article", "um": "mc", "cantitate": 1.0,
        "nr_ordine": nr_ordine, "is_component": is_component, "parent_code": parent_code,
        "pret_material": 0.0, "pret_manopera": 0.0, "pret_utilaj": 0.0, "pret_transport": 0.0,
        "val_material": 0.0, "val_manopera": 0.0, "val_utilaj": 0.0, "val_transport": 0.0,
        "deviz_header": deviz_header or {"obiectivul": "OBJ", "obiectul": "OBL", "categoria": "CAT"},
    }

def test_iter_source_groups_oferta():
    art = _make_article("TST01")
    holistic = {
        "matched_groups": [{"oferta_articles": [art], "ref_articles": [], "deviz_denumire": "A|B|C"}],
        "oferta_only_groups": [],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 1
    header, articles = groups[0]
    assert header["obiectivul"] == "OBJ"
    assert articles[0]["cod"] == "TST01"

def test_iter_source_groups_referinta():
    art = _make_article("REF01", deviz_header={"obiectivul": "R", "obiectul": "RL", "categoria": "RC"})
    holistic = {
        "matched_groups": [{"ref_articles": [art], "oferta_articles": [], "deviz_denumire": "R|RL|RC"}],
        "ref_only_groups": [],
        "oferta_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="referinta"))
    assert len(groups) == 1
    header, articles = groups[0]
    assert header["obiectivul"] == "R"
    assert articles[0]["cod"] == "REF01"

def test_iter_source_groups_includes_only_groups():
    art = _make_article("ONLY01", deviz_header={"obiectivul": "X", "obiectul": "Y", "categoria": "Z"})
    holistic = {
        "matched_groups": [],
        "oferta_only_groups": [{"articles": [art], "deviz_denumire": "X|Y|Z"}],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 1
    _, articles = groups[0]
    assert articles[0]["cod"] == "ONLY01"

def test_iter_source_groups_skips_empty_article_groups():
    holistic = {
        "matched_groups": [{"oferta_articles": [], "ref_articles": [], "deviz_denumire": "A|B|C"}],
        "oferta_only_groups": [],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 0

def test_iter_source_groups_fallback_header_from_deviz_denumire():
    """When articles list is empty but group exists via only_groups with no deviz_header on art."""
    art = {"cod": "X", "denumire": "D", "um": "mc", "cantitate": 1.0,
           "nr_ordine": 1, "is_component": False, "parent_code": None,
           "pret_material": 0.0, "pret_manopera": 0.0, "pret_utilaj": 0.0, "pret_transport": 0.0,
           "val_material": 0.0, "val_manopera": 0.0, "val_utilaj": 0.0, "val_transport": 0.0,
           "deviz_header": {"obiectivul": "OBJ2", "obiectul": "OBL2", "categoria": "CAT2"}}
    holistic = {
        "matched_groups": [],
        "ref_only_groups": [{"articles": [art], "deviz_denumire": "OBJ2|OBL2|CAT2"}],
        "oferta_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="referinta"))
    assert len(groups) == 1
    header, _ = groups[0]
    assert header["obiectivul"] == "OBJ2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py::test_iter_source_groups_oferta -v
```
Expected: `ImportError: cannot import name '_iter_source_groups'`

- [ ] **Step 3: Implement `_iter_source_groups()`**

```python
# Add to shared/lista_oferta_writer.py

def _get_header_from_articles(articles: List[Dict]) -> Dict:
    """Extract group header from first article's deviz_header dict."""
    for art in articles:
        dh = art.get("deviz_header")
        if isinstance(dh, dict):
            return dh
    return {"obiectivul": "", "obiectul": "", "categoria": ""}


def _iter_source_groups(holistic: Dict, source: str):
    """Yield (header_dict, articles_list) for each non-empty group.

    source: "oferta" or "referinta"
    """
    art_key = "oferta_articles" if source == "oferta" else "ref_articles"
    only_key = "oferta_only_groups" if source == "oferta" else "ref_only_groups"

    for group in holistic.get("matched_groups", []):
        articles = group.get(art_key, [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles

    for group in holistic.get(only_key, []):
        articles = group.get("articles", [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v 2>&1 | tail -15
```
Expected: all 10 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): _iter_source_groups — yield (header, articles) from holistic"
```

---

## Task 3: `_fmt_nr_crt()` and `_fmt_price()` helpers

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from shared.lista_oferta_writer import _fmt_nr_crt, _fmt_price

def test_fmt_nr_crt_integer():
    assert _fmt_nr_crt(1) == "1"

def test_fmt_nr_crt_string_subcomp():
    assert _fmt_nr_crt("9.1") == "9.1"

def test_fmt_nr_crt_float_becomes_int():
    # nr_ordine sometimes stored as float 1.0
    assert _fmt_nr_crt(1.0) == "1"

def test_fmt_price_zero_returns_empty():
    assert _fmt_price(0.0) == ""

def test_fmt_price_nonzero_returns_formatted():
    assert _fmt_price(1234.5) == "1.234,50"

def test_fmt_price_rounds_to_2_decimals():
    assert _fmt_price(9.999) == "10,00"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "fmt" -v
```
Expected: `ImportError`

- [ ] **Step 3: Implement helpers**

```python
# Add to shared/lista_oferta_writer.py

def _fmt_nr_crt(nr_ordine) -> str:
    """Format nr_ordine for display. Integers show as '1', subcomponents as '9.1'."""
    if isinstance(nr_ordine, float) and nr_ordine == int(nr_ordine):
        return str(int(nr_ordine))
    return str(nr_ordine)


def _fmt_price(value: float) -> str:
    """Format price: 0.0 → empty string; else Romanian locale (1.234,50)."""
    if not value:
        return ""
    formatted = f"{value:,.2f}"          # "1,234.50"
    # Convert to Romanian locale: swap . and ,
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "fmt" -v
```
Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): _fmt_nr_crt and _fmt_price helpers"
```

---

## Task 4: `_build_table_header()` — 2-row merged F3 header

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

The table has **15 columns**:
```
[0] Nr.  [1] Nr.crt  [2] Cod  [3] Cod principal  [4] Denumire  [5] UM  [6] Cantitate
[7] Pret Material  [8] Pret Manoperă  [9] Pret Utilaje  [10] Pret Transport
[11] Val Material  [12] Val Manoperă  [13] Val Utilaje  [14] Val Transport
```

Row 0: cells 0-6 each span 2 rows. Cell 7 "Pret unitar (lei/UM)" spans cols 7-10 (1 row). Cell 11 "Valoare (lei)" spans cols 11-14 (1 row).
Row 1: cells 7-14 each get their label.

Column widths (cm): `[1.0, 1.2, 2.0, 2.2, 6.5, 1.2, 1.8, 2.0, 2.0, 1.8, 2.0, 2.0, 2.0, 1.8, 2.0]`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from docx import Document
from shared.lista_oferta_writer import _build_table_header

def test_build_table_header_structure():
    doc = Document()
    tbl = doc.add_table(rows=2, cols=15)
    _build_table_header(tbl)
    # Row 0 has content in first 7 cells + merged spans for Pret and Val
    assert tbl.rows[0].cells[0].text == "Nr."
    assert tbl.rows[0].cells[1].text == "Nr.crt"
    assert tbl.rows[0].cells[2].text == "Cod"
    assert tbl.rows[0].cells[3].text == "Cod principal"
    assert tbl.rows[0].cells[4].text == "Denumire"
    assert tbl.rows[0].cells[5].text == "UM"
    assert tbl.rows[0].cells[6].text == "Cantitate"
    # Row 1 price sub-headers
    assert tbl.rows[1].cells[7].text == "Material"
    assert tbl.rows[1].cells[8].text == "Manoperă"
    assert tbl.rows[1].cells[9].text == "Utilaje"
    assert tbl.rows[1].cells[10].text == "Transport"
    assert tbl.rows[1].cells[11].text == "Material"
    assert tbl.rows[1].cells[14].text == "Transport"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/shared/test_lista_oferta_writer.py::test_build_table_header_structure -v
```

- [ ] **Step 3: Implement `_build_table_header()`**

```python
# Add to shared/lista_oferta_writer.py
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.table import Table


HEADER_FILL = "D9D9D9"   # light grey for header rows
COL_WIDTHS_CM = [1.0, 1.2, 2.0, 2.2, 6.5, 1.2, 1.8, 2.0, 2.0, 1.8, 2.0, 2.0, 2.0, 1.8, 2.0]


def _shade_cell(cell, fill_hex: str) -> None:
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill_hex)
    cell._element.get_or_add_tcPr().append(shading)


def _cell_text(cell, text: str, bold: bool = False, center: bool = False, font_size: int = 8) -> None:
    cell.text = ""
    p = cell.paragraphs[0]
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(font_size)


def _merge_vertical(table: Table, col: int, row_start: int = 0, row_end: int = 1) -> None:
    """Merge cells in same column across rows."""
    table.cell(row_start, col).merge(table.cell(row_end, col))


def _build_table_header(table: Table) -> None:
    """Write 2-row F3 header into an existing 2-row, 15-col table."""
    # Set column widths
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            cell.width = Cm(COL_WIDTHS_CM[i])

    row0 = table.rows[0].cells
    row1 = table.rows[1].cells

    # First 7 columns: merge vertically (span 2 rows)
    labels_row0 = ["Nr.", "Nr.crt", "Cod", "Cod principal", "Denumire", "UM", "Cantitate"]
    for i, label in enumerate(labels_row0):
        _merge_vertical(table, i)
        _cell_text(row0[i], label, bold=True, center=True)
        _shade_cell(row0[i], HEADER_FILL)

    # "Pret unitar (lei/UM)" spans cols 7-10
    row0[7].merge(row0[10])
    _cell_text(row0[7], "Pret unitar (lei/UM)", bold=True, center=True)
    _shade_cell(row0[7], HEADER_FILL)

    # "Valoare (lei)" spans cols 11-14
    row0[11].merge(row0[14])
    _cell_text(row0[11], "Valoare (lei)", bold=True, center=True)
    _shade_cell(row0[11], HEADER_FILL)

    # Row 1: sub-labels for price cols
    price_labels = ["Material", "Manoperă", "Utilaje", "Transport",
                    "Material", "Manoperă", "Utilaje", "Transport"]
    for i, label in enumerate(price_labels):
        _cell_text(row1[7 + i], label, bold=True, center=True)
        _shade_cell(row1[7 + i], HEADER_FILL)
```

- [ ] **Step 4: Run test**

```bash
pytest tests/shared/test_lista_oferta_writer.py::test_build_table_header_structure -v
```
Expected: PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): _build_table_header — 2-row F3 merged header with price breakdown"
```

---

## Task 5: `_write_article_row()` — single article row

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

- [ ] **Step 1: Write failing tests**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from shared.lista_oferta_writer import _write_article_row

def _make_full_article(cod="TST01", nr_ordine=1, is_component=False, parent_code=None,
                       pret_material=0.0, val_material=0.0, pret_manopera=0.0, val_manopera=0.0,
                       pret_utilaj=0.0, val_utilaj=0.0, pret_transport=0.0, val_transport=0.0):
    return {
        "cod": cod, "denumire": "Test article", "um": "mc", "cantitate": 2.5,
        "nr_ordine": nr_ordine, "is_component": is_component, "parent_code": parent_code,
        "pret_material": pret_material, "val_material": val_material,
        "pret_manopera": pret_manopera, "val_manopera": val_manopera,
        "pret_utilaj": pret_utilaj, "val_utilaj": val_utilaj,
        "pret_transport": pret_transport, "val_transport": val_transport,
        "deviz_header": {"obiectivul": "", "obiectul": "", "categoria": ""},
    }

def test_write_article_row_principal():
    doc = Document()
    tbl = doc.add_table(rows=0, cols=15)
    row = tbl.add_row()
    art = _make_full_article(cod="TSD06XA", nr_ordine=3)
    _write_article_row(row, seq_nr=3, article=art)
    cells = row.cells
    assert cells[0].text == "3"       # Nr sequential
    assert cells[1].text == "3"       # Nr.crt
    assert cells[2].text == "TSD06XA" # Cod
    assert cells[3].text == ""         # Cod principal (empty for principal)
    assert cells[4].text == "Test article"
    assert cells[5].text == "mc"
    assert cells[6].text == "2.500"   # cantitate 3 decimals
    assert cells[7].text == ""         # pret_material = 0 → empty

def test_write_article_row_subcomponent():
    doc = Document()
    tbl = doc.add_table(rows=0, cols=15)
    row = tbl.add_row()
    art = _make_full_article(cod="IZF16A", nr_ordine="9.1", is_component=True, parent_code="TRA01A10P")
    _write_article_row(row, seq_nr=10, article=art)
    cells = row.cells
    assert cells[0].text == "10"        # Nr sequential
    assert cells[1].text == "9.1"       # Nr.crt from nr_ordine
    assert cells[2].text == "IZF16A"
    assert cells[3].text == "TRA01A10P" # Cod principal

def test_write_article_row_with_prices():
    doc = Document()
    tbl = doc.add_table(rows=0, cols=15)
    row = tbl.add_row()
    art = _make_full_article(cod="X", pret_material=100.0, val_material=250.0,
                              pret_manopera=50.5, val_manopera=126.25)
    _write_article_row(row, seq_nr=1, article=art)
    cells = row.cells
    assert cells[7].text == "100,00"    # pret_material
    assert cells[11].text == "250,00"   # val_material
    assert cells[8].text == "50,50"     # pret_manopera
    assert cells[12].text == "126,25"   # val_manopera
    assert cells[9].text == ""          # pret_utilaj = 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "write_article_row" -v
```

- [ ] **Step 3: Implement `_write_article_row()`**

```python
# Add to shared/lista_oferta_writer.py

def _write_article_row(row, seq_nr: int, article: Dict) -> None:
    """Write article data into a 15-cell table row."""
    nr_crt = _fmt_nr_crt(article.get("nr_ordine", ""))
    parent_code = article.get("parent_code") or ""
    cantitate = article.get("cantitate", 0)

    values = [
        str(seq_nr),
        nr_crt,
        article.get("cod", ""),
        parent_code,
        article.get("denumire", ""),
        article.get("um", ""),
        f"{cantitate:.3f}" if cantitate else "",
        _fmt_price(article.get("pret_material", 0.0)),
        _fmt_price(article.get("pret_manopera", 0.0)),
        _fmt_price(article.get("pret_utilaj", 0.0)),
        _fmt_price(article.get("pret_transport", 0.0)),
        _fmt_price(article.get("val_material", 0.0)),
        _fmt_price(article.get("val_manopera", 0.0)),
        _fmt_price(article.get("val_utilaj", 0.0)),
        _fmt_price(article.get("val_transport", 0.0)),
    ]

    font_size = 7 if article.get("is_component") else 8

    for i, (cell, val) in enumerate(zip(row.cells, values)):
        cell.text = ""
        p = cell.paragraphs[0]
        if i in (0, 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(val)
        run.font.size = Pt(font_size)
        if article.get("is_component"):
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "write_article_row" -v
```
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): _write_article_row — 15-col F3 article row"
```

---

## Task 6: `_write_group_section()` — group title + table + total row

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from shared.lista_oferta_writer import _write_group_section

def test_write_group_section_adds_paragraph_and_table():
    doc = Document()
    header = {"obiectivul": "PROIECT X", "obiectul": "25.4 CAV", "categoria": "1 Copertina"}
    art1 = _make_full_article(cod="TSD06XA", nr_ordine=1)
    art2 = _make_full_article(cod="IZF16A", nr_ordine="1.1", is_component=True, parent_code="TSD06XA")
    _write_group_section(doc, header, [art1, art2], seq_start=1)
    # Should have: 1 paragraph (group title) + 1 table
    tables = doc.tables
    paragraphs = [p for p in doc.paragraphs if p.text.strip()]
    assert len(tables) == 1
    assert "Copertina" in paragraphs[0].text or "25.4" in paragraphs[0].text
    # Table: 2 header rows + 2 article rows + 1 total row = 5 rows
    assert len(tables[0].rows) == 5

def test_write_group_section_returns_next_seq():
    doc = Document()
    header = {"obiectivul": "X", "obiectul": "Y", "categoria": "Z"}
    arts = [_make_full_article(cod=f"A{i}", nr_ordine=i) for i in range(1, 4)]
    next_seq = _write_group_section(doc, header, arts, seq_start=1)
    assert next_seq == 4   # started at 1, 3 articles → next is 4
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "write_group_section" -v
```

- [ ] **Step 3: Implement `_write_group_section()`**

```python
# Add to shared/lista_oferta_writer.py

def _write_group_section(doc: Document, header: Dict, articles: List[Dict], seq_start: int) -> int:
    """Write group title paragraph + F3 table. Returns next seq_nr."""
    # Group title paragraph
    obiectivul = header.get("obiectivul", "")
    obiectul = header.get("obiectul", "")
    categoria = header.get("categoria", "")
    title_parts = [p for p in [obiectivul, obiectul, categoria] if p]
    title = " | ".join(title_parts)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(9)

    # Count main vs subcomponent articles
    main_count = sum(1 for a in articles if not a.get("is_component"))
    sub_count = sum(1 for a in articles if a.get("is_component"))

    # Table: 2 header rows + N article rows + 1 total row
    n_rows = 2 + len(articles) + 1
    tbl = doc.add_table(rows=n_rows, cols=15)
    tbl.style = "Table Grid"

    _build_table_header(tbl)

    seq = seq_start
    for i, art in enumerate(articles):
        row = tbl.rows[2 + i]
        _write_article_row(row, seq_nr=seq, article=art)
        seq += 1

    # Total row
    total_row = tbl.rows[-1]
    total_row.cells[0].merge(total_row.cells[14])
    total_cell = total_row.cells[0]
    total_cell.text = ""
    run = total_cell.paragraphs[0].add_run(
        f"Total grup: {main_count} articole principale"
        + (f" / {sub_count} subcomponente" if sub_count else "")
    )
    run.bold = True
    run.font.size = Pt(8)
    _shade_cell(total_cell, "F2F2F2")

    return seq
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "write_group_section" -v
```
Expected: 2 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): _write_group_section — group title + F3 table + total row"
```

---

## Task 7: `build_docx_for_source()` — full document

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

- [ ] **Step 1: Write failing test**

```python
# Add to tests/shared/test_lista_oferta_writer.py
from shared.lista_oferta_writer import build_docx_for_source
import tempfile, os

def _make_holistic_with_one_group():
    art = _make_full_article("TSD06XA", nr_ordine=1,
                             deviz_header={"obiectivul": "OBJ", "obiectul": "OBL", "categoria": "CAT"})
    return {
        "matched_groups": [{"oferta_articles": [art], "ref_articles": [], "deviz_denumire": "OBJ|OBL|CAT"}],
        "oferta_only_groups": [],
        "ref_only_groups": [],
    }

def test_build_docx_for_source_creates_file():
    holistic = _make_holistic_with_one_group()
    out = tempfile.mktemp(suffix=".docx")
    try:
        build_docx_for_source(
            holistic=holistic,
            source="oferta",
            entity_name="SC. TEST SRL",
            client_name="Test Client",
            label="Oferta 1",
            output_path=out,
        )
        assert os.path.exists(out)
        assert os.path.getsize(out) > 5000
    finally:
        if os.path.exists(out):
            os.unlink(out)

def test_build_docx_for_source_header_contains_entity():
    holistic = _make_holistic_with_one_group()
    out = tempfile.mktemp(suffix=".docx")
    try:
        build_docx_for_source(
            holistic=holistic,
            source="oferta",
            entity_name="SC. KATO SERVICE SRL",
            client_name="CAV Maneciu",
            label="Oferta 1",
            output_path=out,
        )
        doc = Document(out)
        full_text = " ".join(p.text for p in doc.paragraphs)
        assert "KATO" in full_text
        assert "CAV Maneciu" in full_text
    finally:
        if os.path.exists(out):
            os.unlink(out)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "build_docx" -v
```

- [ ] **Step 3: Implement `build_docx_for_source()`**

```python
# Add to shared/lista_oferta_writer.py
from datetime import date

def build_docx_for_source(
    holistic: Dict,
    source: str,
    entity_name: str,
    client_name: str,
    label: str,
    output_path: str,
) -> None:
    """Generate full F3-format DOCX lista for given source ('oferta' or 'referinta').

    Args:
        holistic: loaded holistic_oferta_N.json dict
        source: "oferta" or "referinta"
        entity_name: ofertant or proiectant name
        client_name: display client name
        label: "Oferta 1" or "Referinta"
        output_path: where to save the .docx
    """
    doc = Document()

    # Document header
    entity_label = "Ofertant" if source == "oferta" else "Proiectant"
    for line, bold, size in [
        (f"Lista articole — {label}", True, 14),
        (f"Client: {client_name}", False, 11),
        (f"{entity_label}: {entity_name}", False, 11),
        (f"Generat: {date.today().isoformat()}", False, 9),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.bold = bold
        run.font.size = Pt(size)

    doc.add_paragraph()  # spacer

    seq = 1
    for header, articles in _iter_source_groups(holistic, source=source):
        seq = _write_group_section(doc, header, articles, seq_start=seq)
        doc.add_paragraph()  # spacer between groups

    doc.save(output_path)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "build_docx" -v
```
Expected: 2 PASSED

- [ ] **Step 5: Run full test suite for this file**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v 2>&1 | tail -10
```
Expected: all tests PASSED

- [ ] **Step 6: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "feat(lista): build_docx_for_source — full F3 document generation"
```

---

## Task 8: `gen_lista_oferta.py` — CLI entry point

**Files:**
- Create: `gen_lista_oferta.py`

No unit tests for the CLI wrapper — it's a thin argparse shell tested via smoke test in Task 9.

- [ ] **Step 1: Implement CLI**

```python
#!/usr/bin/env python3
"""Generate F3-format DOCX article lists for referinta and/or offers.

Usage:
    python3 gen_lista_oferta.py --client "CAV Maneciu"             # referinta + all offers
    python3 gen_lista_oferta.py --client "CAV Maneciu" --oferta 1  # offer 1 only
    python3 gen_lista_oferta.py --client "CAV Maneciu" --referinta # referinta only
"""

import argparse
import json
import sys
from pathlib import Path

from shared.client_config import ClientConfig
from shared.lista_oferta_writer import build_docx_for_source, extract_entity_name

INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_referinta(client_name: str, output_dir: Path, input_dir: Path) -> None:
    holistic_candidates = list(output_dir.glob("holistic_oferta_1.json"))
    if not holistic_candidates:
        print(f"  [SKIP] No holistic_oferta_1.json found — run pipeline first.")
        return
    holistic = _load_json(holistic_candidates[0])
    di_path = str(input_dir / "di_referinta.json")
    entity_name = extract_entity_name(di_path, is_referinta=True)
    out_path = str(output_dir / "Lista_Referinta.docx")
    build_docx_for_source(
        holistic=holistic,
        source="referinta",
        entity_name=entity_name,
        client_name=client_name,
        label="Referinta",
        output_path=out_path,
    )
    print(f"  [OK] {out_path}")


def generate_oferta(client_name: str, output_dir: Path, input_dir: Path, oferta_nr: int) -> None:
    holistic_path = output_dir / f"holistic_oferta_{oferta_nr}.json"
    if not holistic_path.exists():
        print(f"  [SKIP] {holistic_path} not found — run pipeline first.")
        return
    holistic = _load_json(holistic_path)
    di_path = str(input_dir / f"di_oferta_{oferta_nr}.json")
    entity_name = extract_entity_name(di_path, is_referinta=False)
    out_path = str(output_dir / f"Lista_Oferta_{oferta_nr}.docx")
    build_docx_for_source(
        holistic=holistic,
        source="oferta",
        entity_name=entity_name,
        client_name=client_name,
        label=f"Oferta {oferta_nr}",
        output_path=out_path,
    )
    print(f"  [OK] {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate F3 article list DOCX")
    parser.add_argument("--client", required=True, help='Client name, e.g. "CAV Maneciu"')
    parser.add_argument("--oferta", type=int, default=None, help="Offer number (default: all)")
    parser.add_argument("--referinta", action="store_true", help="Generate referinta only")
    args = parser.parse_args()

    input_dir = INPUT_BASE / args.client
    output_dir = OUTPUT_BASE / args.client

    if not input_dir.exists():
        print(f"ERROR: input_AO/{args.client}/ not found", file=sys.stderr)
        sys.exit(1)
    if not output_dir.exists():
        print(f"ERROR: output_AO/{args.client}/ not found — run pipeline first", file=sys.stderr)
        sys.exit(1)

    print(f"Client: {args.client}")

    if args.referinta:
        generate_referinta(args.client, output_dir, input_dir)
        return

    if args.oferta is not None:
        generate_oferta(args.client, output_dir, input_dir, args.oferta)
        return

    # Default: referinta + all offers
    generate_referinta(args.client, output_dir, input_dir)
    oferta_nrs = sorted(
        int(p.stem.replace("di_oferta_", ""))
        for p in input_dir.glob("di_oferta_*.json")
    )
    for nr in oferta_nrs:
        generate_oferta(args.client, output_dir, input_dir, nr)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add gen_lista_oferta.py
git commit -m "feat(lista): gen_lista_oferta.py CLI — referinta + offer DOCX generation"
```

---

## Task 9: Smoke test on real client

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v 2>&1 | tail -5
```
Expected: all PASSED, 0 failures

- [ ] **Step 2: Run baseline test suite**

```bash
pytest --tb=short -q 2>&1 | tail -5
```
Expected: same baseline pass count as before (606 pass, 22 pre-existing failures)

- [ ] **Step 3: Run smoke test on CAV Maneciu**

```bash
python3 gen_lista_oferta.py --client "CAV Maneciu" 2>&1
```
Expected output:
```
Client: CAV Maneciu
  [OK] output_AO/CAV Maneciu/Lista_Referinta.docx
  [OK] output_AO/CAV Maneciu/Lista_Oferta_1.docx
  [OK] output_AO/CAV Maneciu/Lista_Oferta_2.docx
  [OK] output_AO/CAV Maneciu/Lista_Oferta_3.docx
  [OK] output_AO/CAV Maneciu/Lista_Oferta_4.docx
  [OK] output_AO/CAV Maneciu/Lista_Oferta_5.docx
```

- [ ] **Step 4: Verify files exist and are non-trivial**

```bash
ls -lh "output_AO/CAV Maneciu/Lista_"*.docx
```
Expected: 6 files, each > 20KB

- [ ] **Step 5: Spot-check oferta 1**

```bash
python3 -c "
from docx import Document
doc = Document('output_AO/CAV Maneciu/Lista_Oferta_1.docx')
print('Paragraphs with text:')
for p in doc.paragraphs[:6]:
    if p.text.strip():
        print(' ', p.text[:80])
print('Tables:', len(doc.tables))
print('First table rows:', len(doc.tables[0].rows))
print('Row 0 cells:', [c.text for c in doc.tables[0].rows[0].cells[:7]])
"
```
Expected: header paragraphs contain "KATO", 11 tables (one per group), first table header has "Nr.", "Nr.crt", "Cod", etc.

- [ ] **Step 6: Run on Drum Tatarani (regression check)**

```bash
python3 gen_lista_oferta.py --client "Drum Tatarani" 2>&1 | tail -5
```
Expected: Lista_Referinta.docx + Lista_Oferta_1.docx + Lista_Oferta_2.docx, no errors

- [ ] **Step 7: Commit**

```bash
git add .
git commit -m "test(lista): smoke-tested gen_lista_oferta on CAV Maneciu + Drum Tatarani"
```
