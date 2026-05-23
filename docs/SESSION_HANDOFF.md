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

## Starea la 2026-05-24 (branch: refactor/v10)

**Branch activ:** `refactor/v10`
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`
**Tag local:** `v10.0` (neimpins inca la origin — necesita SSH)

### Clienti disponibili

| Client | Oferte |
|--------|--------|
| Blocuri Racari | 4 |
| Camin Maneciu | 2 |
| Scoala Dragomiresti | 2 |
| Scoala Sportiva Racari | 3 |

### Metrici baseline (2026-05-24, post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | Note |
|--------|---|---------|-------|-------|----------|------|
| Blocuri Racari | 1 | 308 | 1 | 0 | 20 | DEVIZ_MM=BLC6 consolidat in BLC7 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | neinvestigat |
| Blocuri Racari | 3 | 415 | 5 | 5 | - | |
| Blocuri Racari | 4 | 316 | 2 | 1 | - | |
| **Scoala Dragomiresti** | **1** | **904** | **1** | **0** | **1** | ✅ perfect |
| **Scoala Dragomiresti** | **2** | **904** | **1** | **1** | **1** | IA35B1 genuina |
| Camin Maneciu | - | - | - | - | - | nerunat cu noile fix-uri |
| Scoala Sportiva Racari | - | - | - | - | - | nerunat cu noile fix-uri |

---

## Ce s-a livrat (sesiunile 2026-05-23/24)

### Sub-project A: F3 Detection Enhancement
- `shared/f3_knowledge.py` — knowledge base markeri F3 (start/end) + self-learning
- `shared/f3_markers_knowledge.json` — markeri persistenti
- `_apply_end_detection()` — detectie sfarsit tabel F3, same-page restart
- `source_pages` pe articole — nr pagina fizica PDF
- `[PDF pag. X-Y]` in Word report — pagini sursa per deviz

### Sub-project B: 3-Layer Deviz Header
- `shared/deviz_header_extractor.py` — extrage OBIECTIVUL/Obiectul/Categoria
- Suporta ambele formate: inline si multi-line (BR style)
- Cache key = `md5(lines[:20])` — fix collision pt eDevize same-header
- `deviz_key` + `deviz_header` pe fiecare articol

### Sub-project C: 3-Layer Deviz Matching
- `match_devize_by_3layer()` in `deviz_matcher.py`
- Per-layer minimums (obj2≥0.85, cat≥0.90) — BLOC A ≠ BLOC B
- Same-code verification — BLC6 ref ≠ BLC6 oferta (continut diferit)
- Fix: $-coduri sub-resurse excluse din LIPSA false

---

## Known Issues Active

| # | Issue | Status |
|---|-------|--------|
| 1 | IZDO3D1 OCR O/0 | Acceptat |
| 2 | BR O1 DEVIZ_MM=20 | Contractor consolidat BLC6+BLC7 org.santier in BLC7 |
| 3 | BR O2 DEVIZ_MM=28 | Neinvestigat |
| 4 | CM O2 LIPSA=84 | Neinvestigat |
| 5 | SSR DEVIZ_MM/EXTRA | Neinvestigat |

---

## Arhitectura rapida

```
multi_client_run.py       ← Entry point (--client, --subcomponents)
run_diagnostics.py        ← Diagnostics
local_run.py              ← Orchestration + matching + report
│
├── extract_document():
│   1. load page_classes (checkpoint)
│   2. _apply_end_detection() [in-memory]
│   3. extract_deviz_headers() → deviz_key, deviz_header pe articole
│   4. extract_articles_v3() → source_pages pe articole
│   5. match_devize_by_denomination() [Strategy 0-3]
│   6. match_devize_by_3layer() [Strategy 4, pt devize nemapate]
│
├── shared/f3_knowledge.py          ← knowledge base markeri F3
├── shared/deviz_header_extractor.py ← 3-layer header extraction
├── shared/deviz_header_knowledge.json ← cache autoinvatare
├── shared/f3_page_classifier.py    ← clasificare pagini + end-detection
├── shared/f3_extractor.py          ← extractie articole + source_pages
├── shared/deviz_matcher.py         ← Strategy 0-4 deviz matching
├── AgentComparator_local.py        ← match_global Layer 1-2.5
└── shared/report_word.py           ← Word report cu PDF pag. X-Y
```

---

## Comenzi utile

```bash
# Pipeline complet
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log

# Verificare metrice rapide
python3 -c "
import json; from pathlib import Path; from collections import Counter
for client in ['Blocuri Racari', 'Scoala Dragomiresti']:
    for i in range(1,5):
        f = Path(f'output_AO/{client}/comparatie_oferta_{i}.json')
        if not f.exists(): continue
        comp = json.loads(f.read_text())
        tips = Counter(n['tip'] for n in comp['neconformitati'])
        print(f'{client} O{i}: matched={comp[\"matches\"]} LIPSA={tips.get(\"ARTICOL_LIPSA\",0)} DEVIZ_MM={tips.get(\"DEVIZ_MISMATCH\",0)}')
"

# Reset deviz header cache
echo '{}' > shared/deviz_header_knowledge.json

# Push la origin (necesita SSH agent)
# git push origin refactor/v10 && git push origin v10.0

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py
```

---

## Teste preexistente esuate (nu regresii)

- `tests/test_compound_deviz_extraction.py` — ImportError (functie stearsa)
- `tests/test_subcomponent_matching.py` — ImportError (functie redenumita)
- `tests/shared/test_f3_regex_parser_multiline.py` — 4 teste format vechi
- `tests/test_normalize_cod.py` — 1 test normalizare cod
- `tests/shared/test_f3_page_classifier_*.py` — 4 teste (preexistente, legate de partial_fallback format)
