# Semantic Comparator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Detect two classes of NC currently invisible to the pipeline: (1) same article with different normativ codes matched by NR position; (2) same normativ code but specifications differ significantly from a construction domain expert perspective.

**Architecture:** New module `shared/semantic_comparator.py` with two public functions, called from `group_comparator.py` after `match_global()`. LLM acts as Romanian construction domain specialist (no cache — output is trusted authoritative).

**Tech Stack:** anthropic SDK (already in project), rapidfuzz for pre-filter, existing NC dict schema.

---

## Context

### Why this exists

Pipeline currently produces ARTICOL_LIPSA + ARTICOL_EXTRA for article pairs that:
- Share the same `nr_ordine` in the same matched group
- But use different normativ codes (e.g. ref=`ES08A4*` "Montare DVR 16 canale" vs oferta=`TCB30A1` "MONTARE DVR")

A construction specialist immediately recognises these as the same physical work item — the ofertant used a different normativ code (or an eDevize internal code appears in the referinta). The pipeline also fails to flag cases where the same code matches but the denomination contains technically significant differences (stalp 8m vs stalp 5m).

### Ground truth

From `input_AO/CAV Maneciu/SOLICI~4.DOC` (contracting authority clarification request, July 2024):
- NR=10 electrice: ref `ES08A4*` ↔ oferta `TCB30A1` — both "Montare DVR" → should be `COD_NORMATIV_DIFERIT`
- NR=19 sistematizare: ref `W2A16A#` "stalp 8m" ↔ oferta `W2A16A#` "stalp 5m" → should be `SPECIFICATIE_DIFERITA`

---

## New NC Types

### `COD_NORMATIV_DIFERIT`
Fired by Pass 1. Ref and oferta article at same `nr_ordine`, different codes, LLM confirms same physical work.

```python
{
    "tip": "COD_NORMATIV_DIFERIT",
    "ref_cod": "ES08A4",
    "ref_denumire": "Montare DVR (Digital video recorder) 16 canale",
    "ref_um": "buc",
    "ref_cantitate": 1.0,
    "oferta_cod": "TCB30A1",
    "oferta_denumire": "MONTARE DVR",
    "oferta_um": "buc",
    "oferta_cantitate": 1.0,
    "nr_ordine": 10,
    "diferente": [
        {"camp": "cod_normativ", "ref": "ES08A4", "oferta": "TCB30A1"},
        {"camp": "specificatie", "detaliu": "Oferta omite numărul de canale (16)"}
    ],
    "motiv_llm": "Aceeași lucrare: montare DVR 16 canale; cod normativ diferit",
    # standard fields:
    "deviz_ref": "...", "deviz_denumire": "...", "is_component": False,
    "nr_ordine_ref": 10, "nr_ordine_oferta": 10
}
```

### `SPECIFICATIE_DIFERITA`
Fired by Pass 2. Ref and oferta article matched by code (same normativ code), but denomination contains technically significant differences per LLM specialist.

```python
{
    "tip": "SPECIFICATIE_DIFERITA",
    "ref_cod": "W2A16A",
    "ref_denumire": "stalp pentru iluminat public stradal ... stalp de 8m",
    "oferta_denumire": "stalp pentru iluminat public stradal ... stalp de 5m",
    "ref_um": "buc",
    "ref_cantitate": 8.0,
    "oferta_cantitate": 8.0,
    "nota_specialist": "Înălțime diferită: 8m (referință) vs 5m (ofertă) — impact semnificativ asupra costului și avizului tehnic",
    # standard fields:
    "deviz_ref": "...", "deviz_denumire": "...", "is_component": False,
    "nr_ordine_ref": 19, "nr_ordine_oferta": 19
}
```

---

## Module: `shared/semantic_comparator.py`

### Pass 1 — `semantic_nr_match(unmatched_ref, unmatched_oferta, deviz_context) -> SemanticMatchResult`

**Input:**
- `unmatched_ref`: list of ref articles not matched by Layers 1–2.6
- `unmatched_oferta`: list of oferta articles not matched by Layers 1–2.6
- `deviz_context`: string with group label (obiectul | categoria) for LLM context

**Algorithm:**
1. Index both lists by `nr_ordine` (main articles only — `is_component=False`)
2. Find NR values present in both: `shared_nrs = set(ref_by_nr) & set(off_by_nr)`
3. For each shared NR: call LLM with pair
4. Parse response:
   - `match=True` → build `COD_NORMATIV_DIFERIT` NC, remove from unmatched lists
   - `match=False` → leave in unmatched (will become LIPSA+EXTRA)
5. Return `SemanticMatchResult(new_ncs, remaining_unmatched_ref, remaining_unmatched_oferta)`

**Pass 1 LLM prompt:**
```
Ești specialist în proiectare și execuție lucrări de construcții
(clădiri, drumuri, instalații electrice, sanitare, HVAC, drumuri).
Context deviz: {deviz_context}

Analizează două articole din liste de cantități F3 cu același număr
de ordine, dar coduri normative diferite:

REFERINȚĂ: NR={nr} | Cod={ref_cod} | "{ref_den}" | {ref_um} | cant={ref_cant}
OFERTĂ:    NR={nr} | Cod={off_cod} | "{off_den}" | {off_um} | cant={off_cant}

Reprezintă aceleași lucrări fizice? Dacă da, listează toate diferențele
identificate (cod, specificații tehnice, cantitate, UM).

Răspunde STRICT JSON (fără text în afara JSON):
{
  "match": true,
  "motiv": "Aceeași lucrare: montare DVR; cod normativ diferit",
  "diferente": [
    {"camp": "cod_normativ", "ref": "ES08A4", "oferta": "TCB30A1"},
    {"camp": "specificatie", "detaliu": "Oferta omite numărul de canale (16)"}
  ]
}
```

### Pass 2 — `semantic_spec_check(matched_pairs, deviz_context) -> list[dict]`

**Input:**
- `matched_pairs`: list of `(ref_art, oferta_art)` tuples — articles already matched by code
- `deviz_context`: group label string

**Pre-filter (skip LLM call if):**
- `ref_den == oferta_den` after normalization (strip diacritice, lowercase, collapse spaces)
- One is a substring of the other AND no numeric tokens differ → not significant
- Jaccard similarity of word tokens > 0.85 AND no differing numeric tokens → likely OCR noise

**Trigger LLM if:**
- Numeric tokens differ between ref_den and oferta_den (e.g. "8m" vs "5m", "16 canale" vs "8 canale")
- OR Jaccard similarity ≤ 0.85

**Pass 2 LLM prompt:**
```
Ești specialist în proiectare și execuție lucrări de construcții
(clădiri, drumuri, instalații electrice, sanitare, HVAC, drumuri).
Context deviz: {deviz_context}

Articolul cu codul {cod} apare în ambele documente cu descrieri diferite:
REFERINȚĂ: "{ref_den}"
OFERTĂ:    "{off_den}"

Diferența este semnificativă din punct de vedere tehnic și al costului lucrării?

Semnificative (exemple): înălțime stalp 8m vs 5m, diametru conductă 110 vs 160mm,
  clasă beton C20/25 vs C30/37, număr canale DVR 16 vs 8.
Nesemnificative (exemple): majuscule/minuscule, prescurtări, ordine cuvinte,
  text OCR incomplet care nu contrazice referința.

Răspunde STRICT JSON (fără text în afara JSON):
{
  "diferenta_semnificativa": true,
  "nota_specialist": "Înălțime diferită: 8m (referință) vs 5m (ofertă) — impact semnificativ asupra costului și avizului tehnic"
}
```

**Output:** list of `SPECIFICATIE_DIFERITA` NC dicts for pairs where `diferenta_semnificativa=True`.

---

## Integration: `shared/group_comparator.py`

After calling `match_global()`, before building final NC list:

```python
from shared.semantic_comparator import semantic_nr_match, semantic_spec_check

# Existing: match_global returns neconformitati + still_unmatched_ref + extras_to_report
# (refactor match_global to return these, or extract them here)

# Pass 1
sem_result = semantic_nr_match(still_unmatched_ref, extras_to_report, deviz_context)
neconformitati.extend(sem_result.new_ncs)
still_unmatched_ref = sem_result.remaining_ref
extras_to_report = sem_result.remaining_oferta

# Pass 2
matched_pairs = _build_matched_pairs(ref_articole, oferta_articole, neconformitati)
spec_ncs = semantic_spec_check(matched_pairs, deviz_context)
neconformitati.extend(spec_ncs)

# Existing: generate ARTICOL_LIPSA + ARTICOL_EXTRA from remaining unmatched
```

**`_build_matched_pairs(ref_articole, oferta_articole, neconformitati)`** — private helper:
- Collects ref_cods in LIPSA NCs and oferta_cods in EXTRA NCs
- Remaining ref/oferta articles (not in LIPSA/EXTRA/COD_NORMATIV_DIFERIT) = matched
- Pairs by `nr_ordine` within matched set

---

## DOCX Rendering: `shared/report_word.py`

### `COD_NORMATIV_DIFERIT` row
- Single row, orange background (`FFD966` — between DIFERENTA_CAMP yellow and EXTRA red)
- Column 1: `"COD DIFERIT"` label
- Column 2: `REF: {ref_cod} — {ref_den}`
- Column 3: `OFF: {oferta_cod} — {oferta_den}`
- Column 4 (nota): concatenate `diferente[]` + `motiv_llm`

### `SPECIFICATIE_DIFERITA` row
- Single row, amber background (`FFC000`)
- Column 1: `"SPEC DIFERITA"` label
- Column 2: `REF: {ref_den}`
- Column 3: `OFF: {oferta_den}`
- Column 4: `nota_specialist` from LLM

---

## `shared/pipeline_verifier.py`

Both new NC types are **MEDIUM** severity by default — not CRITICAL/HIGH. Add to known-types list so verifier doesn't flag as unknown.

---

## Tests: `tests/shared/test_semantic_comparator.py`

**Pass 1 unit tests (LLM mocked):**
- Same NR, different codes, LLM says match → produces `COD_NORMATIV_DIFERIT`; articles removed from unmatched
- Same NR, different codes, LLM says no match → articles remain in unmatched
- No shared NR → no LLM calls, unmatched unchanged
- Multiple shared NRs → one LLM call per pair

**Pass 2 unit tests (LLM mocked):**
- Pre-filter: identical text after normalization → no LLM call
- Pre-filter: one is substring, no numeric diff → no LLM call
- Numeric tokens differ (8m vs 5m) → LLM called, `diferenta_semnificativa=True` → NC added
- LLM says `diferenta_semnificativa=False` → no NC added

**Integration smoke test:**
- Run on CAV Maneciu O1 holistic data (or a fixture extracted from it)
- Assert: ES08A4↔TCB30A1 pair produces exactly 1 `COD_NORMATIV_DIFERIT` NC
- Assert: W2A16A# pair (if in matched set) produces exactly 1 `SPECIFICATIE_DIFERITA` NC

**Regression:**
- Run pipeline on Camin Maneciu O1 + O2 → baseline NC counts unchanged (no new CRITICAL/HIGH)

---

## Constraints

- `match_global()` signature must be extended to expose `still_unmatched_ref` and `extras_to_report` — currently internal. Refactor: return them as part of a named tuple or add an optional `debug=True` flag.
- Pass 2 `_build_matched_pairs` must exclude `is_component=True` articles.
- LLM JSON parse failure → log warning, skip pair (treat as no match / no spec diff). Never crash pipeline.
- Both passes run only on **main articles** (`is_component=False`).
- Both passes run inside each matched group independently — never cross groups.
