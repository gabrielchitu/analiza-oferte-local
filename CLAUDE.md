# Project State — Multi-Client Pipeline

**Status:** ✅ RELEASED (v11.2)
**Date:** 2026-05-27
**Branch:** main

## Completed Tasks

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

**No active tasks.** Pipeline refactor is complete and shipped. All work committed to main, tagged 8.0, released.

**Next decision point:** If additional multi-client features needed (e.g., batch mode, client presets, output filtering), create new task list per feature.

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
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log
```

`rtk log` grupeaza errors/warnings cu count, elimina duplicatele. `rtk summary` prea agresiv — pierde informatia.

Alte comenzi:
```bash
rtk git status
rtk grep -r "pattern" shared/
```
