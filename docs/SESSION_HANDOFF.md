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

## Starea la 2026-05-21 (branch: feature/7.0)

**Branch activ:** `feature/7.0`  
**Tag stabil:** `v7.0` (la baza branch-ului)  
**Main (stabil v6.f):** `main` cu tag `v6.f`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Rezultate ultima rulare

| Ofertă | matched | lipsa | extra | similar |
|--------|---------|-------|-------|---------|
| Oferta 1 | 1056 | 3 | 36 | 0 |
| Oferta 2 | 1066 | 89 | 41 | 1 |

**Față de v7.0 baseline (1041/1060):** +15/+6 matched datorită fix-ului parser eDevize.

---

## Ce s-a livrat (sesiunile 2026-05-20/21)

### v7.0
- `nr_ordine`, `parent_nr_ordine` pe articole extrase
- `_apply_parent_inheritance` cu fallback parent detection
- `ARTICOL_ORPHAN`/`lenient` eliminate; deduplicare O(n)
- `shared/report_builder.py`: `build_raport_ierarhic()`
- Raport DOCX ierarhic: col 2+6 principal/secundar, TOTAL DEVIZ split ref/ofertă

### v7.1 parțial
- `build_ref_catalog()` în `AgentComparator_local.py` — `{$cod → parent_cod}` din ref
- `match_global()` returnează **4-tuple**: `(neconformitati, matches, matched_ref_keys, articole_fara_deviz)`
- Articole fără deviz excluse din matching → secțiune "Articole nelocalizate" în DOCX

### Parser fix (2026-05-21)
- **Format eDevize breviar**: linii `-XXXX:NNNNNNN` → convertite la `$NNNNNNN` în `extract_articles_regex`
- **142 coduri** în referință în acest format; parser fix captează o parte din ele (+15 matched OF1)
- Restul (pagina 66, format breviar fără cantitate explicită) — nerezolvat (vezi limitări)

---

## Limitări arhitecturale documentate

| Problemă | Cauza | Fix necesar |
|----------|-------|------------|
| `$6720287` → CK26A fuzzy fals | threshold 0.45 prea mic; nu se poate ridica selectiv | Catalog normativ extern (v7.2) |
| Layer 0 matching imposibil | `display_parent_cod` inconsistent ref vs ofertă (extras din PDF) | Catalog normativ ISDP/eDevize |
| Breviar eDevize pg 66 | Resurse `$` listate fără cantitate între articole normative | Parser extins pentru format breviar |
| Extra +22 față de v7.0 | `$` coduri eDevize care fuzzy-matchuiau greșit la normative → acum EXTRA | Acceptat ca mai precis |

---

## Arhitectura rapidă

```
local_run.py
│
├── extract_document(referinta/oferta)
│   ├── f3_extractor.py → extract_articles_v3() + _apply_parent_inheritance()
│   └── f3_regex_parser.py
│       ├── extract_articles_regex() → normalizare -XXXX:NNNNNNN → $NNNNNNN ← NOU
│       └── nr_ordine, parent_nr_ordine, sub_counter
│
└── compare_and_report()
    ├── AgentComparator_local
    │   ├── build_ref_catalog()              ← v7.1: {$cod→parent}
    │   └── match_global() → 4-tuple         ← v7.1: +articole_fara_deviz
    ├── shared/report_builder.py
    │   └── build_raport_ierarhic(articole_fara_deviz=)
    └── shared/report_word.py
        ├── Tabel ierarhic (col 2+6)
        ├── TOTAL DEVIZ: ref vs ofertă ▼▲✓
        └── "Articole nelocalizate" la final
```

---

## Ce rămâne de făcut

1. **Format breviar eDevize** — resurse `$` fără cantitate (pg 66 referință, SA04E): parser trebuie să le extragă și să le trimită la `_apply_parent_inheritance` pentru a moșteni cant/UM de la normativ
2. **Catalog normativ extern** — mapare `$cod → normativ` din ISDP/eDevize pentru Layer 0 (v7.2)
3. **Merge `feature/7.0` → `main`** — după validare vizuală completă
4. **Testare alte documente** — `Camin Maneciu/`, `Scoala Dragomiresti/`, `Scoala Sportiva Racari/`

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

# Verificare format eDevize în DI
# python3 -c "import json,re; from pathlib import Path; di=json.loads(Path('input_AO/di_referinta.json').read_text()); _RE=re.compile(r'^-\d{4}:\s*(\d+)$'); matches=[(p.get('page_number'), l.get('content','')) for p in di.get('pages',[]) for l in p.get('lines',[]) if _RE.match((l.get('content','') if isinstance(l,dict) else str(l)).strip())]; print(f'{len(matches)} coduri breviar in ref')"
```
