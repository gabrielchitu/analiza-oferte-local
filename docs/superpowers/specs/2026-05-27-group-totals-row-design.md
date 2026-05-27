# Group Totals Row — Design Spec

> **For agentic workers:** Use `superpowers:writing-plans` to turn this spec into an implementation plan.

**Goal:** Add a totals row after each group in the holistic DOCX report, showing main-article counts mirrored (ref left, offer right), to aid manual reconciliation.

---

## Context

The holistic DOCX report (`_generate_word_holistic` in `shared/report_word.py`) renders three group types:

- **matched_groups** — ref group ↔ offer group paired; may have 0 or more nonconformities
- **ref_only_groups** — group exists in reference, absent from offer
- **oferta_only_groups** — group exists in offer, absent from reference

Currently each group shows a heading row + nonconformity rows (or "✓ Grup conform" if clean). There is no per-group article count summary. The flat report (`_generate_word_flat`) has `_add_deviz_summary_row` but it is not used in holistic mode.

---

## What to Build

### New function: `_add_group_totals_row`

```python
def _add_group_totals_row(table, ref_count: int | None, oferta_count: int | None) -> None:
```

Appends one row to `table` with the following layout (11-column table):

| Cols 0-1 (merged) | Cols 2-5 (merged) | Cols 6-9 (merged) | Col 10 |
|---|---|---|---|
| **TOTAL GRUP** | `Referință: N articole` *(or empty)* | `Ofertă: M articole` *(or empty)* | *(empty)* |

- Shading: `GRAY_FILL` on all cells
- Font: bold, 9pt
- `ref_count=None` → cols 2-5 left empty (used for oferta_only groups)
- `oferta_count=None` → cols 6-9 left empty (used for ref_only groups)

### Helper: `_count_main_articles`

```python
def _count_main_articles(articles: list) -> int:
    return sum(1 for a in articles if not a.get("is_component", False))
```

Counts non-component articles only ("articole principale"). Components (`is_component=True`) are excluded.

---

## Where to Call It

In `_generate_word_holistic` (`shared/report_word.py`), after rendering the nonconformity rows (or the "✓ Grup conform" row) for each group:

### Matched groups loop

```python
for mg in raport_holistic.get("matched_groups", []):
    # ... existing heading + nonconformity rows ...
    ref_count = _count_main_articles(mg.get("ref_articles", []))
    oferta_count = _count_main_articles(mg.get("oferta_articles", []))
    _add_group_totals_row(table, ref_count, oferta_count)
```

### Ref-only groups loop

```python
for rg in raport_holistic.get("ref_only_groups", []):
    # ... existing heading + nonconformity rows ...
    ref_count = _count_main_articles(rg.get("articles", []))
    _add_group_totals_row(table, ref_count, None)
```

### Oferta-only groups loop

```python
for og in raport_holistic.get("oferta_only_groups", []):
    # ... existing heading + nonconformity rows ...
    oferta_count = _count_main_articles(og.get("articles", []))
    _add_group_totals_row(table, None, oferta_count)
```

---

## Data Sources

All article lists are already present in the group dicts produced by `group_comparator.py`:

| Group type | Ref articles key | Offer articles key |
|---|---|---|
| matched_groups | `ref_articles` | `oferta_articles` |
| ref_only_groups | `articles` | *(none)* |
| oferta_only_groups | *(none)* | `articles` |

No changes to `group_comparator.py` or any data layer.

---

## Scope

- **File changed:** `shared/report_word.py` only
- **New functions:** `_add_group_totals_row`, `_count_main_articles`
- **Modified function:** `_generate_word_holistic` (3 call-site additions)
- **No data-layer changes**
- **No changes to flat or hierarchical report paths**

---

## Out of Scope

- Flat report (`_generate_word_flat`) already has its own `_add_deviz_summary_row` — leave untouched
- Hierarchical report (`_generate_word_hierarchical`) — leave untouched
- Displaying nonconformity count in totals row — not requested
