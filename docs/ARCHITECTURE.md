# Arhitectura și Logica Codului — Analizator Oferte Constructii

**Ultima actualizare:** 2026-05-19  
**Tag stabil:** `v6.1` (2026-05-18, commit 1360b76) — Linked article extraction, UM variants, lenient matching  
**Actualizare:** 2026-05-19 — Scattered format preprocessor, S474 variant fix, lenient UM matching

---

## Scopul sistemului

Extrage articolele din documentele PDF de ofertă pentru lucrări de construcții (Formularul F3 — Lista cu cantități de lucrări), le compară cu o referință (caiet de sarcini), și generează rapoarte de neconformitate.

**Input:** DI JSON (Azure Document Intelligence) — referință + N oferte  
**Output:** DOCX raport per ofertă, JSON comparație, JSON articole extrase

**Caracteristici 2026-05-19:**
- Lenient matching pentru coduri breviar ($) cu UM gol în referință
- Preprocessor pentru format scattered (articol pe linii separate)
- Detecție variant codes (S474, S475) din denomination
- UM normalization (m cub → mc, TONE → tone, etc.)
- Multi-deviz consolidation cu inheritance
- Orphan table extraction (Format 3 detection)

---

## Fișiere principale

```
local_run.py               — Orchestrator principal (main pipeline)
AgentComparator_local.py   — Motor de matching multi-strat
anthropic_adapter.py       — Wrapper Anthropic API (compatibil OpenAI interface)

shared/
  f3_page_classifier.py    — Clasificare pagini DI: F3 vs NON_F3 (heuristic + LLM)
  f3_extractor.py          — Extragere articole din pagini F3 clasificate
  f3_regex_parser.py       — Parser regex articole din linii brute DI
  f3_page_reclassifier.py  — Post-procesor euristic (dezactivat, referință)
  deviz_reconciler.py      — Auto-reglare: re-scan devize lipsă din documente
  article_matcher.py       — Matching fuzzy cod articol (SequenceMatcher + LLM)
  deviz_normalizer.py      — Normalizare coduri deviz între referință și ofertă
  deviz_mismatch_detector.py — Detectare devize cu cod diferit dar conținut similar
  deviz_namer.py           — Populare denumiri devize din DI
  deviz_corrector.py       — Corecție coduri deviz (OCR fixes)
  comparator.py            — Comparare articole individuale (câmp cu câmp)
  orphan_detector.py       — Detectare articole prezente în ofertă la deviz diferit
  extraction_validator.py  — Validare acoperire extracție + marcare EXTRA suspecte
  table_extractor.py       — Extragere articole din tabele DI (format structurat)
  report_word.py           — Generare raport DOCX
  report_excel.py          — Generare raport XLSX (dezactivat)

tests/                     — Suite teste pytest (87 teste)
docs/superpowers/          — Design specs și implementation plans
```

---

## Fluxul complet (local_run.py::main)

```
1. extract_document(referinta)
   ├── classify_pages (LLM sau checkpoint cache)
   ├── _reclassify_missed_f3_pages (LLM țintit, cu _reclf_checked cache)
   └── extract_articles_v3 + table_extractor

2. Pentru fiecare ofertă:
   ├── extract_document(oferta)   [același flux ca mai sus]
   │
   ├── RECONCILIERE DEVIZE (deviz_reconciler.py)
   │   ├── devize_extra = oferta \ referință
   │   │   └── reconcile_missing_devize(referință, devize_extra)
   │   │       — re-scaneaza referința pentru devize detectate în ofertă
   │   └── devize_lipsa = referință \ ofertă
   │       └── reconcile_missing_devize(oferta, devize_lipsa)
   │           — re-scaneaza oferta pentru devize din referință
   │
   └── compare_and_report(ref_articles, oferta_articles)
       ├── normalize_devize          — normalizare coduri deviz OCR
       ├── detect_deviz_mismatches   — devize cu cod diferit, conținut similar (≥90% → auto-remap)
       ├── match_global              — matching 6 straturi (vezi detalii jos)
       ├── detect_orphans            — articole la deviz greșit
       ├── mark_suspicious_extras    — EXTRA cu cod prezent în referință
       └── generate_word             — raport DOCX
```

---

## Motor de matching (AgentComparator_local.py::match_global)

**6 straturi în ordine de precizie:**

| Strat | Tip | Descriere |
|-------|-----|-----------|
| **Layer 1** | Exact N:M | `(deviz, cod)` identic, potrivire cantitate sortată |
| **Layer 2** | Normalized N:M | `_normalize_cod` egalizează: `O→0`, `l→1`, `AUT6752→$6752`, `$6752→$6752` |
| **Layer 2.5** | Determinist fuzzy | Similaritate cod ≥ 85% + Jaccard denumire ≥ 0.4 (fără LLM) |
| **Layer 2.6** | Denumire+UM+cantitate | Fallback pe UM + cantitate + Jaccard denumire (fără cod) |
| **Layer 3** | LLM fuzzy per deviz | LLM potrivire per grupă deviz pentru rest nemat-uite |
| **Layer 4** | LLM global | LLM fuzzy global pentru ce rămâne cross-deviz |
| **Layer 5** | Lenient UM matching ($ codes) | Post-processing: $ coduri EXTRA cu aceeași deviz dar UM gol în ref → convertit în matched + UM_DIFERIT |

**Preprocesare înainte de matching:**
- Deduplicare 4-tuple: `(deviz, cod, um, cantitate)`
- Filtru artefacte breviar: `cantitate=0` cu UM gol sau majuscule → excluse din comparație
- UM normalization: `M CUB→mc`, `TONE→tone`, `ORE→ore`, etc.
- $ code lenient matching: codes cu prefix $ și UM gol în referință acceptă UM_DIFERIT ca valid

---

## Normalizare coduri articol (`_normalize_cod`)

```
$3271724    →  $3271724    (breviar propriu, prefix $ păstrat)
AUT6752     →  $6752       (utilaj fără prefix → sufix numeric cu $)
6752        →  $6752       (cod bare numeric → $-prefix)
TSC02D11    →  TSC02D11    (cod normativ interleaved, neatins)
VA02B08     →  VA02B08     (cod normativ standard, neatins)
RPCR21O#    →  RPCR21C     (O→0, strip suffix #)
```

---

## Preprocessori de extracție (shared/f3_regex_parser.py)

### Scattered Format Preprocessor (2026-05-19)
**Scopul:** Articole cu linie separată pentru cod, UM, cantitate, și descriere.

**Pattern detectat:**
```
4          <- counter (digits)
5102437    <- code
buc        <- unit
22.0       <- quantity
ELEMENTE DECORATIVE  <- description
```

**Transformare:**
```
4 5102437 - ELEMENTE DECORATIVE
buc
22.0
```

**Locație:** `f3_regex_parser.py::_preprocess_scattered_format()` (linia ~406)  
**Rezultat:** +44 articole din referință (834 → 878)

### Variant Code Skip Pattern (2026-05-19)
**Scopul:** Previne extragere codes ca S474, S475 care apar în denomination (sunt metadata, nu articole).

**Pattern:**
- Inițial: `[A-Z]\d{4,5}` (S474 = 4 digits)
- Azi: `[A-Z]\d{3,5}` (detectează și 3 digits)
- Context: "COT FONTA MALEABILA A1 S474 DN 40" → S474 = product variant

**Locație:** `f3_regex_parser.py::line 761`  
**Rezultat:** -1 LIPSA (124 → 123 nonconformități)

---

## Checkpoint sistem (F3 page classifier)

Checkpoints salvate în `output_AO/checkpoints/di_X_page_classes_<hash>.json`.

**Hash-ul** e MD5 pe sursa `f3_page_classifier.py` → cache invalidat automat la modificarea clasificatorului.

**Structura unei intrări:**
```json
{
  "page_number": 73,
  "is_f3": true,
  "deviz_cod": "226208",
  "deviz_den": "STRUCTURA DE REZISTENTA",
  "lines": ["linie1", "linie2", ...],
  "header_only": false,
  "needs_llm": false,
  "_reclf_checked": true
}
```

**Flag `_reclf_checked`:** pagina a fost verificată de LLM pentru reclasificare → nu se mai apelează LLM în run-uri ulterioare.

---

## Reconciler devize (deviz_reconciler.py)

**Declanșat când:** numărul de devize din ofertă ≠ numărul din referință.

**Algoritm `_find_deviz_page_range`:**
1. Caută codul devizului în toate paginile DI (full scan)
2. **Entry condiție:** codul apare în context `STADIUL FIZIC:` (fereastra 8 linii) — previne false pozitive din FORMULAR C6, footer-uri, totaluri
3. Continuă consecutive până la header cu cod diferit sau pagină deja clasificată alt deviz
4. Actualizează checkpoint: paginile găsite → `is_f3=True`, `deviz_cod=target`
5. Dacă negăsit → raportează `[RECONCILE] NEGASIT — eroare OCR/parsare`

---

## Tipuri de neconformități raportate

| Tip | Semnificație |
|-----|-------------|
| `ARTICOL_LIPSA` | Articol din referință absent complet din ofertă |
| `ARTICOL_EXTRA` | Articol în ofertă fără corespondent în referință |
| `ARTICOL_ORPHAN` | Articol prezent în ofertă la deviz diferit față de referință |
| `COD_SIMILAR` | Cod potrivit prin normalizare/fuzzy (cu diferențe de câmp) |
| `UM_DIFERIT` | Aceeași cantitate, unitate de măsură diferită |
| `DIFERENTA_CAMP` | Cantitate, preț sau altă valoare diferită |
| `ARTICOL_ORPHAN` | Cod prezent în ofertă dar la altă categorie (deviz) |

---

## Variabile de mediu (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001   # sau claude-sonnet-4-6
```

---

## Rulare

```bash
# Instalare
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run complet
rtk python3 local_run.py

# Teste
rtk python3 -m pytest tests/ -v

# Re-clasificare de la zero (sterge checkpoints)
rm output_AO/checkpoints/*.json && rtk python3 local_run.py
```

---

## Strategie Testare Automată

### Suite de teste (tests/ directory)

| Test | Scop | Locație | Trigger |
|------|------|---------|---------|
| `test_f3_regex_parser.py` | Article extraction patterns | Scattered format, variant codes | `rtk python3 -m pytest tests/test_f3_regex_parser.py -v` |
| `test_normalize_cod.py` | Code normalization (O→0, l→1, AUT→$) | _normalize_cod logic | `rtk python3 -m pytest tests/test_normalize_cod.py -v` |
| `test_matching.py` | Layer 1-4 matching logic | Article pairing per deviz | `rtk python3 -m pytest tests/test_matching.py -v` |
| `test_deviz_filter.py` | Deviz code detection | Page classification | `rtk python3 -m pytest tests/test_deviz_filter.py -v` |
| `test_integration_hierarchical.py` | Multi-deviz consolidation | Inheritance logic | `rtk python3 -m pytest tests/test_integration_hierarchical.py -v` |
| `verify_extra_codes.py` | EXTRA code root cause | Extraction gaps vs genuine | `rtk python3 tests/verify_extra_codes.py` |
| `verify_lipsa_codes.py` | LIPSA code root cause | Extraction vs matching gaps | `rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 20` |

### Post-Processing Verification Scripts

**tests/verify_extra_codes.py**
- Classifies EXTRA codes: `FOUND_EXACT`, `FOUND_AS_SUBCOMPONENT`, `GENUINE_EXTRA`
- Searches di_referinta.json for codes NOT extracted into referinta.json
- Result: Root cause analysis (87% extraction gaps vs 13% matching failures)
- Usage: `rtk python3 tests/verify_extra_codes.py`

**tests/verify_lipsa_codes.py**
- Searches di_referinta for LIPSA codes
- Classifications: `NOT_EXTRACTED`, `EXTRACTED_NOT_MATCHED`, `LEGITIMATE_SUBCOMPONENT`
- Filters: per-oferta, limit by count
- Usage: `rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 20`

### Checkpoint Validation
- Classifier: `output_AO/checkpoints/di_referinta_page_classes_<hash>.json`
- Hash = MD5(f3_page_classifier.py source) → invalidates on code change
- Each entry: `{page_number, is_f3, deviz_cod, _reclf_checked}`

---

## Metodologie Verificare Rezultate

### 1. Metrice Finale (output_AO/comparatie_oferta_N.json)

**Output structure:**
```json
{
  "document": "OFERTA 1",
  "ref_total": 1288,
  "offer_total": 1288,
  "matched": 1288,
  "nonconformities": {
    "ARTICOL_EXTRA": 83,
    "ARTICOL_LIPSA": 20,
    "UM_DIFERIT": 18,
    "DIFERENTA_CAMP": 2,
    "total": 123
  },
  "articles_by_deviz": [...]
}
```

**Verificare:**
- `matched + LIPSA ≈ ref_total` (within subcomponent allowance)
- `matched + EXTRA ≈ offer_total`
- Deviz totals consistent with page classification checkpoints

### 2. Regression Testing (session-over-session)

**Tracked via MEMORY.md:**
- OFERTA 1 baseline: 123 nonconformities (stable after 2026-05-19 fixes)
- OFERTA 2 baseline: 117 nonconformities (stable)
- OFERTA 3 baseline: 50 nonconformities (stable)

**Check before commit:**
```bash
rtk python3 local_run.py
# Compare output_AO/comparatie_oferta_*.json vs MEMORY.md session records
# Flag if: nonconformities increase > 2% or LIPSA/EXTRA swap patterns
```

### 3. Manual Verification (Sample-Based)

**Pick 5-10 LIPSA codes per session:**
```bash
rtk python3 tests/verify_lipsa_codes.py --oferta 1 --limit 5
# Output → root cause class (NOT_EXTRACTED vs EXTRACTED_NOT_MATCHED)
# Inspect: does classification match di_referinta.json inspection?
```

**Pick 5-10 EXTRA codes:**
```bash
rtk python3 tests/verify_extra_codes.py
# Output → FOUND_EXACT, FOUND_AS_SUBCOMPONENT, GENUINE_EXTRA
# Inspect: do genuine EXTRA align with offer-specific additions?
```

### 4. Diff-Based Validation (Post-fix)

**After implementing fix (e.g., scattered format):**

1. **Before metrics:**
```bash
# Record: OFERTA 1: referinta=834 extracted, nonconformities=152
```

2. **Apply fix:**
```bash
# Modify: shared/f3_regex_parser.py
```

3. **Run + compare:**
```bash
rtk python3 local_run.py
# Expected: referinta=878 (+44), nonconformities≤152 (ideally -23)
```

4. **Root cause check:**
```bash
rtk python3 tests/verify_extra_codes.py
# Output: EXTRA reduced by 48, LIPSA increased by 22 (expected pattern for extraction improvement)
```

### 5. Lenient Matching Validation ($ codes)

**Verify Layer 5 post-processing:**

1. Count EXTRA codes with prefix `$`:
```bash
grep -c '^\$' output_AO/comparatie_oferta_1.json
# Before lenient: 100 $ codes in EXTRA
```

2. Search ref for same code + deviz + empty UM:
```bash
rtk python3 -c "
import json
with open('output_AO/referinta.json') as f:
    ref = json.load(f)
$ = [a for a in ref['articles'] if a['cod'].startswith('$') and not a.get('um', '').strip()]
print(f'Found {len($)} $ codes with empty UM in ref')
"
```

3. Verify post-processing converted them:
```bash
# Check: comparatie_oferta_1.json UM_DIFERIT section
# Expected: 17 codes matching (100 - 17 = 83 EXTRA)
```

### 6. Field Validation (Data Quality)

**Critical field checks:**
```bash
rtk python3 -c "
import json
# Verify field names consistent
with open('output_AO/referinta.json') as f:
    ref = json.load(f)
articles = ref['articles']
fields = set()
for a in articles:
    fields.update(a.keys())
print('Fields in referinta:', sorted(fields))
# Expected: cod, denumire, um, cantitate, deviz_cod, deviz_den
"
```

**Check: Filter uses correct field names:**
- Line 993 local_run.py: `a.get('denumire', '')` NOT `a.get('descriere', '')`
- Prevents $ code filtering regression

### 7. Performance Baseline

**Track execution time (local_run.py output):**
```
[OK] Classification: 87 pages, 12.3s (LLM: 8 pages)
[OK] Extraction referinta: 878 articles, 2.1s
[OK] Extraction offer 1: 1288 articles, 1.9s
[OK] Matching: 6 layers, 3.4s
[OK] Report generation: 24.2s
Total: 43.9s
```

**Baselines (2026-05-19):**
- Full pipeline: 40-50s (single machine, no parallelization)
- Classification + extraction: 60% of time
- Matching: 8% of time
- Report generation: 55% of time (DOCX write-heavy)
