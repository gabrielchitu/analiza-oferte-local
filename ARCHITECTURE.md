# ARHITECTURA — Sistem Analiză Oferte Construcții
**Actualizat:** 2026-05-22 | **Versiune pipeline:** v8.0 (tag: 8.0)

---

## 1. FLUX GENERAL

```
INPUT: Azure Document Intelligence JSON (di_referinta.json + di_oferta_N.json)
       per client în input_AO/<ClientName>/
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 1: PAGE CLASSIFICATION (shared/f3_page_classifier.py)
│   1a. Classificare fiecare pagina: F3 / NON_F3
│   1b. Extragere deviz_cod (EXPLICIT → COMPOUND → REFERENCE_MATCHED → LLM)
│   1c. LLM batch pentru pagini ambigue (needs_llm=True)
│   1d. Mostenire deviz_cod pentru pagini de continuare
│   1e. Output: page_classifications (lista dicts cu is_f3, deviz_cod, lines)
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 2: ARTICLE EXTRACTION (shared/f3_extractor.py + f3_regex_parser.py)
│   2a. Grupeaza pagini F3 pe deviz (mentin nr_crt corect)
│   2b. Preprocess linii: _preprocess_scattered_format + _preprocess_compound_um
│   2c. Regex state machine: IDLE → WAITING → READING
│   2d. Detectie subcomponente (L: prefix, >>> marker, .L suffix)
│   2e. Deduplicare articole (cod, deviz, cantitate)
│   2f. Mostenire cantitate/UM pentru componente
│   2g. Output: lista articole per client (cod, deviz, cant, um, denumire)
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 3: DEVIZ MAPPING (shared/deviz_matcher.py)
│   3a. match_devize_by_denomination — 4 strategii în ordine:
│
│   Strategy 0 (NOU 2026-05-22): Numeric structural matching
│       Extrage (obj_int, cat_int) din cod compound:
│         "001-004" → (1, 4)   [offer: 3-digit-padded]
│         "1.0-1.4" → (1, 4)   [ref: decimal format]
│       Map direct când (obj_int, cat_int) identic.
│       Rezolva problema "INSTALATII SANITARE" identical in mai multe obiecte.
│
│   Strategy 1: Exact code match (oferta_deviz == ref_deviz)
│   Strategy 2: Exact denomination match (normalized text)
│   Strategy 3: Fuzzy match (SequenceMatcher, prag 0.70)
│
│   3b. Output: deviz_mapping dict {deviz_oferta → deviz_ref}
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 4: MATCHING (AgentComparator_local.py → match_global)
│
│   Layer 1: N:M exact pe (deviz, cod)
│       - Grupeaza ref si oferta dupa (deviz, cod)
│       - Potriveste cantitati in ordine (N ref → M oferta)
│
│   Layer 2: Normalized cod (AUT6752 ↔ $6752)
│       - Strip prefix $ din coduri numerice
│       - Potriveste coduri normalizate
│
│   Layer 2.1: Trailing digit (IC35D ↔ IC35D1)
│       - Daca ref_cod e prefix al oferta_cod sau viceversa
│
│   Layer 2.5: Cod similar OCR (threshold 0.80)
│       - SequenceMatcher pe (deviz, cod) cu prag similaritate
│       - N:M: include TOATE instantele per cheie (fix 2026-05-22)
│
│   Layer 3: LLM fuzzy (disabled/fallback)
│       - Disabled implicit; se activeaza numai la cerere
│
│   Post-processing: Lenient UM ($ coduri EXTRA → MATCHED daca ref UM=empty)
│
│   Output: matches[], neconformitati[]
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 5: REPORTING
│   5a. build_raport_ierarhic (shared/report_builder.py)
│       - Organizeaza neconformitati pe deviz, ierarhic
│       - nr_ordine, display_parent_cod pentru subarticole
│   5b. generate_word (shared/report_word.py)
│       - Tabel 11 coloane: tip/cod/denumire/um/cant/preturi
│       - Coduri color: LIPSA=rosu, EXTRA=galben, DEVIZ_MM=albastru
│   5c. JSON output: comparatie_oferta_N.json + comparatie_deviz_oferta_N.json
│   Output: output_AO/<ClientName>/Raport_Oferta_N.docx + JSON
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 6: DIAGNOSTICS (run_diagnostics.py, optional)
│   Phase 0: Calitate referinta (fara_deviz, componente_orfane, incomplete)
│   Phase 1: EXTRA analysis per deviz ($-coduri vs principale)
│   Phase 2: LIPSA analysis (genuine vs DEVIZ_MISMATCH)
│   Output: output_AO/diagnostics.json + diagnostics.docx
└─────────────────────────────────────────────────────────────────────────────
```

---

## 2. ENTRY POINTS

| Script | Scop |
|--------|------|
| `multi_client_run.py` | Entry point principal — meniu interactiv sau `--client "Nume"` |
| `local_run.py` | Legacy — root di_oferta files |
| `run_diagnostics.py` | Diagnostics (nu re-ruleaza pipeline) — `--client`, `--no-docx` |

**Comanda tipica:**
```bash
python3 multi_client_run.py --client "Blocuri Racari"
python3 run_diagnostics.py --client "Blocuri Racari"
```

---

## 3. STRUCTURA FISIERE

```
analiza-oferte-local/
├── multi_client_run.py          # Entry point v8.0
├── local_run.py                 # Pipeline orchestration (1100+ linii)
├── run_diagnostics.py           # Diagnostics CLI
├── AgentComparator_local.py     # Matching engine (Layer 1-3)
├── shared/
│   ├── client_config.py         # ClientConfig: detectie clienti, path resolution
│   ├── f3_page_classifier.py    # Page classification (local + LLM)
│   ├── f3_extractor.py          # Article extraction & grouping
│   ├── f3_regex_parser.py       # Regex state machine parser (1600+ linii)
│   ├── pattern_detector.py      # Document layout pattern detection
│   ├── deviz_matcher.py         # Deviz matching/assignment (fuzzy)
│   ├── deviz_catalog.py         # Dynamic deviz text map din referinta
│   ├── deviz_corrector.py       # Code-based deviz correction
│   ├── deviz_normalizer.py      # Deviz cod normalization
│   ├── article_matcher.py       # match_unmatched_global (Layer 2/2.1/2.5)
│   ├── comparator.py            # compare_articles (UM_DIFERIT, DIFERENTA_CAMP)
│   ├── report_builder.py        # build_raport_ierarhic
│   ├── report_word.py           # generate_word (DOCX tabel 11 col)
│   ├── diagnostics_builder.py   # Phase 0/1/2 analysis + JSON
│   └── diagnostics_word.py      # DOCX diagnostic
├── tests/
│   ├── shared/test_client_config.py
│   ├── test_diagnostics.py      # 17 teste
│   └── ... (alte teste)
├── input_AO/
│   ├── Blocuri Racari/          # di_referinta.json + di_oferta_1..4.json
│   ├── Camin Maneciu/
│   ├── Scoala Dragomiresti/
│   └── Scoala Sportiva Racari/
└── output_AO/
    ├── <ClientName>/
    │   ├── Raport_Oferta_N.docx
    │   ├── comparatie_oferta_N.json
    │   ├── comparatie_deviz_oferta_N.json
    │   └── checkpoints/
    │       ├── di_oferta_N_page_classes_<hash>.json
    │       └── di_oferta_N_deviz_mapping_<hash>.json
    └── diagnostics.json / diagnostics.docx
```

---

## 4. PAGE CLASSIFIER (shared/f3_page_classifier.py)

### Prioritate detectie deviz_cod

1. **EXPLICIT** — `"Deviz Oferta XXXXX"` → cod direct
2. **COMPOUND** — Obiectul numeric + Categoria numerica → `"{obj}-{cat}"`
3. **REFERENCE_MATCHED** — fuzzy match text vs deviz_text_map (prag 0.65)
4. **LLM** — pagini cu `needs_llm=True`, batch Claude API
5. **INHERITED** — continuare pagina anterioare F3

### IMPORTANT: _CATEGORIA_OPT_RE (Fix 2026-05-22)

`_CATEGORIA_OPT_RE` în `f3_page_classifier.py:107` captura cat_num din "Stadiul fizic:".

**Problema veche:** `[0-9]{0,4}` — nu captura punct decimal.
"Stadiul fizic: 1.4 INSTALATII TERMICE" → cat_num=`1` (nu `1.4`).
Toate stadiile unui obiect (1.1, 1.2, 1.3, 1.4) → cod identic `1.0-1`.

**Fix:** `[0-9]{0,4}(?:\.[0-9]{0,2})?` — captura `1.4` ca cat_num.
Fiecare stadiu obține cod distinct: `1.0-1.1`, `1.0-1.2`, `1.0-1.3`, `1.0-1.4`.

**Impact:** SD DEVIZ_MM 624→2. Potențial același bug la SSR dacă ref are format decimal.

### Checkpointing

Page classes salvate în `checkpoints/di_oferta_N_page_classes_<hash>.json`.
Hash = functie de versiunea clasificatorului. Reutilizare automata la re-rulare.

---

## 5. REGEX PARSER (shared/f3_regex_parser.py)

### State Machine

```
_IDLE → _WAITING → _READING → _IDLE
         (NR_CRT)   (COD)
```

**_IDLE:** Asteapta NR_CRT sau cod inline.
**_WAITING:** NR_CRT gasit, asteapta linia cu cod. Timeout 3 linii → _IDLE.
**_READING:** Cod gasit, colecteaza UM, cant, denumire, preturi.

### Preprocess Pipeline (inainte de state machine)

```python
lines = _preprocess_scattered_format(lines)   # Combina format scatter: NR+COD+DESC separat
lines = _preprocess_compound_um(lines)         # Combina "NR" + "UM" separate → "NR UM"
lines = _merge_wrapped_codes(lines)            # Uneste coduri rupte: "TRI1AA01E" + "3"
```

**IMPORTANT — `_preprocess_scattered_format` (Fix 2026-05-22):**
Detecteaza format: counter(bare digit) + cod + (desc) + UM + QTY pe linii separate.
`is_f3_um` verifica UM in lookahead — **TREBUIE sa fie single-token** pentru a evita
false positives ca `"Art. asimilat"` (ART e in UM_KNOWN dar nu e UM real).
```python
is_f3_um = (len(cand)<20 and re.match(r'^[A-Za-z\s\.]+$', cand)
            and len(_f3_um_tokens) == 1   # ← CRITICAL: single token only
            and _f3_um_tokens[0].rstrip('.') in UM_KNOWN)
```

### Formate coduri articol recunoscute

| Tip | Exemplu | Pattern |
|-----|---------|---------|
| Normativ | `CA01A`, `CK26A#`, `TCB40B1` | `[A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}` |
| Extended | `TRI1AA01C2` | `[A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}` |
| Single-letter | `W2F05C01`, `H1V06H` | `[A-Z]\d[A-Z]{1,3}\d{2,4}` |
| Digit-Letter-Digit | `00106B011` | `\d{3,5}[A-Z]\d{1,3}` |
| Breviar $ | `$2200012`, `$16508` | `\$\d{4,9}` |
| Numeric pur | `6701362` (→ `$6701362`) | `\d{4,9}` |

### UM Detection (in _READING state)

Prioritate:
1. Token UM valid pe linie singura (`BUCATA`, `M`, `MP`, `MC` etc.)
2. Format `{NR} {UM}` (ex: `82 M`) → m_um_norm regex → UM extras
3. Guard `{NR} {UM}` in NR_ALPHA_INLINE: daca "codul" e UM valid si articol fara UM → seteaza UM

**UM_KNOWN:** BUC, BUCATA, M, MP, MC, ML, KG, T, TO, TON, TONA, ORA, ZI, SET, ART, etc.
**UM_SKIP:** ASIM, TSCH, SCH, UM, NR, CRT, TOTAL, PU, VAL.

---

## 6. MATCHING ENGINE (AgentComparator_local.py)

### Cheie de matching

```python
key = (deviz_cod, article_cod)  # ex: ("BLC2", "EA02A1")
```

### Layers

| Layer | Mecanism | Activ |
|-------|----------|-------|
| 1 | N:M exact pe (deviz, cod) | ✅ |
| 2 | Normalized cod: strip `$` prefix | ✅ |
| 2.1 | Trailing digit: IC35D ↔ IC35D1 | ✅ |
| 2.5 | Cod similar OCR (SequenceMatcher ≥ 0.80) | ✅ Fix: N:M complet |
| 3 | LLM fuzzy | ❌ disabled |

**Layer 2.5 Fix (2026-05-22):** `oferta_by_deviz[ok[0]].extend(oferta_by_key[ok])` — include TOATE instantele per cheie, nu doar prima.

### Tipuri neconformitate

| Tip | Definitie |
|-----|-----------|
| `ARTICOL_LIPSA` | Cod in referinta, absent din oferta (sau deviz gresit) |
| `ARTICOL_EXTRA` | Cod in oferta, absent din referinta |
| `DEVIZ_MISMATCH` | Cod gasit in oferta dar in alt deviz decat referinta |
| `UM_DIFERIT` | Acelasi cod+deviz, UM diferit |
| `DIFERENTA_CAMP` | Acelasi cod+deviz, cantitate/pret diferit |

**DEVIZ_MISMATCH — cauza si interpretare:**
Articolul EXISTA in oferta cu codul corect. Ofertantul l-a plasat intr-un deviz diferit
fata de referinta (ex: lucrari de organizare santier puse in arhitectura).
NU este LIPSA reala. Fix propus: deviz_matcher mai agresiv.

---

## 7. DIAGNOSTICS (run_diagnostics.py)

### Faze

| Faza | Continut |
|------|----------|
| Phase 0 | Calitate referinta: articole fara deviz, componente orfane, incomplete |
| Phase 1 | EXTRA analysis: $-coduri vs principale, semnal bug extragere |
| Phase 2 | LIPSA analysis: genuine vs DEVIZ_MISMATCH |

### Rulare

```bash
python3 run_diagnostics.py                        # toti clientii
python3 run_diagnostics.py --client "Blocuri Racari"
python3 run_diagnostics.py --no-docx              # JSON only
```

Output: `output_AO/diagnostics.json` + `output_AO/diagnostics.docx`

---

## 8. BASELINE METRICI (2026-05-22, post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD | Note |
|--------|---|---------|-------|-------|----------|----|------|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 | 46 $-cod + 1 OCR |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 3 | curata |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 | abrevieri OCR reziduale |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 | curata |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 57 | EXTRA neinvestigat |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 121 | LIPSA=84 neinvestigat |
| **Scoala Dragomiresti** | **1** | **910** | **2** | **0** | **1** | 14 | fix DEVIZ_MM 624→1 |
| **Scoala Dragomiresti** | **2** | **910** | **2** | **1** | **1** | 14 | fix DEVIZ_MM 602→1 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 | EXTRA neinvestigat |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 | DEVIZ_MM neinvestigat |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 | EXTRA neinvestigat |

**DD = DESCRIERE_DIFERITA** (tip nou) — Jaccard < 0.50 pe cuvinte după curățare OCR artifacts.
Surse false pozitive reziduale: abrevieri ("pt"→"pentru", "supr."→"suprafata", "termoizol.").
Fix propus: dicționar static abrevieri F3 în `shared/comparator.py` aplicat înainte de tokenizare.

---

## 9. KNOWN ISSUES ACTIVE

| # | Issue | Client | Prioritate | Status |
|---|-------|--------|------------|--------|
| 1 | IZDO3D1 OCR (O vs 0) | BR toate | Low | Acceptat |
| 2 | BR O3 EXTRA=5 | BR O3 | Medium | De investigat |
| 3 | SD DEVIZ_MM=2 | SD | Resolved | ✅ fix _CATEGORIA_OPT_RE + Strategy 0 |
| 4 | CM O2 LIPSA=84 | CM | Medium | Neinvestigat |
| 5 | SSR O3 EXTRA=315 | SSR | High | Neinvestigat |
| 6 | SSR O2/O3 DEVIZ_MM=328/325 | SSR | High | Neinvestigat |

---

## 10. CHECKPOINTING

Checkpoints per oferta (evita re-clasificare LLM):
```
di_oferta_N_page_classes_<hash>.json   # page classifications
di_oferta_N_deviz_mapping_<hash>.json  # deviz mapping
```

Hash calculat din versiunea codului clasificatorului. Re-generate automat la
schimbari in page_classifier sau deviz_matcher.

Reset checkpoint:
```bash
find "output_AO/<Client>/checkpoints" -name "*.json" -delete
```

---

## 11. TESTE

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```

Teste care esueaza (pre-existente, nu regresii):
- `test_compound_deviz_extraction.py` — ImportError functie stearsa
- `test_subcomponent_matching.py` — ImportError functie redenumita

Total teste: 17 (diagnostics) + 6 (client_config) + 17 (multi_client) + altele.
