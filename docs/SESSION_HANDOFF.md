# Session Handoff — Analizator Oferte Construcții

> Citește acest fișier la începutul unei sesiuni noi pe orice mașină.
> Dă-l lui Claude ca prim mesaj: *"Citește docs/SESSION_HANDOFF.md și reia de unde am rămas."*

---

## Ce este acest proiect

Pipeline Python care:
1. Primește documente PDF de ofertă pentru lucrări de construcții, procesate prin **Azure Document Intelligence** → JSON
2. Extrage articolele din formularele **F3** (Lista cu cantități de lucrări)
3. Compară articolele din fiecare ofertă cu o **referință** (caiet de sarcini)
4. Generează rapoarte de neconformitate în format **DOCX**

**Client:** Autorități publice care evaluează oferte de construcții  
**Domeniu:** Devize de construcții românești (ISDP, eDevize format)

---

## Starea la 2026-05-22 (branch: main)

**Branch activ:** `main`  
**Tag stabil:** `8.0` (multi-client pipeline)  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/<client>/` — 4 clienți

### Clienți disponibili

| Client | Oferte |
|--------|--------|
| Blocuri Racari | 4 |
| Camin Maneciu | 2 |
| Scoala Dragomiresti | 2 |
| Scoala Sportiva Racari | 3 |

### Metrici baseline (state.md actualizat)

| Client | Ofertă | matched | LIPSA | EXTRA | DEVIZ_MM |
|--------|--------|---------|-------|-------|----------|
| Blocuri Racari | O1 | 314 | 47 | 0 | 20 |
| Blocuri Racari | O2 | 551 | 2 | 0 | 28 |
| Blocuri Racari | O3 | 395 | 25 | 4 | 19 |
| Blocuri Racari | O4 | 316 | 49 | 1 | 9 |
| Camin Maneciu | O1 | 1056 | 1 | 36 | 2 |
| Camin Maneciu | O2 | 1066 | 84 | 41 | 5 |
| Scoala Dragomiresti | O1 | 651 | 6 | 0 | 624 |
| Scoala Dragomiresti | O2 | 691 | 6 | 1 | 602 |
| Scoala Sportiva Racari | O1 | 2153 | 2 | 122 | 11 |
| Scoala Sportiva Racari | O2 | 1148 | 4 | 55 | 328 |
| Scoala Sportiva Racari | O3 | 2244 | 6 | 315 | 325 |

---

## Ce s-a livrat (sesiunile 2026-05-21/22)

### Diagnostics Pipeline (nou)

```bash
python3 run_diagnostics.py                        # toți clienții
python3 run_diagnostics.py --client "Blocuri Racari"  # un client
python3 run_diagnostics.py --no-docx              # doar JSON
```

Output: `output_AO/diagnostics.json` + `output_AO/diagnostics.docx`

**Faze:**
- Phase 0: Calitate referință (articole fără deviz, componente orfane, incomplete)
- Phase 1: EXTRA per deviz ($-coduri vs principale, semnal bug extragere)
- Phase 2: LIPSA per deviz (genuine vs DEVIZ_MISMATCH)

**Fișiere noi:**
- `run_diagnostics.py`
- `shared/diagnostics_builder.py`
- `shared/diagnostics_word.py`
- `tests/test_diagnostics.py` (17 teste)

### Fix Layer 2.5 (matching)

`AgentComparator_local.py` linia 629: `oferta_map[ok]` → `oferta_by_key[ok]`.  
Layer 2.5 (cod similar OCR) vedea 1 instanță per cheie; acum vede toate instanțele N:M.  
Impact: +6 matched BR O1, +25 BR O3.

### Fix parser `{nr} {UM}` (f3_regex_parser.py)

Format oferta 3 Blocuri Racari: `82 M` pe linie separată (nr_ordine + UM).  
Fix în READING state: dacă NR_ALPHA_INLINE matchuiește cu "cod" = UM valid → tratează ca UM.  
Impact: corect logic, nu rezolvă complet BR O3 (context cumulativ din paginile anterioare).

---

## Known Issues Active

### 1. IZDO3D1 — OCR O/0 ambiguitate (BR O1/O2/O3/O4)
- Ref extrage `IZDO3D1` (litera O, OCR error) + `IZD03D1` (real)
- Oferta extrage `IZD03D1`
- Layer 1 consumă cheia IZD03D1 cu ref-ul real → IZDO3D1 rămâne LIPSA
- **Acceptat.** Fix necesită normalizare O↔0 globală (risc) sau refactor Layer 2

### 2. BR O3 — EA02A1/RPCT49C1/H1B02A3/RPCE34A1 cant=0
- Articole extrase cu cant=0 din oferta_3 (format `82 M` pe linie separată)
- Parser fix funcționează izolat dar state machine cumulativ (paginile 1-5) interferează
- **Investigare în curs.** Root cause: stare incorectă la linia 560+ din pagina 6

### 3. Scoala Dragomiresti — DEVIZ_MISMATCH=600+
- Ref: coduri text ("4.1-01 STRUCTURA"), oferta: coduri eDevize numerice
- `deviz_matcher` nu mapează complet
- **Fix propus:** matching mai agresiv pe cod articol în deviz_matcher

### 4. Camin Maneciu O2 — LIPSA=84
- Neinvestigat. Probabil $-coduri + deviz mismatch.

### 5. Scoala Sportiva Racari O3 — EXTRA=315
- Neinvestigat. SSR ref: 154 componente orfane (Phase 0 red).

---

## Arhitectura rapidă

```
run_diagnostics.py        ← NOU: diagnostic runner toți clienții
multi_client_run.py       ← Entry point principal (v8.0)
local_run.py              ← Legacy (root di_oferta files)
│
├── shared/client_config.py          ← ClientConfig, detect_clients
├── shared/f3_extractor.py           ← extract_articles_v3 + _apply_parent_inheritance
├── shared/f3_regex_parser.py        ← State machine parser + fix 82M
├── shared/f3_page_classifier.py     ← Detectare pagini + fallback partial keys
├── AgentComparator_local.py         ← match_global (Layer 1-3) + build_ref_catalog
│   ├── Layer 1: N:M exact (deviz, cod)
│   ├── Layer 2: normalized cod (AUT6752↔$6752)
│   ├── Layer 2.1: trailing digit (IC35D↔IC35D1)
│   ├── Layer 2.5: cod similar OCR threshold 0.80 ← FIX: N:M complet
│   └── Layer 3: LLM fuzzy (disabled/fallback)
├── shared/report_builder.py         ← build_raport_ierarhic
├── shared/report_word.py            ← generate_word (tabel 11 coloane, ierarhic)
├── shared/diagnostics_builder.py    ← NOU: Phase 0/1/2 + JSON builder
└── shared/diagnostics_word.py       ← NOU: DOCX diagnostic
```

---

## Comenzi utile

```bash
# Pipeline un client
python3 multi_client_run.py --client "Blocuri Racari"

# Toți clienții
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  python3 multi_client_run.py --client "$c"
done

# Diagnostic (citește output_AO/ existente, nu re-rulează)
python3 run_diagnostics.py
python3 run_diagnostics.py --client "Blocuri Racari"

# Teste (17 diagnostics + 154 altele)
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py

# Metrici rapide
python3 -c "
import json; from pathlib import Path; from collections import Counter
for client in ['Blocuri Racari', 'Camin Maneciu', 'Scoala Dragomiresti', 'Scoala Sportiva Racari']:
    for i in range(1,5):
        f = Path(f'output_AO/{client}/comparatie_oferta_{i}.json')
        if not f.exists(): continue
        comp = json.loads(f.read_text())
        tips = Counter(n['tip'] for n in comp['neconformitati'])
        print(f'{client} O{i}: matched={comp[\"matches\"]} LIPSA={tips.get(\"ARTICOL_LIPSA\",0)} EXTRA={tips.get(\"ARTICOL_EXTRA\",0)} DEVIZ_MM={tips.get(\"DEVIZ_MISMATCH\",0)}')
"

# Reset checkpoints pentru re-rulare fresh
rm -f "output_AO/<Client>/checkpoints/"*.json
```

---

## Commits sesiune curentă

```
38e0b6f fix(parser): treat NR+UM line (e.g. '82 M') as UM in READING state
6fdff85 docs: document IZDO3D1 known issue and Layer 2.5 fix in state.md
70e67b9 fix(matching): Layer 2.5 uses all offer instances per key in N:M
7d6b5ec feat(diagnostics): CLI entry point run_diagnostics.py
6e58813 fix(diagnostics): remove unused imports, add type hint in diagnostics_word
aac05ac feat(diagnostics): DOCX generator
6046f07 fix(diagnostics): error handling in discover/load functions
2eda4ee feat(diagnostics): discover/load/JSON builder with tests
3b23c68 feat(diagnostics): Phase 0/1/2 analysis functions with tests
```

**11 commits ahead de origin/main** (push blocat — SSH agent issue în sesiune).

---

## Preexistente eșuate (nu regresii)

- `tests/shared/test_f3_regex_parser_multiline.py` — 4 teste (format multiline vechi)
- `tests/test_normalize_cod.py` — 1 test (IC31A1 vs 1C31A1 normalizare)
- `tests/shared/test_f3_page_classifier_*.py` — 4 teste (classifier vechi)
- `tests/test_compound_deviz_extraction.py` — ImportError (funcție ștearsă)
- `tests/test_subcomponent_matching.py` — ImportError (funcție redenumită)
