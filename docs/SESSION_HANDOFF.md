# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. PDF → Azure Document Intelligence → JSON
2. Extrage articolele din F3 (Lista cu cantitati de lucrari)
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Genereaza rapoarte DOCX cu neconformitati

**Repo:** `refactor/v10` branch | **Tag curent:** `v11.0`

---

## PRIM TASK LA SESIUNEA URMATOARE: Fix SSR holistic=0

**Problema:** Scoala Sportiva Racari are 0 grupuri holistic matched (3-layer extractor nu gaseste Obiectul/Categoria in paginile F3 SSR).

**Diagnostic rapid:**
```bash
.venv/bin/python3 -c "
import json; from pathlib import Path
from shared.deviz_header_extractor import _extract_from_lines
ckpt = list(Path('output_AO/Scoala Sportiva Racari/checkpoints').glob('di_referinta_page_classes_*.json'))[0]
d = json.loads(ckpt.read_text())
pcs = d if isinstance(d, list) else d.get('page_classes', [])
for pc in pcs[:5]:
    if pc.get('is_f3') and not pc.get('header_only'):
        lines = pc.get('lines', [])[:20]
        obj1, obj2, cat = _extract_from_lines(lines)
        print(f'pag {pc[\"page_number\"]}: obj2={repr(obj2)} cat={repr(cat)}')
        print(f'  lines[:5]={lines[:5]}')
"
```

**Ce probabil lipseste:** regex-ul `_OBJ2_RE` si `_CAT_RE` din `shared/deviz_header_extractor.py` nu se potriveste cu formatul SSR.

---

## Starea la 2026-05-24 (v11.0)

### Concept cheie: deviz_key

**deviz_key = hash(OBIECTIVUL + OBIECTUL + CATEGORIA)**

- Calculat PER PAGINA F3 (nu per deviz_cod!)
- Daca OBIECTIVUL = X, Obiectul = Y, Categoria = Z → deviz_key = md5(normalize(X|Y|Z))[:16]
- BLC1 cu 6 blocuri → 6 deviz_key distincte
- Matching ref↔oferta pe deviz_key (nu pe deviz_cod)

### Baseline holistic (v11.0)

| Client | O | matched_arts | matched_groups | Issues |
|--------|---|-------------|----------------|--------|
| Blocuri Racari | 1 | 299 | 22 | |
| Camin Maneciu | 1 | 875 | 19 | |
| **Scoala Dragomiresti** | **1** | **904** | **22** | ✅ |
| Scoala Sportiva Racari | 1 | 2168 | **0** | ❌ fix urgent |

---

## Arhitectura v11.0 (schimbari majore vs v10)

### extract_articles_v3() — schimbare fundamentala

```python
# INAINTE: grupare pe deviz_cod
pages_by_deviz["BLC1"] = [36 pagini]  # toate blocurile combinate
# DUPA: grupare pe (deviz_cod, deviz_key-din-header-paginii)
pages_by_deviz[("BLC1", hash_BLOC_A)] = [6 pagini BLOC A]
pages_by_deviz[("BLC1", hash_BLOC_B)] = [6 pagini BLOC B]
# etc.
```

Fisier: `shared/f3_extractor.py:865-996`

### compare_by_groups() — comparatie holistica

```python
# shared/group_comparator.py
result = compare_by_groups(ref_articles, oferta_articles, ref_dh, oferta_dh)
# result.matched_groups: grupuri matchate ref↔oferta
# result.ref_only_groups: grupuri absente din oferta → ARTICOL_LIPSA
# result.oferta_only_groups: grupuri absente din ref → ARTICOL_EXTRA
```

### _headers_from_articles() — cheie deviz_key

```python
# local_run.py:100-117
# Keyed by deviz_key (nu deviz_cod)
headers["hash_BLOC_A"] = DevizHeader(obj1, obj2, cat, ...)
```

---

## Fisiere cheie

| Fisier | Responsabilitate |
|--------|-----------------|
| `shared/deviz_header_extractor.py` | Extrage OBIECTIVUL+Obiectul+Categoria din liniile F3 |
| `shared/group_comparator.py` | compare_by_groups(), HolisticComparison |
| `shared/report_word.py:_generate_word_holistic()` | Word report holistic |
| `shared/f3_extractor.py:extract_articles_v3()` | Extrage articole per sub-grup pagini |
| `shared/deviz_matcher.py:match_devize_by_3layer()` | Matching grupuri ref↔oferta pe similitudine |
| `local_run.py:_headers_from_articles()` | Reconstituie headers din articole |

---

## Known Issues

| # | Issue | Prioritate |
|---|-------|------------|
| **1** | **SSR holistic=0** — `_extract_from_lines` nu gaseste Obiectul/Categoria in SSR | **URGENT** |
| 2 | BR O2 DEVIZ_MISMATCH ridicat | Medium |
| 3 | CM O2: 6 ref-only, 22 oferta-only | Medium |

---

## Push la origin (SSH)

```bash
! git push origin refactor/v10 && git push origin v11.0
```

---

## Comenzi utile

```bash
# Full pipeline
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti"

# Holistic JSON
python3 -c "import json; from pathlib import Path; h=json.loads(Path('output_AO/Scoala Dragomiresti/holistic_oferta_1.json').read_text()); print(h['sumar'])"

# Teste
.venv/bin/python3 -m pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py --ignore=tests/shared/test_f3_regex_parser_multiline.py --ignore=tests/test_normalize_cod.py

# Diagnostic SSR headers
.venv/bin/python3 -c "
import json; from pathlib import Path
from shared.deviz_header_extractor import _extract_from_lines
ckpt = list(Path('output_AO/Scoala Sportiva Racari/checkpoints').glob('di_referinta_page_classes_*.json'))[0]
d = json.loads(ckpt.read_text())
pcs = d if isinstance(d, list) else d.get('page_classes', [])
for pc in [p for p in pcs if p.get('is_f3')][:3]:
    obj1, obj2, cat = _extract_from_lines(pc.get('lines',[])[:20])
    print(f'pag {pc[\"page_number\"]}: obj2={repr(obj2)} cat={repr(cat)}')
    print(f'  lines[:3]={pc.get(\"lines\",[])[:3]}')
"
```
