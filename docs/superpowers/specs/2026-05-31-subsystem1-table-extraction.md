# Subsystem 1: Table-Native Extraction with Parallel Learning — Specification

**Date:** 2026-05-31  
**Status:** APPROVED  
**Scope:** Replace regex-based article extraction with Azure DI table→cells parsing. Run table + regex in parallel, pick best match. Output includes source metadata for subsystem 4 (autonomous agent) to learn from.

---

## Business Goal

Current extraction (`f3_regex_parser`) is fragile with OCR artifacts and page layout variations. Build robust, table-aware extraction that:
1. Uses Azure Document Intelligence table structure when available
2. Falls back to regex for free-form pages
3. Outputs confidence scores + source metadata
4. Enables subsystem 4 (autonomous agent) to learn which extraction methods work best per document template

---

## Architecture

### Data Flow

```
input_AO/{ClientName}/di_*.json
         ↓
   [TEMPLATE_DETECTOR]
   ├─ Fingerprint page structure (# cols, header patterns, table markers)
   ├─ Assign template_id (e.g., "BR_CONSOLIDATED", "DT_STREETS")
   └─ Store fingerprint in extraction_fingerprints.json
         ↓
   [PARALLEL EXTRACTION] (per page)
   ├─ PATH A: TABLE_EXTRACTOR (if DI table present)
   │   ├─ Parse cells by rowIndex/columnIndex
   │   ├─ Detect hierarchy (merged cells, indentation, grouping)
   │   ├─ Extract: NR, DESCRIERE, UM, CANT
   │   └─ Output: articles + confidence=HIGH
   │
   └─ PATH B: REGEX_EXTRACTOR (always)
       ├─ Use refactored f3_regex_parser
       ├─ Extract: NR, DESCRIERE, UM, CANT
       └─ Output: articles + confidence=MEDIUM
         ↓
   [EXTRACTION_COMPARATOR]
   ├─ Score both extractions (by count, name similarity, structure)
   ├─ Pick winner (TABLE/REGEX/HYBRID)
   └─ Output: merged articles + metadata
         ↓
   [METADATA_LOGGER]
   ├─ Log per-page: which method won, scores, template_id
   └─ Store in extraction_log.json
         ↓
   output_AO/{ClientName}/
     ├─ articole_v2.json (new format with comparison metadata)
     ├─ extraction_log.json (per-page source + confidence)
     └─ extraction_fingerprints.json (learned templates)
```

---

## Components

### 1. TemplateDetector (`shared/template_detector.py`)

**Purpose:** Identify document structure type to guide extraction logic.

**Input:** DI page structure (tables, text blocks, layout positions)

**Output:** `{template_id, fingerprint_hash, certainty}`

**Logic:**
- Inspect first 3-5 pages of DI file
- Extract fingerprint: `{num_tables, num_cols_primary_table, header_row_idx, text_density, grouping_pattern}`
- Lookup fingerprint in `extraction_fingerprints.json`
- If match found: `template_id = "BR_CONSOLIDATED"` (etc.), certainty=HIGH
- If no match: `template_id = "UNKNOWN"`, certainty=LOW (fallback to standard extraction)
- Append new fingerprints to `extraction_fingerprints.json` for future learning

**Examples:**
- Blocuri Racari: 4-column table, header row 0, dense grouping → `"BR_CONSOLIDATED"`
- Drum Tatarani: Multiple 3-column tables per street, sparse → `"DT_STREETS"`
- Camin Maneciu: Mixed table + free-form → `"CM_MIXED"`
- Scoala Dragomiresti: Dense 5-column table → `"SDR_DENSE"`

---

### 2. TableExtractor (`shared/table_extractor.py`)

**Purpose:** Extract articles from Azure DI table structure.

**Input:** DI table (cells with rowIndex, columnIndex, values)

**Output:** `{articles: [], hierarchy_map: {}, confidence: float}`

**Logic:**

1. **Identify parent rows:**
   - Merged cells spanning multiple rows → parent
   - Structural break (blank row or category header) → new group
   - Column 0 contains group code (e.g., "0042 BLOC A") → parent

2. **Identify child rows:**
   - Rows indented relative to parent (column offset)
   - Rows with sub-item numbering (e.g., "1.1", "1.2")
   - Rows grouped under parent by proximity + structure

3. **Extract article fields:**
   - NR: Column 0 (or heuristic for hierarchy)
   - DESCRIERE: Column 1-2 (concatenate if needed)
   - UM: Lookup in UM_KNOWN, normalize
   - CANT: Parse column N as float, handle OCR variants

4. **Confidence calculation:**
   - All fields present + valid: 0.95-1.0
   - Some fields missing or normalized: 0.80-0.95
   - Uncertain hierarchy: 0.70-0.80

---

### 3. RegexExtractor (Refactored `shared/f3_regex_parser.py`)

**Purpose:** Extract articles from free-form text (fallback for non-table pages).

**Input:** Page text (OCR output)

**Output:** `{articles: [], confidence: float}`

**Changes from v1:**
- Add `confidence` field to output (default MEDIUM = 0.65-0.75)
- Adjust confidence based on OCR quality (clean text vs. artifacts)
- Keep all existing patterns: NR_SUBITEM, SKIP_RE, UM_KNOWN
- Output same article schema as TableExtractor

---

### 4. ExtractionComparator (`shared/extraction_comparator.py`)

**Purpose:** Choose best extraction method (TABLE vs REGEX) or merge results.

**Input:** 
- articles_table: `{articles: [], confidence: float}`
- articles_regex: `{articles: [], confidence: float}`

**Output:** `{articles: [], source: "TABLE" | "REGEX" | "HYBRID", confidence: float}`

**Logic:**

1. **If table returned 0 articles:** Use REGEX (source=REGEX, confidence=regex_confidence)

2. **If regex returned 0 articles:** Use TABLE (source=TABLE, confidence=table_confidence)

3. **If both returned articles:**
   - Compare by count: `abs(table_count - regex_count) <= 2` → similar counts
   - Compare by name: Use RapidFuzz on DESCRIERE fields, threshold 0.85
   - If similar: Pick higher confidence (source=TABLE or REGEX)
   - If different: Merge hybrid (take table articles, backfill missing from regex)

**Example:**
- TABLE: 12 articles, confidence 0.95
- REGEX: 12 articles, confidence 0.70
- → Use TABLE (source=TABLE, confidence=0.95)

---

### 5. MetadataLogger (`shared/extraction_v2.py`)

**Purpose:** Log extraction details for subsystem 4 (autonomous agent) to learn from.

**Output:** `extraction_log.json` with per-page entries:

```json
{
  "client": "Blocuri Racari",
  "pages": [
    {
      "page_idx": 0,
      "template_id": "BR_CONSOLIDATED",
      "source_won": "TABLE",
      "table_article_count": 12,
      "regex_article_count": 12,
      "confidence_table": 0.95,
      "confidence_regex": 0.70,
      "matching_readiness": {
        "all_descriere_normalized": true,
        "all_cant_numeric": true,
        "all_um_normalized": true,
        "parsing_issues": 0
      },
      "note": "Perfect match — TABLE won"
    }
  ]
}
```

---

## Output Schema

### articole_v2.json

```json
{
  "client": "Blocuri Racari",
  "di_file": "di_referinta.json",
  "extraction_version": "2.0",
  "template_id": "BR_CONSOLIDATED",
  "grupos": [
    {
      "deviz_cod": "0042",
      "deviz_den": "BLOC A - Obiect 1",
      "source_pages": [0, 1, 2],
      "articole": [
        {
          "nr": "1",
          "descriere": "CIMENT CEM II/A-S 42.5",
          "um": "T",
          "cant": "125",
          
          // Extraction source + confidence
          "extraction_source": "TABLE",
          "confidence": 0.95,
          
          // Hierarchy
          "parent_nr": null,
          "is_component": false,
          
          // Comparison metadata (for subsystems 2-3)
          "descriere_normalized": "ciment cem ii a s 42 5",
          "um_normalized": "t",
          "cant_numeric": 125.0,
          "comparison_key": "1_ciment_cem_ii_a_s_42_5"
        },
        {
          "nr": "1.1",
          "descriere": "Transport",
          "um": "T",
          "cant": "10",
          "extraction_source": "REGEX",
          "confidence": 0.75,
          "parent_nr": "1",
          "is_component": true,
          "descriere_normalized": "transport",
          "um_normalized": "t",
          "cant_numeric": 10.0,
          "comparison_key": "1_1_transport"
        }
      ]
    }
  ]
}
```

### extraction_fingerprints.json

```json
{
  "templates": [
    {
      "template_id": "BR_CONSOLIDATED",
      "fingerprint": {
        "num_tables": 1,
        "num_cols_primary": 4,
        "header_row_idx": 0,
        "text_density": "high",
        "grouping_pattern": "merged_cells"
      },
      "clients": ["Blocuri Racari", "BR BLOC A", "BR BLOC B"],
      "accuracy": 0.98,
      "last_seen": "2026-05-31"
    },
    {
      "template_id": "DT_STREETS",
      "fingerprint": {...},
      "clients": ["Drum Tatarani"],
      "accuracy": 0.95,
      "last_seen": "2026-05-31"
    }
  ]
}
```

---

## Testing Strategy

### Unit Tests

1. **TemplateDetector:**
   - Test fingerprinting on real DI files (all 4 clients)
   - Verify template_id assignment consistency
   - Test unknown template fallback

2. **TableExtractor:**
   - Test hierarchy detection (merged cells, indentation, grouping)
   - Test article field extraction (NR, DESCRIERE, UM, CANT)
   - Test confidence calculation
   - Test OCR variants (merged cells with extra spaces, etc.)

3. **RegexExtractor:**
   - Ensure backward compatibility with v1 extraction
   - Add confidence field to all outputs
   - Test OCR artifact handling

4. **ExtractionComparator:**
   - Test pick-best logic (TABLE vs REGEX)
   - Test hybrid merge (when counts differ by ≤2)
   - Test RapidFuzz scoring (threshold 0.85)

5. **MetadataLogger:**
   - Verify extraction_log schema completeness
   - Test fingerprint persistence (append to extraction_fingerprints.json)

### Integration Tests

1. **End-to-end on all 4 verified clients:**
   - Run extraction_v2 on referinta + each oferta
   - Verify articole_v2.json structure
   - Verify extraction_log completeness
   - Regression: article counts should match v1 (or explain differences)

2. **Parallel extraction comparison:**
   - For pages with both table + regex: verify TABLE wins appropriately
   - For pages with only regex: verify REGEX is chosen

3. **Template learning:**
   - Run on new client → learn new template_id
   - Verify fingerprint saved to extraction_fingerprints.json
   - Next run on same client → reuses learned template

### Validation Tests

1. **Golden path (referinta extraction):**
   - referinta.json → articole_v2.json ✅
   - extraction_log.json complete + readable ✅
   - No crashes on OCR variants ✅

2. **Regression check:**
   - Article counts vs. v1 extraction (should be ≥95% match)
   - If differences found: inspect extraction_log to understand why

3. **All clients + SSR:**
   - Blocuri Racari ✅
   - Camin Maneciu ✅
   - Scoala Dragomiresti ✅
   - Drum Tatarani ✅
   - Scoala Sportiva Racari ✅ (or identify known issues)

---

## Files to Create/Modify

**Create:**
- `shared/template_detector.py` — Template fingerprinting
- `shared/table_extractor.py` — DI table extraction
- `shared/extraction_comparator.py` — Pick-best logic
- `shared/extraction_v2.py` — Orchestrator (entry point)
- `tests/test_table_extractor.py` — Unit tests
- `tests/test_template_detector.py` — Unit tests
- `tests/test_extraction_v2_integration.py` — Integration tests

**Modify:**
- `shared/f3_regex_parser.py` — Add confidence field, keep as fallback
- `local_run.py` — Import extraction_v2 instead of f3_regex_parser
- `multi_client_run.py` — Use extraction_v2

**Output directories:**
- `output_AO/{ClientName}/` — articole_v2.json, extraction_log.json, extraction_fingerprints.json

---

## Success Criteria

- ✅ All 5 clients extract with 0 crashes
- ✅ Article counts match v1 (≥95% for regression clients)
- ✅ Confidence scores are reasonable (TABLE > REGEX for table pages)
- ✅ extraction_log complete + usable by subsystem 4
- ✅ New templates learned + saved to fingerprints.json
- ✅ Unit test coverage ≥80%
- ✅ Integration tests pass on all 5 clients

---

## Dependencies

- **Input:** Azure DI JSON (tables + text)
- **Output:** articole_v2.json + extraction_log.json
- **Subsystem 2 (Hierarchy Alignment)** consumes: articole_v2.json + comparison metadata
- **Subsystem 4 (Autonomous Agent)** consumes: extraction_log.json + fingerprints for learning

---

## Risk Mitigation

1. **Regression risk:** Extract to articole_v2.json (separate file, not overwriting v1 output). Can compare both.
2. **Template risk:** Unknown templates fall back to standard extraction (no crash).
3. **Confidence risk:** Scores are heuristic-based. Subsystem 4 learns what scores correlate with accuracy.
4. **Restore point:** Tag current main as `v1-stable-20260531` before starting implementation.

