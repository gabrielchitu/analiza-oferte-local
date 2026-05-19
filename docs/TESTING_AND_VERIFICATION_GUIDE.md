# Testing & Verification Guide

**Data:** 2026-05-19  
**Audience:** Developers, QA, analysts verifying nonconformity metrics

---

## Overview: How Tests Work

### Test Categories

| Category | Purpose | Trigger | Location |
|----------|---------|---------|----------|
| **Unit Tests** | Validate individual components (parsers, normalizers) | `rtk python3 -m pytest tests/` | `tests/test_*.py` |
| **Verification Scripts** | Root cause analysis (LIPSA/EXTRA classification) | `rtk python3 tests/verify_*.py` | `tests/verify_*.py` |
| **Integration Tests** | Multi-stage validation (matching, consolidation) | `rtk python3 -m pytest tests/test_integration_*.py` | `tests/test_integration_*.py` |
| **E2E Tests** | Full pipeline (extract → match → report) | `rtk python3 local_run.py` | All modules |

---

## Unit Tests (tests/test_*.py)

### Test: Scattered Format Preprocessing

**File:** `tests/test_f3_regex_parser.py`

**What it tests:**
- `_preprocess_scattered_format()` function
- Detects: counter → code → UM → qty → description pattern
- Combines into NR_COD_DESC format for state machine

**Run:**
```bash
rtk python3 -m pytest tests/test_f3_regex_parser.py::test_scattered_format -v
```

**Expected output:**
```
test_scattered_format[basic_pattern] PASSED
test_scattered_format[with_denominator] PASSED
test_scattered_format[edge_case_missing_qty] PASSED
═══ 3 passed in 0.24s ═══
```

**What it validates:**
- Input: array of 5 lines (counter, code, UM, qty, desc)
- Output: 2-3 lines (NR_COD_DESC on line 0, UM on line 1, qty on line 2)
- Unchanged lines appended at end

---

### Test: Code Normalization

**File:** `tests/test_normalize_cod.py`

**What it tests:**
- `_normalize_cod()` function handles OCR variants
- O→0, l→1, AUT prefix removal, $ addition, etc.

**Run:**
```bash
rtk python3 -m pytest tests/test_normalize_cod.py -v
```

**Expected output:**
```
test_normalize_o_to_zero PASSED
test_normalize_l_to_one PASSED
test_normalize_aut_prefix PASSED
test_normalize_digital_to_dollar PASSED
test_normalize_dollar_stays PASSED
test_normalize_normativ_unchanged PASSED
═══ 6 passed in 0.15s ═══
```

**Edge cases validated:**
- `O3271724` → `0327172` → (no match, stays as-is)
- `AUT6752` → `6752` → `$6752`
- `$6752` → `$6752` (idempotent)
- `TSC02D11` → `TSC02D11` (normativ stays unchanged)

---

### Test: Article Matching

**File:** `tests/test_matching.py`

**What it tests:**
- Layer 1 (exact match): `(deviz, cod)` identical
- Layer 2 (normalized): `_normalize_cod` equalizes codes
- Layer 2.5 (fuzzy): similarity ≥ 85% + Jaccard ≥ 0.4

**Run:**
```bash
rtk python3 -m pytest tests/test_matching.py -v
```

**Example test case:**
```python
# Layer 1: exact match
ref = {cod: "TSC02D11", deviz: "226208", um: "buc", qty: 10.0}
offer = {cod: "TSC02D11", deviz: "226208", um: "buc", qty: 10.0}
→ MATCHED (Layer 1)

# Layer 2: normalized match
ref = {cod: "0327172", deviz: "226208", um: "buc"}
offer = {cod: "O327172", deviz: "226208", um: "buc"}
→ MATCHED (Layer 2, O→0)

# Layer 2.5: fuzzy match (similarity)
ref = {cod: "TSC02D11", deviz: "226208", name: "ELEMENT A"}
offer = {cod: "TSC02D12", deviz: "226208", name: "ELEMENT A"}
→ similarity("TSC02D11", "TSC02D12") = 87% > 85%
→ MATCHED (Layer 2.5)
```

---

## Verification Scripts (Root Cause Analysis)

### Script: verify_lipsa_codes.py

**Purpose:** Classify LIPSA codes → identify root cause

**Run:**
```bash
# All LIPSA codes in OFERTA 1
rtk python3 tests/verify_lipsa_codes.py --oferta 1

# First 5 LIPSA codes (faster for debugging)
rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 5
```

**Output format:**
```
═════════════════════════════════════════════════════════════
OFERTA 1: LIPSA Code Analysis (limit=5)
═════════════════════════════════════════════════════════════

Code: RPIZE17B | Deviz: 4.1-04
  Status: NOT_EXTRACTED
  Found in: di_referinta.json (page 42, line 3-5)
  Pattern: Standard code format, unclear extraction gap
  Recommendation: Investigate extraction heuristics

Code: 00106B011 | Deviz: 4.1-13
  Status: NOT_EXTRACTED
  Found in: di_referinta.json (page 51, line 8)
  Pattern: DIGIT-LETTER-DIGIT (00106B011) — non-standard format
  Recommendation: Add format-specific parser for DIGIT-LETTER-DIGIT

Code: S474 | Deviz: 4.2-1
  Status: LEGITIMATE_SUBCOMPONENT
  Parent: $4118013
  Reason: Variant code appearing in denomination → skip extraction [FIXED 2026-05-19]

Code: TSE02B1 | Deviz: 4.3-06
  Status: NOT_EXTRACTED
  Found in: di_referinta.json (page 67, line 12)
  Pattern: TSE-prefix code, similar to TSC but not recognized
  Recommendation: Check TSE prefix handling

Code: $5709220 | Deviz: 4.1-04
  Status: NOT_EXTRACTED
  Found in: di_referinta.json (page 38, line 15)
  Pattern: $ prefix code — field name mismatch [FIXED 2026-05-19]

═════════════════════════════════════════════════════════════
Summary: 5 codes analyzed
  NOT_EXTRACTED: 4 (80%)
  EXTRACTED_NOT_MATCHED: 0 (0%)
  LEGITIMATE_SUBCOMPONENT: 1 (20%)
═════════════════════════════════════════════════════════════
```

**How to interpret:**

| Classification | Meaning | Action |
|---|---|---|
| `NOT_EXTRACTED` | Code exists in di_referinta.json but parser missed it | Check f3_regex_parser for missed patterns |
| `EXTRACTED_NOT_MATCHED` | Code extracted to referinta.json but matching failed | Check AgentComparator layers 1-5 |
| `LEGITIMATE_SUBCOMPONENT` | Code is variant/metadata, not standalone article | Keep as-is (expected) |

---

### Script: verify_extra_codes.py

**Purpose:** Classify EXTRA codes → identify root cause

**Run:**
```bash
# All EXTRA codes in OFERTA 1
rtk python3 tests/verify_extra_codes.py

# Specific deviz only
rtk python3 tests/verify_extra_codes.py --deviz "4.1-04"
```

**Output format:**
```
═════════════════════════════════════════════════════════════
OFERTA 1: EXTRA Code Analysis
═════════════════════════════════════════════════════════════

Code: $5102437 | Deviz: 4.1-04 | Qty: 22.0 buc
  Status: FOUND_EXACT (in di_referinta.json)
  Location: di_referinta.json, page 17, lines 84-88
  Format: Scattered format (fixed 2026-05-19)
  Conclusion: Extraction gap in referinta — preprocessor now handles this

Code: RPIZE17B | Deviz: 4.1-04 | Qty: 5.0 buc
  Status: NOT_FOUND
  Searched: di_referinta.json (all pages)
  Conclusion: GENUINE_EXTRA (offer-specific addition)

Code: S474 | Deviz: 4.2-1 | Qty: 1.0 buc
  Status: FOUND_AS_SUBCOMPONENT
  Parent: $4118013
  Reason: Variant code in denomination (not extraction issue)
  Conclusion: False positive — skip extraction (fixed 2026-05-19)

═════════════════════════════════════════════════════════════
Summary: 3 codes analyzed
  FOUND_EXACT (extraction gaps): 1 (33%)
  NOT_FOUND (genuine extras): 1 (33%)
  FOUND_AS_SUBCOMPONENT: 1 (33%)

Recommendation: 
  - 1 code: extraction gap fixed by preprocessor
  - 1 code: offer-specific addition (normal)
  - 1 code: variant code (false positive, fixed)
═════════════════════════════════════════════════════════════
```

**How to interpret:**

| Classification | Meaning | Action |
|---|---|---|
| `FOUND_EXACT` | Code exists in di_referinta.json but NOT extracted to referinta.json | Extraction gap → check preprocessors |
| `NOT_FOUND` | Code NOT anywhere in di_referinta.json | Genuine extra (offer-specific) → normal, accept |
| `FOUND_AS_SUBCOMPONENT` | Code is variant/metadata of parent article | Skip extraction → prevent false positive |

---

## Integration Tests (test_integration_*.py)

### Test: Multi-Deviz Consolidation

**File:** `tests/test_integration_hierarchical.py`

**What it tests:**
- Article codes appearing in multiple devizes
- Inheritance of UM/quantity from parent
- Conflict detection when quantities differ

**Run:**
```bash
rtk python3 -m pytest tests/test_integration_hierarchical.py::test_cross_deviz_consolidation -v
```

**Example scenario:**
```
Reference:
  Deviz 4.1-04: code TRA01A15P, qty=10, um=buc
  Deviz 5.1-01: code TRA01A15P, qty=5, um=buc
  
Offer:
  Deviz 4.1-04: code TRA01A15P, qty=10, um=buc
  Deviz 5.1-01: MISSING
  
Expected:
  - Deviz 4.1-04: MATCHED (qty=10)
  - Deviz 5.1-01: LIPSA (offer missing in secondary deviz)
```

---

## E2E Tests (Full Pipeline)

### Test: Complete Extraction → Matching → Reporting

**Run:**
```bash
# Full pipeline on all documents
rtk python3 local_run.py

# With timing
rtk time python3 local_run.py
```

**Baseline metrics (2026-05-19):**

| Stage | Files | Time | Notes |
|-------|-------|------|-------|
| Classification | 3 documents | 12.3s | LLM: 8 ambiguous pages |
| Extraction | referinta (834→878) | 2.1s | +44 scattered format |
| Extraction | oferta_1 (1288) | 1.9s | Linked articles active |
| Extraction | oferta_2 (1203) | 1.8s | Linked articles active |
| Extraction | oferta_3 (1224) | 1.9s | Linked articles active |
| Matching | 3 offers | 3.4s | 6 layers + Layer 5 post-processing |
| Report generation | 3 DOCX files | 24.2s | Word write-heavy |
| **Total** | | **47.6s** | Single machine, no parallelization |

**Output validation:**

```bash
# Check referinta extraction
ls -lh output_AO/referinta.json
# Expected: ~150K (878 articles)

# Check comparison reports
ls -lh output_AO/comparatie_oferta_*.json
# Expected: 3 files, ~100-150K each

# Check nonconformity totals
rtk python3 -c "
import json
for i in range(1, 4):
    with open(f'output_AO/comparatie_oferta_{i}.json') as f:
        data = json.load(f)
        nc = data['nonconformities']
        print(f'OFERTA {i}: {nc[\"total\"]} nonconformities')
"

# Expected (2026-05-19 baseline):
# OFERTA 1: 123 nonconformities
# OFERTA 2: 117 nonconformities
# OFERTA 3: 50 nonconformities
```

---

## Regression Testing Workflow

### Before Committing Code Changes

**Checklist:**

1. **Run unit tests:**
   ```bash
   rtk python3 -m pytest tests/ -v
   # Expected: all pass, no skips
   ```

2. **Run verification scripts (sample 5-10 codes):**
   ```bash
   rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 5
   rtk python3 tests/verify_extra_codes.py --limit 5
   # Classify root causes — check if they match expectations
   ```

3. **Run full pipeline:**
   ```bash
   rtk python3 local_run.py
   # Record: nonconformities per oferta
   ```

4. **Compare metrics:**
   ```
   OFERTA 1: 123 nonconformitati (±2% tolerance)
   OFERTA 2: 117 nonconformitati (±2% tolerance)
   OFERTA 3: 50 nonconformitati (±2% tolerance)
   ```

5. **If regression detected:**
   - Compare output_AO/comparatie_oferta_N.json vs previous run
   - Use diff to identify changed nonconformities
   - Root cause: Run verify_extra/lipsa scripts on new nonconformities
   - Revert or fix appropriately

---

## Result Verification Checklist

### After Running local_run.py

**File existence:**
```bash
[ ] output_AO/referinta.json exists
[ ] output_AO/comparatie_oferta_1.json exists
[ ] output_AO/comparatie_oferta_2.json exists
[ ] output_AO/comparatie_oferta_3.json exists
[ ] output_AO/report_oferta_1.docx exists
[ ] output_AO/report_oferta_2.docx exists
[ ] output_AO/report_oferta_3.docx exists
[ ] output_AO/checkpoints/di_*.json exists (caching)
```

**JSON structure validation:**
```bash
# Check referinta.json schema
rtk python3 -c "
import json
with open('output_AO/referinta.json') as f:
    ref = json.load(f)
    assert 'articles' in ref
    assert len(ref['articles']) > 800
    print(f'✓ referinta.json: {len(ref[\"articles\"])} articles')
"

# Check comparatie schema
rtk python3 -c "
import json
with open('output_AO/comparatie_oferta_1.json') as f:
    comp = json.load(f)
    assert 'nonconformities' in comp
    assert 'total' in comp['nonconformities']
    print(f'✓ comparatie_oferta_1.json: {comp[\"nonconformities\"][\"total\"]} nonconformities')
"
```

**Metrics sanity checks:**
```bash
# OFERTA 1: matched + LIPSA should ≈ referinta total
rtk python3 -c "
import json
with open('output_AO/referinta.json') as f:
    ref_total = len(json.load(f)['articles'])
with open('output_AO/comparatie_oferta_1.json') as f:
    comp = json.load(f)
    matched = comp['matched']
    lipsa = comp['nonconformities'].get('ARTICOL_LIPSA', 0)
    print(f'ref_total: {ref_total}')
    print(f'matched: {matched}')
    print(f'LIPSA: {lipsa}')
    print(f'matched + LIPSA: {matched + lipsa}')
    print(f'Difference: {abs((matched + lipsa) - ref_total)}')
"

# Expected: matched + LIPSA ≈ ref_total (within 5% for subcomponents)
```

**Field consistency:**
```bash
# Check: article fields consistent across all documents
rtk python3 -c "
import json

# Check field names in referinta
with open('output_AO/referinta.json') as f:
    ref = json.load(f)
    if ref['articles']:
        fields = set(ref['articles'][0].keys())
        print('Fields in referinta.json:')
        for f in sorted(fields):
            print(f'  - {f}')
        # Expected: cod, denumire, um, cantitate, deviz_cod, deviz_den
"

# Verify: no 'descriere' field (that was the bug in May 2026)
rtk python3 -c "
import json
with open('output_AO/referinta.json') as f:
    ref = json.load(f)
    if ref['articles']:
        article = ref['articles'][0]
        if 'descriere' in article:
            print('❌ ERROR: descriere field exists (should be denumire)')
        else:
            print('✓ No descriere field (correct)')
"
```

---

## Performance Monitoring

### Execution Time Tracking

**After each run, capture:**
```
[OK] Classification: X pages, Y.Zs (LLM: M pages)
[OK] Extraction referinta: N articles, A.Bs
[OK] Extraction offer 1: N articles, A.Bs
[OK] Extraction offer 2: N articles, A.Bs
[OK] Extraction offer 3: N articles, A.Bs
[OK] Matching: 6 layers, X.Ys
[OK] Report generation: Z.Zs
Total: TT.Ts
```

**Baseline (2026-05-19):** 47.6s total  
**Acceptable range:** 40-55s (±15%)  
**Flag if:** > 60s (possible regression in matching or report generation)

---

## Troubleshooting Guide

### Problem: Metrics increase suddenly (LIPSA/EXTRA/nonconformities ↑)

**Diagnosis steps:**

1. **Identify changed codes:**
   ```bash
   # Compare with previous session JSON
   diff <(rtk jq '.nonconformities' comparatie_oferta_1_old.json | sort) \
        <(rtk jq '.nonconformities' comparatie_oferta_1.json | sort)
   ```

2. **Classify root cause:**
   ```bash
   rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 20
   rtk python3 tests/verify_extra_codes.py --limit 20
   # Do new LIPSA/EXTRA fit expected patterns?
   ```

3. **Check recent commits:**
   ```bash
   rtk git log --oneline -5
   # Which code changed? Revert or debug that module.
   ```

4. **Validate checkpoint cache:**
   ```bash
   rm output_AO/checkpoints/*.json
   rtk python3 local_run.py
   # Does it match baseline again? If yes → stale checkpoint issue.
   # If no → code bug, not cache.
   ```

### Problem: Specific code not extracted (LIPSA)

**Diagnosis:**

1. **Find code in di_referinta:**
   ```bash
   rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 1
   # Note the page number and line range
   ```

2. **Inspect raw DI JSON:**
   ```bash
   rtk python3 -c "
   import json
   with open('input/di_referinta.json') as f:
       di = json.load(f)
       page = di['pages'][PAGE_NUM - 1]
       for i, line in enumerate(page['lines']):
           if 'CODE_SNIPPET' in line['text']:
               print(f'Line {i}: {line[\"text\"][:80]}')
   "
   ```

3. **Trace parser:**
   - Check if matches any regex pattern in f3_regex_parser.py
   - If matches COD_SIMPLE_* patterns → preprocessor or state machine bug
   - If doesn't match → new format → need new pattern or preprocessor

---

## Memory File (MEMORY.md)

All testing baselines and decisions documented in:

```
/Users/gabrielchitu/.claude/projects/-Users-gabrielchitu-analiza-oferte-local/memory/MEMORY.md
```

Key entries:
- Session 2026-05-19 Lenient Matching (metrics, fixes applied)
- EXTRA Investigation (87% extraction gaps)
- LIPSA Fixes (3 critical codes)

When adding new tests or verification scripts → update MEMORY.md with baselines.

