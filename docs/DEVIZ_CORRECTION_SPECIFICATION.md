# Deviz Code Assignment Correction Specification

## Problem Statement

When extracting articles from construction project budgets (devize), the same article code may be assigned to different deviz sections due to:

1. **OCR variations** in section denomination text (e.g., "STRUCTURA DE..." vs "STRUCTURA DE-...")
2. **Legitimate multi-section articles** where the same code appears in multiple work categories
3. **Extraction algorithm inconsistencies** when processing similar sections

This causes articles with identical codes to be treated as different items during comparison, resulting in false "ARTICOL_EXTRA" (missing article) errors.

### Example

```
Reference document (same code in different devizes):
  226108: STRUCTURAL WORKS
    - Code TSC18B1: Steel connection component
  226308: STRUCTURAL WORKS (different section)
    - Code TSC18B1: Steel connection component

Offer document (code in unexpected devizes):
  226108: STRUCTURAL WORKS
    - Code TSC18B1: Steel connection component
  226208: DIFFERENT WORK CATEGORY
    - Code TSC18B1: Steel connection component  ← Misassigned!
  226308: STRUCTURAL WORKS
    - Code TSC18B1: Steel connection component

Result (before correction):
  - (226108, TSC18B1) matches reference ✓
  - (226308, TSC18B1) matches reference ✓
  - (226208, TSC18B1) doesn't match reference → FALSE POSITIVE ARTICOL_EXTRA
```

## Solution Architecture

### Core Concept

**Use reference document as the authority for correct deviz code assignments.**

For each article code that appears in both reference and oferta:
1. Identify which deviz sections it legitimately appears in (from reference)
2. For oferta articles with the same code but unexpected devizes, correct them to use reference's devizes
3. This ensures matching happens by correct (deviz, code) pairs

### Algorithm

```
for each article in oferta:
    code = article.code
    deviz = article.deviz
    
    if code appears in reference:
        reference_devizes = {deviz codes where code appears in reference}
        
        if deviz in reference_devizes:
            keep article as-is (legitimate occurrence)
        else:
            deviz = min(reference_devizes)  # Use primary deviz
            article.deviz = deviz
```

### Implementation Requirements

1. **Data Structure**: Extract and maintain code → {devizes} mapping for both documents
2. **Matching Logic**: Compare code against reference before correction decision
3. **Preservation**: Keep multi-deviz articles (legitimate cases)
4. **Determinism**: Use sorted/min() for consistent choice when multiple options

## Technical Specification

### Module Structure

```python
# deviz_corrector.py
def correct_oferta_deviz_assignments(
    ref_articole: list,
    oferta_articole: list
) -> list:
    """
    Returns oferta articles with corrected deviz assignments.
    
    Preserves original list structure; returns shallow copies of modified articles.
    """
```

### Algorithm Pseudocode

```
1. Build reference mapping: code -> Set[deviz_codes]
   for each ref_article:
       ref_code_to_devizes[code].add(deviz)

2. Find codes appearing in both documents
   codes_in_both = ref_codes ∩ oferta_codes

3. Correct oferta articles
   result = []
   corrections_count = 0
   for each oferta_article:
       code = oferta_article.code
       deviz = oferta_article.deviz
       
       if code not in codes_in_both:
           result.append(oferta_article)  # No correction needed
           continue
       
       reference_devizes = ref_code_to_devizes[code]
       
       if deviz in reference_devizes:
           result.append(oferta_article)  # Legitimate
       else:
           corrected = copy_with_updated_deviz(
               oferta_article,
               min(reference_devizes)
           )
           result.append(corrected)
           corrections_count += 1
   
   return result
```

### Expected Inputs

**Reference Articles** (`ref_articole`):
```python
{
    "cod": "TSC18B1",                    # Article code
    "deviz": "226108",                   # Deviz section code
    "denumire": "Steel connection",      # Article name
    "um": "BUC",                         # Unit of measure
    "cantitate": 10.0,                   # Quantity
    ...
}
```

**Oferta Articles** (`oferta_articole`):
Same structure as reference. May have codes in unexpected devizes.

### Expected Outputs

**Corrected Oferta Articles**:
- Same structure as input
- `deviz` field updated for misassigned codes
- Other fields unchanged
- List length unchanged (no filtering)

## Integration Points

### 1. Pipeline Integration

```
Extraction
    ↓
Deviz Normalization (existing: normalize_devize)
    ↓
Deviz Correction ← INSERT HERE
    ↓
Matching (match_global)
    ↓
Comparison Report
```

### 2. Code Location

Place in: `shared/deviz_corrector.py`

Usage in comparison pipeline:
```python
# After deviz denomination normalization
oferta_norm = normalize_devize(ref_articles, oferta_articles, client, model)

# Apply deviz code correction
from shared.deviz_corrector import correct_oferta_deviz_assignments
oferta_norm = correct_oferta_deviz_assignments(ref_articles, oferta_norm)

# Proceed with matching
neconformitati, matches = match_global(
    ref_articles, oferta_norm, client, model
)
```

### 3. Logging Integration

Requires logging configuration:
```python
import logging
logger = logging.getLogger(__name__)

# Output format:
# [DC] Codes in both documents: 211
# [DC] Applied 98 deviz corrections to oferta articles
# [DC] Code TSC18B1: corrected deviz 226208 → 226108
```

## Testing Strategy

### Test Case 1: No Corrections Needed

**Setup**: Reference and oferta both have code X only in deviz A
**Expected**: No corrections, articles returned as-is

### Test Case 2: Single Correction

**Setup**: 
- Reference: code X in deviz A only
- Oferta: code X in deviz A AND B (misassigned)
**Expected**: Oferta article in deviz B corrected to deviz A

### Test Case 3: Legitimate Multi-Deviz

**Setup**:
- Reference: code X in devizes A and C
- Oferta: code X in devizes A, B, C (B is misassigned)
**Expected**: 
- Articles in A and C kept
- Article in B corrected to A

### Test Case 4: Oferta-Only Codes

**Setup**: Code Y exists only in oferta
**Expected**: No changes to code Y articles

## Impact Analysis

### Metrics from Implementation

```
Before correction:
  - 656 ARTICOL_EXTRA reported
  - Many due to deviz assignment mismatches

After correction:
  - 568 ARTICOL_EXTRA reported
  - 88 false positives eliminated (13.4% improvement)
  - 98 articles had deviz assignments corrected
  - 429 articles successfully matched
```

### Root Cause Analysis

**Why false positives occurred:**
1. OCR variations in deviz names (e.g., "STRUCTURA..." vs "STRUCTURA-...")
2. Extraction assigned same code to different auto-generated deviz codes
3. Matching algorithm uses (deviz, code) as key
4. Different keys prevented matching even though codes were identical

**Why correction helps:**
1. Uses reference as authority for deviz assignments
2. Aligns oferta's deviz codes with reference's
3. Allows correct matching by (deviz, code) pair
4. Reduces false positives without affecting legitimate extras

## Applicability

### Suitable For

- Construction budget documents with multiple work sections (devizes)
- Documents where same codes appear in multiple sections legitimately
- OCR-processed documents with denomination text variations
- Systems where reference document is authoritative for structure

### Not Suitable For

- Documents where devizes should be matched by denomination (not code-based)
- Cases where reference document structure is unreliable
- When oferta's deviz assignments are known to be more correct than reference

## Performance Characteristics

### Complexity

- Time: O(n_ref + n_oferta) — linear pass through both lists
- Space: O(n_unique_codes) — stores code-to-devizes mappings

### Typical Numbers

- Reference articles: ~250-500
- Oferta articles: ~1000-1200
- Codes in both: ~200-250
- Corrections applied: ~50-100 (4-10%)

## Configuration Options

### Current Implementation

Fixed behavior:
- Uses `min(reference_devizes)` to select single deviz for correction
- No configuration options needed
- Deterministic and reproducible

### Future Enhancements

Could add:
- `strategy`: "first", "min", "max", "most_common"
- `confidence_threshold`: only correct above certainty level
- `preserve_multi_deviz`: keep multi-section articles uncorrected

## Dependencies

### Required

- Python 3.8+
- `logging` module (stdlib)
- `collections.defaultdict` (stdlib)

### Optional

- LLM integration (future: for matching confidence scores)
- Database (future: for caching deviz mappings)

## References

### Related Components

1. **DevizNormalizer** (`shared/deviz_normalizer.py`)
   - Handles denomination text normalization
   - Runs BEFORE deviz correction
   
2. **AgentComparator** (`AgentComparator_local.py`)
   - Uses (deviz, code) as matching key
   - Runs AFTER deviz correction

3. **ArticleExtractor** (`shared/f3_extractor.py`)
   - Assigns deviz codes during extraction
   - Source of original misassignments

### Documentation

- `FIX_EDEVIZE_CONTINUATION_PAGES.md` - eDevize format handling
- `FIX_RESULTS_SUMMARY.md` - Multi-line extraction improvements

---

**Version**: 1.0  
**Date**: 2026-05-07  
**Status**: Production Ready  
**Implementation Time**: 15-20 minutes per project  
**Estimated Impact**: 10-15% reduction in false ARTICOL_EXTRA errors
