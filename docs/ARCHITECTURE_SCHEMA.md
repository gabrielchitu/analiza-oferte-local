# Architecture Schema — Diagrama Completă a Fluxului

**Data:** 2026-05-19  
**Versiune:** v6.1 cu scattered format, lenient matching, S474 variant fix

---

## Flux Principal — Big Picture

```
┌─────────────────────────────────────────────────────────────────┐
│  INPUT: DI JSON Files (OCR → JSON)                              │
│  - di_referinta.json (reference specification)                 │
│  - di_oferta_1.json, di_oferta_2.json, etc. (offers)           │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 1: PAGE CLASSIFICATION (f3_page_classifier.py)           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Heuristic rules (FORMULAR C, RECAPITULATIE, STADIUL) │   │
│  │ 2. Deviz code extraction from "STADIUL FIZIC" regex     │   │
│  │ 3. LLM classification for ambiguous pages               │   │
│  │ 4. Checkpoint caching (hash-based, auto-invalidates)    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Output: page_classifications                                  │
│  ├── page_number: int                                          │
│  ├── is_f3: bool                                               │
│  ├── deviz_cod: str (e.g., "226208")                          │
│  ├── deviz_den: str (e.g., "STRUCTURA DE REZISTENTA")         │
│  └── _reclf_checked: bool (LLM verification done)             │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 2: ARTICLE EXTRACTION (f3_regex_parser.py)              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Step 2.1: Preprocessors (before regex parsing)          │   │
│  │  ├─ Scattered format detection (code on own line)       │   │
│  │  │   Pattern: counter → code → UM → qty → description  │   │
│  │  │   Transform: "4 5102437 - description" format        │   │
│  │  │   +44 articles from referinta (May 2026)             │   │
│  │  │                                                      │   │
│  │  └─ Variant code skip pattern ([A-Z]\d{3,5})           │   │
│  │      Prevents S474, S475 extraction as articles         │   │
│  │                                                         │   │
│  │ Step 2.2: Regex State Machine (extract_articles_regex) │   │
│  │  ├─ Detect: cod articol, UM, cantitate, denumire       │   │
│  │  ├─ Support: multi-line descriptions                   │   │
│  │  ├─ Support: linked articles (bare numeric + L marker) │   │
│  │  └─ Support: components from $ breviary (>>> pattern)  │   │
│  │                                                         │   │
│  │ Step 2.3: Table Extraction (table_extractor.py)        │   │
│  │  ├─ Metadata detection (STADIUL FIZIC table)           │   │
│  │  ├─ Data table extraction (SECTIUNEA TEHNICA)          │   │
│  │  ├─ Deviz linking from preceding metadata              │   │
│  │  └─ Format 3 orphan table detection                     │   │
│  │                                                         │   │
│  │ Step 2.4: Per-page dedup by (cod, deviz)               │   │
│  │  └─ Keep article with maximum quantity                 │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Output: extracted_articles (per document)                      │
│  ├── cod: str (article code, e.g., "$5102437")                │
│  ├── deviz_cod: str (category code, e.g., "226208")           │
│  ├── deviz_den: str (category name)                           │
│  ├── denumire: str (article description)                      │
│  ├── um: str (unit of measure, normalized)                    │
│  └── cantitate: float (quantity)                              │
└──────────────┬──────────────────────────────────────────────────┘
               │
               │ ┌──────────────────────────┐
               │ │  For offers only:        │
               │ │  Filter to ref_devize    │
               │ │  (ignore extra sections) │
               │ └──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 3: DEVIZ NORMALIZATION                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. OCR fix: O→0, l→1, Il→11                             │   │
│  │ 2. Fuzzy matching: detect "226207" vs "226208" (90%+)   │   │
│  │    → auto-map if similarity ≥ 90%                       │   │
│  │ 3. Terminology matching: "Structura" vs "STRUCTURA"     │   │
│  │    → consolidate devizes with minor text differences    │   │
│  │ 4. Update: all articles to unified deviz code           │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 4: UNIT OF MEASURE NORMALIZATION                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Patterns (case-insensitive):                            │   │
│  │  "M CUB" / "M3" / "mp"      → "mc"                      │   │
│  │  "TONE" / "TONA" / "T"      → "tone"                    │   │
│  │  "ORE" / "OREI"             → "ore"                     │   │
│  │  "PERECHE" / "PERECHI"      → "pereche"                 │   │
│  │  "BUC" / "BUC." / "BUCATA"  → "buc"                     │   │
│  │ UM_DIFERIT nonconformity on mismatch (post-matching)    │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 5: ARTICLE MATCHING (6 layers)                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ Layer 1: EXACT MATCH                                    │   │
│  │  └─ (deviz_cod, cod) identical + sort by quantity       │   │
│  │                                                         │   │
│  │ Layer 2: CODE NORMALIZATION                             │   │
│  │  └─ _normalize_cod: O→0, AUT6752→$6752, etc.           │   │
│  │                                                         │   │
│  │ Layer 2.5: FUZZY DETERMINISTIC                          │   │
│  │  └─ Similarity ≥ 85% + Jaccard(name) ≥ 0.4              │   │
│  │                                                         │   │
│  │ Layer 2.6: NAME + UM + QUANTITY                         │   │
│  │  └─ Fallback when code missing or corrupted             │   │
│  │                                                         │   │
│  │ Layer 3: LLM FUZZY (per deviz)                          │   │
│  │  └─ LLM matching within category boundaries             │   │
│  │                                                         │   │
│  │ Layer 4: LLM GLOBAL                                     │   │
│  │  └─ LLM matching across all categories                  │   │
│  │                                                         │   │
│  │ Layer 5: LENIENT UM MATCHING ($ codes, NEW 2026-05-19)  │   │
│  │  └─ Post-process: $ codes with empty UM in ref          │   │
│  │     Convert EXTRA → matched + UM_DIFERIT               │   │
│  │     (client requirement: lenient matching behavior)     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Preprocessing before layers:                                  │
│  ├─ Dedup by 4-tuple: (deviz, cod, um, cantitate)             │
│  └─ Filter artifacts: qty=0 with empty/uppercase UM           │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 6: NONCONFORMITY DETECTION                               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ After matching completes:                               │   │
│  │                                                         │   │
│  │ 1. ARTICOL_LIPSA: ref article with no match in offer   │   │
│  │    └─ Root cause: NOT_EXTRACTED or EXTRACTED_NOT_MATCHED│   │
│  │                                                         │   │
│  │ 2. ARTICOL_EXTRA: offer article with no match in ref   │   │
│  │    └─ Root cause: GENUINE_EXTRA or extraction gap      │   │
│  │       (87% are extraction gaps per 2026-05-19 analysis) │   │
│  │                                                         │   │
│  │ 3. UM_DIFERIT: matched but unit differs                │   │
│  │    └─ Post-lenient-matching: 17 $ codes with empty UM  │   │
│  │       in ref are converted from EXTRA → this status     │   │
│  │                                                         │   │
│  │ 4. DIFERENTA_CAMP: qty/price/other fields differ       │   │
│  │                                                         │   │
│  │ 5. ORPHAN: articol at wrong category (legacy, unused)   │   │
│  └─────────────────────────────────────────────────────────┘   │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────────────────────────────┐
│  PHASE 7: REPORT GENERATION                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ 1. Generate comparatie_oferta_N.json                    │   │
│  │    ├─ Article-by-article comparison                    │   │
│  │    ├─ Nonconformity summaries per category              │   │
│  │    └─ Category (deviz) consolidated metrics             │   │
│  │                                                         │   │
│  │ 2. Generate report_oferta_N.docx (via report_word.py)  │   │
│  │    ├─ Nonconformity table grouped by deviz              │   │
│  │    ├─ LIPSA articles highlighted                        │   │
│  │    ├─ Article-level details                            │   │
│  │    └─ Charts: nonconformities by type                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
│  Output:                                                        │
│  ├─ output_AO/comparatie_oferta_1.json (JSON report)          │
│  ├─ output_AO/report_oferta_1.docx (DOCX document)            │
│  └─ output_AO/referinta.json (extracted reference articles)    │
└──────────────┬──────────────────────────────────────────────────┘
               │
               ▼
        ┌──────────────┐
        │   OUTPUT     │
        └──────────────┘
```

---

## Data Structures — Key Objects

### 1. Article Object (Core Data Model)

```python
@dataclass
class Article:
    cod: str              # Article code: "$5102437", "TSC02D11", "VA02B08"
    deviz_cod: str        # Category code: "226208", "4.1-04"
    deviz_den: str        # Category name: "STRUCTURA DE REZISTENTA"
    denumire: str         # Article description: "ELEMENTE DECORATIVE"
    um: str               # Unit: "buc", "mc", "tone", "ore", "pereche"
    cantitate: float      # Quantity: 22.0, 1.5, etc.
    cant_oferta: float    # Offer qty (for comparison reports)
    
    # Comparison fields (populated during matching):
    match_status: str     # "MATCHED", "EXTRA", "LIPSA"
    nonconformities: List[str]  # ["UM_DIFERIT", "DIFERENTA_CAMP"]
    ref_article: Article | None  # Link to reference (if matched)
```

### 2. Nonconformity Object

```python
@dataclass
class Nonconformity:
    type: str             # "ARTICOL_EXTRA", "ARTICOL_LIPSA", "UM_DIFERIT", etc.
    deviz_cod: str        # Category code
    article_cod: str      # Article code
    reason: str           # Explanation: "ref UM empty → lenient matching"
    severity: str         # "ERROR", "WARNING" (for report formatting)
```

### 3. Checkpoint Entry (Classification Cache)

```python
@dataclass
class CheckpointEntry:
    page_number: int      # 1-indexed
    is_f3: bool           # Is this page F3 format?
    deviz_cod: str        # Detected category code
    deviz_den: str        # Detected category name
    lines: List[str]      # Raw page lines (for reference)
    header_only: bool     # Just headers, no data?
    needs_llm: bool       # Heuristics inconclusive?
    _reclf_checked: bool  # LLM verification done?
```

---

## File Dependencies (Import Graph)

```
local_run.py (orchestrator)
├── f3_page_classifier.py
│   └── anthropic_adapter.py (LLM calls)
├── f3_extractor.py
│   ├── f3_regex_parser.py
│   │   ├── shared/ (utilities)
│   │   └── _preprocess_scattered_format() [NEW 2026-05-19]
│   └── table_extractor.py
├── deviz_reconciler.py
│   └── f3_page_classifier.py (re-scan)
├── deviz_normalizer.py
├── AgentComparator_local.py (matching logic)
│   ├── article_matcher.py (LLM fuzzy)
│   ├── deviz_mismatch_detector.py
│   ├── comparator.py (field-level comparison)
│   ├── orphan_detector.py
│   └── [Layer 5 lenient UM matching post-processing]
└── report_word.py
    └── anthropic_adapter.py

tests/
├── verify_extra_codes.py
├── verify_lipsa_codes.py
├── test_*.py (unit tests)
└── nonconformity_inspector.py (verification utils)
```

---

## Metrics Flow (Tracking Nonconformities)

```
Input: ref_articles (from referinta), offer_articles (from offer)
│
├─ Pre-matching:
│  └─ Dedup (remove 4-tuple duplicates)
│
├─ Layer 1-4 Matching:
│  ├─ matched ← (deviz_cod, cod, UM) pairs found
│  ├─ unmatched_ref ← articles not found in offer
│  └─ unmatched_offer ← articles not found in ref
│
├─ Nonconformity Classification:
│  ├─ LIPSA: unmatched_ref
│  ├─ EXTRA: unmatched_offer
│  └─ (others: UM_DIFERIT, DIFERENTA_CAMP) on matched articles
│
├─ Layer 5 Post-Processing ($ codes):
│  └─ Convert some EXTRA → matched + UM_DIFERIT
│     (when code exists in ref with same deviz but empty UM)
│
└─ Output Metrics:
   ├─ total_nonconformities = LIPSA + EXTRA + UM_DIFERIT + ...
   ├─ per_deviz breakdown
   └─ per_offer summary
```

---

## Decision Points & Heuristics

### Page Classification Heuristic (Phase 1)

```
is_f3 = False
deviz_cod = ""
deviz_den = ""

FOR each page:
  IF contains("FORMULAR C", "FORMULAR F", "CENTRALIZATOR"):
    is_f3 = False
    deviz_cod = ""  ← RESET
    CONTINUE
  
  IF STADIUL FIZIC regex matches (first 3 lines):
    is_f3 = True
    deviz_cod = extract_from_regex()
    CONTINUE
  
  IF ">>> componenta" found (breviary marker):
    is_f3 = True
    deviz_cod = current_deviz_cod (propagate)
    CONTINUE
  
  IF "NNNNNN pag" + articole codes:
    is_f3 = True
    CONTINUE
  
  ELSE:
    is_f3 = AMBIGUOUS
    needs_llm = True
    → LLM classifies
```

### Code Normalization Heuristic (Phase 5)

```
_normalize_cod(code):
  1. Uppercase all
  2. Replace O→0, l→1
  3. Strip trailing # and [digits]
  4. Pattern matching:
     IF starts with AUT: → remove prefix, add $ → $NNNNNN
     IF all digits: → add $ → $NNNNNN
     ELSE: keep as-is (NOR codes stay unchanged)
  5. Return normalized code
```

### Lenient UM Matching Heuristic (Phase 5, Layer 5)

```
FOR each ARTICOL_EXTRA code C in offer:
  IF code.startswith('$'):
    FOR each ref_article R:
      IF R.cod == C and R.deviz_cod == offer_deviz:
        IF R.um is empty or whitespace:
          → Mark article as MATCHED
          → Add UM_DIFERIT nonconformity
          → Log: "Lenient match: $ code with empty UM in ref"
          BREAK
```

---

## Testing Pyramid

```
                     ┌─────────────────┐
                     │   E2E Test      │  (local_run.py on all offers)
                     │  (Full pipeline)│  → Compare output metrics vs baselines
                     └────────┬────────┘
                              │
                   ┌──────────┴──────────┐
                   │  Integration Tests  │
                   │  - verify_extra_*.py│  (Root cause analysis)
                   │  - verify_lipsa_*.py│  (Classification validation)
                   └──────────┬──────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
   ┌────▼────────┐   ┌────────▼─────────┐  ┌──────▼──────────┐
   │  Unit Tests │   │  Component Tests │  │  Checkpoint     │
   │             │   │                  │  │  Validation     │
   ├─────────────┤   ├──────────────────┤  ├─────────────────┤
   │ test_*.py   │   │ test_matching.py │  │ Hash validation │
   │ (parse,     │   │ test_deviz_*.py  │  │ Auto-invalidate │
   │  normalize) │   │ (integration)    │  │ on code change  │
   └─────────────┘   └──────────────────┘  └─────────────────┘
```

---

## Session Summary — 2026-05-19

| Component | Status | Change | Commit |
|-----------|--------|--------|--------|
| Scattered format preprocessor | ✓ Done | +44 referinta articles (834→878) | feat: scattered format |
| S474 variant skip pattern | ✓ Done | -1 LIPSA (124→123 nonconf) | fix: reject short letter+digit |
| Lenient UM matching ($ codes) | ✓ Done | 17 EXTRA→matched (100→83) | feat: lenient UM matching |
| Field name consistency | ✓ Done | Fixed $6720363 pipeline loss | fix: field mismatch descriere→denumire |
| **Total nonconformitati (OFERTA 1)** | **123** | Stable | v6.1 release |

