# Group Totals Row Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a mirrored totals row after every group in the holistic DOCX report showing reference and offer main-article counts, to aid manual reconciliation.

**Architecture:** Two new functions added to `shared/report_word.py`: `_count_main_articles` (pure helper) and `_add_group_totals_row` (table row builder). Three call sites added inside `_generate_word_holistic` — one per group type (matched, ref_only, oferta_only).

**Tech Stack:** python-docx (`docx`), pytest

---

## File Structure

| File | Change |
|---|---|
| `shared/report_word.py` | Add 2 new functions; add 3 call sites in `_generate_word_holistic` |
| `tests/shared/test_report_word_totals.py` | New test file |

---

### Task 1: `_count_main_articles` helper + tests

**Files:**
- Modify: `shared/report_word.py` (after line 592, before `# ── Hierarchical DOCX helpers`)
- Create: `tests/shared/test_report_word_totals.py`

- [ ] **Step 1: Write failing tests**

Create `tests/shared/test_report_word_totals.py`:

```python
import pytest
from shared.report_word import _count_main_articles


def test_count_main_articles_empty():
    assert _count_main_articles([]) == 0


def test_count_main_articles_all_main():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A02"},  # missing key → not a component
        {"cod": "A03", "is_component": False},
    ]
    assert _count_main_articles(articles) == 3


def test_count_main_articles_filters_components():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A01-sub1", "is_component": True},
        {"cod": "A01-sub2", "is_component": True},
        {"cod": "A02", "is_component": False},
    ]
    assert _count_main_articles(articles) == 2


def test_count_main_articles_all_components():
    articles = [
        {"cod": "X01", "is_component": True},
        {"cod": "X02", "is_component": True},
    ]
    assert _count_main_articles(articles) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError` — `_count_main_articles` not defined yet.

- [ ] **Step 3: Implement `_count_main_articles` in `shared/report_word.py`**

Insert after line 592 (after `_add_deviz_summary_row` closing `}`):

```python
def _count_main_articles(articles: list) -> int:
    return sum(1 for a in articles if not a.get("is_component", False))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py::test_count_main_articles_empty tests/shared/test_report_word_totals.py::test_count_main_articles_all_main tests/shared/test_report_word_totals.py::test_count_main_articles_filters_components tests/shared/test_report_word_totals.py::test_count_main_articles_all_components -v 2>&1 | tail -15
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```bash
git add shared/report_word.py tests/shared/test_report_word_totals.py
git commit -m "feat(report): add _count_main_articles helper"
```

---

### Task 2: `_add_group_totals_row` function + tests

**Files:**
- Modify: `shared/report_word.py` (after `_count_main_articles`)
- Modify: `tests/shared/test_report_word_totals.py`

**Background:** The holistic report table has 11 columns (indices 0–10). Column layout:
- 0: Nr. crt.
- 1: Categoria de lucrări
- 2–5: CERINȚĂ (ref side: Cod, Denumire, UM, Cant.)
- 6–9: CE A OFERTAT (offer side: Cod, Denumire, UM, Cant.)
- 10: Observații

The totals row merges:
- Cols 0–1 → label "TOTAL GRUP"
- Cols 2–5 → "Referință: N articole" (empty string if `ref_count` is None)
- Cols 6–9 → "Ofertă: M articole" (empty string if `oferta_count` is None)
- Col 10 → empty

All cells shaded `GRAY_FILL = "D9D9D9"`.

- [ ] **Step 1: Write failing tests**

Append to `tests/shared/test_report_word_totals.py`:

```python
from docx import Document
from shared.report_word import _add_group_totals_row, GRAY_FILL


def _make_table(doc):
    """11-column table with one data row."""
    table = doc.add_table(rows=1, cols=11)
    return table


def _get_shading_fill(cell):
    """Extract fill hex from cell shading XML, or None."""
    tc = cell._tc
    tcPr = tc.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tcPr"
    )
    if tcPr is None:
        return None
    shd = tcPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}shd"
    )
    if shd is None:
        return None
    return shd.get(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}fill"
    )


def test_add_group_totals_row_matched_adds_one_row():
    doc = Document()
    table = _make_table(doc)
    initial_count = len(table.rows)
    _add_group_totals_row(table, ref_count=10, oferta_count=8)
    assert len(table.rows) == initial_count + 1


def test_add_group_totals_row_matched_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=10, oferta_count=8)
    row = table.rows[-1]
    # After merge, cell 0 = label, cell 2 = ref text, cell 6 = offer text
    label_text = row.cells[0].text
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert "TOTAL" in label_text
    assert "10" in ref_text
    assert "8" in offer_text


def test_add_group_totals_row_ref_only_no_offer_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=5, oferta_count=None)
    row = table.rows[-1]
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert "5" in ref_text
    assert offer_text.strip() == ""


def test_add_group_totals_row_oferta_only_no_ref_text():
    doc = Document()
    table = _make_table(doc)
    _add_group_totals_row(table, ref_count=None, oferta_count=7)
    row = table.rows[-1]
    ref_text = row.cells[2].text
    offer_text = row.cells[6].text
    assert ref_text.strip() == ""
    assert "7" in offer_text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py -k "totals_row" -v 2>&1 | tail -20
```

Expected: `ImportError` — `_add_group_totals_row` not defined yet.

- [ ] **Step 3: Implement `_add_group_totals_row` in `shared/report_word.py`**

Insert directly after `_count_main_articles`:

```python
def _add_group_totals_row(table, ref_count: int | None, oferta_count: int | None) -> None:
    """Append mirrored totals row after a holistic group.

    Cols 0-1: "TOTAL GRUP"
    Cols 2-5: "Referință: N articole" (empty when ref_count is None)
    Cols 6-9: "Ofertă: M articole"   (empty when oferta_count is None)
    Col 10:   empty
    """
    cells = table.add_row().cells

    # Label: merge cols 0-1
    cells[0].merge(cells[1])
    cells[0].paragraphs[0].add_run("TOTAL GRUP").bold = True
    _style_cell(cells[0], 9, bold=True)
    _set_cell_shading(cells[0], GRAY_FILL)

    # Ref side: merge cols 2-5
    cells[2].merge(cells[5])
    if ref_count is not None:
        cells[2].paragraphs[0].add_run(f"Referință: {ref_count} articole principale").bold = True
        _style_cell(cells[2], 9, bold=True)
    _set_cell_shading(cells[2], GRAY_FILL)

    # Offer side: merge cols 6-9
    cells[6].merge(cells[9])
    if oferta_count is not None:
        cells[6].paragraphs[0].add_run(f"Ofertă: {oferta_count} articole principale").bold = True
        _style_cell(cells[6], 9, bold=True)
    _set_cell_shading(cells[6], GRAY_FILL)

    # Col 10: empty
    _set_cell_shading(cells[10], GRAY_FILL)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py -v 2>&1 | tail -20
```

Expected: all 8 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add shared/report_word.py tests/shared/test_report_word_totals.py
git commit -m "feat(report): add _add_group_totals_row for holistic DOCX groups"
```

---

### Task 3: Wire call sites in `_generate_word_holistic`

**Files:**
- Modify: `shared/report_word.py:1070–1105`

The three loops in `_generate_word_holistic` currently end without a totals row. Add the call after each loop body.

- [ ] **Step 1: Write failing integration test**

Append to `tests/shared/test_report_word_totals.py`:

```python
from shared.report_word import _generate_word_holistic


def _make_holistic_comp():
    """Minimal comp dict for _generate_word_holistic."""
    return {"ofertant": "Test SRL", "source_file": "test.pdf"}


def _make_matched_group(n_ref=3, n_oferta=2, n_neconformitati=0):
    return {
        "ref_deviz_cod": "REF01",
        "oferta_deviz_cod": "OFF01",
        "ref_header": None,
        "oferta_header": None,
        "deviz_denumire": "Test deviz",
        "ref_articles": [{"cod": f"R{i}", "is_component": False} for i in range(n_ref)],
        "oferta_articles": [{"cod": f"O{i}", "is_component": False} for i in range(n_oferta)],
        "neconformitati": [],
        "matches": n_oferta,
    }


def _make_ref_only_group(n_articles=4):
    return {
        "ref_deviz_cod": "REF02",
        "ref_header": None,
        "deviz_denumire": "Ref only deviz",
        "articles": [{"cod": f"R{i}", "is_component": False} for i in range(n_articles)],
        "neconformitati": [],
    }


def _make_oferta_only_group(n_articles=5):
    return {
        "oferta_deviz_cod": "OFF02",
        "oferta_header": None,
        "deviz_denumire": "Oferta only deviz",
        "articles": [{"cod": f"O{i}", "is_component": False} for i in range(n_articles)],
        "neconformitati": [],
    }


def _all_row_texts(table):
    texts = []
    for row in table.rows:
        row_text = " | ".join(c.text for c in row.cells)
        texts.append(row_text)
    return texts


def test_holistic_matched_group_has_totals_row():
    doc = Document()
    raport = {
        "matched_groups": [_make_matched_group(n_ref=3, n_oferta=2)],
        "ref_only_groups": [],
        "oferta_only_groups": [],
        "ungrouped": [],
        "unassigned_articles": [],
    }
    _generate_word_holistic(doc, raport, _make_holistic_comp())
    all_texts = _all_row_texts(doc.tables[0])
    assert any("TOTAL GRUP" in t for t in all_texts), "Missing TOTAL GRUP row for matched group"
    assert any("3" in t and "Referință" in t for t in all_texts), "Missing ref count"
    assert any("2" in t and "Ofertă" in t for t in all_texts), "Missing offer count"


def test_holistic_ref_only_group_has_totals_row_ref_side_only():
    doc = Document()
    raport = {
        "matched_groups": [],
        "ref_only_groups": [_make_ref_only_group(n_articles=4)],
        "oferta_only_groups": [],
        "ungrouped": [],
        "unassigned_articles": [],
    }
    _generate_word_holistic(doc, raport, _make_holistic_comp())
    all_texts = _all_row_texts(doc.tables[0])
    assert any("TOTAL GRUP" in t for t in all_texts)
    assert any("4" in t and "Referință" in t for t in all_texts)
    # Offer side must be empty
    total_rows = [t for t in all_texts if "TOTAL GRUP" in t]
    assert all("Ofertă" not in t for t in total_rows)


def test_holistic_oferta_only_group_has_totals_row_offer_side_only():
    doc = Document()
    raport = {
        "matched_groups": [],
        "ref_only_groups": [],
        "oferta_only_groups": [_make_oferta_only_group(n_articles=5)],
        "ungrouped": [],
        "unassigned_articles": [],
    }
    _generate_word_holistic(doc, raport, _make_holistic_comp())
    all_texts = _all_row_texts(doc.tables[0])
    assert any("TOTAL GRUP" in t for t in all_texts)
    assert any("5" in t and "Ofertă" in t for t in all_texts)
    total_rows = [t for t in all_texts if "TOTAL GRUP" in t]
    assert all("Referință" not in t for t in total_rows)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py -k "holistic" -v 2>&1 | tail -20
```

Expected: 3 FAILED — "Missing TOTAL GRUP row" assertions.

- [ ] **Step 3: Add call sites in `_generate_word_holistic`**

In `shared/report_word.py`, modify the three group loops (lines ~1070–1105).

**Matched groups loop** — replace the existing block:

```python
    # --- Grupuri matchate ---
    for mg in raport_holistic.get("matched_groups", []):
        _add_group_heading(table, "matched",
                           mg.get("ref_header"), mg.get("oferta_header"),
                           mg.get("ref_deviz_cod", ""), mg.get("oferta_deviz_cod", ""),
                           mg.get("deviz_denumire", ""))
        visible = _visible(mg.get("neconformitati", []))
        if visible:
            for nc in visible:
                row_nr += 1
                _add_neconf_row(table, row_nr, nc, deviz_map)
        else:
            info_row = table.add_row().cells
            info_row[0].merge(info_row[10])
            info_row[0].paragraphs[0].add_run("  ✓ Grup conform — fara neconformitati").italic = True
            _style_cell(info_row[0], 8)
        _add_group_totals_row(
            table,
            _count_main_articles(mg.get("ref_articles", [])),
            _count_main_articles(mg.get("oferta_articles", [])),
        )
```

**Ref-only groups loop** — replace:

```python
    # --- Grupuri doar in referinta (LIPSA) ---
    for rg in raport_holistic.get("ref_only_groups", []):
        _add_group_heading(table, "ref_only",
                           rg.get("ref_header"), None,
                           ref_deviz_cod=rg.get("ref_deviz_cod", ""),
                           deviz_denumire=rg.get("deviz_denumire", ""))
        for nc in rg.get("neconformitati", []):
            row_nr += 1
            _add_neconf_row(table, row_nr, nc, deviz_map)
        _add_group_totals_row(table, _count_main_articles(rg.get("articles", [])), None)
```

**Oferta-only groups loop** — replace:

```python
    # --- Grupuri doar in oferta (EXTRA) ---
    for og in raport_holistic.get("oferta_only_groups", []):
        _add_group_heading(table, "oferta_only",
                           None, og.get("oferta_header"),
                           oferta_deviz_cod=og.get("oferta_deviz_cod", ""),
                           deviz_denumire=og.get("deviz_denumire", ""))
        for nc in og.get("neconformitati", []):
            row_nr += 1
            _add_neconf_row(table, row_nr, nc, deviz_map)
        _add_group_totals_row(table, None, _count_main_articles(og.get("articles", [])))
```

- [ ] **Step 4: Run all tests to verify they pass**

```bash
.venv/bin/python -m pytest tests/shared/test_report_word_totals.py -v 2>&1 | tail -25
```

Expected: all 11 tests PASSED.

- [ ] **Step 5: Run the full test suite to check for regressions**

```bash
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py 2>&1 | tail -20
```

Expected: all tests pass (2 pre-existing failures in the ignored files are unrelated).

- [ ] **Step 6: Commit**

```bash
git add shared/report_word.py tests/shared/test_report_word_totals.py
git commit -m "feat(report): wire group totals row in holistic DOCX per-group"
```

---

### Task 4: Smoke test on a real client

Verify the change produces valid DOCX output with totals rows visible.

- [ ] **Step 1: Run pipeline for one client**

```bash
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log
```

Expected: completes without errors, generates `output_AO/Blocuri Racari/Raport_Oferta_1.docx`.

- [ ] **Step 2: Verify DOCX contains "TOTAL GRUP"**

```bash
python3 - <<'EOF'
from docx import Document
doc = Document("output_AO/Blocuri Racari/Raport_Oferta_1.docx")
hits = []
for table in doc.tables:
    for row in table.rows:
        text = " ".join(c.text for c in row.cells)
        if "TOTAL GRUP" in text:
            hits.append(text[:120])
print(f"Found {len(hits)} TOTAL GRUP rows")
for h in hits[:5]:
    print(" ", h)
EOF
```

Expected: `Found N TOTAL GRUP rows` where N > 0, with lines showing "Referință: X articole principale" and "Ofertă: Y articole principale".

- [ ] **Step 3: Commit outputs**

```bash
git add "output_AO/Blocuri Racari/"
git commit -m "chore(outputs): baseline Blocuri Racari with group totals rows"
```
