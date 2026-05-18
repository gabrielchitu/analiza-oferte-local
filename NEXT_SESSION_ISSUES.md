# Next Session - Outstanding Issues & Work Items

**Current Status** (2026-05-18):
- OFERTA 1: 10 nonconformities ✅ (excellent)
- OFERTA 2: 47 nonconformities (was 59, improved by -12 with wrapped code fix)
- Recent commits: wrapped code fix, table format detection improvements

---

## ISSUE #1: Duplicate Article Code Extraction Failure
**Severity**: HIGH | **Impact**: 5-10+ LIPSA articles

### Problem
When the same article code appears **multiple times** in the offer, only the first instance is properly extracted. Subsequent instances have:
- `cantitate = 0.0` (quantity lost)
- Empty `um` (unit lost)
- Empty/truncated `denumire` (description corrupted)

### Example
**Reference**:
- QCD22B33 #1: qty 2.461 mp ✓
- QCD22B33 #2: qty 6.048 mp ✓

**Offer** (extracted):
- QCD22B33 #1: qty 2.46 mp ✓ (works)
- QCD22B33 #2: qty 0.0 (extraction failed) ❌
  - Description shows "60,48 mp" or "6,048 mp" - should be parsed as qty!

### Root Cause
Likely in `f3_regex_parser.py` or `f3_extractor.py` - when a code is encountered for the 2nd+ time, the parser treats it as a duplicate or continuation line instead of a new article with its own qty/um/desc.

### Fix Location
- `shared/f3_regex_parser.py`: Check `extract_articles_regex()` state machine (IDLE, READING, WAITING states)
- `shared/f3_extractor.py`: Check deduplication logic around line 369-378

### Test Case
Search OFERTA 2 for all duplicate codes:
```python
from collections import Counter
codes = [a['cod'] for a in articles]
duplicates = [c for c, count in Counter(codes).items() if count > 1]
```

Then verify qty/um not lost for each duplicate.

---

## ISSUE #2: DI Table Column Misalignment (RPCB02E)
**Severity**: MEDIUM | **Impact**: 1-2 articles + 20 similar potential issues

### Problem
Reference document Table 93 has:
- **Header** (Row 0): Col 0="Nr." | Col 1="Capitolul" | Col 5="U.M." | Col 6="Cantitatea" | Col 7="Pretul unitar"
- **Data** (Row 13): Col 0="4" | Col 1="RPCB02E" | Col 3="99 M" | Col 4="CUB" | Col 6="2,17000"

**Result**: Quantity "99" not extracted. Falls back to regex parser which reads "2,17000" (unit price) as qty.

### Example
- **Reference says**: RPCB02E, qty **99 mc**
- **Extracted as**: RPCB02E, qty **1.92 mc** (the unit price!)

### Root Cause
1. Table 93 doesn't have "SECTIUNEA TEHNICA" header marker
2. `extract_articles_from_tables_smart()` doesn't recognize it as F3 table
3. Table is **skipped**, falls back to line parsing
4. Document Intelligence parsed table columns don't match header layout

### Partial Fix Applied
- Added format detection for "CAPITOLUL"/"CANTITATE" headers in smart extractor
- Added fallback column detection in `extract_articles_from_tables()`
- **Status**: Needs verification - table 93 might still not be processed

### Fix Strategy
**Option A** (better): Fix DI table parsing - align data columns to match headers
**Option B** (simpler): Add heuristic to regex parser - prefer integer/round quantities over decimals
**Option C** (pragmatic): Document as known issue - affects reference extraction only, low priority

### Test
```python
rpcb = [a for a in ref_articles if a['cod'] == 'RPCB02E']
assert rpcb[0]['cantitate'] == 99.0, f"Expected 99, got {rpcb[0]['cantitate']}"
```

---

## ISSUE #3: Wrapped Code Across PDF Lines (COMPLETED ✅)
**Status**: FIXED | **Commit**: Latest

### What Was Done
- Added `_merge_wrapped_codes()` in `f3_regex_parser.py`
- Merges codes split across table rows: "TRI1AA01E" + "3" → "TRI1AA01E3"
- Handles optional suffixes: "RPCB02E%" → merged + "99"

### Result
- OFERTA 2: -12 LIPSA articles (38 → 26)
- Example fixed: TRI1AA01E3 now extracts with qty 57.41 tona

**No further work needed** - this is done.

---

## ISSUE #4: Genuine Missing Articles (LIPSA)
**Severity**: INFORMATIONAL | **Impact**: None (correct behavior)

### Articles in Reference but NOT in Offer
These are **correctly marked as LIPSA** - the offer genuinely omits them:
- `00103E011`: placi ceramice antiderapante, qty 17.42 mp (deviz 4.1-04)
- `00106B011`: placi ceramice h=1.5m, qty 156.2 mp (deviz 4.1-04)
- `CNO1A`: vopsea lavabila gri, qty 207.47 mp (deviz 4.1-04)

**Status**: These are real omissions from the offer, not extraction bugs.
**Action**: No fix needed - this is correct matching.

---

## ISSUE #5: Numeric Code Extraction ($6720363)
**Severity**: LOW | **Impact**: 1 article

### Problem
Code appears as `$6720363` in reference but extracted as empty `''` in offer.

**Status**: Low priority, only affects this one article.

---

## Recommended Next Steps (Priority Order)

### 1. FIX ISSUE #1: Duplicate Codes (HIGH IMPACT)
- Could fix 5-10+ LIPSA articles
- Investigation: 30 min
- Fix: 1-2 hours
- Test: 30 min

### 2. VERIFY ISSUE #2: Table Format Detection  
- Check if table 93 now recognized after recent changes
- Run extraction, check RPCB02E qty
- If still broken: decide on fix strategy (A/B/C above)
- Time: 1 hour max

### 3. ANALYZE Remaining 16 LIPSA (after fixing #1)
- Pattern analysis
- Categorize: extraction bugs vs genuine omissions
- Prioritize fixable issues

### 4. DOCUMENT & COMMIT
- Update memory with findings
- Tag final state (v6.2 or similar)

---

## Commands for Next Session

**Quick status check**:
```bash
rtk proxy python3 local_run.py 2>&1 | grep -E "matched=|Neconformitati:"
```

**Find duplicate codes**:
```bash
rtk proxy python3 -c "
from collections import Counter
import json
with open('output_AO/oferta_2.json') as f:
    codes = [a['cod'] for a in json.load(f).get('articole', [])]
dups = [c for c, n in Counter(codes).items() if n > 1]
print(f'Duplicate codes: {len(dups)}\n' + '\n'.join(dups[:10]))
"
```

**Check extracted metrics**:
```bash
rtk proxy python3 -c "
from collections import Counter
import json
with open('output_AO/comparatie_oferta_2.json') as f:
    types = Counter(item['tip'] for item in json.load(f).get('neconformitati', []))
    for t, n in sorted(types.items()): print(f'{t}: {n}')
"
```

---

## Files to Review
- `shared/f3_regex_parser.py` - Wrapped code fix + duplicate code handling
- `shared/table_extractor.py` - Table format detection improvements
- `shared/f3_extractor.py` - Deduplication logic
- Memory: `wrapped_code_fix_2026_05_18.md`, `rpcb02e_quantity_investigation.md`
