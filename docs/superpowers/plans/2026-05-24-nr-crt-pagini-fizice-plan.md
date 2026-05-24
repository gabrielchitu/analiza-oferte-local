# Nr. crt. cu Pagini Fizice + Fix Summary — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Coloana Nr. crt. din raport afiseaza pagina fizica PDF si nr de ordine in grup (ref/oferta); fix summary line "Matched: 0".

**Architecture:**
1. `_enrich()` in `AgentComparator_local.py` — adauga `ref_source_pages` si `oferta_source_pages` pe fiecare neconf
2. `_add_neconf_row()` in `shared/report_word.py` — afiseaza `pag.X/pag.Y\n(nr_ref/nr_of)` in coloana 0
3. `generate_word()` summary line — citeste din `raport_holistic['sumar']` cand disponibil

**Format nou coloana Nr. crt.:**
```
pag.12/28
(3/7)
```
- `pag.12` = prima pagina fizica PDF din source_pages ref
- `28` = prima pagina fizica PDF din source_pages oferta
- `(3/7)` = nr_ordine_ref / nr_ordine_oferta in cadrul grupului
- LIPSA (fara oferta): `pag.12/-` si `(3/-)`
- EXTRA (fara ref): `pag.-/28` si `(-/7)`

**Branch:** `refactor/v10`

**Context cod:**
- `AgentComparator_local.py:81` — `_enrich(neconf, ref_art, oferta_art, deviz_cod_ref, deviz_den)` — adauga campuri pe neconf
- `AgentComparator_local.py:101` — `nr_ordine_ref` deja setat din `ref_art.get("nr_ordine")`
- `AgentComparator_local.py:121` — `nr_ordine_oferta` deja setat din `oferta_art.get("nr_ordine")`
- `shared/report_word.py:403` — `_add_neconf_row(table, row_nr, neconf, deviz_map, use_ref_ordine)` — linia 418 face `nr_text += f"\n({nr_ordine_ref})"` — DE INLOCUIT
- `shared/report_word.py:972` — `generate_word(session, comp, ...)` — summary line la ~1023-1029 citeste `comp.get("matches", 0)` → 0 incorect in holistic mode

---

## Task 1: `_enrich()` — adauga source_pages pe neconf

**Files:**
- Modify: `AgentComparator_local.py:81-124`

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_matching.py
def test_enrich_sets_source_pages():
    """_enrich() trebuie sa copieze source_pages de pe articole."""
    from AgentComparator_local import _enrich

    ref_art = {"cod": "EA02A1", "deviz": "D1", "nr_ordine": 3,
               "source_pages": [12, 13], "denumire": "test", "um": "mp",
               "cantitate": 1.0, "is_component": False, "parent_cod": ""}
    oferta_art = {"cod": "EA02A1", "deviz": "D1", "nr_ordine": 7,
                  "source_pages": [28], "denumire": "test", "um": "mp",
                  "cantitate": 1.0}

    nc = {"tip": "DIFERENTA_CAMP"}
    _enrich(nc, ref_art, oferta_art, "D1", "Test Deviz")

    assert nc["ref_source_pages"] == [12, 13]
    assert nc["oferta_source_pages"] == [28]
    assert nc["nr_ordine_ref"] == 3
    assert nc["nr_ordine_oferta"] == 7


def test_enrich_lipsa_no_oferta_source_pages():
    """LIPSA — oferta_art e {} → oferta_source_pages = []."""
    from AgentComparator_local import _enrich

    ref_art = {"cod": "EA02A1", "deviz": "D1", "nr_ordine": 5,
               "source_pages": [12], "denumire": "t", "um": "mp",
               "cantitate": 1.0, "is_component": False, "parent_cod": ""}

    nc = {"tip": "ARTICOL_LIPSA"}
    _enrich(nc, ref_art, {}, "D1", "Test")

    assert nc["ref_source_pages"] == [12]
    assert nc.get("oferta_source_pages", []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_matching.py::test_enrich_sets_source_pages tests/test_matching.py::test_enrich_lipsa_no_oferta_source_pages -v 2>&1 | tail -5
```
Expected: FAIL — `KeyError: 'ref_source_pages'`

- [ ] **Step 3: Modify `_enrich()` in `AgentComparator_local.py`**

In `_enrich()` at line 84, after the `neconf.update({...})` block (after line 105), add `ref_source_pages`:

```python
    neconf.update({
        ...existing fields...,
        "nr_ordine_ref": ref_art.get("nr_ordine"),
        "parent_cod_ref": ref_art.get("parent_cod"),
        "parent_nr_ordine_ref": ref_art.get("parent_nr_ordine"),
        "display_parent_cod": ref_art.get("display_parent_cod"),
        "cant_mostenita": ref_art.get("cant_mostenita", False),
        "ref_source_pages": ref_art.get("source_pages", []),  # NOU
    })
    if oferta_art:
        neconf.update({
            ...existing fields...,
            "nr_ordine_oferta": oferta_art.get("nr_ordine"),
            "oferta_display_parent_cod": oferta_art.get("display_parent_cod"),
            "oferta_source_pages": oferta_art.get("source_pages", []),  # NOU
        })
```

**IMPORTANT:** Do NOT rewrite the whole function. Only ADD the two new keys:
- `"ref_source_pages": ref_art.get("source_pages", [])` in the first `neconf.update()`
- `"oferta_source_pages": oferta_art.get("source_pages", [])` in the `if oferta_art:` block

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_matching.py -v 2>&1 | tail -10
```
Expected: all PASS including 2 new tests.

- [ ] **Step 5: Commit**

```bash
git add AgentComparator_local.py tests/test_matching.py
git commit -m "feat(comparator): enrich neconf with ref/oferta source_pages"
```

---

## Task 2: `_add_neconf_row()` — display pag.X/Y + (nr_ref/nr_of)

**Files:**
- Modify: `shared/report_word.py:403-419`

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_report_word.py
def test_neconf_row_shows_page_numbers():
    """_add_neconf_row afiseaza pag.ref/oferta si nr_ordine in Nr. crt. coloana."""
    from docx import Document
    from shared.report_word import _add_neconf_row

    doc = Document()
    table = doc.add_table(rows=0, cols=11)
    nc = {
        "tip": "DIFERENTA_CAMP", "camp": "cantitate",
        "ref_cod": "EA02A1", "ref_denumire": "test", "ref_um": "mp",
        "ref_cantitate": 10.0, "oferta_cantitate": 9.0,
        "oferta_cod": "EA02A1", "oferta_denumire": "test", "oferta_um": "mp",
        "deviz_ref": "D1", "deviz_denumire": "Test",
        "nr_ordine_ref": 3, "nr_ordine_oferta": 7,
        "ref_source_pages": [12, 13], "oferta_source_pages": [28],
        "is_component": False,
    }
    _add_neconf_row(table, 1, nc, {})
    cell_text = table.rows[0].cells[0].text

    assert "12" in cell_text   # ref page
    assert "28" in cell_text   # oferta page
    assert "3" in cell_text    # nr_ordine_ref
    assert "7" in cell_text    # nr_ordine_oferta
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py::test_neconf_row_shows_page_numbers -v 2>&1 | tail -5
```
Expected: FAIL — cell_text doesn't have "28" or both page numbers yet.

- [ ] **Step 3: Modify `_add_neconf_row()` in `shared/report_word.py:403-419`**

Read lines 403-419 first, then replace the nr_text block:

Current code (lines 412-419):
```python
    nr_ordine_ref = neconf.get("nr_ordine_ref")
    if use_ref_ordine and nr_ordine_ref is not None:
        nr_text = str(nr_ordine_ref)
    else:
        nr_text = str(row_nr)
        if nr_ordine_ref is not None:
            nr_text += f"\n({nr_ordine_ref})"
    row[0].paragraphs[0].add_run(nr_text)
```

Replace with:
```python
    nr_ordine_ref = neconf.get("nr_ordine_ref")
    nr_ordine_of = neconf.get("nr_ordine_oferta")
    ref_pages = neconf.get("ref_source_pages") or []
    of_pages = neconf.get("oferta_source_pages") or []

    ref_pag = str(ref_pages[0]) if ref_pages else "-"
    of_pag = str(of_pages[0]) if of_pages else "-"

    # Linia 1: pagini fizice PDF (ref/oferta)
    pag_text = f"pag.{ref_pag}/{of_pag}"

    # Linia 2: nr ordine in grup (ref/oferta)
    nr_ref_str = str(nr_ordine_ref) if nr_ordine_ref is not None else "-"
    nr_of_str = str(nr_ordine_of) if nr_ordine_of is not None else "-"
    ord_text = f"({nr_ref_str}/{nr_of_str})"

    nr_text = f"{pag_text}\n{ord_text}"
    row[0].paragraphs[0].add_run(nr_text)
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py -v 2>&1 | tail -15
```
Expected: toate PASS inclusiv noul test.

- [ ] **Step 5: Commit**

```bash
git add shared/report_word.py tests/test_report_word.py
git commit -m "feat(report): Nr. crt. shows pag.ref/oferta + (nr_ordine_ref/of)"
```

---

## Task 3: Fix summary line in `generate_word()`

**Files:**
- Modify: `shared/report_word.py:1018-1029` (summary paragraph block)

**Context:** La linia ~1021-1029 in `generate_word()`:
```python
    total_matched    = comp.get("matches", 0)
    total_neconf     = comp.get("total_neconformitati", 0)
    p_sumar = doc.add_paragraph()
    p_sumar.add_run(
        f"Articole referință: {ref_art_count}  │  "
        f"Articole ofertă: {oferta_art_count}  │  "
        f"Matched: {total_matched}  │  "
        f"Neconformități: {total_neconf}"
    ).bold = True
```

In holistic mode, `comp.get("matches", 0)` returneaza 0 (matches e numarul din match_global la nivel de deviz, nu total holistic). In holistic mode, totalul corect e in `raport_holistic['sumar']['total_matched_articles']`.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_report_word.py
def test_generate_word_holistic_summary_correct():
    """Summary line in holistic mode arata matched_articles din holistic sumar."""
    from shared.report_word import generate_word
    from shared.group_comparator import HolisticComparison
    from shared.report_builder import build_raport_holistic
    from docx import Document
    import io

    hc = HolisticComparison(
        matched_groups=[{
            "ref_deviz_cod": "D1", "oferta_deviz_cod": "D1",
            "ref_header": None, "oferta_header": None,
            "ref_articles": [], "oferta_articles": [],
            "neconformitati": [], "matches": list(range(42)),  # 42 matches
        }],
        ref_only_groups=[], oferta_only_groups=[], ungrouped=[],
    )
    raport_holistic = build_raport_holistic(hc)
    # Verify sumar has correct count
    assert raport_holistic["sumar"]["total_matched_articles"] == 42

    comp = {
        "neconformitati": [], "oferta_nr": 1, "source_file": "test",
        "deviz_mismatches": [], "matches": 0,  # old field = 0 (wrong in holistic)
        "total_neconformitati": 5,
        "ref_art_count": 100, "oferta_art_count": 95,
        "raport_holistic": raport_holistic,
    }
    session = {"client_name": "Test", "obiect_investitii": ""}

    doc_bytes = generate_word(session, comp)
    doc = Document(io.BytesIO(doc_bytes))

    # Find the summary paragraph
    summary_text = ""
    for para in doc.paragraphs:
        if "Matched:" in para.text:
            summary_text = para.text
            break

    assert "42" in summary_text, f"Expected 42 in summary, got: {summary_text}"
    assert "Matched: 0" not in summary_text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py::test_generate_word_holistic_summary_correct -v 2>&1 | tail -5
```
Expected: FAIL — "42" not in summary_text

- [ ] **Step 3: Fix summary block in `generate_word()` in `shared/report_word.py`**

Find the summary paragraph block at ~line 1019. Replace:

```python
    total_matched    = comp.get("matches", 0)
    total_neconf     = comp.get("total_neconformitati", 0)
    p_sumar = doc.add_paragraph()
    p_sumar.add_run(
        f"Articole referință: {ref_art_count}  │  "
        f"Articole ofertă: {oferta_art_count}  │  "
        f"Matched: {total_matched}  │  "
        f"Neconformități: {total_neconf}"
    ).bold = True
```

With:
```python
    # In holistic mode, get correct matched count from holistic sumar
    raport_holistic_comp = comp.get("raport_holistic") or {}
    holistic_sumar = raport_holistic_comp.get("sumar", {})
    if holistic_sumar:
        total_matched = holistic_sumar.get("total_matched_articles", 0)
        total_neconf = sum(holistic_sumar.get("neconformitati_by_tip", {}).values())
    else:
        total_matched = comp.get("matches", 0)
        total_neconf = comp.get("total_neconformitati", 0)

    p_sumar = doc.add_paragraph()
    p_sumar.add_run(
        f"Articole referință: {ref_art_count}  │  "
        f"Articole ofertă: {oferta_art_count}  │  "
        f"Matched: {total_matched}  │  "
        f"Neconformități: {total_neconf}"
    ).bold = True
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py -v 2>&1 | tail -15
```
Expected: toate PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/report_word.py tests/test_report_word.py
git commit -m "fix(report): summary line reads matched_articles from holistic sumar"
```

---

## Task 4: Regression + Integration Check

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py \
  2>&1 | tail -8
```
Expected: 193+ passed, aceleasi 4 pre-existing failures.

- [ ] **Step 2: Run SD pipeline si verifica**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | grep "\[HOLISTIC\]\|\[COMP\] matched" | head -5
```
Expected: matched=904, holistic 22 grupuri.

- [ ] **Step 3: Commit final dacă e nevoie**

```bash
git log --oneline -5
```
