# LLM Baseline Comparison
**Scop:** Comparație calitate output pipeline între modele LLM diferite (via LiteLLM proxy).

---

## Model: `mistral-small` @ `localhost:4000`
**Data:** 2026-06-16 | Config: `ANTHROPIC_BASE_URL=http://localhost:4000`, `ANTHROPIC_MODEL=mistral-small`

### DT2 — Pipeline principal (`multi_client_run.py`)

| Document | Articole extrase | matched_groups | ref_only | oferta_only |
|----------|-----------------|----------------|----------|-------------|
| referinta.json | 1576 | — | — | — |
| holistic_oferta_1 | — | **189** | 0 | 0 |
| holistic_oferta_2 | — | **189** | 0 | 0 |

NC-uri: 0 (toate grupurile perfect matched, fără neconformități detectate în holistic)

### EuroProject — Sursă de încărcare (`gen_sursa_incarcare.py`)

| Metric | Valoare |
|--------|---------|
| Articole extrase | **93** |
| Cu breakdown | **90** (96.8%) |
| Status verificare | **OK** |
| Iterații | 1 |
| COUNT_DEVIZE | ✅ |
| NR_CRT_GAPS | ✅ |
| LAST_NR_CRT | ✅ |
| TOTAL_CAPITOL | ✅ |
| TOTAL_DEVIZ | ✅ |
| BREAKDOWN_CONTROL | ✅ |

---

## Model: `qwen-coder` @ `localhost:4000`
**Data:** 2026-06-16 | Config: `ANTHROPIC_BASE_URL=http://localhost:4000`, `ANTHROPIC_MODEL=qwen-coder`

### DT2 — Pipeline principal (`multi_client_run.py`)

| Document | Articole extrase | matched_groups | ref_only | oferta_only |
|----------|-----------------|----------------|----------|-------------|
| referinta.json | 1576 | — | — | — |
| holistic_oferta_1 | — | **189** | 0 | 0 |
| holistic_oferta_2 | — | **189** | 0 | 0 |

NC-uri: 0

### EuroProject — Sursă de încărcare (`gen_sursa_incarcare.py`)

| Metric | Valoare |
|--------|---------|
| Articole extrase | **93** |
| Cu breakdown | **90** (96.8%) |
| Status verificare | **OK** |
| Iterații | 1 |
| COUNT_DEVIZE | ✅ |
| NR_CRT_GAPS | ✅ |
| LAST_NR_CRT | ✅ |
| TOTAL_CAPITOL | ✅ |
| TOTAL_DEVIZ | ✅ |
| BREAKDOWN_CONTROL | ✅ |

---

## Diferențe

| Metric | mistral-small | qwen-coder | Delta |
|--------|--------------|------------|-------|
| DT2 matched O1 | 189 | 189 | **0** ✅ |
| DT2 matched O2 | 189 | 189 | **0** ✅ |
| EP articole | 93 | 93 | **0** ✅ |
| EP breakdown | 90 | 90 | **0** ✅ |
| EP status | OK | OK | **identic** ✅ |

**Concluzie:** Output identic pe ambele modele. Pipeline robust față de schimbarea LLM — extracția și matching-ul nu depind de calitatea răspunsurilor LLM pentru aceste documente (checkpoints page_classes cached; group matching via rapidfuzz, LLM chemat doar ca fallback).
