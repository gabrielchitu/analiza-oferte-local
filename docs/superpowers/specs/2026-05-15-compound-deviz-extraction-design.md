# Compound Deviz Identifier Extraction Design

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Extract and construct deviz codes from compound identifiers (Obiectul + Categoria de lucrari) when explicit "Deviz Oferta" codes are missing, enabling extraction of non-standard F3 document formats.

**Architecture:** Enhanced page classifier with priority-based extraction (explicit codes first, compound fallback), state management for inheritance, and checkpoint-based cross-validation between reference and offers.

**Tech Stack:** Python regex, JSON checkpoint files, existing f3_page_classifier.py framework

---

## Problem Statement

Current extraction pipeline fails on construction estimate documents (eDevize) that lack standard 6-digit deviz codes (e.g., "226348") or explicit "STADIUL FIZIC" markers. Instead, articles are grouped under invalid identifiers ("CAMINE", "CAMIN", etc.) which are filtered out, resulting in zero extracted articles.

New format documents have:
- Explicit "Obiectul: 4.1" (Object/Section number)
- Explicit "Categoria de lucrari: 03 Arhitectura" (Category/Physical State)
- No standard 6-digit deviz code
- No "STADIUL FIZIC" section

**Solution:** Construct deviz identifier as compound: `[Obiectul]-[Categoria]` (e.g., `4.1-03`)

---

## Design Details

### 1. Extraction Logic & Priority

**Three-tier priority system** in `f3_page_classifier.py`:

#### Tier 1: Explicit "Deviz Oferta" (Highest Priority)
- Pattern: `Deviz\s+[Oo]ferta\s+([A-Z0-9]{5,8})`
- Context: Search in full content (not line-by-line to avoid OCR splits)
- Returns: Direct code (e.g., "226238")
- Use case: eDevize standard format, offers with explicit codes

#### Tier 2: Compound Identifier (Fallback)
- Extract "Obiectul" using pattern: `Obiectul\s*:\s*([0-9.]+)\s*(.+?)(?=\n|Categoria|$)`
  - Captures: Number (e.g., "4.1") + Description (e.g., "Cladire camin")
- Extract "Categoria de lucrari" or "Stadiul fizic" using: `(?:Categoria\s+de\s+lucrari|Stadiul\s+fizic)\s*:\s*([0-9]{2,4})\s*(.+?)(?=\n|Lista|$)`
  - Captures: Number (e.g., "03") + Description (e.g., "Arhitectura - eligibile tip I")
- Construct: `deviz_cod = f"{object_num}-{category_num}"` → "4.1-03"
- Store: Both parts + full text descriptions for validation
- Use case: New format documents without explicit codes

#### Tier 3: Existing Logic (Fallback)
- Preserve current 6-digit extraction from "STADIUL FIZIC", eDevize headers
- Fallback for documents with partial markers
- Use case: Mixed or partial format documents

### 2. State Management & Inheritance

- **Page-level extraction**: Extract Obiectul + Categoria from each page (or inherit from previous)
- **Deviz inheritance**: If a continuation page lacks both Obiectul and Categoria markers, inherit from previous page's constructed deviz_cod
- **Tracking**: Maintain `current_deviz_cod`, `current_obiectul`, `current_categoria` during page classification loop

### 3. Checkpoint File System

**Location:** `output_AO/checkpoints/deviz_mapping_{classifier_hash}.json`

**Schema:**
```json
{
  "metadata": {
    "source": "di_referinta.json|di_oferta_N.json",
    "document_type": "reference|offer",
    "extracted_at": "ISO8601 timestamp",
    "classifier_version": "hash"
  },
  "deviz_groups": [
    {
      "deviz_cod": "4.1-03",
      "type": "compound",
      "extraction_method": "Obiectul-Categoria",
      "obiectul": { "number": "4.1", "description": "Cladire camin" },
      "categoria": { "number": "03", "description": "Arhitectura - eligibile tip I" },
      "article_count": 47,
      "pages": [1, 2, 3, 5, 7],
      "normalized_key": "4.1-03"
    },
    {
      "deviz_cod": "226238",
      "type": "explicit",
      "extraction_method": "Deviz Oferta",
      "description": "MONTAT BOILER",
      "article_count": 12,
      "pages": [8, 9],
      "normalized_key": "226238"
    }
  ],
  "validation": {
    "total_articles": 59,
    "total_pages_with_deviz": 7,
    "coverage": "100%"
  }
}
```

**Cross-validation strategy:**
- Reference checkpoint is primary authority
- When processing offers, load reference checkpoint
- Validate that every offer deviz_cod has matching reference deviz_cod (normalized)
- Log discrepancies: offers with devizes not in reference → warning
- Allow new devizes in offers (articles added by bidder)

### 4. False Positive Avoidance

**Context-aware matching:**
- "deviz" word appearing in Obiectul description → Not confused with "Deviz Oferta"
  - Example: "CONSTRUIRE GARD DIN DEHEZ" should not capture "HEZ" as code
  - Solution: Explicit pattern match `Deviz\s+Oferta`, not substring search

- "Categoria de lucrari" with random text → Only match when numeric prefix present
  - Requirement: `[0-9]{2,4}` must be present (2-4 digit category number)

- "Stadiul fizic" vs "Categoria de lucrari" precedence
  - Both patterns search independently
  - "Categoria de lucrari" preferred (more standard)
  - "Stadiul fizic" as fallback for eDevize variants

### 5. Integration Points

**In `classify_page_local(page: dict)`:**
- Add call to `_extract_compound_deviz(lines)` after existing F3 detection
- Update return dict to include extraction method: `"extraction_method": "compound"|"explicit"|"inheritance"`

**In `build_page_classifications(pages: list[dict])`:**
- After classifying all pages, build checkpoint mapping
- Call new function: `_build_deviz_checkpoint(results, document_type, source_path)`
- Save to `checkpoints/deviz_mapping_{hash}.json`

**In `local_run.py`:**
- Load reference checkpoint before processing offers
- Pass checkpoint to comparison function for validation
- Log validation results and discrepancies

### 6. Data Flow

```
DI JSON pages
    ↓
classify_page_local() [per page]
    ├─→ Check "Deviz Oferta XXXX" (explicit)
    ├─→ Check "Obiectul" + "Categoria" (compound)
    ├─→ Fall back to existing logic
    └─→ Inherit from previous page if needed
    ↓
build_page_classifications() [all pages]
    ├─→ Propagate deviz_cod with inheritance
    └─→ Build checkpoint mapping
    ↓
_build_deviz_checkpoint() [post-classification]
    ├─→ Aggregate all deviz_cod encountered
    ├─→ Count articles per deviz
    ├─→ Normalize keys for cross-validation
    └─→ Save to checkpoint JSON
    ↓
local_run.py
    ├─→ Load reference checkpoint
    ├─→ Extract articles with validated deviz codes
    └─→ Log validation results
```

### 7. Error Handling

- **No Obiectul found**: Use Categoria alone if available (less preferred but functional)
- **No Categoria found**: Use Obiectul alone (less preferred but functional)
- **Neither found**: Return empty string (fallback to inheritance or existing logic)
- **Invalid format**: Log warning, return empty string gracefully
- **Checkpoint creation fails**: Log error, continue extraction (non-blocking)
- **Checkpoint validation fails**: Log discrepancy, allow extraction (warn user)

---

## Success Criteria

1. ✓ Compound deviz codes ("4.1-03") are extracted and articles grouped correctly
2. ✓ Explicit "Deviz Oferta" codes still take priority and work as before
3. ✓ Existing 6-digit code extraction (226XXX) continues to work
4. ✓ Deviz inheritance works for continuation pages without explicit markers
5. ✓ Checkpoint files are created with valid structure and complete metadata
6. ✓ No false ARTICOL_EXTRA entries due to invalid deviz codes
7. ✓ Cross-validation between reference and offers detects mismatches
8. ✓ Backward compatible: all existing test documents still extract correctly

---

## Implementation Files

- **Modified:** `shared/f3_page_classifier.py`
  - Add regex patterns: `_DEVIZ_OFERTA_RE`, `_OBIECTUL_RE`, `_CATEGORIA_RE`
  - Add function: `_extract_compound_deviz(lines: list[str]) -> tuple[str, str, str]`
  - Modify: `classify_page_local()` to call compound extraction
  - Add function: `_build_deviz_checkpoint(results, document_type, source_path) -> dict`
  - Modify: `build_page_classifications()` to create checkpoint

- **Modified:** `local_run.py`
  - Load reference checkpoint before offer processing
  - Pass checkpoint to comparison functions
  - Add validation logging

---

## Testing Strategy

1. **Unit tests:** Test `_extract_compound_deviz()` with sample text (with/without codes)
2. **Integration tests:** Full page classification on test documents (new format + standard format)
3. **Regression tests:** Existing documents (Scoala Sportiva Racari) still extract correctly
4. **Checkpoint validation:** Verify structure and cross-validation works
5. **Manual verification:** Check article grouping and non-conformity reports

---

## Edge Cases Handled

- Multiple Obiectul/Categoria pairs in same document → Each becomes separate deviz group
- Inheritance across 10+ continuation pages → Last known deviz_cod carried forward
- Mixed document (some pages with explicit codes, some with compound) → Both extraction methods coexist
- Empty descriptions → Handled gracefully, code still constructed
- OCR-damaged text → Regex patterns use lookahead/context to avoid partial matches
- Special characters in descriptions → Normalized in checkpoint (whitespace cleanup)

