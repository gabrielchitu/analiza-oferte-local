# Session State — 2026-05-24 (FINAL)

## Baseline COMPLET (post toate fix-urile sesiunii 2026-05-23/24)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD |
|--------|---|---------|-------|-------|----------|----|
| Blocuri Racari | 1 | 308 | 1 | 0 | 20 | 0 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 |
| Blocuri Racari | 3 | 415 | 5 | 5 | - | - |
| Blocuri Racari | 4 | 316 | 2 | 1 | - | - |
| **Scoala Dragomiresti** | **1** | **904** | **1** | **0** | **1** | **0** |
| **Scoala Dragomiresti** | **2** | **904** | **1** | **1** | **1** | **1** |

**Note:** CM si SSR inca nu rulate cu noile fix-uri din refactor/v10.

## Sub-project A — F3 Detection Enhancement

12. **F3Knowledge** — `shared/f3_knowledge.py` + `shared/f3_markers_knowledge.json`
    - knowledge base globala markeri F3 start/end
    - self-learning: LLM pattern-uri noi salvate in JSON
    - cache key = md5(lines[:20]) — fix collision pt eDevize same-header pages

13. **`_apply_end_detection()`** — `shared/f3_page_classifier.py`
    - detectie sfarsit tabel F3 (TOTAL CHELT. DIRECTE etc.)
    - same-page restart cand incepe un nou tabel F3 pe aceeasi pagina
    - ruleaza in `extract_document()` DUPA checkpoint load (niciodata salvat in checkpoint)

14. **`source_pages`** — `shared/f3_extractor.py`
    - fiecare articol extras primeste `source_pages: list[int]` cu paginile fizice PDF

15. **`[PDF pag. X-Y]`** — `shared/report_word.py`
    - header deviz in Word report arata paginile sursa (ref + oferta)

## Sub-project B — 3-Layer Deviz Header

16. **`shared/deviz_header_extractor.py`** — nou
    - extrage OBIECTIVUL + Obiectul + Categoria din headerele F3
    - suporta inline ("Obiectivul: text") SI multi-line ("Obiectivul:\ntext urmatoare linie")
    - `DevizHeaderCache` — autoinvatare per run, cache key = md5(lines[:20])
    - `deviz_key` = md5[:16] din 3 layere normalizate
    - `is_valid=True` daca toate 3 layere extrase

17. **Integrare pipeline** — `local_run.py`
    - `deviz_key` + `deviz_header` pe fiecare articol

## Sub-project C — 3-Layer Deviz Matching

18. **`match_devize_by_3layer()`** — `shared/deviz_matcher.py`
    - mapeaza oferta_deviz_cod → ref_deviz_cod pe similitudine 3-layer
    - per-layer minimums: obj2 ≥ 0.85, cat ≥ 0.90 (evita BLOC A ≡ BLOC B)
    - same-code verification: BLC6 ref ≠ BLC6 oferta (continut diferit) → nu rezervat
    - ruleaza DUPA Strategy 0-3, pt devize nemapate

19. **Fix: $-coduri LIPSA false** — `AgentComparator_local.py`
    - Sub-resursele eDevize ($-coduri breviar) excluse din LIPSA
    - conditie: devizul are articole normative (non-$) in oferta
    - BR O1: LIPSA 47→1, SD: LIPSA 2→1

## Comenzi utile

```bash
# Pipeline
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log

# Test suite
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py

# Reset deviz header cache (daca corrupt)
echo '{}' > shared/deviz_header_knowledge.json
```

## Known Issues
1. IZDO3D1 OCR — acceptat
2. BR O1 DEVIZ_MM=20 — contractor consolidat BLC6+BLC7 ORGANIZARE SANTIER in BLC7
3. BR O2 DEVIZ_MM=28 — neinvestigat
4. CM O2 LIPSA=84 — neinvestigat
5. SSR DEVIZ_MM/EXTRA — neinvestigat

## Ce urmează
- Push refactor/v10 + tag v10.0 catre origin (SSH)
- Run CM/SSR cu noile fix-uri
- Investigare BR O2 DEVIZ_MM=28
