# Session State — 2026-05-22 (actualizat)

## Fix 3: Scoala Dragomiresti DEVIZ_MM 624→2 (2026-05-22)

### Problema
`_CATEGORIA_OPT_RE` în `f3_page_classifier.py:107` captura `[0-9]{0,4}` — nu poate
captura punct decimal. "Stadiul fizic: 1.4 INSTALATII TERMICE" → cat_num=`1` (nu `1.4`).
Toate 4 stadii din obiect 1 (1.1, 1.2, 1.3, 1.4) → cod identic `1.0-1` în referință.
Oferta: "Stadiul fizic: 004 1.4..." → cat_num=`004` corect → `001-004`.
Rezultat: 624 DEVIZ_MISMATCH false (articolele existau dar deviz diferit).

### Fix 1: `f3_page_classifier.py:107`
`[0-9]{0,4}` → `[0-9]{0,4}(?:\.[0-9]{0,2})?`
Referința obține `1.0-1.1`, `1.0-1.2`, `1.0-1.3`, `1.0-1.4` (4 coduri distinct).

### Fix 2: `deviz_matcher.py` — Strategy 0 (numeric structural)
Înaintea fuzzy text: extrage `(obj_int, cat_int)` din ambele formate:
- `001-004` → `(1, 4)` (int(001)=1, int(004)=4)
- `1.0-1.4` → `(1, 4)` (int(1.0)=1, frac(1.4)×10=4)
Map direct când `(obj_i, cat_i)` identic. 22/22 devize SD mapate corect.

**Impact:** SD O1: matched 651→910 (+259), DEVIZ_MM 624→2. SD O2: matched 692→910 (+218), DEVIZ_MM 602→2.

---

## Fix 2: Parser Scatter Format BR O3 (commit HEAD-1)

`_preprocess_scattered_format` în `shared/f3_regex_parser.py:535`:
`"Art. asimilat"` detectat fals ca UM (ART in UM_KNOWN, verificare pe primul token).
Fix: `len(_f3_um_tokens) == 1`.
**Impact:** BR O3: matched 395→414 (+19), LIPSA 25→21 (-4).

---

## Baseline REAL (post-toate-fix-urile, 2026-05-22)

| Client | Ofertă | matched | LIPSA | EXTRA | DEVIZ_MM |
|--------|--------|---------|-------|-------|----------|
| Blocuri Racari | O1 | 308 | 47 | 0 | 20 |
| Blocuri Racari | O2 | 551 | 2 | 0 | 28 |
| Blocuri Racari | O3 | 414 | 21 | 5 | - |
| Blocuri Racari | O4 | 316 | 49 | 1 | 9 |
| Camin Maneciu | O1 | 1056 | 1 | 36 | 2 |
| Camin Maneciu | O2 | 1066 | 84 | 41 | 5 |
| **Scoala Dragomiresti** | **O1** | **910** | **2** | **0** | **2** |
| **Scoala Dragomiresti** | **O2** | **910** | **2** | **1** | **2** |
| Scoala Sportiva Racari | O1 | 2152 | 2 | 122 | 11 |
| Scoala Sportiva Racari | O2 | 1142 | 4 | 56 | 328 |
| Scoala Sportiva Racari | O3 | 2260 | 6 | 315 | 325 |

**Nota:** BR = Blocuri Racari baseline real=308 (checkpoints noi). SD dramatic îmbunătățit.

---

## Known Issues Active

1. **IZDO3D1 OCR** — acceptat
2. **BR O3 EXTRA=5** — de investigat
3. **SD DEVIZ_MM=2** — 2 rămase, probabil LIPSA reale (de verificat)
4. **CM O2 LIPSA=84** — neinvestigat
5. **SSR O3 EXTRA=315** — neinvestigat
6. **SSR O2/O3 DEVIZ_MM=328/325** — neinvestigat (posibil același tip de bug ca SD?)

---

## Commits sesiune 2026-05-22

```
fix(deviz): resolve 620+ false DEVIZ_MISMATCH for Scoala Dragomiresti
fix(parser): scatter format is_f3_um requires single-token UM
fix(matching): Layer 2.5 uses all offer instances per key in N:M
fix(parser): treat NR+UM line (e.g. '82 M') as UM in READING state
feat(diagnostics): ...
```

**12+ commits ahead origin/main** (SSH push blocat)

---

## Cum să rulezi

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti"

for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  .venv/bin/python3 multi_client_run.py --client "$c"
done

.venv/bin/python3 run_diagnostics.py

.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```

## Ce urmează

Refactorizare. Baseline arhitectural documentat. Citește ARCHITECTURE.md înainte.
