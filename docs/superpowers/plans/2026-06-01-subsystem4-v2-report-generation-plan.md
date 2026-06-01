# Subsystem 4: v2 Report Generation — Plan

**Status:** Planning Phase  
**Date:** 2026-06-01  
**Goal:** v2 pipeline produces identical v1-compatible reports on all 4 clients

---

## Overview

Subsystem 4 integrates v2 extraction (S1-S2) + v2 matching (S3) into a complete pipeline that generates Word reports identical to v1 output.

**Entry Point:** `run_v2_pipeline.py` (new orchestrator)  
**Output:** `output_AO/{ClientName}/Raport_Oferta_N_v2.docx` (matches v1 format exactly)

---

## Architecture

```
input_AO/{ClientName}/
  ├─ di_referinta.json
  └─ di_oferta_N.json
         ↓
[EXTRACTION_V2] (S1-S2) ← ExtractionOrchestrator
  ref_extracted, oferta_extracted
         ↓
[MATCHING_V2] (S3) ← MatchingOrchestratorV2
  holistic_oferta_N.json (v1-compatible)
         ↓
[REPORT_GENERATION] ← Word DOCX generator
  Raport_Oferta_N_v2.docx (identical format to v1)
         ↓
output_AO/{ClientName}/
```

---

## Tasks (6 total)

### Task 1: Pipeline Orchestrator (V2EndToEndOrchestrator)

**Goal:** Single class orchestrating extract → match → report  
**Acceptance Criteria:**
- Accepts: client_config, oferta_num
- Returns: {extracted_ref, extracted_offers, holistic_json, report_path}
- Caches intermediate results (extraction, matching)
- 100% v1 format compatibility

**Files:**
- `shared/v2_orchestrator.py` (new, ~80 lines)

**Tests:**
- `tests/shared/test_v2_orchestrator.py` (8-10 tests)
  - Basic end-to-end (extract → match → report)
  - Caching behavior
  - Error handling (missing files, invalid client)

---

### Task 2: Report Word Generator (v2-compatible format)

**Goal:** Generate identical Word reports to v1  
**Acceptance Criteria:**
- Reads holistic JSON (v1-compatible format)
- Produces DOCX with: Summary table (7 metrics) + matched/ref-only/oferta-only sections
- Formatting: fonts, colors, tables match v1 exactly
- Per-group totals row (from S3 implementation)

**Files:**
- `shared/report_word_v2.py` (new, ~150 lines) OR reuse `shared/report_word.py`

**Tests:**
- `tests/shared/test_report_word_v2.py` (6-8 tests)
  - Report structure validation
  - Content accuracy (metrics, article counts)
  - DOCX file integrity

---

### Task 3: v2 vs v1 Report Comparison Tool

**Goal:** Verify v2 reports match v1 reports  
**Acceptance Criteria:**
- CLI: `python3 compare_reports.py --client "BlocuriRacari" --oferta 1`
- Extracts text from both .docx files
- Compares: Summary metrics, article counts, per-group totals
- Reports: identical / differences (with diffs)
- Exit code: 0 = match, 1 = mismatch

**Files:**
- `compare_reports.py` (new, ~120 lines)

**Tests:**
- `tests/test_compare_reports.py` (4-6 tests)
  - Exact match scenarios
  - Metric mismatch detection
  - Group count mismatch detection

---

### Task 4: CLI Tool (run_v2_pipeline_full)

**Goal:** Execute full v2 pipeline for one or all clients  
**Acceptance Criteria:**
- CLI: `python3 run_v2_pipeline.py --client "BlocuriRacari"` (all offers)
- CLI: `python3 run_v2_pipeline.py --client "BlocuriRacari" --oferta 2` (single offer)
- CLI: `python3 run_v2_pipeline.py --all` (all clients, all offers)
- Output: reports in `output_AO/{ClientName}/Raport_Oferta_N_v2.docx`
- Progress: prints per-stage (extract ref, extract offers, match, report)

**Files:**
- `run_v2_pipeline.py` (new, ~100 lines)

**Tests:**
- `tests/test_run_v2_pipeline.py` (5-6 tests)
  - Single client, single offer
  - Single client, all offers
  - All clients

---

### Task 5: E2E Integration Tests (v2 Pipeline)

**Goal:** Validate v2 produces correct output on all 4 clients  
**Acceptance Criteria:**
- 4 clients × 4 offers = 16 parametrized tests
- For each: extract → match → report succeeds
- Validates: holistic JSON structure, report DOCX exists
- Metrics: matched > 0 for all client/offer pairs
- Regression: all 122 S3 tests still pass

**Files:**
- `tests/test_subsystem4_e2e.py` (new, ~300 lines)

**Tests:**
- 16 parametrized: test_v2_pipeline_full[client][offer_num]
  - 4 clients × 4 offers (even Drum Tatarani has O1, O2)

---

### Task 6: v1 vs v2 Report Validation

**Goal:** Confirm v2 reports match v1 reports on all clients  
**Acceptance Criteria:**
- Run both pipelines (v1 via existing, v2 via S4)
- Compare reports: identical metrics, article counts, formatting
- Generate HTML report: side-by-side comparison
- 0 critical differences expected (formatting OK, content exact)

**Files:**
- `validate_v2_reports.py` (new, ~150 lines)

**Tests:**
- `tests/test_v1_vs_v2_reports.py` (4-6 tests)
  - Metric comparison
  - Article count validation
  - Group count validation

---

## Quality Gates

✅ **Spec Compliance:** All code matches specification  
✅ **Code Quality:** Clean, efficient, well-tested  
✅ **Integration:** 0 regressions (all 122 S3 tests + 116 prior tests still pass)  
✅ **E2E Validation:** All 4 clients, all offers, reports generated  
✅ **v1 Compatibility:** v2 reports identical to v1 (metrics, format, content)

---

## Timeline

- **Task 1:** Orchestrator (~1 hour)
- **Task 2:** Report Generator (~1.5 hours)
- **Task 3:** Comparison Tool (~1 hour)
- **Task 4:** CLI Tool (~1 hour)
- **Task 5:** E2E Tests (~1.5 hours)
- **Task 6:** v1 vs v2 Validation (~1.5 hours)

**Total:** ~7.5 hours (subagent-driven, sequential review gates)

---

## Success Metrics

- ✅ All 6 tasks completed
- ✅ 40+ new tests passing (30+ E2E + integration + comparison)
- ✅ 0 regressions (122 S3 + 116 prior tests still pass)
- ✅ v2 reports generated for all 4 clients
- ✅ v2 reports identical to v1 (zero critical diffs)
- ✅ CLI tools production-ready

---

## Execution

Sequential task execution with subagent-driven development:
1. Spec written (done)
2. Task 1 → code review → approval
3. Task 2 → code review → approval
4. Task 3 → code review → approval
5. Task 4 → code review → approval
6. Task 5 → code review → approval
7. Task 6 → code review → approval
8. Final subsystem validation + release
