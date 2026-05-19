---
name: session_2026_05_19_extra_investigation
description: "2026-05-19: EXTRA code analysis + referinta extraction fix; scattered format preprocessor; 87% of EXTRA are extraction gaps, not genuine extras"
metadata:
  type: project
  date: 2026-05-19
  focus: EXTRA code root cause analysis; referinta extraction improvement
---

## Key Finding: EXTRA = Extraction Gaps, Not Genuine Extras

### Investigation Results
Created `verify_extra_codes.py` script:
- **Total EXTRA codes**: 150 in OFERTA 1
- **87% in di_referinta pages but NOT extracted**: 131 codes
- **13% in referinta.json but not matched**: 19 codes
- **Conclusion**: EXTRA problem is referinta extraction incompleteness

### Example: Code 5102437
- Location: di_referinta.json page 17, lines 84-88
- Format: scattered (code on separate line from UM, quantity, description)
- Status before: NOT extracted
- Status after: ✓ extracted ($5102437, buc, qty=22.0)

## Scattered Format Preprocessor

### Implementation
Added `_preprocess_scattered_format()` in f3_regex_parser.py (before line 406):
- Detects pattern: counter → code → UM → quantity → description (each on own line)
- Combines into NR_COD_DESC format: "NR CODE - description"
- Leaves UM/QTY on separate lines for state machine to extract

### Results
- **Groups combined**: 44 scattered format groups across referinta
- **Code 5102437**: Now extracted with all fields
- **Referinta extraction**: 834 → 878 articles (+44)

## Metrics Changes
**OFERTA 1:**
- Total nonconformitati: 152 → 129 (-23)
- EXTRA: 150 → 102 (-48, -32%)
- LIPSA: 1 → 23 (+22, all found in source—extraction gaps)
- Matches: 963 → 989 (+26)

**OFERTA 2:**
- EXTRA: 386 → 337 (-49)
- LIPSA: 6 → 76 (extraction gaps)
- Matches: ~1652 → 1686

## LIPSA Verification (OFERTA 1)
All 23 LIPSA codes found in di_referinta source:
- **10 codes**: NOT extracted from referinta (extraction gaps)
  - RPIZE17B, RPCI42E, RPCJ27XA, 00106B011, 00101B031, RPCE05XF, $5709220, $6103749, $8811743, TSE02B1
- **5 codes**: Extracted but NOT matched (matching failures)
  - 01501A1, VC22XB, CC01C1, CB01A1, TSE02C1
- **5 codes**: Legitimate subcomponents
  - S474, CE10XA, 01311A1, EC04A1, W3G02A1

## Remaining Extraction Gaps
Scattered format preprocessor only handles ONE format. Other unextracted codes suggest additional missing formats:
- RPIZE17B, RPCI42E (unknown format)
- 00106B011, 00101B031 (digit-letter-digit codes)
- Others: Various normativ/extended codes

## Commits (2026-05-19)
1. `feat: automated EXTRA code verification script`
   - Analyzes EXTRA codes with root cause classification
   - Detects extraction gaps vs. genuine extras vs. subcomponents
   
2. `fix: field name mismatch in $ code filter (descriere → denumire)`
   - Fixed filter that was removing all $ codes (CRITICAL BUG)
   - $6720363 now matched instead of LIPSA
   
3. `cleanup: remove debug logging from local_run.py`

4. `feat: add scattered format preprocessor for referinta extraction`
   - Combines multi-line scattered codes into parser-compatible format
   - 44 groups combined successfully
   
5. `fix: scattered format preprocessor uses NR_COD_DESC pattern`
   - Changed format to match NR_COD_DESC_RE regex
   - Added UM/QTY on separate lines for state machine

## Architecture Insights
1. **Offer extraction** (local_run.py + f3_regex_parser.py): Better at handling varied formats
2. **Referinta extraction**: Uses same logic but misses certain formats
3. **Solution**: Expand preprocessor to handle more format variations

## Next Steps
1. Identify remaining extraction gap patterns (RPIZE17B, 00106B011, etc.)
2. Add preprocessors for those patterns
3. Re-verify LIPSA and EXTRA metrics
4. Consider matching improvements for subcomponents (S474, etc.)
