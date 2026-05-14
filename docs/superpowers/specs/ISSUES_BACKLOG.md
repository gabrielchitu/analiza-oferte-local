# Known Issues Backlog

**Date:** 2026-05-14  
**Status:** Documented for future resolution

---

## Issue 1: Duplicate Article Codes (NS001)

### Description

When an article code appears multiple times in the reference with different quantities, the matching algorithm treats each instance as an independent article rather than aggregating them.

### Current Behavior

**Reference (Deviz 9.1):**
- NS001, UM=buc, Quantity=2.0
- NS001, UM=buc, Quantity=9.0

**Offer 1 & 2 (Deviz 9.1):**
- NS001, UM=buc, Quantity=2.0

**Current Result:**
- NS001 (cant 2) ↔ NS001 (cant 2) = **MATCH** ✓
- NS001 (cant 9) ↔ (no match) = **ARTICOL_LIPSA** ✓ (technically correct)

### Expected Behavior (TBD)

Two possible interpretations:

**Option A - Aggregate matching:**
- Treat duplicate codes as a group: Ref has 2 instances (total 11 buc), Offer has 1 instance (2 buc)
- Report as DIFERENTA_CAMP with quantities 11 vs 2

**Option B - Smart matching:**
- Attempt to pair duplicates intelligently: Match cant 2 with cant 2, report cant 9 as ARTICOL_LIPSA separately

**Option C - Current behavior is correct:**
- Each row is an independent article; duplicates with different quantities should be treated separately

### Root Cause

The matching algorithm in `AgentComparator_local.py::match_global()` processes each article instance independently, without aggregating duplicate codes before matching.

### Files Involved

- `AgentComparator_local.py:match_global()` — multi-layer matching algorithm
- `shared/comparator.py` — per-article comparison logic

---

## Issue 2: W3H18C1 Not Extracted from Tables

### Description

Article code W3H18C1 exists in the offer PDF at position 93, but is not extracted because it appears only in PDF tables, not in line-based text.

### Current Behavior

**Extraction Status:**
- W3H18C1 appears in offer PDF tables (structured table format)
- Not extracted by line-based extractor
- Table extraction is **disabled** (metadata detection fails)
- Result: W3H18C1 appears as **ARTICOL_LIPSA** (missing from offer)

### Root Cause Analysis

1. **Table extraction logic** (`shared/table_extractor.py::extract_articles_from_tables_smart()`):
   - Requires preceding "STADIUL FIZIC:" metadata tables to link deviz codes
   - If metadata tables not found → all 189 F3 data tables are skipped

2. **Why it's disabled:**
   - Enabling table extraction without fixing metadata detection would create **221+ duplicate entries**
   - Codes like CE13A01 appear multiple times with different UMs and quantities
   - Risk: Data corruption from conflicting entries

3. **Why not a quick fix:**
   - Safe fix requires careful refactoring of deduplication logic
   - Would need to merge table-extracted articles with line-based articles without creating conflicts

### Comparison

**Similar code that DOES extract correctly:**
- RPCI22C+ ✓ extracts (appears in line-based text, not just tables)

**Unlike W3H18C1:**
- W3H18C1 appears ONLY in tables, never in line-based text extraction

### Files Involved

- `shared/table_extractor.py` — table extraction and metadata linking
- `shared/f3_page_classifier.py` — PDF structure detection
- `local_run.py::extract_document()` — extraction orchestration

### Current Decision

**Accept W3H18C1 as ARTICOL_LIPSA** (safe state) until metadata detection can be reliably fixed.

---

## Recommended Next Steps

### For Issue #1 (NS001):
1. Clarify expected behavior with stakeholders (aggregate vs. independent matching)
2. If aggregate matching preferred: refactor `match_global()` to group by code pre-matching
3. Add regression tests for duplicate-code scenarios

### For Issue #2 (W3H18C1):
1. Redesign table extraction metadata detection to reliably find STADIUL FIZIC tables
2. Implement safe merge of table-extracted articles with line-based articles
3. Add comprehensive deduplication tests

---

## Session References

- **v4 Release Session (2026-05-14):** Initial identification of both issues
- **Memory:** `/Users/gabrielchitu/.claude/projects/-Users-gabrielchitu-analiza-oferte-local/memory/v4-session-summary.md`
