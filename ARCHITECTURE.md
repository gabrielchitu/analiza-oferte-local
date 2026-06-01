# ARHITECTURA — Sistem Analiză Oferte Construcții
**Actualizat:** 2026-05-27 | **Versiune pipeline:** v12.1 (tag: 12.1)

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
│ ETAPA 3: DEVIZ MAPPING — ⚠️ LEGACY (neapelat din pipeline principal)
│   shared/deviz_matcher.py::match_devize_by_denomination există în cod
│   dar nu este apelat din local_run.py. Inlocuit de group_comparator.py
│   care grupeaza direct dupa deviz_key (OBIECTIVUL|OBIECTUL|CATEGORIA hash).
│   Fisierul deviz_matcher.py poate fi sters daca nu mai e nevoie de fallback.
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
│ ETAPA 4.5: HOLISTIC GROUP COMPARATOR (shared/group_comparator.py)
│   Activ cand local_run foloseste modul holistic (implicit).
│   4.5a. Grupeaza articole dupa deviz_key (MD5 hash de OBIECTIVUL|OBIECTUL|CATEGORIA)
│   4.5b. Matching grupuri in 3 faze:
│       Phase 1  (same-code)    — deviz_key identic in ref si oferta
│       Phase 1.5 (deviz_cod prefix) — ref.deviz_cod prefix al offer.categoria
│           Normalizeaza CATEGORIA: strip "oferta ", strip "^\d{1,3} " (ISDP/eDevize)
│       Phase 2  (knowledge)    — shared/group_match_knowledge.json (per-client cache)
│       Phase 2  (LLM fallback) — Claude API cu denomination strings, chunk=15
│   4.5c. Output: HolisticComparison (matched_groups, ref_only_groups, oferta_only_groups)
│       Fiecare grup contine: ref_articles, oferta_articles, neconformitati, matches
│   4.5d. match_trace salvat in matching_debug_oferta_N.json
│
│ IMPORTANT — f3_markers_knowledge.json: MANUAL ONLY
│   ALL LLM marker learning este DISABLED in f3_page_classifier.py.
│   Motivatie: auto-invatate "Pag N" ca end-markers → f3_line_end=2 → 0 articole extrase.
│   Fisierul contine doar intrari cu "source": "manual". Nu adauga "source": "llm".
└─────────────────────────────────────────────────────────────────────────────
    ↓
┌─────────────────────────────────────────────────────────────────────────────
│ ETAPA 5: REPORTING
│   5a. build_raport_holistic (shared/report_builder.py)
│       - Converteste HolisticComparison → dict serializabil cu sumar
│       - build_raport_ierarhic EXISTS în cod dar nu e apelat din pipeline
│   5b. generate_word (shared/report_word.py)
│       - Tabel 11 coloane (landscape A4): cols 0-1=label, 2-5=CERINȚĂ(ref), 6-9=CE A OFERTAT, 10=obs
│       - Mod holistic: _generate_word_holistic — grupuri match/ref_only/oferta_only
│         Dupa fiecare grup: rand TOTAL GRUP cu nr articole principale (stanga=ref, dreapta=oferta)
│         _count_main_articles filtra is_component=True
│       - Mod flat: _generate_word_flat (fallback)
│       - Coduri color: LIPSA=rosu, EXTRA=galben, DEVIZ_MM=albastru
│   5c. JSON output: holistic_oferta_N.json (raport complet) +
│       matching_debug_oferta_N.json (match_trace grupuri)
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
| `verify_agent.py` | Verificare output pipeline — 6 checks, loop convergenta, raport MD |

**Comanda tipica:**
```bash
python3 multi_client_run.py --client "Blocuri Racari"
python3 run_diagnostics.py --client "Blocuri Racari"
python3 verify_agent.py --client "Blocuri Racari" --verify-only
python3 verify_agent.py --client "Camin Maneciu" --max-iter 2
```

---

## 3. STRUCTURA FISIERE

```
analiza-oferte-local/
├── multi_client_run.py          # Entry point v8.0
├── local_run.py                 # Pipeline orchestration (1100+ linii)
├── run_diagnostics.py           # Diagnostics CLI
├── verify_agent.py              # Verification agent CLI (v12.1)
├── AgentComparator_local.py     # Matching engine (Layer 1-3) + OCR learned patterns
├── shared/
│   ├── client_config.py         # ClientConfig: detectie clienti, path resolution
│   ├── f3_page_classifier.py    # Page classification (local + LLM) — LLM marker learning DISABLED
│   ├── f3_extractor.py          # Article extraction & grouping
│   ├── f3_regex_parser.py       # Regex state machine parser (1600+ linii)
│   ├── f3_knowledge.py          # F3Knowledge: find_start/end_marker (skip_header_lines=20)
│   ├── f3_markers_knowledge.json # Markeri F3 start/end — MANUAL ONLY, nu adauga source:llm
│   ├── pattern_detector.py      # Document layout pattern detection
│   ├── deviz_matcher.py         # Deviz matching/assignment (fuzzy)
│   ├── deviz_catalog.py         # Dynamic deviz text map din referinta
│   ├── deviz_corrector.py       # Code-based deviz correction
│   ├── deviz_normalizer.py      # Deviz cod normalization
│   ├── article_matcher.py       # match_unmatched_global (Layer 2/2.1/2.5)
│   ├── comparator.py            # compare_articles (UM_DIFERIT, DIFERENTA_CAMP)
│   ├── group_comparator.py      # Holistic group matching (Phase 1/1.5/2 knowledge+LLM)
│   ├── group_match_knowledge.json # Per-client LLM group match cache (nu sterge fara motiv)
│   ├── pipeline_verifier.py     # 6 structural checks pe holistic_oferta_N.json (v12.1)
│   ├── agent_knowledge.json     # Jurnal runs + thresholds per client (v12.1)
│   ├── ocr_patterns_knowledge.json # OCR substitutii aditionale — ADDITIVE, nu suprascrie hardcoded
│   ├── report_builder.py        # build_raport_holistic (pipeline) + build_raport_ierarhic (legacy)
│   ├── report_word.py           # generate_word (DOCX tabel 11 col, holistic+flat+ierarhic)
│   ├── diagnostics_builder.py   # Phase 0/1/2 analysis + JSON
│   └── diagnostics_word.py      # DOCX diagnostic
├── tests/
│   ├── shared/
│   │   ├── test_client_config.py
│   │   ├── test_f3_knowledge.py
│   │   ├── test_f3_page_classifier_*.py
│   │   ├── test_f3_regex_parser_*.py
│   │   └── test_report_word_totals.py  # 11 teste group totals row
│   ├── test_diagnostics.py      # 17 teste
│   └── ... (alte teste)
├── input_AO/
│   ├── Blocuri Racari/          # di_referinta.json + di_oferta_1..4.json
│   ├── BR BLOC A/               # idem
│   ├── BR BLOC A2/
│   ├── BR BLOC A3/
│   ├── BR BLOC A4/
│   ├── BR BLOC B/
│   ├── BR BLOC C/
│   ├── Camin Maneciu/
│   ├── Scoala Dragomiresti/
│   └── Scoala Sportiva Racari/
└── output_AO/
    ├── <ClientName>/
    │   ├── Raport_Oferta_N.docx
    │   ├── holistic_oferta_N.json          # raport holistic complet
    │   ├── matching_debug_oferta_N.json    # match_trace grupuri
    │   ├── referinta.json                  # articole extrase referinta
    │   ├── verify_report_YYYY-MM-DD_HHMMSS.md  # raport verificare (v12.1)
    │   └── checkpoints/
    │       └── di_oferta_N_page_classes_<hash>.json
    ├── Raport_Verificare_Blocuri_Racari.docx  # cross-check consolidat vs blocuri
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
| 2 | Normalized cod: strip `$` prefix, `_normalize_cod` (I→1, O→0) + OCR learned patterns | ✅ |
| 2.1 | Trailing digit: IC35D ↔ IC35D1 | ✅ |
| 2.5 | Cod similar OCR (SequenceMatcher ≥ 0.80) | ✅ Fix: N:M complet |
| 3 | LLM fuzzy | ❌ disabled |

**OCR learned patterns (v12.1):** `_normalize_cod` incarca `shared/ocr_patterns_knowledge.json` la startup. Union cu regulile hardcodate (L→1, I→1, O→0). Regulile hardcodate NU pot fi suprascrise. Fisierul porneste gol — se adauga MANUAL noi substitutii.

**Layer 2 Fix (v12.0, commit d1d8bc0):** Eliminat `and (diffs or arith)` guard din COD_SIMILAR — perechi OCR (SA131↔SA13I, IZLO5XF↔IZL05XF) se normalizeaza via `_normalize_cod` (I→1, O→0) → match in Layer 2 N:M, nu Layer 2.5. Fara guard, genereaza COD_SIMILAR corect.

**Layer 1 is_component check (v12.0, commit d1d8bc0):** Dupa `compare_articles()`, daca `ra.is_component != oferta_art.is_component` → genereaza `DIFERENTA_CAMP(tip_articol)`. Fix pentru `$4202729` (SD): ref=articol_principal, oferta=subcomponenta → count divergenta silentioasa rezolvata.

**EXTRA loop fix (v12.0, commit 1814cd2):** `ref_component_cods` — codul promovat din subcomponenta in articol principal de ofertant genereaza `DIFERENTA_CAMP(tip_articol)` in loc de skip silentios. Fix pentru CK25A/IZK03C1 (BR BLOC A).

**Layer 2.5 Fix (2026-05-22):** `oferta_by_deviz[ok[0]].extend(oferta_by_key[ok])` — include TOATE instantele per cheie, nu doar prima.

### Tipuri neconformitate

| Tip | Definitie |
|-----|-----------|
| `ARTICOL_LIPSA` | Cod in referinta, absent din oferta (sau deviz gresit) |
| `ARTICOL_EXTRA` | Cod in oferta, absent din referinta |
| `DEVIZ_MISMATCH` | Cod gasit in oferta dar in alt deviz decat referinta |
| `UM_DIFERIT` | Acelasi cod+deviz, UM diferit |
| `DIFERENTA_CAMP` | Acelasi cod+deviz, camp diferit (cantitate, pret, **tip_articol**) |
| `COD_SIMILAR` | Cod usor diferit (OCR) — Layer 2 sau Layer 2.5 |

**DIFERENTA_CAMP(tip_articol):** Generat cand acelasi cod e `is_component=True` in ref dar `is_component=False` in oferta (sau invers). Afecteaza ecuatia de conservare (ref_main_count ≠ off_main_count) dar NU e violare silentioasa — NC exista.

**DEVIZ_MISMATCH — cauza si interpretare:**
Articolul EXISTA in oferta cu codul corect. Ofertantul l-a plasat intr-un deviz diferit
fata de referinta (ex: lucrari de organizare santier puse in arhitectura).
NU este LIPSA reala. Fix propus: deviz_matcher mai agresiv.

---

## 7. HOLISTIC GROUP COMPARATOR (shared/group_comparator.py)

### deviz_key

```python
deviz_key = md5(f"{obiectivul}|{obiectul}|{categoria}").hexdigest()
```

Cheie canonică per grup. NICIODATĂ `deviz_cod` ca lookup key (string instabil, duplicat).

### Faze de matching

| Faza | Mecanism | Note |
|------|----------|------|
| Phase 1 | Same deviz_key (exact) | Deterministic |
| Phase 1.5 | deviz_cod prefix al offer.categoria | ISDP/eDevize compat. Strip "oferta ", strip `^\d{1,3} ` |
| Phase 2a | group_match_knowledge.json (per-client cache) | Populate dupa LLM |
| Phase 2b | LLM fallback (Claude API) | chunk=15 grupuri, max_tokens=2000 |

### SSR Structural Mismatch (documentat, nefixat)

Scoala Sportiva Racari: ref are 1-2 grupuri per obiect, oferta are 8-12 sub-devize per obiect.
Phase 1.5 (deviz_cod prefix) rezolva ~9-12/13 ref grupuri.
Restul (sub-devize oferta extra) ramane oferta_only — **arhitectura bijective nu suporta 1→many**.
Fix ar necesita strategie noua: ref deviz_cod ↔ offer CATEGORIA prefix matching multi-target.

### group_match_knowledge.json

Cache LLM per client. Structura: `{"ClientName": [{"ref_den": "...", "oferta_den": "..."}]}`.
**Nu sterge fara motiv** — re-populare necesita API calls costisitoare.
**Nu pastra intrari invalide** — verifica dupa fiecare run LLM ca perechile sunt corecte.

### f3_markers_knowledge.json + f3_knowledge.py

`find_end_marker` sare primele 20 linii (`skip_header_lines=20`) pentru a evita header-uri ca "Pag N".
**LLM marker learning este DISABLED** — istoricul: "Pag N" auto-invatat ca end-marker → `f3_line_end=2` → 0 articole extrase pe toate clientii.

---

## 8. DIAGNOSTICS (run_diagnostics.py)

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

## 9. BASELINE METRICI (v12.1, 2026-05-27)

### Holistic Group Matching (grouped per client)

| Client | O | matched_groups | ref_only | oferta_only | total_nc | silent_violations |
|--------|---|----------------|----------|-------------|----------|-------------------|
| Blocuri Racari | 1 | 35 | 0 | 0 | — | **0** ✅ |
| Blocuri Racari | 2 | 35 | 0 | 0 | — | **0** ✅ |
| Blocuri Racari | 3 | 35 | 0 | 2 | — | **0** ✅ |
| Blocuri Racari | 4 | 35 | 0 | 3 | — | **0** ✅ |
| BR BLOC A-C (each) | 1-4 | varies | 0 | 0 | varies | **0** ✅ |
| Scoala Dragomiresti | 1 | 22 | 0 | 0 | 24 | **0** ✅ |
| Scoala Dragomiresti | 2 | 22 | 0 | 0 | 26 | **0** ✅ |
| Camin Maneciu | 1 | 35 | 0 | 0 | 245 | **0** ✅ |
| Camin Maneciu | 2 | 35 | 0 | 0 | 488 | **0** ✅ |
| Scoala Sportiva Racari | — | — | — | — | — | neverificat |

**Invariant verificat:** Ecuatia `ref_main - LIPSA = off_main - EXTRA` se respecta in toate grupurile (0 violari silentioase pe 9 clienti verificati).

**_count_main_articles (v12.0):** Filtrare stricta — `not is_component AND cantitate > 0`. Aliniata cu `match_global` pentru consistenta DOCX ↔ JSON.

**DD = DESCRIERE_DIFERITA** (tip nou) — pipeline `_clean_den()` în `shared/comparator.py`:
1. Strip OCR artifacts (antet stanga, l: notatie, garbage financiar, "nr capitol de lucrari u.m")
2. Normalizare diacritice (ă→a, â→a, î→i, ș→s, ț→t) — rezolvă "cofraje stâlpi" ↔ "cofraje stalpi"
3. Expandare abrevieri din `shared/abbreviations.py` (pt→pentru, supr.→suprafata etc.)
4. Jaccard < 0.50 pe cuvinte → DESCRIERE_DIFERITA
5. Perechi borderline (0.25-0.50) marcate `borderline_llm=True` → `shared/abbreviation_learner.py`

**LLM Learner:** `python3 shared/abbreviation_learner.py --client "NumeClient"` → `output_AO/learned_abbreviations.json`

---

## 9b. VERIFICATION AGENT (v12.1)

### verify_agent.py

CLI de autoverificare output pipeline. Pur Python, fara LLM.

```bash
python3 verify_agent.py --client "Camin Maneciu" --verify-only   # check only, raport MD
python3 verify_agent.py --client "Camin Maneciu" --max-iter 2    # loop + re-run pipeline
```

### shared/pipeline_verifier.py — 6 Checks

| # | Check | Conditie | Severitate |
|---|-------|----------|------------|
| 1 | SILENT_VIOLATION | `ref_main - LIPSA != off_main - EXTRA` AND `ncs == []` | CRITICAL |
| 2 | OFERTA_ONLY_GROUP | orice grup in `oferta_only_groups` | HIGH |
| 3 | REF_ONLY_GROUP | orice grup in `ref_only_groups` | HIGH |
| 4 | HIGH_EXTRA | grup matched cu `ARTICOL_EXTRA > 3` (default) | MEDIUM |
| 5 | HIGH_LIPSA | grup matched cu `ARTICOL_LIPSA > 3` (default) | MEDIUM |
| 6 | COD_SIMILAR_CLUSTER | grup matched cu `COD_SIMILAR > 5` (default) | LOW |
| 7 | EMPTY_MATCHED_GROUP | grup matched cu `ref_articles=[]` sau `oferta_articles=[]` | HIGH |

Thresholds configurabile per client in `shared/agent_knowledge.json`.

### Knowledge Files

- `shared/agent_knowledge.json` — jurnal runs (timestamp, nc_before/after, findings_count) per client
- `shared/ocr_patterns_knowledge.json` — OCR substitutii aditionale. Format:
  ```json
  {"char_substitutions": [{"from": "B", "to": "8", "source": "manual", ...}], "suffix_patterns": []}
  ```
  **ADDITIVE:** union cu hardcodate din `_normalize_cod`. Hardcodate (L/I/O) NU pot fi suprascrise.

---

## 10. KNOWN ISSUES ACTIVE

| # | Issue | Client | Prioritate | Status |
|---|-------|--------|------------|--------|
| 1 | SSR structural mismatch — ref 1-2 grupuri/obiect, oferta 8-12 sub-devize/obiect | SSR | Arhitectural | Documentat, necesita strategie noua (1→many matching) |
| 2 | SSR "U" codes (226U08/226U18 ref ≠ 226028/226018 offer) | SSR | Medium | Neinvestigat |
| 3 | CM HIGH_EXTRA masiv — 37 MEDIUM findings, 733 NC total | CM | Medium | Diagnostic: subcomponente ofertate ca principale sau granularitate deviz diferita |
| 4 | 16 teste pre-existente failure | toate | Low | ImportError functii sterse/redenumite — safe to ignore |

---

## 11. CHECKPOINTING

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

## 12. TESTE

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```

Teste care esueaza (pre-existente, nu regresii):
- `test_compound_deviz_extraction.py` — ImportError functie stearsa
- `test_subcomponent_matching.py` — ImportError functie redenumita

Total teste: ~610 (V1 + V2). Baseline: 588 passed, 22 failed (toate pre-existente).

---

## 13. PIPELINE V2 (feature/v2-table-extraction)

Pipeline paralel, independent de V1. Produce `Raport_Oferta_N_v2.docx`.

### Entry Point

```bash
python3 run_v2_pipeline.py --client "Drum Tatarani"
python3 run_v2_pipeline.py --client "Drum Tatarani" --oferta 2
```

### Flux V2

```
input_AO/<ClientName>/di_referinta.json + di_oferta_N.json
    ↓
[V2 S1: TABLE EXTRACTION] — shared/extraction_v2.py::ExtractionOrchestrator
    1a. TemplateDetector — fingerprint document (shared/template_detector.py)
    1b. Per-pagina: TableExtractor (Azure DI table → articole)
                    + RegexExtractor (fallback: f3_regex_parser)
    1c. ExtractionComparator — alege sursa mai buna per pagina
    1d. Grupare articole pe deviz_cod din page_classes checkpoint
    1e. Filtrare PAGE_N (pagini neclasificate cu articole goale)
    ↓
[V2 S2: HIERARCHY CORRECTION] — shared/hierarchy_corrector.py
    2a. Detecteaza relatii parinte-copil rupte (HierarchyAnalyzer)
    2b. Forward-fill parinte pentru articole orfane
    2c. Output: articole corectate cu is_component + parent_code corecte
    ↓
output: extracted_ref_v2.json + extracted_offer_v2.json
        (cached in output_AO/<Client>/checkpoints/<stem>_extracted.json)
    ↓
[V2 S3: GROUP MATCHING] — shared/group_set_matcher.py
    3a. OBIECTIVUL/OBIECTUL/CATEGORIA text similarity (SequenceMatcher)
        - _normalize(): strip prefixe cod numeric/alfanumeric (NU cuvinte)
        - Pondere: 0.7 * categoria + 0.3 * obiectul (dacă obiectul are litere)
        - Threshold: 0.55 (mai lax decât V1 0.80 RapidFuzz — SM mai strict)
        - Fallback: exact deviz_cod când header text absent
    3b. Greedy 1:1 assignment (sort sim desc, first-come)
    3c. Per-grup article matching (set_based_matcher):
        - NR → COD → hash(descriere+um+cant)
    3d. Output: matched_groups, ref_only_groups, oferta_only_groups
    ↓
[V2 S4: REPORT GENERATION]
    Via report_word.py (identic cu V1, holistic input)
    Output: output_AO/<Client>/Raport_Oferta_N_v2.docx
```

### Module V2

```
shared/
├── extraction_v2.py          # ExtractionOrchestrator: S1+S2 entry point
├── template_detector.py      # Fingerprint document tip (DI table vs regex)
├── table_extractor.py        # Azure DI table → articole (coloane COD/UM/CANT)
├── extraction_comparator.py  # Alege table vs regex per pagina
├── hierarchy_analyzer.py     # Detecteaza componente orfane
├── hierarchy_corrector.py    # Forward-fill parinte
├── group_set_matcher.py      # S3: group matching OBIECTUL+CATEGORIA
├── set_based_matcher.py      # S3: article matching NR→COD→hash
├── holistic_generator.py     # Produce holistic JSON (matched/ref_only/oferta_only)
├── matching_orchestrator_v2.py # S3 orchestrator
└── v2_orchestrator.py        # End-to-end: extract→match→report (cu caching)
run_v2_pipeline.py            # CLI entry point V2
```

### Outputs V2

```
output_AO/<Client>/
├── Raport_Oferta_N_v2.docx       # Raport Word (identic format V1)
├── holistic_oferta_N_v2.json     # Holistic matching result
└── checkpoints/
    ├── <stem>_extracted.json     # Cache extragere V2 (regenerat dacă stale)
    ├── di_<stem>_deviz_mapping_<hash>.json   # V1 deviz headers (partajat)
    └── di_<stem>_page_classes_<hash>.json    # V1 page classifier (partajat)
```

### Performanță V2 pe Drum Tatarani (2026-06-01)

| | V1 (prod) | V2 |
|-|-----------|----|
| O1 grupuri matched | 189/189 | 185/189 |
| O1 ref_only genuine | 0 | 4 (AN1-AN4 Aninoasei, absent offer) |
| O2 grupuri matched | 189/189 | 188/189 |
| O2 ref_only genuine | 0 | 1 (BAPC Str.Zoica, absent offer) |

### Limitare V2: Compound deviz_cod collision

Clienți cu multiple sub-grupuri (deviz_key diferit) partajând același deviz_cod în page_classes:
- **Drum Tatarani:** `0017-0169` → 5 sub-grupuri AN1-AN5
- **Blocuri Racari:** `001-001` etc. → 6 instanțe per bloc
- **Scoala Sportiva Racari:** `4-2264` etc. → 10 instanțe

V1 identifică grupuri prin deviz_key (MD5 hash unic per sub-grup).
V2 identifică prin deviz_cod → coliziunile creează un singur grup în loc de mai multe.

**Fix viitor:** `_load_deviz_headers()` să returneze {deviz_key → header}, page_classes să stocheze deviz_key per pagina, sau inspectarea conținutului paginii pentru sub-grup detection.

### Checkpointing V2

`_cached_extraction()` în v2_orchestrator salvează extragerea per fișier.
Cache invalidat când: CONSOLIDATED group OR `obiectul` lipsă din primul grup.
Filtrare PAGE_N aplicată și la load din cache (nu doar la extragere fresh).

### Teste V2

```bash
pytest tests/test_group_set_matcher.py      # 13 teste S3 group matching
pytest tests/test_holistic_generator.py     # 10 teste holistic JSON
pytest tests/test_set_based_matcher.py      # articole matching
pytest tests/test_extraction_v2_regression.py  # E2E (necesită V2 rulat anterior)
pytest tests/test_e2e_set_matching.py       # E2E matching pe toți clienții
```
