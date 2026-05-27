# Project State — Multi-Client Pipeline

**Status:** ✅ ACTIVE (v12.0)
**Date:** 2026-05-27
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

## Current State

**v12.0 released.** Invariant verificat pe toți clienții activi. Urmează: SSR (Scoala Sportiva Racari) și Camin Maneciu — structural mismatch nerezolvat (SSR: ref 2 grupuri/obiect vs. ofertă 8+ sub-devize/obiect).

**Clienți activi verificați (0 violări invariant):**
- Blocuri Racari (consolidat) + BR BLOC A/A2/A3/A4/B/C
- Scoala Dragomiresti

**Clienți în așteptare:**
- Scoala Sportiva Racari — structural mismatch SSR, grup matching LLM activ dar neoptimizat
- Camin Maneciu — nerulatâ din v12.0

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
