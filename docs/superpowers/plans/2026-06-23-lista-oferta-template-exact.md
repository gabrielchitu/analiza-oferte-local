# Lista Oferta — Format Template Exact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `lista_oferta_writer.py` și adaugă `write_docx_v2` în `sursa_incarcare_writer.py` pentru output identic cu `docs/Template_exact.docx`.

**Architecture:** Task 1 fixeaza cele 5 diferențe punctuale in `lista_oferta_writer.py` (lățimi coloane exacte în twips, borduri none, header paragraf pipe-separat, fonturi bold, margini 1.5cm). Task 2 adaugă `write_docx_v2` în `sursa_incarcare_writer.py` cu același format vizual dar acceptând modelul de date sursa (`capitole > articole > sub_items`). Task 3 wires `gen_sursa_incarcare.py` la v2.

**Tech Stack:** python-docx, pytest, lxml (pentru XML OoxML direct)

## Global Constraints

- Python 3.10+
- Lățimi coloane exacte (twips): `[397, 510, 1020, 1020, 3175, 567, 1020, 624, 624, 624, 624]` — nu cm, nu aprox.
- Borduri: `tblBorders` cu toate laturile `w:val="none"` — NU altă metodă
- Header paragraf grup: `"{obiectivul} | {obiectul} | {categoria}"` — fara label, un singur run, 9pt bold
- Fonturi header document: toate 4 linii bold (14pt, 11pt, 11pt, 9pt)
- Margini document: 1.5cm toate laturile (nu 1.8 top/bottom)
- `write_docx` v1 în `sursa_incarcare_writer.py` ramas nemodificat
- Teste existente (214 pass) nu trebuie sa regreseze

---

## File Map

| Fișier | Acțiune | Responsabilitate |
|--------|---------|-----------------|
| `shared/lista_oferta_writer.py` | Modify | Fix 5 diferențe vizuale față de template |
| `tests/shared/test_lista_oferta_writer.py` | Modify | Adaugă teste pentru noile comportamente |
| `shared/sursa_incarcare_writer.py` | Modify | Adaugă `write_docx_v2` + helpers |
| `tests/shared/test_sursa_incarcare_writer_v2.py` | Create | Teste pentru write_docx_v2 |
| `gen_sursa_incarcare.py` | Modify | `--ofertant` arg + apel `write_docx_v2` |

---

### Task 1: Fix lista_oferta_writer.py — format identic cu template

**Files:**
- Modify: `shared/lista_oferta_writer.py`
- Modify: `tests/shared/test_lista_oferta_writer.py`

**Interfaces:**
- Consumes: nimic nou — același API public
- Produces: același API public — `build_docx_for_source`, `_build_table_header`, `_write_group_section`

- [ ] **Step 1: Scrie testele care vor eșua pentru noile comportamente**

Adaugă la sfârșitul `tests/shared/test_lista_oferta_writer.py`:

```python
# ── Tests for template-exact formatting ──────────────────────────────────────

def test_col_widths_exact_twips():
    """tblGrid trebuie să conțină exact lățimile din template (twips)."""
    from docx.oxml.ns import qn
    from shared.lista_oferta_writer import _COL_WIDTHS_TWIPS, _build_table_header
    doc = Document()
    tbl = doc.add_table(rows=2, cols=11)
    _build_table_header(tbl)
    tblGrid = tbl._tbl.find(qn('w:tblGrid'))
    assert tblGrid is not None, "tblGrid missing"
    widths = [int(gc.get(qn('w:w'))) for gc in tblGrid.findall(qn('w:gridCol'))]
    assert widths == _COL_WIDTHS_TWIPS


def test_suppress_table_borders_xml():
    """_suppress_table_borders adaugă tblBorders cu toate laturile none."""
    from docx.oxml.ns import qn
    from shared.lista_oferta_writer import _suppress_table_borders
    doc = Document()
    tbl = doc.add_table(rows=2, cols=11)
    tbl.style = "Table Grid"
    _suppress_table_borders(tbl)
    tblPr = tbl._tbl.find(qn('w:tblPr'))
    borders = tblPr.find(qn('w:tblBorders'))
    assert borders is not None, "tblBorders element missing"
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = borders.find(qn(f'w:{side}'))
        assert el is not None, f"missing border side: {side}"
        assert el.get(qn('w:val')) == 'none', f"{side} val != none"


def test_group_section_header_pipe_format():
    """Paragraf grup: 'OBJ | OBL | CAT' — fara label, fara newlines."""
    from shared.lista_oferta_writer import _write_group_section
    doc = Document()
    header = {"obiectivul": "PROIECT X", "obiectul": "25.4 CAV", "categoria": "1 Copertina"}
    _write_group_section(doc, header, [], deviz_denumire="")
    # Primul paragraf non-gol este header-ul grupului
    para_texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert len(para_texts) >= 1
    title = para_texts[0]
    assert title == "PROIECT X | 25.4 CAV | 1 Copertina"
    assert "Obiectivul:" not in title
    assert "\n" not in title


def test_group_section_header_no_label():
    """Daca obiectivul e numeric, foloseste deviz_denumire pipe-separat."""
    from shared.lista_oferta_writer import _write_group_section
    doc = Document()
    header = {"obiectivul": "0232 000000232", "obiectul": "", "categoria": ""}
    _write_group_section(doc, header, [], deviz_denumire="DRUMURI | Ob 1 | Str. X")
    para_texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert "DRUMURI" in para_texts[0]
    assert "Obiectivul:" not in para_texts[0]


def test_document_header_all_bold():
    """Toate 4 linii din header document trebuie sa fie bold."""
    import tempfile, os
    holistic = {"matched_groups": [], "ref_only_groups": [], "oferta_only_groups": []}
    out = tempfile.mktemp(suffix=".docx")
    try:
        build_docx_for_source(
            holistic=holistic, source="oferta",
            entity_name="TestOfertant", client_name="TestClient",
            label="Oferta 1", output_path=out,
        )
        doc = Document(out)
        header_paras = [p for p in doc.paragraphs if p.text.strip()][:4]
        assert len(header_paras) == 4
        for p in header_paras:
            for run in p.runs:
                assert run.bold, f"Run not bold in: {p.text!r}"
    finally:
        if os.path.exists(out): os.unlink(out)


def test_document_margins_1_5cm():
    """Margini document: 1.5cm toate laturile."""
    import tempfile, os
    from docx.shared import Cm
    holistic = {"matched_groups": [], "ref_only_groups": [], "oferta_only_groups": []}
    out = tempfile.mktemp(suffix=".docx")
    try:
        build_docx_for_source(
            holistic=holistic, source="oferta",
            entity_name="E", client_name="C", label="Oferta 1", output_path=out,
        )
        doc = Document(out)
        s = doc.sections[0]
        assert abs(s.top_margin - Cm(1.5)) < 100, f"top_margin={s.top_margin}"
        assert abs(s.bottom_margin - Cm(1.5)) < 100, f"bottom_margin={s.bottom_margin}"
    finally:
        if os.path.exists(out): os.unlink(out)
```

- [ ] **Step 2: Rulează testele să confirmi că eșuează**

```bash
pytest tests/shared/test_lista_oferta_writer.py -k "test_col_widths_exact or test_suppress or test_group_section_header or test_document_header_all_bold or test_document_margins" -v
```

Expected: toate 6 teste FAIL.

- [ ] **Step 3: Implementează fix-urile în lista_oferta_writer.py**

Înlocuiește în `shared/lista_oferta_writer.py`:

**3a. Adaugă constant + helpers (după imports, înainte de `extract_entity_name`)**

```python
# Exact column widths from Template_exact.docx (twips, dxa)
_COL_WIDTHS_TWIPS = [397, 510, 1020, 1020, 3175, 567, 1020, 624, 624, 624, 624]


def _set_cell_width_twips(cell, twips: int) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    existing = tcPr.find(qn('w:tcW'))
    if existing is not None:
        tcPr.remove(existing)
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(twips))
    tcW.set(qn('w:type'), 'dxa')
    tcPr.insert(0, tcW)


def _suppress_table_borders(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        el.set(qn('w:color'), 'auto')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _set_tbl_grid(tbl) -> None:
    tbl_el = tbl._tbl
    existing = tbl_el.find(qn('w:tblGrid'))
    if existing is not None:
        tbl_el.remove(existing)
    tblGrid = OxmlElement('w:tblGrid')
    for w in _COL_WIDTHS_TWIPS:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(w))
        tblGrid.append(gc)
    tblPr = tbl_el.find(qn('w:tblPr'))
    if tblPr is not None:
        tblPr.addnext(tblGrid)
    else:
        tbl_el.insert(0, tblGrid)
```

**3b. Înlocuiește `_build_table_header`** (elimină `COL_WIDTHS_CM`, folosește twips + tblGrid):

```python
def _build_table_header(table: Table) -> None:
    """Write 2-row F3 header into an existing 2-row, 11-col table."""
    _set_tbl_grid(table)

    row0 = table.rows[0].cells
    row1 = table.rows[1].cells

    for ci in range(11):
        _set_cell_width_twips(row0[ci], _COL_WIDTHS_TWIPS[ci])
        _set_cell_width_twips(row1[ci], _COL_WIDTHS_TWIPS[ci])
        if ci in _NO_WRAP_COLS:
            _set_cell_no_wrap(row0[ci])
            _set_cell_no_wrap(row1[ci])

    labels_row0 = ["Nr.", "Nr.crt", "Cod", "Cod principal", "Denumire", "UM", "Cantitate"]
    for i, label in enumerate(labels_row0):
        _merge_vertical(table, i)
        _cell_text(row0[i], label, bold=True, center=True)
        _shade_cell(row0[i], HEADER_FILL)

    row0[7].merge(row0[10])
    _cell_text(row0[7], "Pret unitar (lei/UM)", bold=True, center=True)
    _shade_cell(row0[7], HEADER_FILL)

    for i, label in enumerate(["Material", "Manoperă", "Utilaje", "Transport"]):
        _cell_text(row1[7 + i], label, bold=True, center=True)
        _shade_cell(row1[7 + i], HEADER_FILL)
```

**3c. Înlocuiește blocul de header paragraf din `_write_group_section`**

Elimina:
```python
    first_line = True
    for label, val in [
        ("Obiectivul", obiectivul),
        ("Obiectul", obiectul),
        ("Cod de lucrari sau stare fizica", categoria),
    ]:
        if val:
            if not first_line:
                p.add_run().add_break()
            run = p.add_run(f"{label}: {val}")
            run.bold = True
            run.font.size = Pt(9)
            first_line = False
```

Înlocuiește cu:
```python
    parts = [s.strip() for s in [obiectivul, obiectul, categoria] if s.strip()]
    run = p.add_run(" | ".join(parts))
    run.bold = True
    run.font.size = Pt(9)
```

Înlocuiește și blocul `if _is_numeric_only(obiectivul) and deviz_denumire:`:
```python
    if _is_numeric_only(obiectivul) and deviz_denumire:
        raw_parts = [s.strip() for s in deviz_denumire.split("|")]
        title = " | ".join(p for p in raw_parts if p)
        run = p.add_run(title)
        run.bold = True
        run.font.size = Pt(9)
    else:
        parts = [s.strip() for s in [obiectivul, obiectul, categoria] if s.strip()]
        run = p.add_run(" | ".join(parts))
        run.bold = True
        run.font.size = Pt(9)
```

Adaugă `_suppress_table_borders(tbl)` imediat după `tbl.style = "Table Grid"`:
```python
    tbl = doc.add_table(rows=n_rows, cols=11)
    tbl.style = "Table Grid"
    _suppress_table_borders(tbl)          # ← adaugă această linie
    _set_table_fixed_layout(tbl)
```

**3d. Schimbă bold și margini în `build_docx_for_source`**

```python
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)      # era 1.8
    section.bottom_margin = Cm(1.5)   # era 1.8

    entity_label = "Ofertant" if source == "oferta" else "Proiectant"
    for line, bold, size in [
        (f"Lista articole — {label}", True, 14),
        (f"Client: {client_name}", True, 11),          # era False
        (f"{entity_label}: {entity_name}", True, 11),  # era False
        (f"Generat: {date.today().isoformat()}", True, 9),  # era False
    ]:
```

Elimina și `COL_WIDTHS_CM = [0.7, 0.9, 1.8, 1.8, 5.6, 1.0, 1.8, 1.1, 1.1, 1.1, 1.1]` (înlocuit de `_COL_WIDTHS_TWIPS`).

- [ ] **Step 4: Rulează testele să confirmi că trec**

```bash
pytest tests/shared/test_lista_oferta_writer.py -v
```

Expected: toate testele relevante PASS. Verifică că nu ai regresii față de baseline.

Notă: testele care anterior se bazau pe `COL_WIDTHS_CM` nu există (au fost verificate). Testul `test_write_group_section_adds_paragraph_and_table` verifică `"Copertina" in paragraphs[0].text` — va trece deoarece noul format `"PROIECT X | 25.4 CAV | 1 Copertina"` conține "Copertina".

- [ ] **Step 5: Commit**

```bash
git add shared/lista_oferta_writer.py tests/shared/test_lista_oferta_writer.py
git commit -m "fix(lista-oferta): format identic cu Template_exact — twips, fara borduri, header pipe, bold, margini 1.5cm"
```

---

### Task 2: write_docx_v2 în sursa_incarcare_writer.py

**Files:**
- Modify: `shared/sursa_incarcare_writer.py`
- Create: `tests/shared/test_sursa_incarcare_writer_v2.py`

**Interfaces:**
- Consumes: `devize: list[dict]` cu structură `[{obiectivul, obiectul, categoria, capitole: [{titlu, articole: [{nr_crt, cod, denumire, um, cantitate, breakdown: {material, manopera, utilaj, transport}, sub_items: [{nr_crt, cod, denumire, um, cantitate}]}]}]}]`
- Produces: `write_docx_v2(devize, output_path, metadata=None)` — scrie DOCX

- [ ] **Step 1: Scrie testele**

Creează `tests/shared/test_sursa_incarcare_writer_v2.py`:

```python
import os
import tempfile
import pytest
from docx import Document
from docx.oxml.ns import qn
from shared.sursa_incarcare_writer import write_docx_v2


def _make_deviz(n_main=2, n_sub=1):
    """Minimal deviz for testing."""
    articles = []
    for i in range(1, n_main + 1):
        art = {
            "nr_crt": str(i),
            "cod": f"TST0{i}A",
            "denumire": f"Articol test {i}",
            "um": "mc",
            "cantitate": float(i),
            "pret_unitar": 0.0,
            "total": 0.0,
            "breakdown": {
                "material": {"pret": 10.0 * i, "total": 0.0},
                "manopera": {"pret": 0.0, "total": 0.0},
                "utilaj": {"pret": 0.0, "total": 0.0},
                "transport": {"pret": 0.0, "total": 0.0},
            },
            "sub_items": [],
        }
        if i == 1 and n_sub > 0:
            art["sub_items"] = [{
                "nr_crt": "1.1",
                "cod": "SPEC_SUB",
                "denumire": "Subcomponent test",
                "um": "buc",
                "cantitate": 5.0,
            }]
        articles.append(art)
    return {
        "obiectivul": "OBIECTIV TEST",
        "obiectul": "Ob 001",
        "categoria": "Cat Test",
        "capitole": [{"titlu": "Capitol 1", "articole": articles}],
    }


def _write_and_open(devize, metadata=None):
    out = tempfile.mktemp(suffix=".docx")
    write_docx_v2(devize, out, metadata=metadata)
    return out, Document(out)


def test_write_docx_v2_creates_file():
    out, doc = _write_and_open([_make_deviz()])
    try:
        assert os.path.exists(out)
        assert os.path.getsize(out) > 3000
    finally:
        os.unlink(out)


def test_write_docx_v2_document_header_paragraphs():
    """Primele 4 paragrafe: Lista articole, Client, Ofertant, Generat."""
    meta = {"offer_label": "Oferta 2", "client": "Test Client", "ofertant": "SC TEST SRL", "date": "2026-06-23"}
    out, doc = _write_and_open([_make_deviz()], metadata=meta)
    try:
        paras = [p.text for p in doc.paragraphs if p.text.strip()]
        assert paras[0] == "Lista articole — Oferta 2"
        assert "Test Client" in paras[1]
        assert "SC TEST SRL" in paras[2]
        assert "2026-06-23" in paras[3]
    finally:
        os.unlink(out)


def test_write_docx_v2_document_header_all_bold():
    out, doc = _write_and_open([_make_deviz()])
    try:
        header_paras = [p for p in doc.paragraphs if p.text.strip()][:4]
        for p in header_paras:
            for run in p.runs:
                assert run.bold, f"Not bold: {p.text!r}"
    finally:
        os.unlink(out)


def test_write_docx_v2_group_header_pipe_format():
    """Paragraf grup: 'OBIECTIV TEST | Ob 001 | Cat Test'."""
    out, doc = _write_and_open([_make_deviz()])
    try:
        group_paras = [p for p in doc.paragraphs if p.text.strip()][4:]
        assert group_paras[0].text == "OBIECTIV TEST | Ob 001 | Cat Test"
    finally:
        os.unlink(out)


def test_write_docx_v2_table_11_cols():
    """Fiecare grup are exact un tabel cu 11 coloane."""
    out, doc = _write_and_open([_make_deviz()])
    try:
        assert len(doc.tables) == 1
        tblGrid = doc.tables[0]._tbl.find(qn('w:tblGrid'))
        assert tblGrid is not None
        cols = tblGrid.findall(qn('w:gridCol'))
        assert len(cols) == 11
    finally:
        os.unlink(out)


def test_write_docx_v2_col_widths_exact():
    from shared.sursa_incarcare_writer import _COL_WIDTHS_TWIPS_V2
    out, doc = _write_and_open([_make_deviz()])
    try:
        tblGrid = doc.tables[0]._tbl.find(qn('w:tblGrid'))
        widths = [int(gc.get(qn('w:w'))) for gc in tblGrid.findall(qn('w:gridCol'))]
        assert widths == _COL_WIDTHS_TWIPS_V2
    finally:
        os.unlink(out)


def test_write_docx_v2_no_borders():
    out, doc = _write_and_open([_make_deviz()])
    try:
        tbl = doc.tables[0]
        tblPr = tbl._tbl.find(qn('w:tblPr'))
        borders = tblPr.find(qn('w:tblBorders'))
        assert borders is not None
        top = borders.find(qn('w:top'))
        assert top is not None and top.get(qn('w:val')) == 'none'
    finally:
        os.unlink(out)


def test_write_docx_v2_table_header_text():
    out, doc = _write_and_open([_make_deviz()])
    try:
        tbl = doc.tables[0]
        assert tbl.rows[0].cells[0].text == "Nr."
        assert tbl.rows[0].cells[2].text == "Cod"
        assert tbl.rows[0].cells[7].text == "Pret unitar (lei/UM)"
        assert tbl.rows[1].cells[7].text == "Material"
        assert tbl.rows[1].cells[10].text == "Transport"
    finally:
        os.unlink(out)


def test_write_docx_v2_article_data_rows():
    """Rânduri date: Nr, Nr.crt, Cod, Cod principal, Denumire, UM, Cantitate."""
    out, doc = _write_and_open([_make_deviz(n_main=2, n_sub=0)])
    try:
        tbl = doc.tables[0]
        row2 = tbl.rows[2]  # first data row (after 2 header rows)
        assert row2.cells[0].text == "1"       # Nr local
        assert row2.cells[1].text == "1"       # nr_crt
        assert row2.cells[2].text == "TST01A"  # Cod
        assert row2.cells[3].text == ""         # Cod principal empty for main
        assert row2.cells[4].text == "Articol test 1"
        assert row2.cells[5].text == "mc"
        assert row2.cells[6].text == "1.00"    # cantitate
    finally:
        os.unlink(out)


def test_write_docx_v2_subitem_cod_principal():
    """Sub-item: Cod principal = parent.cod."""
    out, doc = _write_and_open([_make_deviz(n_main=2, n_sub=1)])
    try:
        tbl = doc.tables[0]
        # rows: 0,1=header; 2=main art1; 3=sub_item(1.1); 4=main art2; 5=total
        sub_row = tbl.rows[3]
        assert sub_row.cells[1].text == "1.1"    # nr_crt decimal
        assert sub_row.cells[2].text == "SPEC_SUB"
        assert sub_row.cells[3].text == "TST01A"  # parent.cod
    finally:
        os.unlink(out)


def test_write_docx_v2_breakdown_prices():
    """Material pret din breakdown → col 7, format Romanian locale."""
    out, doc = _write_and_open([_make_deviz(n_main=1, n_sub=0)])
    try:
        tbl = doc.tables[0]
        row2 = tbl.rows[2]
        # art 1: breakdown.material.pret = 10.0
        assert row2.cells[7].text == "10,00"
        assert row2.cells[8].text == ""   # manopera = 0 → empty
    finally:
        os.unlink(out)


def test_write_docx_v2_total_grup_row():
    """Ultima linie: 'Total grup: N articole principale / M subcomponente'."""
    out, doc = _write_and_open([_make_deviz(n_main=2, n_sub=1)])
    try:
        tbl = doc.tables[0]
        last_row = tbl.rows[-1]
        text = last_row.cells[0].text
        assert "Total grup:" in text
        assert "2 articole principale" in text
        assert "1 subcomponente" in text
    finally:
        os.unlink(out)


def test_write_docx_v2_multiple_devize():
    """Un paragraf + un tabel per deviz."""
    out, doc = _write_and_open([_make_deviz(), _make_deviz(n_main=1, n_sub=0)])
    try:
        assert len(doc.tables) == 2
        group_paras = [p for p in doc.paragraphs if "OBIECTIV TEST" in p.text]
        assert len(group_paras) == 2
    finally:
        os.unlink(out)
```

- [ ] **Step 2: Rulează testele să confirmi că eșuează**

```bash
pytest tests/shared/test_sursa_incarcare_writer_v2.py -v
```

Expected: toate 12 teste FAIL (ImportError sau AttributeError — `write_docx_v2` nu există).

- [ ] **Step 3: Implementează write_docx_v2 în sursa_incarcare_writer.py**

Adaugă la sfârșitul fișierului `shared/sursa_incarcare_writer.py` (după `write_pdf_native`):

```python
# ── V2: Template-exact format ──────────────────────────────────────────────

_COL_WIDTHS_TWIPS_V2 = [397, 510, 1020, 1020, 3175, 567, 1020, 624, 624, 624, 624]
_NO_WRAP_COLS_V2 = {0, 1, 2, 3, 5, 6, 7, 8, 9, 10}
_HEADER_FILL_V2 = 'D9D9D9'
_TOTAL_FILL_V2 = 'F2F2F2'


def _set_cell_width_twips_v2(cell, twips: int) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    existing = tcPr.find(qn('w:tcW'))
    if existing is not None:
        tcPr.remove(existing)
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(twips))
    tcW.set(qn('w:type'), 'dxa')
    tcPr.insert(0, tcW)


def _set_cell_no_wrap_v2(cell) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(OxmlElement('w:noWrap'))


def _suppress_borders_v2(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        el.set(qn('w:color'), 'auto')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _set_tbl_grid_v2(tbl) -> None:
    tbl_el = tbl._tbl
    existing = tbl_el.find(qn('w:tblGrid'))
    if existing is not None:
        tbl_el.remove(existing)
    tblGrid = OxmlElement('w:tblGrid')
    for w in _COL_WIDTHS_TWIPS_V2:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(w))
        tblGrid.append(gc)
    tblPr = tbl_el.find(qn('w:tblPr'))
    if tblPr is not None:
        tblPr.addnext(tblGrid)
    else:
        tbl_el.insert(0, tblGrid)


def _shade_cell_v2(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _cell_write_v2(cell, text: str, bold: bool = False, size: float = 8,
                   center: bool = False, right: bool = False) -> None:
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if right:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _fmt_price_ro(value) -> str:
    """None/0 → ''; else Romanian locale: 1.234,50."""
    if not value:
        return ''
    formatted = f'{value:,.2f}'
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


def _build_sursa_table_header(tbl) -> None:
    """Write 2-row F3 header (same structure as Template_exact.docx)."""
    row0 = tbl.rows[0].cells
    row1 = tbl.rows[1].cells

    for ci in range(11):
        _set_cell_width_twips_v2(row0[ci], _COL_WIDTHS_TWIPS_V2[ci])
        _set_cell_width_twips_v2(row1[ci], _COL_WIDTHS_TWIPS_V2[ci])
        if ci in _NO_WRAP_COLS_V2:
            _set_cell_no_wrap_v2(row0[ci])
            _set_cell_no_wrap_v2(row1[ci])

    labels = ["Nr.", "Nr.crt", "Cod", "Cod principal", "Denumire", "UM", "Cantitate"]
    for i, label in enumerate(labels):
        tbl.cell(0, i).merge(tbl.cell(1, i))
        _cell_write_v2(row0[i], label, bold=True, center=True)
        _shade_cell_v2(row0[i], _HEADER_FILL_V2)

    row0[7].merge(row0[10])
    _cell_write_v2(row0[7], "Pret unitar (lei/UM)", bold=True, center=True)
    _shade_cell_v2(row0[7], _HEADER_FILL_V2)

    for i, label in enumerate(["Material", "Manoperă", "Utilaje", "Transport"]):
        _cell_write_v2(row1[7 + i], label, bold=True, center=True)
        _shade_cell_v2(row1[7 + i], _HEADER_FILL_V2)


def _write_sursa_row_v2(row, seq_nr: int, art: dict, is_sub: bool, parent_cod: str) -> None:
    bd = art.get('breakdown') or {}
    font_size = 7 if is_sub else 8

    values = [
        str(seq_nr),
        str(art.get('nr_crt', '')),
        art.get('cod', '') or '',
        parent_cod or '',
        art.get('denumire', ''),
        art.get('um', ''),
        f"{art.get('cantitate', 0):.2f}" if art.get('cantitate') else '',
        _fmt_price_ro(bd.get('material', {}).get('pret')),
        _fmt_price_ro(bd.get('manopera', {}).get('pret')),
        _fmt_price_ro(bd.get('utilaj', {}).get('pret')),
        _fmt_price_ro(bd.get('transport', {}).get('pret')),
    ]
    right_cols = {1, 6, 7, 8, 9, 10}
    center_cols = {0, 5}

    for ci, (cell, val) in enumerate(zip(row.cells, values)):
        cell.text = ''
        p = cell.paragraphs[0]
        if ci in right_cols:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif ci in center_cols:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(val)
        run.font.size = Pt(font_size)
        if is_sub:
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)


def _build_sursa_group(doc, deviz: dict) -> None:
    """Add group header paragraph + 11-col table for one deviz."""
    obiectivul = deviz.get('obiectivul', '')
    obiectul   = deviz.get('obiectul', '')
    categoria  = deviz.get('categoria', '')

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    parts = [s.strip() for s in [obiectivul, obiectul, categoria] if s.strip()]
    run = p.add_run(' | '.join(parts))
    run.bold = True
    run.font.size = Pt(9)

    # Flatten capitole → articole + sub_items
    flat: list[tuple[bool, dict, str]] = []  # (is_sub, art, parent_cod)
    for cap in deviz.get('capitole', []):
        for art in cap.get('articole', []):
            flat.append((False, art, ''))
            for sub in art.get('sub_items', []):
                flat.append((True, sub, art.get('cod', '') or ''))

    main_count = sum(1 for is_sub, _, _ in flat if not is_sub)
    sub_count  = sum(1 for is_sub, _, _ in flat if is_sub)

    n_rows = 2 + len(flat) + 1
    tbl = doc.add_table(rows=n_rows, cols=11)
    tbl.style = 'Table Grid'
    _set_tbl_grid_v2(tbl)
    _suppress_borders_v2(tbl)

    _build_sursa_table_header(tbl)

    for i, (is_sub, art, parent_cod) in enumerate(flat):
        _write_sursa_row_v2(tbl.rows[2 + i], seq_nr=i + 1,
                            art=art, is_sub=is_sub, parent_cod=parent_cod)

    total_row = tbl.rows[-1]
    total_row.cells[0].merge(total_row.cells[10])
    cell = total_row.cells[0]
    cell.text = ''
    suffix = f' / {sub_count} subcomponente' if sub_count else ''
    run = cell.paragraphs[0].add_run(
        f'Total grup: {main_count} articole principale{suffix}'
    )
    run.bold = True
    run.font.size = Pt(8)
    _shade_cell_v2(cell, _TOTAL_FILL_V2)


def write_docx_v2(devize: list, output_path, metadata: dict | None = None) -> None:
    """Write F3-format DOCX identical with Template_exact.docx."""
    from datetime import date as _date
    meta = metadata or {}

    doc = Document()
    section = doc.sections[0]
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)

    offer_label = meta.get('offer_label', 'Oferta')
    client_name = meta.get('client', '')
    ofertant    = meta.get('ofertant', '')
    gen_date    = meta.get('date', _date.today().isoformat())

    for line, size in [
        (f'Lista articole — {offer_label}', 14),
        (f'Client: {client_name}', 11),
        (f'Ofertant: {ofertant}', 11),
        (f'Generat: {gen_date}', 9),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.bold = True
        run.font.size = Pt(size)

    for deviz in devize:
        _build_sursa_group(doc, deviz)

    doc.save(str(output_path))
```

- [ ] **Step 4: Rulează testele să confirmi că trec**

```bash
pytest tests/shared/test_sursa_incarcare_writer_v2.py -v
```

Expected: toate 12 teste PASS.

- [ ] **Step 5: Rulează suita completă să verifici că nu ai regresii**

```bash
pytest --tb=short -q
```

Expected: ≥214 pass, 0 noi eșecuri față de baseline.

- [ ] **Step 6: Commit**

```bash
git add shared/sursa_incarcare_writer.py tests/shared/test_sursa_incarcare_writer_v2.py
git commit -m "feat(sursa-incarcare): write_docx_v2 — format identic Template_exact (11 col, fara borduri, pipe header)"
```

---

### Task 3: Wire gen_sursa_incarcare.py la write_docx_v2

**Files:**
- Modify: `gen_sursa_incarcare.py`

**Interfaces:**
- Consumes: `write_docx_v2` din Task 2
- Produces: CLI `--ofertant` arg; `_run_pipeline` apelează `write_docx_v2`

- [ ] **Step 1: Modifică gen_sursa_incarcare.py**

**3a. Adaugă `write_docx_v2` la importul din `sursa_incarcare_writer`** (linia ~24):

```python
from shared.sursa_incarcare_writer import make_acronym, write_docx, write_docx_v2, write_xlsx, write_pdf, write_pdf_native
```

**3b. Adaugă `--ofertant` la argparse** (în `main()`, după `--force`):

```python
parser.add_argument("--ofertant", default="", help="Numele ofertantului (apare in header DOCX)")
```

**3c. Pasează `ofertant` din `main()` la `_run_pipeline`** — schimbă semnătura:

```python
def _run_pipeline(client_name: str, json_path: Path, no_pdf: bool = False,
                  force: bool = False, ofertant: str = "") -> None:
```

Și în `main()`:
```python
_run_pipeline(client_name, json_path, no_pdf=args.no_pdf, force=args.force, ofertant=args.ofertant)
```

**3d. Înlocuiește apelul `write_docx` cu `write_docx_v2`** în `_run_pipeline` (după Step 3/extracție):

Înlocuiește:
```python
    write_docx(extracted, docx_path)
    print(f"\nOutput generat:")
    print(f"  {docx_path}  OK")
```

Cu:
```python
    json_stem_num = ''.join(filter(str.isdigit, json_stem)) or '1'
    metadata = {
        "offer_label": f"Oferta {json_stem_num}",
        "client": client_name,
        "ofertant": ofertant,
    }
    write_docx_v2(extracted, docx_path, metadata=metadata)
    print(f"\nOutput generat:")
    print(f"  {docx_path}  OK")
```

- [ ] **Step 2: Rulează smoke test**

```bash
python3 gen_sursa_incarcare.py --client "CAV Maneciu" --json di_oferta_1 --no-pdf --ofertant "CUANTUM PROJECTS"
```

Expected:
- Output: `output_AO/CAV Maneciu/Lista-proiect-...docx`
- Deschis în Word/LibreOffice: identic cu `docs/Template_exact.docx` ca format

- [ ] **Step 3: Rulează testele finale**

```bash
pytest --tb=short -q
```

Expected: ≥214 pass, 0 regresii.

- [ ] **Step 4: Commit**

```bash
git add gen_sursa_incarcare.py
git commit -m "feat(gen-sursa): wire write_docx_v2, add --ofertant CLI arg"
```
