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

## Starea la 2026-05-20 (ultima sesiune)

**Branch:** `main`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Ce s-a construit în ultima sesiune (2026-05-19/20)

#### Fix 1: F3-order scattered format preprocessor
**Fișier:** `shared/f3_regex_parser.py::_preprocess_scattered_format`  
**Problema:** Preprocessorul detecta ordinea referinței (counter/CODE/UM/QTY/DEN) dar nu ordinea standard F3 (counter/CODE/DEN/UM/QTY). Coduri numerice bare (ex: `9000815`) pe pagini F3 eDevize (pag 128-129 of2) nu erau extrase.  
**Fix:** Ramură nouă în `_preprocess_scattered_format`: când `is_valid_code=True` dar `is_valid_um=False`, scanează înainte (max 12 linii) pentru UM, colectând linii de descriere pe parcurs.  
**Rezultat:** +16 matched, -9 LIPSA în Oferta 2.

#### Fix 2: SKIP_RE guard pentru linii NR_COD_DESC_RE
**Fișier:** `shared/f3_regex_parser.py` — bucla principală state machine  
**Problema:** `SKIP_RE` are pattern `STE[\-\s]` care se potrivea cu `PESTE` în descrieri lungi emit de preprocessor (ex: "sapatura ... avand sub 1.00 m sau **PESTE** 1.00 m..."). Linia combinată `"1 TSA02F1 - Sapatura..."` era skip-uită înainte să ajungă la state machine.  
**Fix:** Dacă `NR_COD_DESC_RE.match(line)` sau `NR_COD_CONCAT_RE.match(line)` — override `skip_due_to_filter=False`. Start de articol → nu se skip niciodată.  
**Rezultat:** TSA02F1 (deviz 4.2-1) extras corect.

#### Fix 3: NR_COD_DESC_RE trailing `\d?`
**Fișier:** `shared/f3_regex_parser.py::NR_COD_DESC_RE`  
**Problema:** `COD_NORM_STANDALONE_RE` are `\d?` la final (pentru coduri ca `IC19XB1`), dar `NR_COD_DESC_RE` nu. Linia combinată `"36 IC19XB1 - SUPORȚI..."` nu era parsată pentru că `1` după `IC19XB` rupe separator-ul.  
**Fix:** Adăugat `\d?` la prima alternativă în `NR_COD_DESC_RE`.  
**Rezultat:** IC19XB1 (4.1-12) și TRB05B25 (4.1-13) extrase corect.

---

## Rezultate ultima rulare (2026-05-20 00:48)

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1040 | 3 | 14 | 0 |
| Oferta 2 | 1054 | 91 | 21 | 2 |

### Analiza celor 91 LIPSA în Oferta 2

| Categorie | Nr. | Detalii |
|-----------|-----|---------|
| GENUINELY_ABSENT | ~83 | Ofertantul nu a inclus articolele — neconformitate reală |
| EXTRACTION_GAP | ~5 | Cod apare în resource list non-F3 (fals pozitiv în clasificare) |
| MATCHING_FAIL | ~3 | Articol în oferta_2.json dar nematch-uit (cross-deviz orphan) |

**Concluzie:** Majoritate LIPSA sunt reale, nu bug-uri de extracție.

---

## Commits sesiunea curentă

```
fix(parser): extract breviar codes in F3-order scattered format
fix(parser): handle SKIP_RE false-positives and codes with trailing digit
fix(comparator): suppress subcomponent codes from ARTICOL_EXTRA
fix(extractor): stop non-F3 pages from being promoted into deviz extraction
fix(comparator): populate ref_denumire from ref_art in lenient UM_DIFERIT records
fix(parser): fix scatter UM misidentification for multi-word descriptions
fix(parser): recover articles lost at page boundaries and mixed-code formats
```

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
│       ├── _preprocess_compound_um()
│       └── extract_articles_regex()         → state machine principal
│
├── deviz_reconciler.py         → auto-heal devize lipsă (FĂRĂ LLM)
│
└── compare_and_report()
    ├── deviz_normalizer.py     → normalizare coduri deviz OCR
    ├── AgentComparator_local   → matching 6 straturi
    │   ├── Layer 1: exact N:M (deviz+cod)
    │   ├── Layer 2: normalized N:M (AUT6752→$6752, O→0, l→1)
    │   ├── Layer 2.5: fuzzy determinist (similaritate cod + Jaccard denumire)
    │   ├── Layer 2.6: UM + cantitate + denumire
    │   ├── Layer 3: LLM per deviz
    │   └── Layer 4: LLM global
    ├── orphan_detector.py      → articole la deviz greșit
    └── report_word.py          → DOCX
```

**Checkpoint sistem:** `output_AO/checkpoints/di_X_page_classes_<md5_hash>.json`  
Hash = MD5 pe sursa `f3_page_classifier.py` → invalidat automat la modificări.

---

## Ce rămâne de investigat

1. **LIPSA 3 în OF1** — minor, posibil cross-deviz orphan nedetectat
2. **EXTRA 14 în OF1** — minor, posibil extracție greșită sau articole genuine extra
3. **LIPSA 91 în OF2** — ~83 reale (nu bug-uri). Cele ~5 din resource list pot fi excluse din raport printr-un filtru de tip "articol absent dar present în breviar"
4. **Raport DOCX** — secțiunea `EROARE_EXTRACTIE` (devize negăsite de reconciler) nu e încă adăugată în raport — apare doar în log

---

## Comenzi utile

```bash
# Rulare
.venv/bin/python local_run.py

# Teste
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_compound_deviz_extraction.py

# Re-clasificare completă (șterge cache LLM)
rm output_AO/checkpoints/*.json && .venv/bin/python local_run.py

# Verificare rapidă metrici
python3 -c "
import json; from pathlib import Path; from collections import Counter
for f in ['comparatie_oferta_1.json', 'comparatie_oferta_2.json']:
    comp = json.loads(Path(f'output_AO/{f}').read_text())
    by_tip = Counter(a.get('tip','?') for a in comp['neconformitati'])
    print(f'{f}: matched={comp[\"matches\"]}', dict(sorted(by_tip.items())))
"
```

---

## Fișiere cheie de citit la reluare

1. `docs/ARCHITECTURE.md` — arhitectura completă
2. `shared/f3_regex_parser.py` — parser principal (scatter preprocessor + state machine)
3. `AgentComparator_local.py` — motor matching
4. `local_run.py` — orchestrator
