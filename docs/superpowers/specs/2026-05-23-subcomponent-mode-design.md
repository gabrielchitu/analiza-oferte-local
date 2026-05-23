# Design: Subcomponent Mode CLI Parameter

**Date:** 2026-05-23
**Status:** Approved

## Problem

Sub-articolele (is_component=True) din format eDevize (ex: fitinguri polipropilena sub SA04A01)
genereaza zeci de DIFERENTA_CAMP in raportul Word. Aceste diferente sunt reale dar zgomotoase —
utilizatorul vrea optiunea de a le suprima si a vedea doar LIPSA/EXTRA.

## Solution

Parametru CLI `--subcomponents` cu 3 moduri. Afecteaza **doar raportul Word** — JSON-ul
`comparatie_oferta_N.json` ramane complet.

## CLI Interface

```bash
# Default — comportament actual, toate neconformitatile vizibile
python3 multi_client_run.py --client "Blocuri Racari"
python3 multi_client_run.py --client "Blocuri Racari" --subcomponents full

# Suprima DIFERENTA_CAMP + UM_DIFERIT pentru sub-componente
python3 multi_client_run.py --client "Blocuri Racari" --subcomponents fields

# Suprima TOT pentru sub-componente matched (doar LIPSA/EXTRA raman)
python3 multi_client_run.py --client "Blocuri Racari" --subcomponents summary
```

## Filtering Logic

```python
SUPPRESSED_BY_MODE = {
    "full":    set(),  # nimic suprimat
    "fields":  {"DIFERENTA_CAMP", "UM_DIFERIT"},
    "summary": {"DIFERENTA_CAMP", "UM_DIFERIT", "COD_SIMILAR",
                "DESCRIERE_DIFERITA", "EROARE_ARITMETICA"},
}

# In generate_word(), la iterarea neconformitatilor:
suppressed = SUPPRESSED_BY_MODE.get(subcomponent_mode, set())
if neconf.get("is_component") and neconf.get("tip") in suppressed:
    continue  # skip row in Word
```

ARTICOL_LIPSA si ARTICOL_EXTRA **nu sunt filtrate niciodata** — au is_component=False
(sunt articole lipsa/extra la nivel de referinta, nu neconformitati de camp).

## Files Changed

| File | Schimbare |
|------|-----------|
| `multi_client_run.py` | `add_argument("--subcomponents", choices=["full","fields","summary"], default="full")` |
| `local_run.py` | `run_pipeline(client_config, subcomponent_mode="full")` → `compare_and_report(..., subcomponent_mode)` → `generate_word(..., subcomponent_mode)` |
| `shared/report_word.py` | `generate_word(..., subcomponent_mode="full")` — filter logic in neconformitate loop |

## Data Flow

```
multi_client_run.py (parse args)
  └── run_pipeline(client_config, subcomponent_mode)
        └── _run_analysis_pipeline(...)
              └── compare_and_report(..., subcomponent_mode)
                    └── generate_word(raport, ..., subcomponent_mode)
                          └── [filter neconf per is_component + mode]
```

## Constraints

- `local_run.py` direct (legacy entry point) nu are `--subcomponents` — default `full`
- Checkpointurile nu sunt afectate
- JSON complet indiferent de mod
- Backward compatible: lipsa `--subcomponents` = `full` = comportament actual
