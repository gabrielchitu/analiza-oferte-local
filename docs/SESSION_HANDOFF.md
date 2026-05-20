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

## Starea la 2026-05-20 (branch: feature/7.0, tag: v7.0)

**Branch activ:** `feature/7.0` — **Tag stabil:** `v7.0`  
**Main (stabil v6.f):** `main` cu tag `v6.f`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Rezultate ultima rulare (v7.0, fresh fără checkpointuri)

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1040 | 3 | 14 | 0 |
| Oferta 2 | 1054 | 91 | 21 | 1 |

**Metrici identice cu v6.f** — v7.0 nu a introdus regresii în matching.

---

## Ce s-a construit în v7.0 (sesiunea 2026-05-20)

### Structura de date (parser + extractor)
1. **`nr_ordine`** — adăugat pe fiecare articol extras (int pentru principale, "1.1" pentru subarticole din NR_SUBITEM)
2. **`parent_nr_ordine`** — pe subarticole `is_component=True`
3. **`_apply_parent_inheritance`** — post-procesare în `f3_extractor.py`:
   - Subarticole `is_component=True` moștenesc cant/UM de la principal → `cant_mostenita=True`
   - Coduri `$`-prefixate care **împart `nr_ordine`** cu articolul non-`$` precedent primesc `display_parent_cod` (FĂRĂ a modifica `is_component` — matchingul rămâne neatins)
4. **`extract_articles_v3`** — nu mai suprascrie `is_component=False` pe articolele regex; apelează `_apply_parent_inheritance`

### Matching (`AgentComparator_local.py`)
5. **`ARTICOL_ORPHAN` eliminat** — conceptul dispare complet; articolele cu deviz greșit devin `ARTICOL_EXTRA`
6. **Deduplicare O(n)** — înlocuit implementarea O(n²) cu dict-based
7. **`_enrich` extins** — propagă `nr_ordine_ref`, `parent_cod_ref`, `display_parent_cod`, `cant_mostenita` în neconformitate
8. **`lenient` mode eliminat** — `_should_match_cant_um` și `comp_mode` șterse; moștenirea cant/UM acoperă toate cazurile
9. **Checkpointuri șterse** la fiecare rulare fresh necesară

### Raport (`shared/report_word.py`, `shared/report_builder.py`)
10. **`shared/report_builder.py`** — modul nou: `build_raport_ierarhic(ref_articole, neconformitati, matches)` → JSON ierarhic
11. **Raport DOCX ierarhic** — structura tabelului **identică cu v6.f** (11 coloane, același cap), plus:
    - **Toate devizele** apar în raport în ordinea referinței
    - Devize fără neconformitati → cap deviz + `TOTAL DEVIZ: N principale | M subarticole`
    - Devize cu neconformitati → rânduri ordonate: principal → subarticolele sale
    - Principal MATCHED când subarticol are neconf → **rând context verde** `▶ articol principal (matched)`
    - **Col 0**: `nr_ordine` din referință (ex: `33`) în loc de număr secvențial
    - **Col cod**: pentru subarticole → `↑ QCD22B33` (codul principal) sub codul subarticolului
    - Aceleași culori, roșu, stânga=referință, dreapta=ofertă

### Fix-uri critice descoperite în implementare
- **`nc_index` în `report_builder.py`** — folosea `deviz` (câmp inexistent), trebuia `deviz_ref`. Toate neconformitățile (LIPSA, DIFERENTA_CAMP etc.) prin `_enrich` au `deviz_ref` nu `deviz`.
- **`matched_ref` fără deviz** — `matches` list nu conține `deviz`. Fixat cu `matched_ref_cods` (ref_cod only).
- **`extract_articles_v3` linia 851** — suprascria `is_component=False` pe toate articolele regex, incluzând subarticolele detectate de parser. Eliminată suprascrierea.
- **`display_parent_cod` vs `is_component`** — modificarea `is_component=True` pe `$` coduri le excludea din `ref_dedup` în `match_global` (line 280). Soluție: câmp separat `display_parent_cod` pentru afișare, fără efect pe matching.

---

## Arhitectura rapidă (v7.0)

```
local_run.py
│
├── extract_document(referinta/oferta)
│   ├── f3_page_classifier.py   → clasificare pagini F3/NON_F3 (LLM + heuristic)
│   ├── f3_extractor.py         → extragere articole
│   │   ├── extract_articles_v3()        → calea principală (local_run)
│   │   ├── _apply_parent_inheritance()  → post-proc: parent_cod, display_parent_cod, cant_mostenita
│   │   └── extract_articles_from_text_v2() → cale alternativă (fără LLM)
│   └── f3_regex_parser.py      → parser regex
│       ├── nr_ordine, parent_nr_ordine pe fiecare articol
│       └── sub_counter reset la NR_SUBITEM
│
├── deviz_reconciler.py         → auto-heal devize lipsă (FĂRĂ LLM)
│
└── compare_and_report()
    ├── AgentComparator_local   → matching 5 straturi (ORPHAN eliminat)
    │   ├── Layer 1: best-first N:M (deviz+cod)
    │   ├── Layer 2: normalized N:M (AUT6752→$6752)
    │   ├── Layer 2.5: fuzzy determinist
    │   ├── Layer 2.6: UM + cantitate + denumire
    │   ├── Layer 3: LLM per deviz
    │   └── Layer 4: LLM global
    ├── shared/report_builder.py → build_raport_ierarhic()
    └── shared/report_word.py   → DOCX ierarhic (tabel identic v6.f + nr_ordine + parent)
```

**Spec v7.0:** `docs/superpowers/specs/2026-05-20-v7.0-design.md`  
**Plan v7.0:** `docs/superpowers/plans/2026-05-20-v7.0-implementation.md`  
**Checkpoint:** `output_AO/checkpoints/di_X_page_classes_<md5_hash>.json`

---

## Ce rămâne de făcut

1. **Merge `feature/7.0` → `main`** — când raportul e validat vizual complet
2. **Matching ierarhic v7.1** — cheia de căutare `deviz + cod_principal + cod_secundar` (deferit din v7.0; spec 2.2)
3. **OF1 LIPSA 3 / EXTRA 14** — minor, posibil cross-deviz
4. **Alte documente** — `Camin Maneciu/`, `Scoala Dragomiresti/`, `Scoala Sportiva Racari/` netestați
5. **`display_parent_cod`** verificat vizual în Word pentru `$8527036` → `↑ QCD22B33`

---

## Comenzi utile

```bash
# Branch curent
git checkout feature/7.0

# Rulare (șterge checkpointuri dacă e nevoie de extracție fresh)
rm -f output_AO/checkpoints/*.json
.venv/bin/python local_run.py

# Teste
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_compound_deviz_extraction.py

# Verificare metrici
.venv/bin/python -c "
import json; from pathlib import Path; from collections import Counter
for f in ['comparatie_oferta_1.json', 'comparatie_oferta_2.json']:
    comp = json.loads(Path(f'output_AO/{f}').read_text())
    by_tip = Counter(a.get('tip','?') for a in comp['neconformitati'])
    print(f'{f}: matched={comp[\"matches\"]}', dict(sorted(by_tip.items())))
"

# Verificare display_parent_cod pe un articol specific
.venv/bin/python -c "
import json; from pathlib import Path
data = json.loads(Path('output_AO/referinta.json').read_text())
arts = data.get('articole', [])
for a in arts:
    if a.get('display_parent_cod'):
        print(a.get('cod'), '→', a.get('display_parent_cod'), 'nr:', a.get('nr_ordine'))
" | head -20
```
