# Architecture - Analizator Local Oferte Constructii

## Overview

System for extracting and comparing construction articles from Document Intelligence (DI) JSON files containing building estimates (devize).

**Pipeline**: DI JSON → Page Classification → Grouping Key Extraction → Article Extraction → Comparison & Reports

---

## Core Components

### 1. Page Classification (`shared/f3_page_classifier.py`)

**Responsibility**: Identify F3 pages and extract their deviz grouping codes

**Two-Phase Algorithm**:

#### Phase 1A: Fast Page Type Detection
- Checks for F3 markers: "Formular F3", "SECTIUNEA TEHNICA", "STADIUL FIZIC"
- Detects non-F3 pages: summaries, recaps, footers
- Output: `is_f3` boolean for each page

#### Phase 1B: Grouping Key Extraction (Three-Tier Priority)
```
Tier 1: Explicit "Deviz Oferta XXXXX"
  Pattern: Deviz\s+Oferta\s+([A-Z0-9]{5,8})
  Returns: "226348" (direct code)
  Use case: Standard eDevize format

Tier 2: Compound "Obiectul-Categoria"
  Pattern 1: Obiectul\s*:\s*([0-9.]+)\s*(.+?)
  Pattern 2: Categoria\s+de\s+lucrari\s*:\s*([0-9]{2,4})\s*(.+?)
  Returns: "4.1-03" (e.g., 4.1 + 03)
  Use case: New format, numeric prefixes present

Tier 3: Partial Text-Only (LLM Fallback)
  Pattern: Same as Tier 2, but numeric parts missing
  Returns: "__partial__:{obj_text}:{cat_text}"
  Use case: New format, no numeric prefixes

Tier 4: None
  Returns: "" (empty code, page will be filtered)
```

**State Management**:
- `current_deviz_cod`: Carries across continuation pages
- `current_obiectul`, `current_categoria`: Metadata for LLM resolution
- Inheritance: If a page lacks grouping markers, inherits from previous page

#### Phase 2: LLM Resolution (When Needed)
- Triggered when `__partial__` sentinels detected
- Collects unique (obiectul_text, categoria_text) pairs
- Sends to LLM for semantic matching against reference deviz groups
- Results:
  - Match found: Replace sentinel with reference code (e.g., "4.1-03")
  - No match: Use fallback (first word of categoria text, max 20 chars)

### 2. Article Extraction (`shared/f3_extractor.py`, `shared/f3_regex_parser.py`)

**Responsibility**: Extract individual articles from F3 pages

**Two Extraction Methods**:

#### Method A: Regex Parsing (Line-Based)
- **File**: `shared/f3_regex_parser.py`
- **Approach**: State machine parsing of text lines
- **Handles**:
  - Codes: numeric (226348), alphanumeric (SE56A, IA22C1), normative (ASIM, TSCH)
  - Quantities: integer, decimal with . or , separators
  - UM: validated against whitelist (BUC, M, MP, MC, KG, ORA, etc.)
  - Prices: 8-field structure (material, manopera, utilaj, transport × cost + value)
  - Multi-line articles: codes on one line, description on next, etc.

#### Method B: Table Extraction
- **File**: `shared/table_extractor.py`
- **Two Strategies**:
  1. `extract_articles_from_tables()`: Extract with explicit deviz code parameter
  2. `extract_articles_from_tables_smart()`: Infer deviz from metadata tables

**UM Normalization** (CRITICAL - Fixed in v6):
- Remove dots: "M.C." → "MC"
- Remove numeric prefixes: "99 M" → "M" (was bug, now fixed)
- Validate against whitelist
- Fallback to empty if invalid

### 3. Comparison (`shared/deviz_reconciler.py`, `shared/deviz_namer.py`)

**Responsibility**: Match offer articles to reference and generate reports

**Process**:
1. Load reference articles (source of truth)
2. For each offer:
   - Group by deviz code
   - Match articles by (code, UM, quantity)
   - Detect: matched, missing (lipsa), extra, orphaned, near-matches
   - Generate DOCX report with analysis
   - Generate JSON comparison by deviz

**Matching Logic**:
- Primary: (code, UM, quantity) exact match
- Secondary: Code + quantity match (UM different)
- Tertiary: Fuzzy match (code similarity)
- Fallback: Manual deviz reconciliation (search reference for missing codes)

---

## Data Flow

```
input_AO/
  ├── di_referinta.json
  └── di_oferta_N.json
         ↓
classify_pages()
  ├── classify_page_local() × N pages
  │   └─ extract_grouping_key() [3-tier priority]
  ├─ _resolve_partial_keys_with_llm() [if needed]
  └─ Returns: [page_classes], checkpoint
         ↓
extract_articles_v3()
  ├── Group pages by deviz_cod
  ├── Extract from lines [regex parser]
  ├── Extract from tables [smart table parser]
  └── Deduplicate, filter invalid UM
         ↓
output_AO/
  ├── referinta.json [458 articles, 33 devizes]
  ├── oferta_1.json [1097 articles, 35 devizes]
  ├── oferta_2.json [1046 articles, 49 devizes]
  ├── Raport_Oferta_*.docx [formatted comparison]
  └── comparatie_oferta_*.json [by-deviz analysis]
```

---

## Key Files

### Core Logic
| File | Purpose |
|------|---------|
| `shared/f3_page_classifier.py` | Page classification + deviz key extraction |
| `shared/f3_regex_parser.py` | Line-based article extraction (state machine) |
| `shared/table_extractor.py` | Table-based article extraction |
| `shared/f3_extractor.py` | Article grouping + deduplication |
| `shared/deviz_reconciler.py` | Missing deviz resolution |
| `local_run.py` | Main pipeline orchestration |

### Supporting
| File | Purpose |
|------|---------|
| `shared/deviz_namer.py` | Populate denominations from DI reference |
| `shared/deviz_normalizer.py` | Normalize deviz codes (U→0, etc.) |
| `shared/report_json.py` | Generate comparison JSON by deviz |
| `anthropic_adapter.py` | OpenAI-compatible wrapper for Anthropic API |

### Configuration
| File | Purpose |
|------|---------|
| `.env` | API keys and model selection |
| `input_AO/` | Input DI JSON files |
| `output_AO/` | Extracted articles and reports |
| `output_AO/checkpoints/` | Cached page classifications |

---

## Key Design Decisions

### 1. Two-Phase Grouping Key Extraction
- **Why**: Different document formats need different strategies
- **Benefit**: General algorithm handles explicit codes, compound codes, and text-only
- **Trade-off**: LLM fallback adds cost but eliminates invalid "CAMINE" codes

### 2. State Machine for Article Parsing
- **Why**: F3 articles span multiple lines with complex formatting
- **Benefit**: Handles OCR corruption, multi-line descriptions, variable column order
- **Trade-off**: Complex state logic but more robust than regex-only

### 3. Table-Based Article Priority
- **Why**: Tables have structured, reliable data
- **Benefit**: Accurate extraction when table format is consistent
- **Trade-off**: Some documents mix table + line formats (handled with merging)

### 4. UM Whitelist Validation
- **Why**: OCR produces garbage values
- **Benefit**: Only known units accepted, invalid values skipped
- **Trade-off**: May skip rare units (e.g., MM explicitly excluded per design)

### 5. Checkpoint Caching
- **Why**: LLM classification is slow (2-5 min)
- **Benefit**: Re-running pipeline skips LLM for cached documents
- **Trade-off**: Stale cache if classifier code changes (hash-based invalidation)

---

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| Page classification (LLM) | 2-5 min | Cached if classifier code unchanged |
| Article extraction | <30 sec | Regex + table parsing combined |
| Comparison | <1 min | Matching + report generation |
| **Total pipeline** | **3-6 min** | First run; <1 min if cached |

## Data Quality Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Invalid codes (CAMINE/CAMIN) | 0 | Eliminated by LLM fallback |
| UM corruption | 0% | Fixed v6 (removed numeric prefixes) |
| Compound codes (ref) | 33/33 | 100% successful extraction |
| Compound codes (offer) | 34/49 | 69% from LLM, 31% fallback |
| Article matching (O1 vs ref) | 450/1097 | 41% match; rest extra/missing |

---

## Extension Points

### Adding New Document Formats
1. Add pattern to `_STADIUL_FIZIC_RE` or create new `_FORMAT_X_RE`
2. Update `classify_page_local()` Phase B detection
3. Test with sample DI JSON

### Customizing Article Extraction
1. Modify regex patterns in `f3_regex_parser.py` (COD_*, UM_RE, etc.)
2. Add new state transitions in parsing state machine
3. Update `UM_KNOWN` whitelist if new units needed

### Improving LLM Resolution
1. Refine system prompt in `_resolve_partial_keys_with_llm()`
2. Add semantic clustering of reference deviz groups
3. Implement confidence scoring for matches

---

## Known Limitations & Future Work

### Current Limitations
- ~49% of reference articles have empty UM (source doesn't provide)
- LLM resolution ~30% success rate (semantic ambiguity)
- No handling of deviz split/merge between reference and offers
- Comparison assumes 1:1 deviz mapping (not hierarchical)

### Future Improvements
- [ ] Machine learning for UM inference from denomination
- [ ] Hierarchical deviz matching (parent-child relationships)
- [ ] Batch article reconciliation (handle bulk changes)
- [ ] Price validation (detect unrealistic unit costs)
- [ ] Incremental classification (only re-classify changed pages)

---

**Version**: v6 (2026-05-15)
**Last Updated**: Two-phase compound deviz extraction complete, UM bug fixed
