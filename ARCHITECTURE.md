# ARHITECTURA - Sistem Extragere F3 + Comparație Oferte vs Referință

## 1. FLUX GENERAL (High-Level)

```
INPUT: DI JSON files (reference + offers)
    ↓
┌─────────────────────────────────────────────────────────────
│ ETAPA 1: PAGE CLASSIFICATION (local_run.py extract_document)
│
│  1a. Load reference articles + build dynamic deviz_text_map
│      from actual reference denomination texts
│
│  1b. Classify each page (classify_page_local):
│      - Detect F3 vs NON_F3
│      - Extract deviz code via priority:
│        * EXPLICIT: "Deviz Oferta XXXXX" (5-8 alphanum)
│        * COMPOUND: numeric Obiectul + numeric Categoria
│        * REFERENCE_MATCHED: match text against deviz_text_map
│        * PARTIAL: fallback sentinel "__partial__:..." (sent to LLM)
│        * NONE: unresolved
│
│  1c. LLM batch for pages marked needs_llm (partial/ambiguous)
│
│  1d. Deviz code inheritance for continuation pages
│      (when page has blank/unresolved deviz, inherit from last F3 page)
└─────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────
│ ETAPA 2: ARTICLE EXTRACTION (shared/f3_extractor + f3_regex_parser)
│
│  2a. Group pages by deviz (maintain order for quantity continuity)
│
│  2b. Detect pattern from document sample
│      (via shared/pattern_detector)
│
│  2c. Extract articles using regex parser:
│      - NR_CRT (article number): 001-999
│      - COD: normative (CA01A), numeric ($2200012), or breviar ($12345)
│      - DENUMIRE: multi-line text description
│      - UM: unit of measure (M2, MC, BUC, TONA, ML, etc.)
│      - CANTITATE: quantity (decimal or integer)
│      - PRETURI: prices for cost breakdown
│
│  2d. Detect subcomponents:
│      - L: prefix (e.g., "L:LC08") marks subcomponent lines
│      - Subcomponents inherit parent's quantity (no own quantity)
│      - Parent-child relationship tracked via parent_code field
│
│  2e. UM Normalization: m/mc→m2, buc/bucata→buc, tona/ton/t→tona, etc.
│
│  2f. Component quantity/unit inheritance
│      (subcomponents get parent's quantity/UM if not specified)
└─────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────
│ ETAPA 3: DEVIZ ASSIGNMENT (already done in page classification)
│
│  3a. Each article inherits deviz_cod from its page classification
│
│  3b. Code-based deviz correction (for unresolved articles):
│      - Look up article code in reference
│      - If reference has this code in specific deviz, use that deviz
│      - Only applies to articles without explicit numeric deviz
└─────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────
│ ETAPA 4: COMPARISON & REPORTING (local_run.py)
│
│  4a. Matching rule: (deviz_code, article_code) pair must exist in both
│
│  4b. Comparison metrics:
│      - ARTICOL_LIPSA: in reference but not in offer
│      - ARTICOL_EXTRA: in offer but not in reference
│      - UM_DIFERIT: same code & deviz, different unit
│      - DIFERENTA_CAMP: same code, different quantity
│
│  4c. Generate reports (XLSX, DOCX, JSON)
└─────────────────────────────────────────────────────────────
```

---

## 2. STEP 1: PAGE CLASSIFICATION (`shared/f3_page_classifier.py`)

### Overview
Pages are classified into three categories: **F3** (formula F3 data pages), **NON_F3** (non-data pages), **AMBIGUOUS** (uncertain).

**Two-phase algorithm:**
- **Phase A**: Fast non-F3 detection (forms, summaries, metadata)
- **Phase B**: F3 detection and deviz code extraction

### Phase A: Non-F3 Detection

Immediately return NON_F3 if page matches:
- FORMULAR [CF][0-9] (F1, F2, C4-C6) — non-F3 forms
- CENTRALIZATORUL cheltuielilor — summary forms
- RECAPITULATIE + no article codes — summary pages
- TOTAL GENERAL + no article codes — summary footers

### Phase B: F3 Detection

Page is F3 if it matches ANY of:
1. **B1**: "Formular F3" or "SECTIUNEA TEHNICA" — explicit marker
2. **B2**: "STADIUL FIZIC:" header — quantity sheet marker
3. **B3**: ">>> componenta" + article codes — component lines
4. **B4**: "XXXXXX pag" format (6-char code + "pag") — eDevize page header
5. **B5**: "Stadiul fizic: [CODE] DESCRIPTION" — eDevize cover format

### Grouping Key Extraction (`_extract_grouping_key`)

**Priority order** for extracting deviz code from F3 page:

1. **EXPLICIT** (highest priority)
   - Pattern: "Deviz Oferta XXXXX" where XXXXX is 5-8 alphanum chars
   - Returns numeric code directly

2. **COMPOUND** (second priority)
   - Both numeric parts present:
     * Obiectul: numeric (e.g., "4.1")
     * Categoria/Stadiul: numeric (e.g., "03")
   - Combines as: deviz_cod = f"{obj_num}-{cat_num}" → "4.1-03"

3. **REFERENCE_MATCHED** (third priority)
   - Obiectul/Categoria extracted as TEXT (no numeric prefix)
   - Match against `deviz_text_map` (built from reference denomination texts)
   - Uses fuzzy matching (SequenceMatcher) with 0.65 similarity threshold
   - Exact substring match has priority (highest confidence)
   - Example: "Arhitectura - eligibili tip I" → matches "4.1-03"

4. **PARTIAL** (fallback)
   - Text parts exist but no match in deviz_text_map
   - Creates sentinel: `__partial__:{obj_text[:40]}:{cat_text[:40]}`
   - These pages sent to LLM for resolution in Phase 2

5. **NONE** (no extractable data)
   - No Obiectul/Categoria, no explicit code
   - deviz_cod = ""

### Dynamic Deviz Text Map

Built from reference articles (in `classify_pages` function):
```python
deviz_text_map = build_deviz_text_map(reference_articles)
# Returns: {
#   "4.1-03": {
#     "texts": ["arhitectura - eligibili tip i", "arhitectura eligibili", ...],
#     "count": 47  # articles with this deviz code
#   },
#   ...
# }
```

This allows matching page text against ACTUAL denomination texts from reference, not hardcoded lists.

### Phase 2: LLM Resolution

Pages marked `needs_llm=True` (partial sentinels or ambiguous):
- Send to Claude API
- LLM classifies (F3 vs NON_F3)
- LLM extracts deviz_cod if possible
- Results merged back into page classifications

### Phase 3: Deviz Code Inheritance

Continuation pages inherit deviz from last F3 page:
```python
if not is_f3 or extraction_method == "partial_fallback":
    # Unresolved page inherits from previous
    pc["deviz_cod"] = last_deviz_cod
    pc["deviz_den"] = last_deviz_den
    if not is_f3:
        pc["is_f3"] = True
        pc["extraction_method"] = "inherited"
```

---

## 3. STEP 2: ARTICLE EXTRACTION (`shared/f3_regex_parser.py` + `f3_extractor.py`)

### Overview
Extracts individual articles (line items) from F3 pages using regex state machine + LLM pattern detection.

### State Machine: IDLE → WAITING → READING

**IDLE State**:
- Waiting for article header (NR_CRT or article code)
- Patterns recognized:
  * NR_CRT (1-999) with optional inline code (e.g., "024 CK26A#")
  * Article code alone (e.g., "3270513 - BANDA AVERTIZARE...")
  * Format: "NR COD - DESCRIPTION" (e.g., "6 CA01J1 - TURNARE BETON")

**WAITING State**:
- NR_CRT found, waiting for code line
- If code not found within 3 lines, return to IDLE

**READING State**:
- Code found, building article
- Collecting denomination, UM, quantity, prices
- Stops when:
  * New NR_CRT found (with quantity already set)
  * New code line found (article complete)
  * EOF reached

### Article Code Formats

Parser recognizes:
- **Normative codes**: CA01A, CK26A#, TCB40B1 (2-5 letters + 1-4 digits + optional letter + 0-2 digits + optional suffix)
- **Extended codes**: TRI1AA01C2 (2-5L + 1-2D + 1-3L + 2-4D)
- **Single-letter**: W2F05C01, H1V06H (L + D + 1-3L + 2-4D)
- **Single-digit multi-char**: C003A01 (L + 2-3D + L + 2D)
- **Digit-Letter-Digit**: 00106B011 (3-5D + L + 1-3D)
- **Numeric breviar**: $2200012, $16508 ($ prefix + 4-9 digits)
- **Numeric pure**: 6701362 (4-9 digits, converted to $prefix internally)

### Quantity Extraction

Priority in READING state:
1. **Decimal quantity** (CANT_DECIMAL_RE): "4,75000", "18.5", "306.000"
   - Detects via regex, parsed with _parse_number()
   
2. **Integer quantity** (CANT_INT_RE): standalone integer
   - Only after UM is set (avoids mistaking NR_CRT for quantity)
   
3. **Pipe format**: "M.C. | 18.144 | BETON..." (reference format)
   - UM extracted from group 1, quantity from group 2
   
4. **Trailing decimals**: "306" on one line, "000" on next → 306.000
   - Handles page breaks splitting decimal

5. **Price numbers** (PRET_RE): collected for cost breakdown

### Unit of Measure (UM) Extraction

- Detected as standalone line or within code line
- Valid UM tokens: M2, MC, BUC, BUCATA, TONA, ML, LITRU, MP, KMP, etc.
- Format: "100 MC." or "99 ZECI MP" (number + descriptor + unit)
- **KM always skipped**: "20 KM" is distance specification, not work unit

### Subcomponent Detection

Subcomponents marked with "L:" prefix on separate lines:
- Example: "L:LC08", "L:LB03"
- No quantity on L: line (inherits from parent)
- Parent-child relationship stored in `parent_code` field

### Pattern Detection

For each deviz, detect layout pattern from first 50 lines:
- Uses `shared/pattern_detector.py`
- Identifies document layout (standard F3, eDevize, breviar, etc.)
- Used for debugging/logging, doesn't affect extraction logic

---

## 4. STEP 3: NORMALIZATION

### Unit Normalization (`_normalize_um`)

```python
m, mc        → m2      (square meters)
buc, bucata  → buc     (pieces)
ml, litru    → ml      (liquid)
tona, ton, t → tona    (weight)
```

Applied to all articles after extraction.

### Code Normalization

- Strip suffix artifacts: `-`, `@`, `%`, `#`, `*`, `^`, `+`
- Strip bracket suffixes: `[1]`, `[2]`
- Strip designator prefixes: `ASIM`, `TSCH`
- OCR fix: `U` → `0` (226U38 → 226038)

### Denomination Normalization

- Lowercase
- Normalize quotes: `"` → `'`
- Remove points after single letters: "M." → "M"
- Collapse multiple spaces

---

## 5. STEP 4: COMPARISON & MATCHING

### Matching Rule

**Definition**: Article from offer matches reference if:
- SAME deviz code (e.g., "4.1-03")
- SAME article code (e.g., "CK08A", "$2200012")
- Both found in reference AND in offer

```python
key = (article_cod, article_deviz)
# must exist in both reference and offer
```

### Nonconformity Types

1. **ARTICOL_LIPSA**: key in reference but NOT in offer
   - Root causes:
     * Article genuinely omitted by bidder
     * Article misclassified to wrong deviz during extraction
     * OCR/parsing error in offer

2. **ARTICOL_EXTRA**: key in offer but NOT in reference
   - Article added by bidder (legitimate or error)
   - Must be verified manually

3. **UM_DIFERIT**: same key, different unit
   - After normalization: "m2" vs "mc" → should match
   - If still different: "buc" vs "tona" → legitimate difference

4. **DIFERENTA_CAMP**: same key, different quantity
   - Quantity parsing might differ from OCR vs manual input

---

## 6. CURRENT METRICS (Session 2026-05-17)

**Reference**: ~700 articles
**OFERTA 2**: 608 matched articles, 288 nonconformities total

| Metric | Count | % |
|--------|-------|---|
| ARTICOL_LIPSA | 249 | 86.5% |
| ARTICOL_EXTRA | 22 | 7.6% |
| UM_DIFERIT | 9 | 3.1% |
| DIFERENTA_CAMP | 8 | 2.8% |

**Root cause of LIPSA (249)**:
- ~200 (80%): articles misclassified to wrong devizes (page classification issue)
- ~40 (16%): genuine omissions by bidder
- ~9 (4%): data quality/parsing errors

---

## 7. KNOWN ISSUES

### Issue 1: F3 Layout Variance (CK08A Case)

**Problem**: Some documents have non-standard F3 layout where quantity appears BEFORE article code:
```
Line 42: 4,75000      (QUANTITY for CK08A — CORRECT)
Line 43: 2            (ARTICLE CODE: 2)
Line 52: 3,25         (Subcomponent value on L: line — INCORRECT)
```

**Current behavior**: Parser captures 3.25 (from subcomponent line) instead of 4.75000

**Root cause**: When parsing sequentially line-by-line, parser doesn't distinguish between:
- Quantity for main article vs subcomponent values
- Values on L: subcomponent lines (which should not have quantity)

**Fix needed**: Enhance quantity extraction to:
- Detect when quantity comes BEFORE article code (non-standard layout)
- Avoid capturing values from L: prefix lines as main article quantities
- Maintain correct parent-subcomponent quantity relationship

### Issue 2: Page Classification Sentinels (Partial→Fallback)

**Problem**: Pages that fall through to LLM (partial sentinels) sometimes get generic fallback codes like "Arhitectura" or "Instalatii" that map to multiple devizes

**Example**: "Arhitectura" matches both:
- 4.1-03: "Arhitectura - eligibili"
- 4.1-04: "Arhitectura conexe"

**Current mitigation**: deviz_text_map with reference matching reduces these cases. Inheritance logic prevents some fallback pages from affecting articles.

---

## 8. FILE ORGANIZATION

| File | Lines | Purpose |
|------|-------|---------|
| `local_run.py` | 1011 | Main orchestration, pipeline coordinator |
| `shared/f3_page_classifier.py` | 892 | Page classification (local + LLM) |
| `shared/f3_extractor.py` | 853 | Article extraction & grouping |
| `shared/f3_regex_parser.py` | 1264 | Regex state machine for parsing |
| `shared/deviz_catalog.py` | 122 | Dynamic deviz text mapping from reference |
| `shared/deviz_corrector.py` | 104 | Code-based deviz correction |
| `shared/deviz_matcher.py` | 342 | Deviz matching/assignment logic |
| `shared/deviz_namer.py` | 84 | Denomination extraction/naming |
| `shared/deviz_normalizer.py` | 233 | Deviz code normalization |
| `shared/pattern_detector.py` | 291 | Document layout pattern detection |
| `shared/subcomponent_formats.py` | (referenced) | Subcomponent layout detection |

---

## 9. ALGORITHM CORRECTNESS

### ✅ Strengths

1. **Multi-deviz articles**: Correctly preserved (e.g., TRA01A15P in 5 devizes)
2. **Component inheritance**: Subcomponents inherit parent's quantity/UM
3. **Matching rule**: (deviz, code) pair is correct for comparison
4. **Dynamic catalog**: Adapts to actual reference denomination texts
5. **Fallback path**: LLM resolution for ambiguous pages

### ⚠️ Known Limitations

1. **Layout variance**: CK08A quantity extraction issue (qty comes before code in some layouts)
2. **Subcomponent ambiguity**: L: prefix detection sometimes fails with OCR noise
3. **Partial sentinel resolution**: ~200 LIPSA articles due to page classification misplacement
4. **Pattern detection**: Doesn't yet use detected pattern to adjust extraction parameters

---

## 10. NEXT PRIORITY FIXES

### Priority 1: Fix F3 Layout Variance (CK08A)
- **Impact**: HIGH (affects extraction accuracy)
- **Effort**: MEDIUM
- **Expected improvement**: +5-10 correct extractions

### Priority 2: Improve Page Classification (Partial→Reference)
- **Impact**: HIGH (could eliminate ~200 LIPSA)
- **Effort**: MEDIUM
- **Current**: ~100 pages resolved via catalog, could be more
- **Expected improvement**: -150 to -200 LIPSA

### Priority 3: Subcomponent Format Detection
- **Impact**: MEDIUM
- **Effort**: LOW (already partially implemented)
- **Current**: Format detected, not yet used in extraction

---

## SUMMARY

The extraction system uses a **multi-phase, hybrid approach**:
1. **Page classification** (local regex + dynamic reference matching + LLM fallback)
2. **Article parsing** (regex state machine with pattern detection)
3. **Deviz assignment** (explicit code priority, reference matching, inheritance)
4. **Normalization** (UM standardization, code cleanup)
5. **Comparison** (matching on deviz+code pair)

The architecture is fundamentally **correct**: objects have proper (cod, deviz, parent/subcomponent relationships, cantitate, UM), and the matching rule is sound. Remaining nonconformities are mainly **data classification** issues (articles extracted to wrong devizes), not structural problems.
