# Subcomponent Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `--subcomponents {full,fields,summary}` CLI parameter that controls whether sub-article neconformitati (DIFERENTA_CAMP, UM_DIFERIT etc.) appear in the Word report.

**Architecture:** Filter applied inside `_generate_word_hierarchical()` in `shared/report_word.py`. Parameter propagates: CLI → `run_pipeline()` → `_run_analysis_pipeline()` → `compare_and_report()` → `generate_word()` → `_generate_word_hierarchical()`. JSON output (`comparatie_oferta_N.json`) is untouched.

**Tech Stack:** Python 3.11, python-docx, argparse

---

## Modes

| Mode | What's suppressed for is_component=True articles |
|------|--------------------------------------------------|
| `full` (default) | nothing — current behavior |
| `fields` | `DIFERENTA_CAMP`, `UM_DIFERIT` |
| `summary` | `DIFERENTA_CAMP`, `UM_DIFERIT`, `COD_SIMILAR`, `DESCRIERE_DIFERITA`, `EROARE_ARITMETICA` |

ARTICOL_LIPSA and ARTICOL_EXTRA are never filtered (they don't have `is_component=True`).

---

## Task 1: Write Failing Tests

**Files:**
- Modify: `tests/test_report_word.py`

- [ ] **Step 1: Add `_make_raport_with_subcomp` helper to `tests/test_report_word.py`**

```python
def _make_raport_with_subcomp(sub_nc_tip: str = 'DIFERENTA_CAMP'):
    """Build minimal raport_ierarhic with one sub-article having one neconformitate."""
    sub_nc = {
        'tip': sub_nc_tip,
        'camp': 'cantitate',
        'is_component': True,
        'ref_cod': '$6719485',
        'ref_denumire': 'teu D40mm',
        'ref_um': 'buc',
        'ref_cantitate': 10.0,
        'oferta_cod': '$6719485',
        'oferta_denumire': 'teu D40mm',
        'oferta_um': 'buc',
        'oferta_cantitate': 5.0,
        'deviz_ref': 'DVZ1',
        'deviz_denumire': 'INSTALATII',
        'nr_ordine_ref': None,
    }
    raport = {
        'devize': [{
            'cod_deviz': 'DVZ1',
            'denumire_deviz': 'INSTALATII',
            'sumar_deviz': {'lipsa': 0, 'matched': 1, 'neconformitati': 0, 'total': 1},
            'articole': [{
                'cod': 'SA04A01',
                'denumire': 'teava polipropilena',
                'nr_ordine': 1,
                'status_match': 'NECONFORMITATE',
                'cantitate': 1.0,
                'um': 'buc',
                'is_component': False,
                'neconformitati': [],
                'subarticole': [{
                    'cod': '$6719485',
                    'denumire': 'teu D40mm',
                    'nr_ordine': None,
                    'status_match': 'NECONFORMITATE',
                    'cantitate': 10.0,
                    'um': 'buc',
                    'cant_mostenita': False,
                    'is_component': True,
                    'neconformitati': [sub_nc],
                }],
            }],
        }],
    }
    return raport, sub_nc


def _load_doc_with_mode(subcomponent_mode: str, sub_nc_tip: str = 'DIFERENTA_CAMP'):
    """Build comp with raport_ierarhic and generate_word with given subcomponent_mode."""
    raport, sub_nc = _make_raport_with_subcomp(sub_nc_tip)
    comp = {
        'oferta_nr': 1,
        'source_file': 'test.json',
        'ofertant': 'Test SRL',
        'neconformitati': [sub_nc],
        'total_neconformitati': 1,
        'matches': 1,
        'ref_art_count': 1,
        'oferta_art_count': 1,
        'deviz_mismatches': [],
        'ref_articles': [],
        'oferta_articles': [],
        'raport_ierarhic': raport,
    }
    session = {'client_name': 'TEST', 'obiect_investitii': ''}
    docx_bytes = generate_word(
        session, comp,
        devize_extra=[], devize_lipsa=[],
        subcomponent_mode=subcomponent_mode,
    )
    return Document(io.BytesIO(docx_bytes))
```

- [ ] **Step 2: Add failing tests for all 3 modes**

```python
def _count_data_rows(doc):
    """Count non-header rows in first table (excludes header rows 0-2)."""
    if not doc.tables:
        return 0
    table = doc.tables[0]
    # First 3 rows are headers; deviz heading rows and total rows are additional
    # We count rows that have a non-empty col[2] (ref_cod column)
    count = 0
    for row in table.rows[3:]:
        text = row.cells[2].text.strip()
        if text and text not in ('', '▶'):
            count += 1
    return count


def test_subcomponent_mode_full_shows_diferenta_camp():
    """Mode=full: DIFERENTA_CAMP for sub-component IS shown."""
    doc = _load_doc_with_mode('full')
    assert _count_data_rows(doc) >= 1, "full mode: sub-component DIFERENTA_CAMP should appear"


def test_subcomponent_mode_fields_hides_diferenta_camp():
    """Mode=fields: DIFERENTA_CAMP for sub-component is suppressed."""
    doc = _load_doc_with_mode('fields')
    assert _count_data_rows(doc) == 0, "fields mode: DIFERENTA_CAMP sub-component should be hidden"


def test_subcomponent_mode_fields_hides_um_diferit():
    """Mode=fields: UM_DIFERIT for sub-component is suppressed."""
    doc = _load_doc_with_mode('fields', sub_nc_tip='UM_DIFERIT')
    assert _count_data_rows(doc) == 0, "fields mode: UM_DIFERIT sub-component should be hidden"


def test_subcomponent_mode_summary_hides_all_neconf():
    """Mode=summary: all neconformitati for sub-component are suppressed."""
    doc = _load_doc_with_mode('summary')
    assert _count_data_rows(doc) == 0, "summary mode: all sub-component neconf should be hidden"


def test_subcomponent_mode_full_shows_cod_similar():
    """Mode=full: COD_SIMILAR for sub-component IS shown."""
    doc = _load_doc_with_mode('full', sub_nc_tip='COD_SIMILAR')
    assert _count_data_rows(doc) >= 1, "full mode: COD_SIMILAR sub-component should appear"


def test_subcomponent_mode_fields_shows_cod_similar():
    """Mode=fields: COD_SIMILAR for sub-component is NOT suppressed (only DIFERENTA_CAMP/UM_DIFERIT)."""
    doc = _load_doc_with_mode('fields', sub_nc_tip='COD_SIMILAR')
    assert _count_data_rows(doc) >= 1, "fields mode: COD_SIMILAR should still appear"
```

- [ ] **Step 3: Run tests — verify they FAIL**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py::test_subcomponent_mode_full_shows_diferenta_camp tests/test_report_word.py::test_subcomponent_mode_fields_hides_diferenta_camp -v
```

Expected: `TypeError: generate_word() got an unexpected keyword argument 'subcomponent_mode'`

---

## Task 2: Implement Filter in `report_word.py`

**Files:**
- Modify: `shared/report_word.py`

- [ ] **Step 1: Add `SUPPRESSED_BY_MODE` constant near top of file (after existing constants)**

In `shared/report_word.py`, after the existing color constants (e.g., after `LILA_FILL = "C8A0DC"`):

```python
# Tipuri de neconformitate suprimate per mod subcomponente
SUPPRESSED_BY_MODE: dict[str, frozenset] = {
    "full":    frozenset(),
    "fields":  frozenset({"DIFERENTA_CAMP", "UM_DIFERIT"}),
    "summary": frozenset({"DIFERENTA_CAMP", "UM_DIFERIT", "COD_SIMILAR",
                           "DESCRIERE_DIFERITA", "EROARE_ARITMETICA"}),
}
```

- [ ] **Step 2: Add `subcomponent_mode` param to `_generate_word_hierarchical`**

Change signature at line 672:
```python
# BEFORE:
def _generate_word_hierarchical(doc, raport: dict, comp: dict,
                                deviz_mismatches_list: list, devize_extra: list,
                                devize_lipsa: list, audit_data: dict) -> None:

# AFTER:
def _generate_word_hierarchical(doc, raport: dict, comp: dict,
                                deviz_mismatches_list: list, devize_extra: list,
                                devize_lipsa: list, audit_data: dict,
                                subcomponent_mode: str = "full") -> None:
```

- [ ] **Step 3: Add filter logic in the article loop in `_generate_word_hierarchical`**

Replace the article loop (lines ~712–730):
```python
# BEFORE:
        for art in dv.get('articole', []):
            principal_ncs = art.get('neconformitati', [])
            subs_with_ncs = [s for s in art.get('subarticole', []) if s.get('neconformitati')]

            if not principal_ncs and not subs_with_ncs:
                continue

            if not principal_ncs and subs_with_ncs:
                _add_principal_context_row(table, art, dv_cod, dv_den)
            else:
                for nc in principal_ncs:
                    row_nr += 1
                    _add_neconf_row(table, row_nr, nc, deviz_map, use_ref_ordine=True)

            for sub in subs_with_ncs:
                for nc in sub.get('neconformitati', []):
                    row_nr += 1
                    _add_neconf_row(table, row_nr, nc, deviz_map, use_ref_ordine=True)

# AFTER:
        suppressed = SUPPRESSED_BY_MODE.get(subcomponent_mode, frozenset())

        for art in dv.get('articole', []):
            principal_ncs = art.get('neconformitati', [])

            def _visible(ncs: list) -> list:
                if not suppressed:
                    return ncs
                return [nc for nc in ncs if nc.get('tip') not in suppressed]

            subs_with_ncs = [
                s for s in art.get('subarticole', [])
                if _visible(s.get('neconformitati', []))
            ]

            if not principal_ncs and not subs_with_ncs:
                continue

            if not principal_ncs and subs_with_ncs:
                _add_principal_context_row(table, art, dv_cod, dv_den)
            else:
                for nc in principal_ncs:
                    row_nr += 1
                    _add_neconf_row(table, row_nr, nc, deviz_map, use_ref_ordine=True)

            for sub in subs_with_ncs:
                for nc in _visible(sub.get('neconformitati', [])):
                    row_nr += 1
                    _add_neconf_row(table, row_nr, nc, deviz_map, use_ref_ordine=True)
```

- [ ] **Step 4: Add `subcomponent_mode` param to `generate_word` and pass it through**

Change `generate_word` signature (line 895):
```python
# BEFORE:
def generate_word(
    session: dict,
    comp: dict,
    comparison_mode: str = "cu_pret",
    audit_data: dict = None,
    devize_extra: list = None,
    devize_lipsa: list = None,
) -> bytes:

# AFTER:
def generate_word(
    session: dict,
    comp: dict,
    comparison_mode: str = "cu_pret",
    audit_data: dict = None,
    devize_extra: list = None,
    devize_lipsa: list = None,
    subcomponent_mode: str = "full",
) -> bytes:
```

Change the `_generate_word_hierarchical` call (line ~956):
```python
# BEFORE:
        _generate_word_hierarchical(doc, raport_ierarhic, comp,
                                    deviz_mismatches_list, devize_extra,
                                    devize_lipsa, audit_data)

# AFTER:
        _generate_word_hierarchical(doc, raport_ierarhic, comp,
                                    deviz_mismatches_list, devize_extra,
                                    devize_lipsa, audit_data,
                                    subcomponent_mode=subcomponent_mode)
```

- [ ] **Step 5: Run tests — verify they PASS**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py -v -k "subcomponent_mode"
```

Expected output:
```
test_subcomponent_mode_full_shows_diferenta_camp PASSED
test_subcomponent_mode_fields_hides_diferenta_camp PASSED
test_subcomponent_mode_fields_hides_um_diferit PASSED
test_subcomponent_mode_summary_hides_all_neconf PASSED
test_subcomponent_mode_full_shows_cod_similar PASSED
test_subcomponent_mode_fields_shows_cod_similar PASSED
```

- [ ] **Step 6: Run full test suite (excluding pre-existing failures)**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```

Expected: all tests pass (no new failures)

- [ ] **Step 7: Commit**

```bash
git add shared/report_word.py tests/test_report_word.py
git commit -m "feat(report): subcomponent_mode filter in generate_word (full/fields/summary)"
```

---

## Task 3: Propagate Through `local_run.py`

**Files:**
- Modify: `local_run.py` (lines 69, 99, 291, 810, 1059)

- [ ] **Step 1: Add `subcomponent_mode` to `run_pipeline`**

```python
# BEFORE (line 69):
def run_pipeline(client_config: ClientConfig) -> None:

# AFTER:
def run_pipeline(client_config: ClientConfig, subcomponent_mode: str = "full") -> None:
```

Change the call to `_run_analysis_pipeline` inside `run_pipeline` (line 96):
```python
# BEFORE:
    _run_analysis_pipeline(client_config, referinta_data, oferta_data_list)

# AFTER:
    _run_analysis_pipeline(client_config, referinta_data, oferta_data_list,
                           subcomponent_mode=subcomponent_mode)
```

- [ ] **Step 2: Add `subcomponent_mode` to `_run_analysis_pipeline`**

```python
# BEFORE (line 99):
def _run_analysis_pipeline(client_config: ClientConfig, ref_di_json: dict, oferta_di_list: list) -> None:

# AFTER:
def _run_analysis_pipeline(client_config: ClientConfig, ref_di_json: dict, oferta_di_list: list,
                            subcomponent_mode: str = "full") -> None:
```

Change the call to `compare_and_report` inside `_run_analysis_pipeline` (line 291):
```python
# BEFORE:
        _, comp = compare_and_report(
            ref_articles, oferta_articles, oferta_nr, oferta_path, client, model,
            ofertant_name=ofertant_name, ref_di_json=ref_di_raw,
            checkpoint_data=oferta_checkpoint_data, client_config=client_config
        )

# AFTER:
        _, comp = compare_and_report(
            ref_articles, oferta_articles, oferta_nr, oferta_path, client, model,
            ofertant_name=ofertant_name, ref_di_json=ref_di_raw,
            checkpoint_data=oferta_checkpoint_data, client_config=client_config,
            subcomponent_mode=subcomponent_mode,
        )
```

- [ ] **Step 3: Add `subcomponent_mode` to `compare_and_report`**

```python
# BEFORE (line 810):
def compare_and_report(
    ref_articles: list,
    oferta_articles: list,
    oferta_nr: int,
    oferta_path: Path,
    client,
    model: str,
    include_prices: bool = False,
    ofertant_name: str = "",
    ref_di_json: dict = None,
    checkpoint_data: dict = None,
    client_config: ClientConfig = None,
):

# AFTER:
def compare_and_report(
    ref_articles: list,
    oferta_articles: list,
    oferta_nr: int,
    oferta_path: Path,
    client,
    model: str,
    include_prices: bool = False,
    ofertant_name: str = "",
    ref_di_json: dict = None,
    checkpoint_data: dict = None,
    client_config: ClientConfig = None,
    subcomponent_mode: str = "full",
):
```

Change the `generate_word` call inside `compare_and_report` (line ~1059):
```python
# BEFORE:
        docx_bytes = generate_word(
            session, comp,
            comparison_mode=comparison_mode,
            devize_extra=_devize_extra,
            devize_lipsa=_devize_lipsa,
        )

# AFTER:
        docx_bytes = generate_word(
            session, comp,
            comparison_mode=comparison_mode,
            devize_extra=_devize_extra,
            devize_lipsa=_devize_lipsa,
            subcomponent_mode=subcomponent_mode,
        )
```

- [ ] **Step 4: Run existing tests to verify no regression**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add local_run.py
git commit -m "feat: propagate subcomponent_mode through run_pipeline → compare_and_report"
```

---

## Task 4: Add CLI Parameter to `multi_client_run.py`

**Files:**
- Modify: `multi_client_run.py` (lines 68–78, 131)

- [ ] **Step 1: Add `--subcomponents` argument to `parse_args()`**

```python
# BEFORE (lines 68–78):
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-client offer analysis pipeline"
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Client name (skip menu if provided)",
    )
    return parser.parse_args()

# AFTER:
def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-client offer analysis pipeline"
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Client name (skip menu if provided)",
    )
    parser.add_argument(
        "--subcomponents",
        choices=["full", "fields", "summary"],
        default="full",
        help=(
            "Sub-component neconformitate display mode in Word report: "
            "full=all (default), fields=hide DIFERENTA_CAMP+UM_DIFERIT, "
            "summary=hide all except LIPSA/EXTRA"
        ),
    )
    return parser.parse_args()
```

- [ ] **Step 2: Pass `subcomponent_mode` to `run_pipeline` in `main()`**

```python
# BEFORE (line 131):
        run_pipeline(client_config)

# AFTER:
        run_pipeline(client_config, subcomponent_mode=args.subcomponents)
```

- [ ] **Step 3: Smoke test — verify CLI help shows new flag**

```bash
.venv/bin/python3 multi_client_run.py --help
```

Expected output contains:
```
  --subcomponents {full,fields,summary}
                        Sub-component neconformitate display mode in Word report
```

- [ ] **Step 4: Smoke test — run pipeline with `--subcomponents fields` for SD**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" --subcomponents fields
```

Expected: pipeline runs, DOCX generated. Check `output_AO/Scoala Dragomiresti/Raport_Oferta_1.docx` — sub-article DIFERENTA_CAMP rows absent.

- [ ] **Step 5: Commit**

```bash
git add multi_client_run.py
git commit -m "feat(cli): --subcomponents {full,fields,summary} parameter for Word report"
```

---

## Self-Review

**Spec coverage:**
- ✅ 3 modes (full/fields/summary) — Tasks 1–2
- ✅ Filter only Word report, JSON untouched — filter in generate_word, not compare_and_report logic
- ✅ CLI param in multi_client_run.py — Task 4
- ✅ Backward compatible (default="full") — all params have defaults
- ✅ local_run.py legacy entry point unchanged (no --subcomponents there, defaults to full) — Task 3 only touches internal functions

**Placeholder scan:** No TBD/TODO. All code complete.

**Type consistency:**
- `subcomponent_mode: str = "full"` — consistent across all signatures
- `SUPPRESSED_BY_MODE` — referenced by exact name in both constant definition and filter logic
- `_visible(ncs)` — defined and called within same loop scope
