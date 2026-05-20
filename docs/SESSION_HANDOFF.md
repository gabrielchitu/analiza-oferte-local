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

### Rezultate ultima rulare (v7.0 post-sesiune)

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1041 | 2 | 14 | 0 |
| Oferta 2 | 1060 | 90 | 22 | 1 |

---

## Ce s-a construit în această sesiune (2026-05-20 cont.)

### Extractor (`shared/f3_extractor.py`)
1. **`_apply_parent_inheritance` — fallback parent detection** — când `$` cod nu împarte `nr_ordine` cu precedentul non-`$` (ex: CK25A apare de 2× cu cantități diferite), caută cel mai recent articol normativ nerevendicat din același deviz. Rezolvă cazul `$6720301` → `CK25A` (al doilea).
2. **Moștenire cant/UM pentru `display_parent_cod`** — `$` coduri cu `display_parent_cod` și `cantitate=0` moștenesc cant de la principal (ex: `$2608118` → cant=370 de la RPIF09C).
3. **`extract_articles_v3`** — nu mai suprascrie `is_component=False`; apelează `_apply_parent_inheritance`.

### Raport (`shared/report_word.py`)
4. **Col 1 "Categoria de lucrări"** — identic cu v6.f (deviz pe fiecare rând).
5. **Col 2 + Col 6 (cod REF/OFERTĂ)** — ierarhic: cod principal **bold+underline** sus-stânga, cod secundar jos-dreapta indentat (14pt).
6. **ARTICOL_EXTRA** — `oferta_display_parent_cod` propagat → principalul apare și pentru articole extra (nu doar LIPSA/DIFERENTA).
7. **Linie TOTAL DEVIZ** — split stânga/dreapta:
   - **Stânga**: `Ref: N principale + M subarticole`
   - **Dreapta**: `Ofertă: K principale ▼/▲/✓` cu culori (roșu=lipsă, portocaliu=extra, verde=egal)
   - Formula ofertă = `matched + neconformitati + extra` (nu doar `matched + extra`)
8. **Toate devizele** apar în raport (inclusiv cele fără neconformitati — doar cap + total).

### Comparator (`AgentComparator_local.py`)
9. **ARTICOL_EXTRA** — adăugat `oferta_display_parent_cod` și `nr_ordine_oferta` în nc-urile construite manual (nu treceau prin `_enrich`).

### Investigații/Decizii arhitecturale
10. **Matching ierarhic v7.1** — TENTAT dar REVERTAT. Problema: `display_parent_cod` asignat din ordinea extracției PDF. Același `$` cod poate avea parinte diferit în ref vs ofertă (PDF-uri cu structuri diferite) → cheia `(deviz, parent, cod)` nu e consistentă. Necesită catalog normativ pentru parent mapping (problemă de domeniu).
11. **Fuzzy matching `$` → normativ** — fuzzy matching legitim pentru resurse normative (`$7801893` "hidroizolatie" → `IZC06A`). Nu se poate bloca selectiv fără regresii majore.

---

## Arhitectura rapidă (v7.0)

```
local_run.py
│
├── extract_document(referinta/oferta)
│   ├── f3_page_classifier.py
│   ├── f3_extractor.py
│   │   ├── extract_articles_v3()            → calea principală
│   │   └── _apply_parent_inheritance()       → parent_cod, display_parent_cod,
│   │                                            cant_mostenita, fallback detection
│   └── f3_regex_parser.py                   → nr_ordine, parent_nr_ordine
│
└── compare_and_report()
    ├── AgentComparator_local → Layer 1-4 matching (deviz+cod)
    │   ├── Layer 1: best-first N:M exact
    │   ├── Layer 2: normalized N:M
    │   ├── Layer 2.5: fuzzy denominator
    │   ├── Layer 3: LLM per deviz
    │   └── Layer 4: LLM global
    ├── shared/report_builder.py → build_raport_ierarhic()
    └── shared/report_word.py   → DOCX ierarhic
        ├── Col 1: deviz (neschimbat)
        ├── Col 2: cod REF (principal bold, secundar indentat)
        ├── Col 6: cod OFERTĂ (idem)
        └── TOTAL DEVIZ: ref vs ofertă cu semnal vizual
```

**Spec v7.0:** `docs/superpowers/specs/2026-05-20-v7.0-design.md`

---

## Ce rămâne de făcut

1. **Merge `feature/7.0` → `main`** — după validare vizuală completă pe toate documentele
2. **Matching ierarhic v7.1** — necesită catalog normativ pentru mapare `$cod → normativ`; nu se poate face din structura PDF (inconsistentă între documente)
3. **Cazul `$6720287`/`$20020752`** — oferta are coduri DIFERITE sub CK25A față de ref; fuzzy le matchuiește la normative diferite (fals pozitiv). Fix în v7.1.
4. **Testare alte documente** — `Camin Maneciu/`, `Scoala Dragomiresti/`, `Scoala Sportiva Racari/`

---

## Comenzi utile

```bash
# Branch curent
git checkout feature/7.0

# Rulare fresh (șterge checkpointuri)
rm -f output_AO/checkpoints/*.json
.venv/bin/python local_run.py

# Teste
.venv/bin/python -m pytest tests/ -v --ignore=tests/test_compound_deviz_extraction.py

# Metrici
.venv/bin/python -c "
import json; from pathlib import Path; from collections import Counter
for f in ['comparatie_oferta_1.json', 'comparatie_oferta_2.json']:
    comp = json.loads(Path(f'output_AO/{f}').read_text())
    by_tip = Counter(a.get('tip','?') for a in comp['neconformitati'])
    print(f'{f}: matched={comp[\"matches\"]}', dict(sorted(by_tip.items())))
"

# Verificare display_parent_cod pe articole specifice
.venv/bin/python -c "
import json; from pathlib import Path
data = json.loads(Path('output_AO/referinta.json').read_text())
arts = data.get('articole', [])
subs = [a for a in arts if a.get('display_parent_cod')][:10]
for a in subs:
    print(a.get('cod'), '→', a.get('display_parent_cod'), 'nr:', a.get('nr_ordine'), 'cant:', a.get('cantitate'))
"
```

---

## Probleme cunoscute (nu bugs, limitări arhitecturale)

| Problemă | Cauză | Fix |
|----------|-------|-----|
| `$6720287` matchuit fuzzy la CK26A (fals pozitiv) | `display_parent_cod` inconsistent ref vs ofertă → Layer 0 imposibil | v7.1 cu catalog normativ |
| `$6720301` LIPSA în ref (parent=CK25A nr=6) | Parser extrage CK25A la nr=4 (ar trebui nr=6) — off-by-one PDF | Fallback parent OK pt display, match merge prin Layer 1 |
| Fuzzy `$` → normativ blocabil fără regresii | 110 matched se pierd dacă bloci cross-type | Acceptat ca v6.f behavior |
