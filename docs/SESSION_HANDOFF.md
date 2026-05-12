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

## Starea la 2026-05-12 (ultima sesiune)

**Branch:** `main` — **Tag stabil:** `V2_2026.06.12`  
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`  
**Date de test:** `input_AO/` — baza sportivă Răcari (1 referință + 3 oferte)

### Ce s-a construit în ultima sesiune

#### 1. Deviz Reconciler (`shared/deviz_reconciler.py`)
Mecanism de auto-reglare: dacă numărul de devize diferă între referință și o ofertă, sistemul re-scanează documentul DI pentru a găsi devizul lipsă fără a apela LLM.

**Logică critică — entry condition:**
- Codul devizului (ex: `226400`) trebuie găsit pe o pagină care are `STADIUL FIZIC:` în primele 8 linii
- **NU** este suficient ca numărul să apară oriunde pe pagină (footer, FORMULAR C6, total)
- Bug inițial fixat: găsea pagini FORMULAR C6 cu numărul în liste de resurse → marca 26 pagini greșit ca F3 → 513 articole false

#### 2. Fix matching Layer 2: N:M + filtru breviar

**Problema:** Ofertanții scriu uneori `6752` în loc de `AUT6752` (fără prefix). Parserul extrage `6752` → `$6752` (normalizare corectă), dar Layer 2 era 1:1 nu N:M.

**Fix aplicat în `AgentComparator_local.py::match_global`:**
- Filtrare artefacte breviar din referință: `cantitate=0` cu UM gol sau majuscule (ex: `ORA`, `BUC`) → excluse din matching (sunt template entries, nu articole reale)
- Layer 2 upgradeat de la 1:1 la N:M: toate instanțele cu același `norm_key` se potrivesc grupat

**Rezultat Oferta 1:** LIPSA scăzut 22 → 9, matched crescut cu 6.

---

## Rezultate ultima rulare

| Ofertă | matched | lipsa | extra | orphan |
|--------|---------|-------|-------|--------|
| Oferta 1 | 1376 | 9 | 26 | 7 |
| Oferta 2 | 1375 | 13 | 7 | 6 |
| Oferta 3 | 1352 | 35 | 13 | 6 |

### Devize cu situații speciale
- `226113` (OF1) ≈ `226118` (REF) — 100% overlap, auto-remap, ofertant a renumerotat
- `226400` (OF3) — deviz suplimentar: *montare lift persoane cu dizabilități*, absent din referință (pag 134, eDevize format) — **CORECT, nu bug**
- `226728` (OF1) — *Cheltuieli conexe organizării de șantier*, absent din referință
- `226F08` (REF) — *Amenajări exterioare*, absent din OF1 — posibil neinclus de ofertant

---

## Arhitectura rapidă

```
local_run.py
│
├── extract_document(referinta)
│   ├── f3_page_classifier.py   → clasificare pagini F3/NON_F3 (LLM + heuristic)
│   ├── f3_extractor.py         → extragere articole din pagini clasificate
│   └── f3_regex_parser.py      → parser regex linii brute DI
│
├── deviz_reconciler.py         → auto-heal devize lipsă (FĂRĂ LLM)
│   └── _find_deviz_page_range  → caută STADIUL FIZIC + cod în toate paginile
│
└── compare_and_report()
    ├── deviz_normalizer.py     → normalizare coduri deviz OCR
    ├── deviz_mismatch_detector → devize cu cod diferit dar conținut similar
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
Flag `_reclf_checked=True` → pagina verificată de LLM, nu se mai apelează în run-uri viitoare.

---

## Normalizare coduri articol

```python
# _normalize_cod în AgentComparator_local.py
"$3271724"  →  "$3271724"   # breviar propriu, prefix $ păstrat
"AUT6752"   →  "$6752"      # utilaj: prefix litere strip, sufix numeric cu $
"6752"      →  "$6752"      # bare numeric → $-prefix
"TSC02D11"  →  "TSC02D11"   # cod normativ interleaved (nemodificat)
"RPCR21O#"  →  "RPCR21C"    # O→0, strip # suffix
```

---

## Ce rămâne de investigat / îmbunătățit

1. **LIPSA rămase (9 în OF1, 13 în OF2, 35 în OF3):** unele sunt cross-deviz (orphan nedetectat complet), altele pot fi reale. Necesită verificare manuală.
2. **EXTRA 26 în OF1:** unele pot fi din extracție greșită. Investigare pagini breviar nefiltrate.
3. **UM_DIFERIT 66 în OF2:** volum mare, probabil OCR unitate de măsură (`ora` vs `ORA`, `mp` vs `MP`). Normalizare UM ar reduce zgomotul.
4. **Coduri `226F08` cu literă în poziție numerică:** verificat că e cod real (nu confuzie OCR). Mismatch-urile legate de el sunt reale.
5. **Raport DOCX:** secțiunea `EROARE_EXTRACTIE` (devize negăsite de reconciler) nu e încă adăugată în raport — apare doar în log.

---

## Comenzi utile

```bash
# Clonare pe mașină nouă
git clone <repo_url>
cd analiza-oferte-local
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # adaugă ANTHROPIC_API_KEY

# Rulare
.venv/bin/python local_run.py

# Teste
.venv/bin/python -m pytest tests/ -v

# Re-clasificare completă (șterge cache LLM)
rm output_AO/checkpoints/*.json && .venv/bin/python local_run.py

# Verificare rapidă devize
python3 -c "
import json; from pathlib import Path
ref = json.loads(Path('output_AO/referinta.json').read_text())
devize = sorted(set(a.get('deviz','') for a in ref['articole'] if a.get('deviz')))
print(f'Referinta: {len(devize)} devize: {devize}')
"
```

---

## Fișiere cheie de citit la reluare

1. `docs/ARCHITECTURE.md` — arhitectura completă
2. `shared/deviz_reconciler.py` — reconciler nou (sesiunea curentă)
3. `AgentComparator_local.py` — motor matching, funcțiile `_normalize_cod` și `match_global`
4. `local_run.py` — orchestrator, funcțiile `extract_document`, `compare_and_report`, `main`
