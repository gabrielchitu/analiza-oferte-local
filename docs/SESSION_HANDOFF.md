# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.
> Da-l lui Claude ca prim mesaj: *"Citeste docs/SESSION_HANDOFF.md si reia de unde am ramas."*

---

## Ce este acest proiect

Pipeline Python care:
1. Primeste documente PDF de oferta pentru lucrari de constructii, procesate prin **Azure Document Intelligence** → JSON
2. Extrage articolele din formularele **F3** (Lista cu cantitati de lucrari)
3. Compara articolele din fiecare oferta cu o **referinta** (caiet de sarcini)
4. Genereaza rapoarte de neconformitate in format **DOCX**

**Client:** Autoritati publice care evalueaza oferte de constructii
**Domeniu:** Devize de constructii romanesti (ISDP, eDevize format)

---

## Starea la 2026-05-23 (branch: main)

**Branch activ:** `main`
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`
**Commits ahead origin/main:** 20+ (SSH push blocat — necesita `! git push origin main`)

### Clienti disponibili

| Client | Oferte |
|--------|--------|
| Blocuri Racari | 4 |
| Camin Maneciu | 2 |
| Scoala Dragomiresti | 2 |
| Scoala Sportiva Racari | 3 |

### Metrici baseline (2026-05-23, post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD | Note |
|--------|---|---------|-------|-------|----------|----|------|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 | |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 | |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 | |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 | |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 56 | EXTRA neinvestigat |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 117 | LIPSA=84 neinvestigat |
| **Scoala Dragomiresti** | **1** | **904** | **2** | **0** | **1** | **0** | ✅ perfect |
| **Scoala Dragomiresti** | **2** | **904** | **2** | **1** | **1** | **1** | IA35B1 genuina |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 | neinvestigat |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 | neinvestigat |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 | neinvestigat |

---

## Ce s-a livrat (sesiunea 2026-05-23)

### Feature: `--subcomponents {full,fields,summary}`

```bash
python3 multi_client_run.py --client "SD" --subcomponents summary
```

| Mod | Ce suprima (pt sub-componente) | Filename |
|-----|-------------------------------|----------|
| `full` (default) | nimic | `Raport_Oferta_N.docx` |
| `fields` | DIFERENTA_CAMP + UM_DIFERIT | `Raport_Oferta_N_fields.docx` |
| `summary` | tot (raman LIPSA/EXTRA) | `Raport_Oferta_N_summary.docx` |

**Filtru pe:** `is_component=True` SAU `cod.startswith('$')` (sub-resurse ISDP).
**JSON neatins** — filtrul e doar in Word report.

### Fix: D20MM/D25MM extrase gresit ca articole

**Root cause:** OCR wrapeaza "SA04A01> - Teava PN16, D20mm" pe linii separate. "D20mm" pe linie separata → parser crea articol D20MM fals cu cant furdata din linia urmatoare.

**Fix:** `shared/f3_extractor.py` — filtru `^D\d+MM$` cu denumire goala, **INAINTE** de `_apply_parent_inheritance`. Rezultat: `display_parent_cod` = SA04A01 (corect), nu D20MM.

**Impact:** 6 articole false eliminate per rulare. matched SD 910→904.

---

## Known Issues Active

| # | Issue | Status |
|---|-------|--------|
| 1 | IZDO3D1 OCR O/0 | Acceptat |
| 2 | CM O2 LIPSA=84 | Neinvestigat |
| 3 | SSR DEVIZ_MM=300+/EXTRA=318 | Neinvestigat |
| 4 | DD BR O3=46, CM 56/117 | LLM learner candidati |

---

## Arhitectura rapida

```
multi_client_run.py       ← Entry point (--client, --subcomponents)
run_diagnostics.py        ← Diagnostics
local_run.py              ← Orchestration + matching + report
│
├── shared/client_config.py
├── shared/f3_page_classifier.py
├── shared/f3_extractor.py          ← FIX: filtru D20MM inainte parent inheritance
├── shared/f3_regex_parser.py       ← FIX: is_f3_um single-token
├── AgentComparator_local.py        ← match_global Layer 1-2.5
├── shared/deviz_matcher.py         ← Strategy 0 format-aware
├── shared/report_builder.py
├── shared/report_word.py           ← FIX: subcomponent_mode filter
├── shared/comparator.py            ← DESCRIERE_DIFERITA + diacritice
├── shared/abbreviations.py         ← dict static abrevieri
└── shared/abbreviation_learner.py  ← LLM learner
```

---

## Comenzi utile

```bash
# Pipeline cu subcomponent mode
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" --subcomponents summary
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" --subcomponents fields
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti"

# Toti clientii
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  .venv/bin/python3 multi_client_run.py --client "$c"
done

# Diagnostics
.venv/bin/python3 run_diagnostics.py

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py

# Metrici rapide
.venv/bin/python3 -c "
import json; from pathlib import Path; from collections import Counter
for client in ['Blocuri Racari', 'Camin Maneciu', 'Scoala Dragomiresti', 'Scoala Sportiva Racari']:
    for i in range(1,5):
        f = Path(f'output_AO/{client}/comparatie_oferta_{i}.json')
        if not f.exists(): continue
        comp = json.loads(f.read_text())
        tips = Counter(n['tip'] for n in comp['neconformitati'])
        print(f'{client} O{i}: matched={comp[\"matches\"]} LIPSA={tips.get(\"ARTICOL_LIPSA\",0)} EXTRA={tips.get(\"ARTICOL_EXTRA\",0)} DEVIZ_MM={tips.get(\"DEVIZ_MISMATCH\",0)} DD={tips.get(\"DESCRIERE_DIFERITA\",0)}')
"

# Push (necesita SSH agent activ)
# ! git push origin main
```

---

## Teste preexistente esuate (nu regresii)

- `tests/test_compound_deviz_extraction.py` — ImportError (functie stearsa)
- `tests/test_subcomponent_matching.py` — ImportError (functie redenumita)
- `tests/shared/test_f3_regex_parser_multiline.py` — 4 teste format vechi
- `tests/test_normalize_cod.py` — 1 test normalizare cod
