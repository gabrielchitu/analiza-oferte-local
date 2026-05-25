# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.

---

## TASK COMPLETED: Dedup Fix + deviz_cod Elimination (2026-05-25)

**Issue:** "4 ORGANIZARE SANTIER | BLC7" aparea ca grup absent din oferta, desi exista in referinta.

**Root Cause:** Deduplicarea articolelor in `local_run.py` folosea `art["deviz"]` (deviz_cod string = "BLC7") ca dimensiune grup. Referinta are doua grupuri distincte cu acelasi deviz_cod "BLC7":
- Paginile 18-19: "3 ORGANIZARE SANTIER" (deviz_cod="BLC7")
- Paginile 102-127: "4 ORGANIZARE SANTIER" (deviz_cod="BLC7")

Ambele aveau acelasi deviz_cod → acelasi dedup key → al doilea grup pierdut.

**Fix** ✅ FIXED
- `local_run.py`: dedup foloseste `deviz_key` (hash MD5) nu `deviz_cod` string
- `group_comparator.py`: eliminat tot codul mort care facea `ref_deviz_headers.get("BLC7")` intr-un dict cu hash-uri (returna intotdeauna None)
- `group_comparator.py`: parametru `deviz_cod` → `group_key` in `_compare_articles_in_group()`
- `group_comparator.py`: injectat `deviz_denumire` in fiecare nc din matched_groups (lipsea)

**Rezultat BR:**
- O1: **35/0/0** (era 21/2/3 inainte)
- O2: **35/0/0**
- O3: **35/0/3**
- O4: **32/3/12**

---

## TASK COMPLETED: Coloana 1 Raport Fix (2026-05-25)

**Issue:** Coloana "Categoria de lucrari" din raport afisa hash MD5 sau deviz_cod brut.

**Fix** ✅ FIXED
- `report_word.py`: col 1 afiseaza `Obiectul | Categoria` (ultimele 2 parti din deviz_denumire)
- `report_word.py`: `_add_principal_context_row()` semnat `(table, art, deviz_denumire)` — nu mai primeste deviz_cod
- OBIECTIVUL NU se afiseaza in col 1 — e deja in heading-ul grupului

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. PDF → Azure Document Intelligence → JSON
2. Extrage articolele din F3 (Lista cu cantitati de lucrari)
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Genereaza rapoarte DOCX cu neconformitati

**Repo:** `main` branch

---

## Baseline Holistic Results — Curent (2026-05-25)

| Client | O | matched_groups | ref-only | oferta-only | Note |
|--------|---|----------------|----------|-------------|------|
| Blocuri Racari | 1 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 2 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 3 | 35 | 0 | 3 | neinvestigat |
| Blocuri Racari | 4 | 32 | 3 | 12 | structura diferita |
| **Scoala Dragomiresti** | **1** | **22** | **0** | **0** | ✅ perfect |
| **Scoala Dragomiresti** | **2** | **22** | **0** | **0** | ✅ perfect |
| Scoala Sportiva Racari | 1-3 | 0 | — | — | ❌ SSR header format incompatibil |

---

## Arhitectura Cheie

### deviz_key = md5(OBIECTIVUL + OBIECTUL + CATEGORIA)
- Identificator canonic unic per grup de articole
- `deviz_cod` string (ex: "BLC7") NU e unic — NICIODATA ca lookup key sau dedup key
- Mai multe grupuri logice pot imparti acelasi deviz_cod (BLC5 = BLOC A, A2, A3, A4, B, C etc.)

### compare_by_groups()
```python
result = compare_by_groups(ref_articles, oferta_articles, ref_dh, oferta_dh)
# result.matched_groups: grupuri matchate ref↔oferta
# result.ref_only_groups: grupuri absente din oferta → ARTICOL_LIPSA
# result.oferta_only_groups: grupuri absente din ref → ARTICOL_EXTRA
```

### Deduplicare articole (local_run.py)
```python
# CORECT:
key = (art.get("deviz_key") or art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
```

---

## Fisiere cheie

| Fisier | Responsabilitate |
|--------|-----------------|
| `shared/deviz_header_extractor.py` | Extrage + normalizeaza deviz headers (OBIECTIVUL+Obiectul+Categoria) |
| `shared/group_comparator.py` | compare_by_groups(), HolisticComparison |
| `shared/report_word.py` | _generate_word_holistic(), col 1 = Obiectul|Categoria |
| `local_run.py` | Main pipeline, extract_document() x2 + compare_by_groups() |
| `shared/f3_extractor.py` | extract_articles_v3() — extrage articole per sub-grup pagini |

---

## Known Issues (pentru sesiunea urmatoare)

| # | Client | Issue | Prioritate |
|---|--------|-------|-----------|
| 1 | SSR | 0 grupuri holistic — `_extract_from_lines()` nu gaseste Obiectul/Categoria din format SSR | **PRIORITAR** |
| 2 | BR O3 | 3 oferta-only | Low |
| 3 | BR O4 | 3 ref-only, 12 oferta-only | Low |
| 4 | CM | Groups mismatch ref/oferta | Medium |

## Bug SSR — Debugging Start

```bash
.venv/bin/python3 -c "
import json; from pathlib import Path
from shared.deviz_header_extractor import _extract_from_lines
ckpt = list(Path('output_AO/Scoala Sportiva Racari/checkpoints').glob('di_referinta_page_classes_*.json'))[0]
d = json.loads(ckpt.read_text())
pcs = d if isinstance(d, list) else d.get('page_classes', [])
for pc in pcs:
    if pc.get('is_f3') and not pc.get('header_only'):
        lines = pc.get('lines', [])[:20]
        obj1, obj2, cat = _extract_from_lines(lines)
        print(f'pag {pc[\"page_number\"]}: obj2={obj2} cat={cat}')
        print('lines[:5]:', lines[:5])
        break
"
```

---

## Comenzi utile

```bash
# Pipeline
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log

# Holistic sumar rapid
python3 -c "
import json; from pathlib import Path
for f in sorted(Path('output_AO/Blocuri Racari').glob('holistic_oferta_*.json')):
    h = json.loads(f.read_text()); s = h['sumar']
    print(f.name, s.get('matched_groups'), s.get('ref_only_groups'), s.get('oferta_only_groups'))
"

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py
```

---

## Git State (2026-05-25)

Commits din sesiunea azi:
1. `fix(report): show Obiectul|Categoria in col1, not deviz_cod hash`
2. `fix(dedup): use deviz_key hash in article deduplication, not deviz_cod string`
3. `Revert "fix(deviz_key): strip all leading numeric section prefixes..."` (revert gresit)
4. `refactor(group_comparator): eliminate deviz_cod as lookup key`
