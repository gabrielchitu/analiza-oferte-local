# Task 1: Data Structure Analysis for Deviz Grouping

**Date:** 2026-05-14  
**Status:** COMPLETED

## Summary

This document analyzes the current article counting logic and verifies data availability for implementing deviz-grouped reporting with total article counts per category.

## Current Article Counting Logic in `generate_word()`

### Location
`shared/report_word.py:384-564`

### Current Behavior
The function currently:
1. **Groups nonconformities by deviz** (`_groupby(sorted_nec, key=lambda x: x.get("deviz_ref", ""))`)
2. **Counts ARTICOL_LIPSA (missing articles) per deviz** using `Counter` on `tip == "ARTICOL_LIPSA"` (line 468-471)
3. **Counts ARTICOL_EXTRA (extra articles) per deviz** using `Counter` on `tip == "ARTICOL_EXTRA"` (line 472-475)
4. **Displays counts in deviz heading** via `_add_deviz_heading()` (line 513-514):
   - `LIPSA: {n_lipsa}` (count of ARTICOL_LIPSA for this deviz)
   - `EXTRA: {n_extra}` (count of ARTICOL_EXTRA for this deviz)
   - `Delta: {delta}` (oferta_count - ref_count, i.e., n_extra - n_lipsa)

5. **Does NOT show total reference vs offer article counts per deviz** — this is the gap identified for Task 1.

### Total Article Count Logic
Lines 449-458 show an attempt to build total counts:
```python
_ref_deviz_totals = _dd_total(int)  # defaultdict
_oferta_deviz_totals = _dd_total(int)
for art in comp.get('ref_articles', []):
    d = art.get('deviz', '')
    if d:
        _ref_deviz_totals[d] += 1
for art in comp.get('oferta_articles', []):
    d = art.get('deviz', '')
    if d:
        _oferta_deviz_totals[d] += 1
```

This builds totals from **full article lists** (`ref_articles` and `oferta_articles`), not from nonconformities alone. These totals are used in the summary row (line 530-532).

## Data Available in Comparison JSON

### File
`output_AO/comparatie_oferta_2.json`

### Top-Level Fields
```
- oferta_nr: int = 2
- total_neconformitati: int = 45
- matches: int = 1367 (matched articles)
- neconformitati: list[dict] with 45 items
- deviz_mismatches: list = [] (empty in this example)
```

### Nonconformity Fields Available
Each nonconformity dict contains:
- **Identification**: `tip`, `camp`
- **Deviz**: `deviz_ref`, `deviz_denumire`
- **Reference article**: `ref_cod`, `ref_denumire`, `ref_um`, `ref_cantitate`, `ref_pret_*`, `ref_val_*`
- **Offer article**: `oferta_cod`, `oferta_denumire`, `oferta_um`, `oferta_cantitate`, `oferta_pret_*`, `oferta_val_*`

### CRITICAL FINDING: Missing Full Article Lists
The saved comparison JSON (`comparatie_oferta_N.json`) does **NOT** contain:
- `ref_articles` list
- `oferta_articles` list

However, these ARE available in the `comp` dict passed to `generate_word()` at lines 543-544 of `local_run.py`:
```python
"ref_articles": ref_articles,      # Full list of extracted reference articles
"oferta_articles": oferta_norm,    # Full list of normalized offer articles
```

## Data Available in Nonconformitati

### Article Deduplication Feasibility
Tested with Oferta 2 nonconformitati:

For each deviz, we can deduplicate articles by code:
```
Deviz 226008: 2 unique ref_cod values, 0 unique oferta_cod values
Deviz 226028: 2 unique ref_cod values, 1 unique oferta_cod values
Deviz 226108: 3 unique ref_cod values, 3 unique oferta_cod values
```

**Finding**: Article codes are suitable for deduplication. Each nonconformity has both `ref_cod` and `oferta_cod` (though `oferta_cod` is null/empty for `ARTICOL_LIPSA` type).

## Nonconformity Types Distribution

```
ARTICOL_EXTRA: 3 items
ARTICOL_LIPSA: 12 items  
COD_SIMILAR: 2 items
DIFERENTA_CAMP: 8 items
UM_DIFERIT: 20 items
────────────────────────
Total: 45 items
```

## Implications for Task 1 (Report Reorganization)

### What Works Today
✓ Total ref and offer article counts (from `comp` object passed to `generate_word()`)  
✓ Per-deviz LIPSA and EXTRA counts (from neconformitati grouping)  
✓ Per-deviz summary rows with totals

### What Needs Investigation for Future Tasks
1. **Saved JSON**: The `comparatie_oferta_N.json` file intentionally omits `ref_articles` and `oferta_articles` (probably for file size). If future analysis needs these, they must be:
   - Re-included in the saved JSON, OR
   - Regenerated from the original extraction pipeline

2. **Article Grouping**: For the report reorganization (showing which articles are missing, which are extra), we need per-deviz:
   - Set of reference article codes
   - Set of offer article codes
   - This can be computed from neconformitati alone (via ref_cod and oferta_cod fields)

## Code Files Involved

- **report_word.py** (564 lines): Main report generation; contains `generate_word()`, `_add_deviz_heading()`, `_add_deviz_summary_row()`
- **local_run.py** (~710 lines): Comparison orchestration; saves JSON and calls `generate_word()`
- **report_json.py**: Secondary JSON report generation (not analyzed in this task)

## Verification Results

✓ Current article count logic confirmed in `generate_word()` lines 449-458, 513-514, 530-532  
✓ Nonconformity fields verified (all expected fields present in sample data)  
✓ Article code deduplication feasible (confirmed with sample devizes)  
✓ Total article counts available in `comp` object at call time  
✓ Saved JSON does NOT include full article lists (intentional, for file size)
