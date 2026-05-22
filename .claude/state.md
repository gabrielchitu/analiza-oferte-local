# Session State — 2026-05-22 (final)

## Fix-uri livrate sesiunea curentă (în ordine)

### Fix 1: Parser Scatter (BR O3, commit anterior)
`shared/f3_regex_parser.py:535` — `is_f3_um` single-token only.

### Fix 2: SD DEVIZ_MM (commit anterior)
- `f3_page_classifier.py:107` — `_CATEGORIA_OPT_RE` captează decimal
- `shared/deviz_matcher.py` — Strategy 0 numeric structural

### Fix 3: Raport client + ofertant (commit anterior)
- `local_run.py:299,996` — `client_config.name` în session
- `local_run.py:347` — `_extract_ofertant_name` rewrite (Executant: prioritar)

### Fix 4: COD_SIMILAR mereu + DESCRIERE_DIFERITA + cant=0 filter
- `AgentComparator_local.py` — Layer 2.1/2.6 COD_SIMILAR always; cant=0 skip
- `shared/comparator.py` — DESCRIERE_DIFERITA tip nou (sim < 0.85)
- `shared/report_word.py` — LILA_FILL pentru DESCRIERE_DIFERITA

### Fix 5: Strategy 0 numai când formate diferă (CM regresia)
- `shared/deviz_matcher.py` — Strategy 0 aplică NUMAI când offer e padded-integer (001) si ref e decimal (1.0)
- `_extract_numeric_struct` returnează `is_padded` flag

## Baseline FINAL (2026-05-22, post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD |
|--------|---|---------|-------|-------|----------|----|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 3 |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 52 |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 5 |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 223 |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 201 |
| Scoala Dragomiresti | 1 | 910 | 2 | 0 | 1 | 14 |
| Scoala Dragomiresti | 2 | 910 | 2 | 1 | 1 | 14 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 |

**DD = DESCRIERE_DIFERITA** — tip nou. CM/SSR/BR O3 au multe — parte false pozitive din OCR.

## Known Issues Active

1. **IZDO3D1 OCR** — acceptat
2. **DD false pozitive** (CM 200+, BR O3 52) — artefacte OCR în denumire. Prag 0.85 prea relaxat pt CM.
3. **CM O2 LIPSA=84** — neinvestigat
4. **SSR O2/O3 DEVIZ_MM=300+** — neinvestigat
5. **SSR O3 EXTRA=318** — neinvestigat

## Ce urmează

Refactorizare. Citește ARCHITECTURE.md.

## Comenzi utile

```bash
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  .venv/bin/python3 multi_client_run.py --client "$c"
done

.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```
