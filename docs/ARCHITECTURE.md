# Arhitectura și Logica Codului — Analizator Oferte Constructii

**Ultima actualizare:** 2026-05-12  
**Tag stabil:** `V2_2026.06.12`

---

## Scopul sistemului

Extrage articolele din documentele PDF de ofertă pentru lucrări de construcții (Formularul F3 — Lista cu cantități de lucrări), le compară cu o referință (caiet de sarcini), și generează rapoarte de neconformitate.

**Input:** DI JSON (Azure Document Intelligence) — referință + N oferte  
**Output:** DOCX raport per ofertă, JSON comparație, JSON articole extrase

---

## Fișiere principale

```
local_run.py               — Orchestrator principal (main pipeline)
AgentComparator_local.py   — Motor de matching multi-strat
anthropic_adapter.py       — Wrapper Anthropic API (compatibil OpenAI interface)

shared/
  f3_page_classifier.py    — Clasificare pagini DI: F3 vs NON_F3 (heuristic + LLM)
  f3_extractor.py          — Extragere articole din pagini F3 clasificate
  f3_regex_parser.py       — Parser regex articole din linii brute DI
  f3_page_reclassifier.py  — Post-procesor euristic (dezactivat, referință)
  deviz_reconciler.py      — Auto-reglare: re-scan devize lipsă din documente
  article_matcher.py       — Matching fuzzy cod articol (SequenceMatcher + LLM)
  deviz_normalizer.py      — Normalizare coduri deviz între referință și ofertă
  deviz_mismatch_detector.py — Detectare devize cu cod diferit dar conținut similar
  deviz_namer.py           — Populare denumiri devize din DI
  deviz_corrector.py       — Corecție coduri deviz (OCR fixes)
  comparator.py            — Comparare articole individuale (câmp cu câmp)
  orphan_detector.py       — Detectare articole prezente în ofertă la deviz diferit
  extraction_validator.py  — Validare acoperire extracție + marcare EXTRA suspecte
  table_extractor.py       — Extragere articole din tabele DI (format structurat)
  report_word.py           — Generare raport DOCX
  report_excel.py          — Generare raport XLSX (dezactivat)

tests/                     — Suite teste pytest (87 teste)
docs/superpowers/          — Design specs și implementation plans
```

---

## Fluxul complet (local_run.py::main)

```
1. extract_document(referinta)
   ├── classify_pages (LLM sau checkpoint cache)
   ├── _reclassify_missed_f3_pages (LLM țintit, cu _reclf_checked cache)
   └── extract_articles_v3 + table_extractor

2. Pentru fiecare ofertă:
   ├── extract_document(oferta)   [același flux ca mai sus]
   │
   ├── RECONCILIERE DEVIZE (deviz_reconciler.py)
   │   ├── devize_extra = oferta \ referință
   │   │   └── reconcile_missing_devize(referință, devize_extra)
   │   │       — re-scaneaza referința pentru devize detectate în ofertă
   │   └── devize_lipsa = referință \ ofertă
   │       └── reconcile_missing_devize(oferta, devize_lipsa)
   │           — re-scaneaza oferta pentru devize din referință
   │
   └── compare_and_report(ref_articles, oferta_articles)
       ├── normalize_devize          — normalizare coduri deviz OCR
       ├── detect_deviz_mismatches   — devize cu cod diferit, conținut similar (≥90% → auto-remap)
       ├── match_global              — matching 6 straturi (vezi detalii jos)
       ├── detect_orphans            — articole la deviz greșit
       ├── mark_suspicious_extras    — EXTRA cu cod prezent în referință
       └── generate_word             — raport DOCX
```

---

## Motor de matching (AgentComparator_local.py::match_global)

**6 straturi în ordine de precizie:**

| Strat | Tip | Descriere |
|-------|-----|-----------|
| **Layer 1** | Exact N:M | `(deviz, cod)` identic, potrivire cantitate sortată |
| **Layer 2** | Normalized N:M | `_normalize_cod` egalizează: `O→0`, `l→1`, `AUT6752→$6752`, `$6752→$6752` |
| **Layer 2.5** | Determinist fuzzy | Similaritate cod ≥ 85% + Jaccard denumire ≥ 0.4 (fără LLM) |
| **Layer 2.6** | Denumire+UM+cantitate | Fallback pe UM + cantitate + Jaccard denumire (fără cod) |
| **Layer 3** | LLM fuzzy per deviz | LLM potrivire per grupă deviz pentru rest nemat-uite |
| **Layer 4** | LLM global | LLM fuzzy global pentru ce rămâne cross-deviz |

**Preprocesare înainte de matching:**
- Deduplicare 4-tuple: `(deviz, cod, um, cantitate)`
- Filtru artefacte breviar: `cantitate=0` cu UM gol sau majuscule → excluse din comparație

---

## Normalizare coduri articol (`_normalize_cod`)

```
$3271724    →  $3271724    (breviar propriu, prefix $ păstrat)
AUT6752     →  $6752       (utilaj fără prefix → sufix numeric cu $)
6752        →  $6752       (cod bare numeric → $-prefix)
TSC02D11    →  TSC02D11    (cod normativ interleaved, neatins)
VA02B08     →  VA02B08     (cod normativ standard, neatins)
RPCR21O#    →  RPCR21C     (O→0, strip suffix #)
```

---

## Checkpoint sistem (F3 page classifier)

Checkpoints salvate în `output_AO/checkpoints/di_X_page_classes_<hash>.json`.

**Hash-ul** e MD5 pe sursa `f3_page_classifier.py` → cache invalidat automat la modificarea clasificatorului.

**Structura unei intrări:**
```json
{
  "page_number": 73,
  "is_f3": true,
  "deviz_cod": "226208",
  "deviz_den": "STRUCTURA DE REZISTENTA",
  "lines": ["linie1", "linie2", ...],
  "header_only": false,
  "needs_llm": false,
  "_reclf_checked": true
}
```

**Flag `_reclf_checked`:** pagina a fost verificată de LLM pentru reclasificare → nu se mai apelează LLM în run-uri ulterioare.

---

## Reconciler devize (deviz_reconciler.py)

**Declanșat când:** numărul de devize din ofertă ≠ numărul din referință.

**Algoritm `_find_deviz_page_range`:**
1. Caută codul devizului în toate paginile DI (full scan)
2. **Entry condiție:** codul apare în context `STADIUL FIZIC:` (fereastra 8 linii) — previne false pozitive din FORMULAR C6, footer-uri, totaluri
3. Continuă consecutive până la header cu cod diferit sau pagină deja clasificată alt deviz
4. Actualizează checkpoint: paginile găsite → `is_f3=True`, `deviz_cod=target`
5. Dacă negăsit → raportează `[RECONCILE] NEGASIT — eroare OCR/parsare`

---

## Tipuri de neconformități raportate

| Tip | Semnificație |
|-----|-------------|
| `ARTICOL_LIPSA` | Articol din referință absent complet din ofertă |
| `ARTICOL_EXTRA` | Articol în ofertă fără corespondent în referință |
| `ARTICOL_ORPHAN` | Articol prezent în ofertă la deviz diferit față de referință |
| `COD_SIMILAR` | Cod potrivit prin normalizare/fuzzy (cu diferențe de câmp) |
| `UM_DIFERIT` | Aceeași cantitate, unitate de măsură diferită |
| `DIFERENTA_CAMP` | Cantitate, preț sau altă valoare diferită |
| `ARTICOL_ORPHAN` | Cod prezent în ofertă dar la altă categorie (deviz) |

---

## Variabile de mediu (.env)

```
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-haiku-4-5-20251001   # sau claude-sonnet-4-6
```

---

## Rulare

```bash
# Instalare
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# Run complet
python local_run.py

# Teste
python -m pytest tests/ -v

# Re-clasificare de la zero (sterge checkpoints)
rm output_AO/checkpoints/*.json && python local_run.py
```
