---
title: Hierarchical Component System - End-to-End Design
date: 2026-05-17
author: Design Brainstorming Session
status: Draft
---

# Hierarchical Component System (A + B + C)

## Executive Summary

Refactor extraction, matching, and reporting to properly handle hierarchical component structures. Components appear both in reference (as subcomponent codes in array) and in offer (as separate line items). The system must:

1. **Detect pattern** (diverse formats: MANECIU, DRAGOMIRESTI, SPORTIVA, etc.)
2. **Extract with parent-child links** (parent_code field connects components to parents)
3. **Match identically** (all articles use deviz+cod pair, regardless of parent status)
4. **Report with hierarchy** (DOCX shows components indented under parents)

---

## 1. Pattern Detection & Learning (Pass 1)

### Overview
Offer documents use diverse component notation:
- MANECIU: `L:SL05 -0020:6717077` (prefixed format)
- DRAGOMIRESTI: `1.1`, `1.2` under parent `1` (hierarchy numbering)
- SPORTIVA: `material:`, `manopera:` sections (section headers)
- Variants: Full-text indentation, mixed formats

### Process

```
Input: Offer document + checkpoint (if exists)
│
├─ Identify chapter boundaries (STADIUL FIZIC: deviz_code)
├─ Load known patterns from pattern library
├─ For FIRST UNPROCESSED chapter:
│  ├─ Extract ENTIRE chapter text (full scope, not sampling)
│  ├─ Try match vs known patterns (scan full chapter)
│  │  ├─ Match found (confidence > 0.70)?
│  │  │  └─ Save pattern_name + confidence to checkpoint
│  │  └─ No match or low confidence?
│  │     └─ LLM analyze FULL chapter 
│  │        → generate template 
│  │        → save as NEW pattern in library
│  └─ Subsequent chapters (in same offer): reuse detected pattern
│
└─ Output: checkpoint with (pattern_name, confidence, extraction_rules)
```

### Pattern Template (JSON)

```json
{
  "name": "MANECIU",
  "description": "Prefixed subcomponent format with L: marker",
  "confidence": 0.95,
  "parent_indicators": [
    "^\\d+\\s+[A-Z0-9]+"
  ],
  "component_indicators": [
    {
      "pattern": "^\\d+\\.\\d+\\s+",
      "type": "hierarchy",
      "description": "Dotted numbering: 1.1, 1.2 under parent 1"
    },
    {
      "pattern": "^L:\\s*[A-Z0-9]+\\s+-",
      "type": "prefix",
      "description": "Prefixed format: L:SL05 -0020:6717077"
    },
    {
      "pattern": "material:|manopera:|utilaj:|transport:",
      "type": "section_header",
      "description": "Section separators for cost categories"
    }
  ],
  "quantity_rule": "inherit_from_parent",
  "extraction_rules": {
    "parent_cod_extraction": "group(1) from parent_pattern",
    "component_cod_extraction": "group(1) from component_pattern",
    "parent_detection": "first match in section",
    "component_grouping": "all following until next parent"
  }
}
```

### Checkpoint Storage

Checkpoint file (`di_oferta_N.json.checkpoint`) includes:
```json
{
  "pattern_detection": {
    "4.3-07": {
      "pattern_name": "MANECIU",
      "confidence": 0.92,
      "detected_at": "2026-05-17T20:00:00Z"
    }
  },
  "extraction_status": "pass_1_complete"
}
```

---

## 2. Extraction Architecture (Pass 2) - Pattern-Based

### Flow

```
Input: Offer document + detected pattern from checkpoint
│
├─ Load pattern rules from checkpoint
├─ Parse text lines (existing parser)
├─ For each line, apply pattern-specific rules:
│  │
│  ├─ Is PARENT?
│  │  ├─ Extract: cod, denumire, um, cantitate, deviz
│  │  ├─ parent_code = null
│  │  ├─ is_component = false
│  │  └─ Save article
│  │
│  └─ Is COMPONENT?
│     ├─ Extract: cod, denumire
│     ├─ parent_code = last_parent_cod
│     ├─ is_component = true
│     ├─ Quantity logic:
│     │  ├─ If reference component has explicit qty
│     │  │  └─ Use reference qty
│     │  ├─ Else if parent has qty
│     │  │  └─ Inherit from parent
│     │  └─ Else
│     │     └─ qty = 0
│     ├─ Unit:
│     │  ├─ If offer has explicit unit
│     │  │  └─ Use offer unit
│     │  └─ Else
│     │     └─ Inherit from parent
│     └─ Save article
│
└─ Output: articles[] with parent_code + is_component fields
```

### Data Model Changes

**Article Structure (NEW/UPDATED fields):**

```python
{
  # Existing fields
  "cod": "6717077",
  "denumire": "teava polietilena inalta densitate...",
  "um": "m",
  "cantitate": 2.0,
  "deviz": "4.3-07",
  "deviz_denumire": "Conducte apa incinta",
  
  # NEW fields
  "parent_code": "SA14J",        # null for parents, cod for components
  "is_component": true,          # false for parents, true for components
  
  # Existing but UPDATED semantics
  "subcomponents": []            # Only parents have non-empty; components always []
}
```

**Example: SA14J with components**

Reference extraction:
```json
{
  "cod": "SA14J",
  "parent_code": null,
  "is_component": false,
  "subcomponents": ["6717077", "6719428", "6719435", "0003000"],
  "um": "m",
  "cantitate": 2.0
}
```

Offer extraction (new):
```json
{
  "cod": "SA14J",
  "parent_code": null,
  "is_component": false,
  "subcomponents": [],
  "um": "m",
  "cantitate": 2.0
},
{
  "cod": "6717077",
  "parent_code": "SA14J",
  "is_component": true,
  "subcomponents": [],
  "um": "m",
  "cantitate": 2.0  // inherited from parent
},
{
  "cod": "6719428",
  "parent_code": "SA14J",
  "is_component": true,
  "subcomponents": [],
  "um": "buc",
  "cantitate": 2.0  // inherited from parent
}
```

---

## 3. Matching Logic (Section B) - Unified

### Single Matching Rule

**All articles (parent or component) use identical rule:**

```
For each article (parent_code=null or parent_code=something):
│
├─ Match on (deviz, cod) pair
│  ├─ Find reference article with same deviz + same cod
│  ├─ If found: Check consistency
│  │  ├─ UM match?
│  │  ├─ Cantitate match?
│  │  ├─ If all OK: MATCHED
│  │  └─ If diff: UM_DIFERIT, CANTITATE_DIFERITA
│  └─ If not found: ARTICOL_EXTRA (offer) or ARTICOL_LIPSA (reference)
│
└─ parent_code is ONLY for reporting/hierarchy, not matching logic
```

### Why Unified?

Because **components inherit quantity from parent**, all articles have a quantity value. Therefore:
- No special case for components
- No "missing quantity = orphan" logic
- Matching is deterministic and simple

---

## 4. Reporting (Section C) - DOCX with Hierarchy

### Keep Existing Format, Add Markers

**DOCX Report - Enhanced Output:**

```
4.3-07: Conducte apa incinta
─────────────────────────────

SA14J - TEAVA DIN MATERIAL PLASTIC PE, D=110MM
M | 2.00 | ✓ MATCH

  └─ [COMPONENT] 6717077 (parent: SA14J)
     TEAVA POLIETILENA INALTA DENSITATE, PE100, PN10, DEXT 110
     M | 2.00 | ✓ MATCH

  └─ [COMPONENT] 6719428 (parent: SA14J)
     MUFA POLIETILENA, INALTA DENSITATE, ELECTROFUZIUNE, D=110
     BUC | 2.00 | ✓ MATCH

  └─ [COMPONENT] 6719435 (parent: SA14J)
     COT POLIETILENA, INALTA DENSITATE, ELECTROFUZIUNE, D=110
     BUC | 2.00 | ✓ MATCH

  └─ [COMPONENT] 0003000 (parent: SA14J)
     APARAT DE SUDURA PRIN POLIFUZIUNE SI ELECTROFUZIUNE
     ORE | 0.60 | ✓ MATCH
```

### Visual Markers (Minimal)

- **Indentation**: 2 spaces for components
- **Prefix**: `[COMPONENT]` before code
- **Parent ref**: `(parent: SA14J)` after code
- **No collapsing/expanding**: Linear list with visual nesting

### JSON Report (Internal)

Structure for programmatic processing:

```json
{
  "deviz": "4.3-07",
  "articles": [
    {
      "parent_article": {
        "ref_cod": "SA14J",
        "oferta_cod": "SA14J",
        "matched": true,
        "issues": []
      },
      "components": [
        {
          "ref_cod": "6717077",
          "oferta_cod": "6717077",
          "parent_code": "SA14J",
          "matched": true,
          "issues": []
        },
        ...
      ]
    }
  ]
}
```

---

## 5. Files to Modify

### Core Extraction
- `shared/f3_regex_parser.py`: Update `_make_article()` signature, add parent_code + is_component fields
- `shared/f3_extractor.py`: Add pattern detection Pass 1, integrate checkpoint
- `shared/subcomponent_formats.py`: Extend with new pattern templates (LLM-generated)

### Matching
- `AgentComparator_local.py`: Update matching logic (should be minimal - already uses deviz+cod)
- `shared/deviz_matcher.py`: No changes needed (matching unchanged)

### Reporting
- `shared/report_word.py`: Update DOCX generation to:
  - Detect parent_code in articles
  - Group components under parents
  - Add [COMPONENT] prefix + indentation + parent ref

### Testing
- `tests/`: Add tests for:
  - Pattern detection (known patterns)
  - Pattern generation (LLM fallback)
  - Component extraction (parent_code assignment)
  - Hierarchical matching
  - DOCX rendering with components

---

## 6. Success Criteria

- ✓ SA14J extracted with 4 component articles (6717077, 6719428, 6719435, 0003000)
- ✓ Each component has parent_code="SA14J"
- ✓ All components inherit quantity from parent (2.0, 2.0, 2.0, 0.6)
- ✓ Matching uses (deviz, cod) pair for all articles
- ✓ DOCX shows hierarchy: parent + indented components with parent ref
- ✓ Unknown patterns trigger LLM → new template saved
- ✓ No $ prefix in component codes (clean codes)

---

## 7. Constraints & Assumptions

- **Quantity inheritance**: If reference component has no explicit qty, inherit from parent (applies to both reference and offer)
- **Pattern library**: Grows over time (LLM-generated templates)
- **Checkpoint**: Persists pattern detection (avoid re-detecting same document)
- **Component detection**: Pattern-based (no heuristics or guessing)
- **Matching**: Unchanged (deviz+cod pair for all articles)

---

## 8. Risk & Mitigation

| Risk | Mitigation |
|------|-----------|
| LLM generates incorrect pattern | Manual review + test before adding to library |
| Component cod collides with parent | Codes are unique (design assumption) |
| Quantity inheritance causes mismatch | Reference determines source of truth |
| DOCX rendering breaks with deep hierarchies | Currently 2-level only (parent + components) |

---

## 9. Future Enhancements (Out of Scope)

- Multi-level hierarchy (components with sub-components)
- Expandable/collapsible sections in DOCX
- Excel export with hierarchy columns
- Component matching by denomination (fallback)

