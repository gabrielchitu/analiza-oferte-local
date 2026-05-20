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

## Starea la 2026-05-20 (tag: v6.f)

**Branch:** `main` — **Tag stabil:** `v6.f`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Rezultate ultima rulare

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1040 | 3 | 14 | 0 |
| Oferta 2 | 1054 | 91 | 21 | 1 |

### Analiza 91 LIPSA Oferta 2

| Categorie | Nr. | Detalii |
|-----------|-----|---------|
| GENUINELY_ABSENT | ~83 | Ofertantul nu a inclus articolele — neconformitate reală |
| EXTRACTION_GAP | ~5 | Cod în resource list non-F3 (fals pozitiv clasificare) |
| MATCHING_FAIL | ~3 | Cross-deviz orphan nedetectat |

**Concluzie:** Majoritate LIPSA sunt reale, nu bug-uri pipeline.

---

## Fix-uri sesiunea curentă (2026-05-19/20)

### Parser (`shared/f3_regex_parser.py`)
1. **F3-order scattered format** — preprocessor detecta ordinea referinței (NR/CODE/UM/QTY/DEN) dar nu ordinea standard F3 (NR/CODE/DEN/UM/QTY). Adăugat ramură secundară cu lookahead pentru UM.
2. **SKIP_RE guard** — `STE[\-\s]` se potrivea cu "PESTE" în descrieri lungi. Linii care matchuiesc `NR_COD_DESC_RE` nu mai sunt skip-uite.
3. **NR_COD_DESC_RE trailing `\d?`** — coduri ca `IC19XB1`, `TRB05B25` (trailing digit după letter) acum capturate. Aliniat cu `COD_NORM_STANDALONE_RE`.

### Extractor (`shared/f3_extractor.py`)
4. **Non-F3 page promotion** — paginile non-F3 cu `deviz_cod` gol nu mai sunt promovate în ultimul deviz văzut. Fix OF2: 961 articole false eliminate din breviar.

### Comparator (`AgentComparator_local.py`)
5. **Best-first N:M matching** — algoritmul greedy (sortare după cantitate, pairing secvențial) genera matchuri greșite când pool-ul ofertei era mai mic decât ref-ul. Înlocuit cu best-first global: la fiecare pas, perechea cu scor minim din tot cross-product-ul. Ex: ref=[101.2, 683.0] + offer=[683.0] → acum corect 683.0↔683.0, 101.2→LIPSA.
6. **Subcomponent codes din EXTRA** — ref_component_cods populat din câmpul `subcomponents` al articolelor părinte, nu doar din `is_component=True`.
7. **ref_denumire în lenient UM_DIFERIT** — fix câmp gol în raport pentru $ coduri convertite din EXTRA.

### Session anterioară (2026-05-19)
- Fix `descriere→denumire` (filtru $ coduri) — bug critic, toate $ codurile erau filtrate
- Scattered format preprocessor pentru referință (+44 articole extrase)
- Lenient UM matching pentru $ coduri cu UM gol în referință

---

## Arhitectura rapidă

```
local_run.py
│
├── extract_document(referinta/oferta)
│   ├── f3_page_classifier.py   → clasificare pagini F3/NON_F3 (LLM + heuristic)
│   ├── f3_extractor.py         → extragere articole din pagini clasificate
│   └── f3_regex_parser.py      → parser regex linii brute DI
│       ├── _preprocess_scattered_format()  → combină linii separate (2 ordine)
│       └── extract_articles_regex()         → state machine principal
│
├── deviz_reconciler.py         → auto-heal devize lipsă (FĂRĂ LLM)
│
└── compare_and_report()
    ├── AgentComparator_local   → matching 6 straturi
    │   ├── Layer 1: best-first N:M (deviz+cod, nearest-neighbor global)
    │   ├── Layer 2: normalized N:M (AUT6752→$6752)
    │   ├── Layer 2.5: fuzzy determinist
    │   ├── Layer 2.6: UM + cantitate + denumire
    │   ├── Layer 3: LLM per deviz
    │   └── Layer 4: LLM global
    ├── orphan_detector.py      → articole la deviz greșit
    └── report_word.py          → DOCX
```

**Checkpoint:** `output_AO/checkpoints/di_X_page_classes_<md5_hash>.json`

---

## Ce rămâne de investigat

1. **OF1 LIPSA 3 / EXTRA 14** — minor, posibil cross-deviz orphan și articole genuine
2. **OF2 LIPSA 91** — ~83 reale. Posibil filtru în raport pentru articole din breviar absent
3. **DOCX** — secțiunea `EROARE_EXTRACTIE` (devize negăsite de reconciler) nu e în raport
4. **Alte documente** — `Camin Maneciu/`, `Scoala Dragomiresti/`, `Scoala Sportiva Racari/` netestați

---

## Comenzi utile

```bash
# Rulare
.venv/bin/python local_run.py

# Teste
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_compound_deviz_extraction.py

# Verificare metrici
python3 -c "
import json; from pathlib import Path; from collections import Counter
for f in ['comparatie_oferta_1.json', 'comparatie_oferta_2.json']:
    comp = json.loads(Path(f'output_AO/{f}').read_text())
    by_tip = Counter(a.get('tip','?') for a in comp['neconformitati'])
    print(f'{f}: matched={comp[\"matches\"]}', dict(sorted(by_tip.items())))
"
```
