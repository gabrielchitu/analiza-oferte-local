# Project State — Multi-Client Pipeline

**Status:** ✅ ACTIVE (v12.3)
**Date:** 2026-05-28
**Branch:** main

## Completed Tasks

### Comparator Invariant Fixes + Verification Reports (v12.0)

Invariant: "0-NC matched group → ref_main_count == off_main_count". 0 violations across all 8 target clients.

**Root causes fixed (parser, commit c295137):**
- `NR_SUBITEM` (`x.y` decimal marker): only sets `explicit_component_marker=True` when `base_nr == last_nr_crt`
- Same-nr inline detection: set `explicit_component_marker` when nr equals `current_parent_nr`
- Linked markers (`NR_LINKED`, `BARE_L`, `DOT_L`): set `explicit_component_marker=True`

**Root causes fixed (comparator, commit d1d8bc0):**
- Layer 2 COD_SIMILAR: removed `and (diffs or arith)` guard — OCR pairs (SA131↔SA13I, IZLO5XF↔IZL05XF) always generate COD_SIMILAR (root cause: `_normalize_cod` maps I→1/O→0, so these match in Layer 2 N:M, NOT Layer 2.5)
- `is_component` mismatch: generate `DIFERENTA_CAMP(tip_articol)` in Layer 1 when matched articles classify differently — fixes `$4202729` silent count divergence in Scoala Dragomiresti
- Removed fuzzy denomination matching (45% threshold silently absorbed ARTICOL_EXTRA NCs)
- Added `_dedup_articles` in `group_comparator.py` — fixes BLC7 duplicate deviz (Blocuri Racari oferta_3)
- Removed garbage `oferta_N.json` output from `local_run.py`

**Quality:**
- ✅ 214/230 tests pass; 16 pre-existing failures unrelated
- ✅ 0 invariant violations across: Blocuri Racari, BR BLOC A/A2/A3/A4/B/C, Scoala Dragomiresti

### Verification Report — Blocuri Racari Cross-Check (v12.0)

One-shot client-facing Word report (`output_AO/Raport_Verificare_Blocuri_Racari.docx`) documenting:
- **Ecuatie conservare:** 0 violări silențioase pe toți 7 clienți (28 rulări total)
- **Cross-check BR consolidat vs. suma blocuri individuale:** 601 vs. 628 articole, diferență constantă de 27 la toate 4 ofertele
- **Cauza diferenței:** 9 coduri comune (șantier/organizare/transport) apar 3× în PDF-ul consolidat (3 obiecte) vs. 6× în suma blocurilor individuale — structura PDF-ului, nu eroare pipeline

Generator: `/tmp/gen_report.py` (rulat ad-hoc, nu integrat în pipeline).

### 6 Clienți Blocuri Individuale Adăugați (v12.0)

`input_AO/BR BLOC A/`, `A2/`, `A3/`, `A4/`, `B/`, `C/` — di_referinta.json + di_oferta_1-4.json per bloc.
Toate 6 rulează prin `multi_client_run.py --client "BR BLOC X"`. 0 violări invariant.

### Group Totals Row in Holistic DOCX Report (v11.2)

Per-group article count summary row after each group in holistic DOCX report.

**Files:**
- `shared/report_word.py` — `_count_main_articles` + `_add_group_totals_row` + 3 call sites in `_generate_word_holistic`
- `tests/shared/test_report_word_totals.py` — 11 tests (unit + integration + shading)

**Quality:**
- ✅ 11/11 tests passing
- ✅ Smoke test: 35 TOTAL GRUP rows in Blocuri Racari Raport_Oferta_1.docx
- ✅ Commits: 61879bc → f6cd0ad

### Holistic Group Matching + SSR deviz_cod Prefix (v11.1.x)

LLM group matching with knowledge cache, deviz_cod prefix matching for ISDP/eDevize format compatibility.

**Key files:** `shared/group_comparator.py`, `shared/group_match_knowledge.json`, `shared/f3_knowledge.py`, `shared/f3_markers_knowledge.json`

**Critical stability fix:** ALL LLM marker learning disabled in `f3_page_classifier.py` — false positives caused "Pag N" as end markers → 0 articles extracted. `f3_markers_knowledge.json` is MANUAL ONLY.

### Multi-Client Pipeline Refactor (v8.0)

All 6 implementation tasks complete + released to origin/main with tag 8.0.

**Architecture:** Single-client hardcoded → Multi-client with interactive menu + CLI override

**Files:**
- `shared/client_config.py` — ClientConfig class (detect clients, resolve paths, validate)
- `multi_client_run.py` — Entry point (menu, CLI parsing, orchestration)
- `local_run.py` — Refactored to accept ClientConfig parameter
- `tests/shared/test_client_config.py` — Unit tests (6 tests)
- `tests/test_multi_client_run.py` — Integration tests (17 tests)
- `README.md` — Updated with usage guide

**Quality:**
- ✅ 23/23 tests passing
- ✅ All 4 real clients tested (Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari)
- ✅ Backward compatibility verified (root di_oferta files still work)
- ✅ Commits: c10f065 (ClientConfig) + be6992f (refactor local_run) + cbaa104 (multi_client_run) + 03543b5 (tests) + 72bb624 (regression) + a57b8fc (docs)

**Release:** https://github.com/gabrielchitu/analiza-oferte-local/releases/tag/8.0

### Verification Agent (v12.1)

Agent de autoverificare output pipeline. 6 checks structurale pe `holistic_oferta_N.json`, loop convergenta, raport MD.

**Files:**
- `verify_agent.py` — CLI orchestrator (`--client`, `--verify-only`, `--max-iter`)
- `shared/pipeline_verifier.py` — 6 checks: SILENT_VIOLATION, OFERTA_ONLY_GROUP, REF_ONLY_GROUP, HIGH_EXTRA, HIGH_LIPSA, COD_SIMILAR_CLUSTER, EMPTY_MATCHED_GROUP
- `shared/agent_knowledge.json` — jurnal runs per client
- `shared/ocr_patterns_knowledge.json` — OCR patterns aditionale (additive union cu hardcodate)
- `AgentComparator_local.py` — `_normalize_cod` incarca ocr_patterns_knowledge.json la startup

**Quality:** 236 passed, 16 pre-existing failures (neschimbate)

**CM verify-only result (v12.2):** 0 CRITICAL, 0 HIGH, 18 MEDIUM (HIGH_EXTRA/LIPSA genuine catalog differences), 1 LOW COD_SIMILAR.

### Parser Fixes — CM ARTICOL_EXTRA (v12.2, commits bf5aa46 + 36e7447 + b9391a4)

Three rounds of extraction fixes for Camin Maneciu:

1. **SKIP_RE digit range** `^\d{4,8}$` → `^(?:\d{4,6}|\d{8,})$` — 7-digit catalog codes were filtered
2. **SKIP_RE bare `424`** → `\b424\b(?!\d)` — substring match inside longer codes (e.g. `6719424`)
3. **`LITRU` not in UM_KNOWN** — added + normalized to `'l'`
4. **3-line OCR L: merge** + `explicit_component_marker` reset — CM subcomponent extraction
5. **`SUBCOMP_PREFIXED_RE` dot in prefix** `[A-Z0-9]+` → `[A-Z0-9.]+` — OCR `101.73` (was `10173`) blocked `$2100916` under `ACD04C1`

**Result:** CM O1+O2 → 0 genuine ARTICOL_EXTRA; remaining 18 MEDIUM are real catalog differences.

### Drum Tatarani — Client Nou (v12.3, commits c66b90e → 38a0d01)

Format document complet diferit față de ceilalți clienți. Fixes în `shared/deviz_header_extractor.py`:

1. **Multi-line obiectivul/obiectul** — `Obiectivul:\n0232 000000232\nDRUMURI TATARANI` pe 2-3 linii; `_next_lines_value()` merge continuation lines
2. **`_DEVIZ_OFERTA_LETTERED_RE`** — regex nou pentru coduri deviz cu prefix litere (`ZO0001`, `AN1`, `LC001A`); override față de `_CAT_RE` care altfel colapsează toate devizele pe strada la un grup
3. **1-digit suffix** `\d{3,6}` → `\d{1,6}` — coduri `AN1`, `AN2` (Aninoasei)
4. **Trailing letter** `\d{1,6}` → `\d{1,6}[A-Z]?` — cod `LC001A` (Lucrari complementare)
5. **Stale cache** `deviz_header_knowledge.json` — șters entries cu categoria numerică pură (`0169`, `1000`, `0122`) rămase din înainte de fix
6. **Knowledge entries O2** — 7 perechi manuale adăugate pentru format oferta_2 (`0050 45230000` prefix vs `0232 000000232` din O1)
7. **Fix match greșit Padurii** — LLM ↔ PA0005 MARCAJE LATERALE → ref `0004 Acostamente` (greșit); corectat: PA0004↔Acostamente, PA0005↔Marcaje laterale

**Format DT:**
- Obiectivul: `0232 000000232 DRUMURI TATARANI` (O1) / `0050 45230000 MODERNIZARE DRUMURI...` (O2)
- Obiectul: `000N N Strada NumeStrada`
- Categoria: din `Deviz oferta XXNNN Denumire` (NU din `Categoria de lucrari: 0169`)
- Prefix-uri stradă: ZO=Zoica, BI=Bisericii, BR=Branii, AN=Aninoasei, PA=Padurii, LC=Lucrari complementare, T=Teiului, D=Dobre, MO=Molanesti, VS=Valea Satului

**Rezultat:** O1=189/189 grupuri matched, O2=189/189, 0 violări invariant.
**Verify agent:** 0 CRITICAL, 0 HIGH; MEDIUM findings sunt HIGH_EXTRA/LIPSA pe devize complexe (Podete, Prefabricate) — neinvestigate încă.

## Current State

**v12.3.** DT adăugat și verificat. CM fully verified. SSR nerezolvat.

**Clienți activi verificați (0 violări invariant):**
- Blocuri Racari (consolidat) + BR BLOC A/A2/A3/A4/B/C
- Scoala Dragomiresti
- Camin Maneciu ✅ (0 CRITICAL/HIGH, 18 MEDIUM genuine)
- Drum Tatarani ✅ (189/189 O1+O2, 0 CRITICAL/HIGH, MEDIUM neinvestigate)

**Clienți în așteptare:**
- Scoala Sportiva Racari — structural mismatch SSR, grup matching LLM activ dar neoptimizat

**Unde să pornești dacă continui:**
1. Rulează `python3 multi_client_run.py` → alege clientul
2. Verifică `holistic_oferta_N.json` — `matched_groups`, `ref_only_groups`, `oferta_only_groups`
3. Rapoarte DOCX în `output_AO/<client>/Raport_Oferta_N.docx`
4. Pentru debugging grup matching: `matching_debug_oferta_N.json`

## Usage

Interactive menu:
```bash
python3 multi_client_run.py
```

Direct client:
```bash
python3 multi_client_run.py --client "Blocuri Racari"
```

Legacy (root files):
```bash
python3 local_run.py
```

## Known Constraints

- 2 pre-existing test failures (unrelated to multi-client work):
  - `tests/test_compound_deviz_extraction.py` — ImportError: `_extract_compound_deviz`
  - `tests/test_subcomponent_matching.py` — ImportError: `_should_match_cant_um`
  - These are old tests for removed/renamed functions. Safe to ignore or fix separately.

## Token Optimization

Use `rtk` prefix for all Bash commands (git, grep, etc.) to save ~60-90% tokens per command (~1.8M saved in previous sessions).

**python3** — RTK nu rescrie automat python3 (no rewrite). Comprima output cu pipe:
```bash
rtk proxy python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log
```

`rtk log` grupeaza errors/warnings cu count, elimina duplicatele. `rtk summary` prea agresiv — pierde informatia.

Alte comenzi:
```bash
rtk git status
rtk grep -r "pattern" shared/
```
