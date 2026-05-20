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

## Starea la 2026-05-20 (branch: feature/7.0, post-sesiune v7.1 parțial)

**Branch activ:** `feature/7.0`  
**Tag stabil:** `v7.0` (la baza branch-ului)  
**Main (stabil v6.f):** `main` cu tag `v6.f`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Rezultate ultima rulare

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1041 | 3 | 14 | 0 |
| Oferta 2 | 1060 | 90 | 22 | 1 |

---

## Ce s-a livrat în v7.1 (parțial, aceeași sesiune)

### Livrat și funcțional
1. **`build_ref_catalog(ref_articole)`** în `AgentComparator_local.py` — catalog `{$cod → parent_cod}` extras exclusiv din referință. Baza pentru v7.2 matching ierarhic.
2. **Separare articole fără deviz** — în `match_global()`, orice articol (principal sau subarticol) fără `deviz` setat e exclus din matching și returnat ca al 4-lea element al tuple-ului: `articole_fara_deviz = [('ref'|'oferta', art), ...]`
3. **`match_global` returnează 4-tuple**: `(neconformitati, matches, matched_ref_keys, articole_fara_deviz)`
4. **`articole_nelocalizate` în raport** — `build_raport_ierarhic()` acceptă `articole_fara_deviz=` și le include în output JSON. Raportul DOCX afișează secțiunea "Articole nelocalizate — verificare manuală" la final.

### Nerealizat (necesită v7.2)
- **Layer 0 matching ierarhic** — TENTAT și REVERTAT de 2× din cauza regresiei (1041→804 matched). Problema: `display_parent_cod` e inconsistent între ref și ofertă (extras din PDF, nu din catalog normativ). Necesită catalog normativ extern.
- **Caz A** — `$` fără parent dar cu deviz: exclus cu Layer 0. Revine în v7.2.
- **`$6720287` false positive** — fuzzy-matchuit la CK26A (0.54 pe "pvc"). Fix imposibil fără catalog normativ: blocarea selectivă afectează 152 matches legitime.

---

## Limitări arhitecturale documentate

| Problemă | Cauza | Fix necesar |
|----------|-------|------------|
| `$6720287` → CK26A fuzzy fals | threshold 0.45 prea mic; nu se poate ridica selectiv | Catalog normativ extern (v7.2) |
| Layer 0 imposibil | `display_parent_cod` din PDF — inconsistent ref vs ofertă | Catalog normativ ISDP/eDevize |
| `$6720289` LIPSA nerezolvat | Ref are `$6720289`, oferta are `$6720287` sub același CK25A | Același catalog normativ |

---

## Arhitectura rapidă (v7.0 + v7.1 parțial)

```
local_run.py
│
├── extract_document(referinta/oferta)
│   ├── f3_extractor.py → extract_articles_v3() + _apply_parent_inheritance()
│   └── f3_regex_parser.py → nr_ordine, parent_nr_ordine, sub_counter
│
└── compare_and_report()
    ├── AgentComparator_local
    │   ├── build_ref_catalog()              ← NOU v7.1: {$cod→parent}
    │   ├── match_global() → 4-tuple         ← NOU v7.1
    │   │   ├── Separă articole fără deviz (Caz B)
    │   │   └── Layer 1-4 (neschimbat)
    │   └── _apply_parent_inheritance()
    ├── shared/report_builder.py
    │   └── build_raport_ierarhic(articole_fara_deviz=) ← NOU v7.1
    └── shared/report_word.py
        ├── Tabel ierarhic (col 2+6: principal bold, secundar indentat)
        ├── TOTAL DEVIZ: ref vs ofertă cu semnal vizual ▼▲✓
        └── "Articole nelocalizate" la final         ← NOU v7.1
```

**Spec v7.1:** `docs/superpowers/specs/2026-05-20-v7.1-matching-ierarhic-design.md`

---

## Ce rămâne de făcut (v7.2)

1. **Catalog normativ extern** — mapare `$cod → normativ_cod` din baza de date ISDP/eDevize, independent de extracția PDF. Fără asta, Layer 0 și Caz A sunt imposibile.
2. **Layer 0 matching** cu catalog extern — cheie `(deviz, catalog_parent, $cod)` fiabilă
3. **Caz A** — `$` fără parent dar cu deviz: rând ⚠ în raport, exclus matching
4. **Merge `feature/7.0` → `main`** — după validare vizuală completă
5. **Testare alte documente** — `Camin Maneciu/`, `Scoala Dragomiresti/`, `Scoala Sportiva Racari/`

---

## Comenzi utile

```bash
# Branch curent
git checkout feature/7.0

# Rulare fresh
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

# Verificare ref_catalog
.venv/bin/python -c "
from AgentComparator_local import build_ref_catalog
import json; from pathlib import Path
ref = json.loads(Path('output_AO/referinta.json').read_text())['articole']
cat = build_ref_catalog(ref)
print(f'Catalog: {len(cat)} coduri resursa cu parent cunoscut')
print(list(cat.items())[:5])
"
```
