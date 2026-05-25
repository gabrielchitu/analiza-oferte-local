# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.

---

## TASK COMPLETED: BR Oferta 1 DEVIZ_MISMATCH Fix (2026-05-25)

**Root cause:** BR oferta 1 had 20 false DEVIZ_MISMATCH from cross-BLOC article matching (EC05B1 BLOC A vs BLOC B)

**Layer 1: Page Prefix Normalization** ✅ FIXED (commit e8b2c7e)
- Issue: Ref extracts `"1 LUCRARI..."` but Offer extracts `"001 1 LUCRARI..."` (page prefix from F3)
- Fix: Strip "00X " in `_make_deviz_key()` before hashing
- File: `shared/deviz_header_extractor.py` (function `_strip_page_prefix()` added)
- Result: -1 false DEVIZ_MISMATCH, +6 matched articles (308→314)

**Layer 2: Checkpoint Header Persistence** ✅ FIXED (commit ae25cd4)
- Issue: `compare_by_groups()` receives reconstructed headers from `_headers_from_articles()`, which loses page-level deviz_keys
- Solution: Persist deviz_headers to checkpoint_data in extract_document(), load directly in compare_and_report()
- Files modified:
  - `local_run.py:715-725`: Serialize deviz_headers to checkpoint_data
  - `local_run.py:1026-1058`: Load DevizHeader objects from checkpoint instead of page_classes
  - `local_run.py:329`: Pass ref_checkpoint_data to compare_and_report()
- Result: Ref & Oferta now have matching 7 deviz_keys, 18 matched groups (up from 0)

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. PDF → Azure Document Intelligence → JSON
2. Extrage articolele din F3 (Lista cu cantitati de lucrari)
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Genereaza rapoarte DOCX cu neconformitati

**Repo:** `main` branch | **Tag curent:** `v11.1`

---

## Baseline Holistic Results — v11.2 (2026-05-25 post Layer 2)

| Client | matched_arts | nonconformities | matched_groups | Notes |
|--------|-------------|-----------------|----------------|-------|
| Blocuri Racari | 308+553+434+316=1611 | 22+6+66+9=103 total | 18+0+0+0 | O1: 20 DEVIZ_MM (unchanged, architecture issue) |
| Camin Maneciu | 875+895=1770 | 227+291=518 | 0+0 | Groups mismatch (different headers ref/oferta) |
| **Scoala Dragomiresti** | **904+904=1808** | **35+39=74** | **21+0** | O1 headers matched (21/22), O2 headers mismatch |
| Scoala Sportiva Racari | — | — | — | JSON parse error (unrelated to this fix) |

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

## Remaining Issues After Layer 2

| # | Issue | Analysis |
|---|-------|----------|
| **1** | BR O1: 20 DEVIZ_MISMATCH still present (unchanged from 22 total) | Root cause ≠ headers—headers now matched. New hypothesis: articles themselves have wrong deviz_key assignment. |
| **2** | CM O1/O2: 0 matched_groups despite headers present | Ref has 19 deviz codes, offer has 35-36. Ref extraction not finding all building types. |
| **3** | SD O2: 0 matched_groups (22 deviz codes, both sides) | Headers loaded but keys don't match. May be different building/phase classification. |
| **4** | SSR: JSON parse error in pattern library | Unrelated to Layer 2; fix pattern_library.json corruption. |

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
