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

## Issue 3: 5858393 Not Extracted from Deviz 226218

### Description

Article code 5858393 exists in the reference PDF (deviz 226218) but is not being extracted. The article is visible in the PDF but missing from the final extraction output.

### Current Behavior

**PDF Content (Page 30, Lines 44-47):**
```
031 5858393         (NR_CRT + numeric code)
L                   (UM: liter)
317.700             (price/quantity)
Solutie de protectie a lemnului tip  (denomination: wood protection solution)
```

**Extraction Status:**
- NR_NUMERIC_INLINE_RE pattern matches "031 5858393" correctly
- Article is extracted as **hollow**:
  - Code: $5858393 ✓
  - UM: (empty) ✗
  - Quantity: 0.0 ✗
  - Denomination: (empty) ✗
- Hollow article is filtered out before final output
- Result: 5858393 **NOT present** in reference.json

### Root Cause Analysis

1. **Pattern Matching:** Works correctly (NR_NUMERIC_INLINE_RE matches)
2. **State Transition:** Article enters READING state after code extraction
3. **UM Detection Failure:** Line "L" is not being recognized as UM despite:
   - "L" is in UM_KNOWN list
   - _is_valid_um("L") returns True
   - Code path at line 928-933 should trigger
4. **Result:** Article finalized without UM/quantity/denomination data, then filtered

### Example Code Pattern

Similar numeric codes that **DO** extract correctly:
- $2100833, $2100843, $2100853, $2101131, etc.

### Files Involved

- `shared/f3_regex_parser.py::extract_articles_regex()` — UM detection (lines 928-933)
- `shared/f3_regex_parser.py::_is_valid_um()` — UM validation logic
- `local_run.py::extract_document()` — article filtering/finalization

### Current Decision

**Documented for investigation** — Likely state machine or condition issue preventing UM capture for this specific format. Similar to the now-fixed bare-integer quantity issue (Issue from 2026-05-14 session).

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

### For Issue #3 (5858393):
1. Add detailed logging to UM detection code path (line 928-933)
2. Trace state machine transitions for this specific article format
3. Compare with similar working codes ($2100843, etc.) to identify divergence
4. May be related to bare-integer quantity parsing fix — review condition logic

---

## Session References

- **v4 Release Session (2026-05-14):** Initial identification of issues #1 and #2
- **Session 2026-05-14 (continued):** 
  - Fixed: Truncation deduplication ($0156 vs $3270156, etc.)
  - Identified: Issue #3 (5858393 extraction failure)
- **Memory:** `/Users/gabrielchitu/.claude/projects/-Users-gabrielchitu-analiza-oferte-local/memory/v4-session-summary.md`
