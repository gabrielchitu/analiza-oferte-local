# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.

---

## TASK COMPLETED: Deviz Denomination Report Display Fix (2026-05-25)

**Issue:** Reports showed MD5 hashes (e.g., `4d91083264aeebaa`) instead of three-element denomination (e.g., `OBIECTIVUL | Obiectul | Categoria`)

**Root Cause:** Reports used MD5 hash as deviz denomination fallback when headers not found
- group_comparator.py fell back to `arts[0].deviz_denumire` which contained hash
- report_word.py displayed code (hash) when header object was None

**Fix** ✅ FIXED (commit 78f8418)
- group_comparator.py: Add fallback chain (3 levels) to extract three-element denomination
  1. Try header lookup by deviz_key (primary)
  2. Try header lookup by deviz_cod from article (handles deviz_key mismatch)
  3. Use article's deviz_header metadata (last resort)
- report_word.py: Pass deviz_denumire to report builder, use it when header is None
- Result: All reports now show "OBIECTIVUL | Obiectul | Categoria" instead of hash

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

## Architecture Issue Identified: deviz_key Mismatch

**Root cause:** Ref and oferta extract different deviz_keys for same buildings
- deviz_key = MD5(OBIECTIVUL | Obiectul | Categoria)
- Same building: ref key ≠ oferta key (OCR/formatting differences)
- Articles grouped by deviz_key, headers keyed by deviz_cod
- Result: Headers not found when looking up by article deviz_key

**Impact on current results:**
- BR O1: Matched groups 18→5 (when changed to deviz_key keying)
- Deviz_denumire empty in reports (headers not found)
- All clients affected: different deviz_keys prevent cross-document matching

## Next Session: Two Options

**Option A (Recommended):** Fix deviz_key normalization
- Strip more prefixes, normalize OCR variants
- Ensure same building → same deviz_key across documents
- Enables proper page-level grouping and header matching

**Option B (Quick):** Revert to deviz_cod grouping
- Change _articles_by_deviz to group by deviz (code) not deviz_key (hash)
- Headers will be found (keyed by deviz_cod)
- Trade: lose page-level grouping capability

**See memory:** session_2026_05_25_layer2_and_reporting.md for architecture notes

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
