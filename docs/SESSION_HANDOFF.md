# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.

---

## PRIM TASK LA SESIUNEA URMATOARE (2026-05-25 BLOCKED)

**Problema:** BR oferta 1 has 20 false DEVIZ_MISMATCH. Root cause: **TWO-LAYER ARCHITECTURE BUG**

**Layer 1: Page Prefix Normalization** ✅ FIXED
- Issue: Ref extracts `"1 LUCRARI..."` but Offer extracts `"001 1 LUCRARI..."` (page prefix from F3)
- Fix: Strip "00X " in `_make_deviz_key()` before hashing
- File: `shared/deviz_header_extractor.py` (function `_strip_page_prefix()` added)
- Result: -1 false DEVIZ_MISMATCH, +6 matched articles (308→314)

**Layer 2: Matching Headers Architecture** ❌ BLOCKED (NEXT TASK)
- Issue: `compare_by_groups()` receives reconstructed headers from `_headers_from_articles()`, which loses page-level deviz_keys
- Evidence: Ref & Offer both have IDENTICAL 36 deviz_keys (verified), but matching returns only 1 matched instead of ~14
- Root: checkpoint_data doesn't persist page_classes, so original page-level headers can't be reconstructed
- **Solution:** Modify extract_document() to save deviz_headers to checkpoint_data, then pass them directly to compare_by_groups()
- **See memory:** `br_deviz_key_matching_fix_2026_05_25.md` for exact implementation steps

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. PDF → Azure Document Intelligence → JSON
2. Extrage articolele din F3 (Lista cu cantitati de lucrari)
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Genereaza rapoarte DOCX cu neconformitati

**Repo:** `main` branch | **Tag curent:** `v11.1`

---

## Baseline Holistic Results — v11.1 (2026-05-25)

| Client | matched_arts | nonconformities | matched_groups | Notes |
|--------|-------------|-----------------|----------------|-------|
| Blocuri Racari | 308+553+434+316=1611 | 9+6+66+9=90 total | varies per oferta | O1: 20 DEVIZ_MM (false) |
| Camin Maneciu | 0 | 343 (all LIPSA) | 0 | no extraction |
| **Scoala Dragomiresti** | **904+904=1808** | **35+39=74** | **22+22** | ✅ clean |
| Scoala Sportiva Racari | 1198 | 709 (389 DEVIZ_MM) | 0 | ❌ 0 matched_groups |

---

## Arhitectura v11.1 (schimbari vs v11.0)

### extract_articles_v3() — schimbare fundamentala

```python
# INAINTE: grupare pe deviz_cod
pages_by_deviz["BLC1"] = [36 pagini]  # toate blocurile combinate
# DUPA: grupare pe (deviz_cod, deviz_key-din-header-paginii)
pages_by_deviz[("BLC1", hash_BLOC_A)] = [6 pagini BLOC A]
pages_by_deviz[("BLC1", hash_BLOC_B)] = [6 pagini BLOC B]
```

### compare_by_groups() — comparatie holistica

```python
result = compare_by_groups(ref_articles, oferta_articles, ref_dh, oferta_dh)
# result.matched_groups: grupuri matchate ref↔oferta
# result.ref_only_groups: grupuri absente din oferta → ARTICOL_LIPSA
# result.oferta_only_groups: grupuri absente din ref → ARTICOL_EXTRA
```

### deviz_key concept

**deviz_key = md5(OBIECTIVUL + OBIECTUL + CATEGORIA)**
- Distinct per page (not per deviz_cod)
- Same article code in different blocs = different deviz_keys
- Example: BLOC A vs BLOC B = different groups

---

## Known Issues

| # | Issue | Status |
|---|-------|--------|
| **1** | BR oferta 1: 20 false DEVIZ_MISMATCH (page prefix + headers architecture) | **BLOCKED** — Layer 1 done, Layer 2 next |
| **2** | CM: 0 extraction (no articles found) | Medium |
| **3** | SSR: 0 matched_groups (headers not found) | Medium |

---

## Fisiere cheie

| Fisier | Responsabilitate |
|--------|-----------------|
| `shared/deviz_header_extractor.py` | Extrage + normalizeaza deviz headers (OBIECTIVUL+Obiectul+Categoria) |
| `shared/group_comparator.py` | compare_by_groups(), HolisticComparison |
| `local_run.py` | Main pipeline, calls extract_document() x2 + compare_by_groups() |
| `shared/f3_extractor.py:extract_articles_v3()` | Extrage articole per sub-grup pagini (per deviz_key) |

---

## Comenzi utile

```bash
# Run BR oferta 1
python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | grep -E "(Neconformitati|Matched|DEVIZ_MM)"

# Diagnostic: list all deviz_keys from checkpoint
python3 << 'EOF'
import json; from pathlib import Path
from shared.deviz_header_extractor import _extract_from_lines, _make_deviz_key

ckpt = list(Path('output_AO/Blocuri Racari/checkpoints').glob('di_oferta_1_page_classes_*.json'))[0]
pcs = json.loads(ckpt.read_text())
pcs = pcs if isinstance(pcs, list) else pcs.get('page_classes', [])

for pc in [p for p in pcs if p.get('is_f3')][:3]:
    obj1, obj2, cat = _extract_from_lines(pc.get('lines', [])[:25])
    key, valid = _make_deviz_key('OBJ_INV', obj2, cat)
    print(f'Page {pc["page_number"]}: {key} | Obj: {obj2}')
EOF
```

---

## Git State (2026-05-25 EOD)

- Branch: main (tracking origin/main)
- Latest commits:
  - `memory(br-fix)`: document deviz_key matching architecture issue and two-layer solution plan
  - `wip: add deviz_headers extraction from checkpoint (incomplete - page_classes not saved)`
  - `fix(deviz_key): strip '00X ' page prefix from Obiect/Categoria to fix cross-page matching`

All fixes for Layer 1 (prefix normalization) committed. Layer 2 (checkpoint persistence) WIP.
