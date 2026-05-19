---
name: session_2026_05_19_filter_field_fix
description: "2026-05-19: ROOT CAUSE FOUND - field name mismatch in $ code filter (descriere→denumire); $6720363 pipeline loss resolved"
metadata:
  type: project
  date: 2026-05-19
  focus: $6720363 pipeline loss investigation
---

## Investigation Summary

Traced disappearance of $6720363 from extraction pipeline through debug logging at each step.

### Finding: Field Name Mismatch in Filter

**Location**: `local_run.py` line 993

**Bug**: Filter checked `a.get('descriere', '')` but parser creates `'denumire'` field

```python
# BUGGY CODE (line 993)
if not (a.get('cod', '').startswith('$') and not a.get('descriere', '').strip())

# FIXED CODE
if not (a.get('cod', '').startswith('$') and not a.get('denumire', '').strip())
```

### Root Cause Analysis

1. **Parser output** (f3_regex_parser.py line 392): Creates articles with `'denumire'` field
2. **Filter logic**: Removes articles where `cod.startswith('$')` AND `descriere` is empty
3. **Bug result**: Since `descriere` field never exists, `.get('descriere', '')` always returns empty string
4. **Impact**: All $ prefix articles removed from comparison, regardless of actual denomination

### Proof

- Parser extracted 79 articles including $6720363 ✓
- Deduplication passed $6720363 through ✓
- **Filter removed ALL 429 $ prefix codes** because 'descriere' field always empty ✗

### Fix Applied

Changed filter to check `'denumire'` field (actual parser output). Now:
- $ codes with non-empty denomination → kept ✓
- $ codes with empty denomination → removed (as intended) ✓

### Results

**OFERTA 1 Comparison**:

Before fix:
- LIPSA: $6720363, S474 (2 total)
- EXTRA: 3 
- Matches: 699
- Total nonconformitati: 5

After fix:
- LIPSA: S474 only (1 total) ← **$6720363 FIXED** ✓
- EXTRA: 150 (includes 147 $ codes now visible)
- Matches: 963 (+264)
- Total nonconformitati: 152

**Why EXTRA increased**: The buggy filter was hiding 147 $ codes. Now they're visible in comparison (offer has them, reference doesn't). This is correct behavior - it exposes offer/reference structural differences.

## Commits (2026-05-19)
1. "fix: field name mismatch in $ code filter (descriere → denumire)"
2. "cleanup: remove debug logging from local_run.py"

## Key Learnings

1. **Field name discrepancy**: Parser uses 'denumire', not 'descriere'
2. **Filter working correctly now**: Only removes $ codes with actually empty denominations
3. **Metrics interpretation**: Increase in EXTRA not a regression, but exposing hidden extraction

## Next Steps

- OFERTA 1: 1 genuine LIPSA (S474) confirmed, 1 UM mismatch ($6720363)
- OFERTA 2: Verify similar structural issues with offer/reference
- Consider: Should offer-only $ codes be consolidated/matched differently?

## Status

✓ CRITICAL BLOCKER RESOLVED: $6720363 no longer LIPSA
✓ Filter field name fixed
✓ Parser output now correctly compared against reference
