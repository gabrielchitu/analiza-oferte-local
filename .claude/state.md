# Session State — 2026-05-24 (v11.0)

## Baseline FINAL (post v11.0)

| Client | O | matched_arts | matched_groups | ref-only | oferta-only | Note |
|--------|---|-------------|----------------|----------|-------------|------|
| Blocuri Racari | 1 | 299 | 22 | 1 | 2 | |
| Blocuri Racari | 2 | 541 | 22 | 1 | 0 | |
| Blocuri Racari | 3 | 460 | 23 | 0 | 2 | |
| Blocuri Racari | 4 | 286 | 17 | 6 | 2 | |
| Camin Maneciu | 1 | 875 | 19 | 0 | 16 | |
| Camin Maneciu | 2 | 895 | 13 | 6 | 22 | |
| **Scoala Dragomiresti** | **1** | **904** | **22** | **0** | **0** | ✅ perfect |
| **Scoala Dragomiresti** | **2** | **904** | **22** | **0** | **0** | ✅ perfect |
| Scoala Sportiva Racari | 1 | 2168 | **0** | 13 | 84 | ❌ 0 holistic |
| Scoala Sportiva Racari | 2 | 1159 | **0** | 13 | 75 | ❌ 0 holistic |
| Scoala Sportiva Racari | 3 | 2280 | **0** | 13 | 32 | ❌ 0 holistic |

**SD matched=904** — baseline principal.
**SSR holistic=0** — header F3 SSR incompatibil cu 3-layer extractor → bug activ.

## Arhitectura v11.0

### deviz_key = hash(OBIECTIVUL + OBIECTUL + CATEGORIA)
- Identificator canonic per grup de articole
- Generat PER PAGINA F3 (nu per deviz_cod)
- BLC1 cu 6 blocuri → 6 deviz_key distincte (BLOC A, A2, A3, A4, B, C)
- Deduplicare articole pe (cod, deviz_key, cantitate) — nu pe (cod, deviz_cod)

### Flux extract_document()
```
1. load page_classes (checkpoint)
2. _apply_end_detection() [in-memory]
3. extract_articles_v3() [grupeaza pe deviz_key per-pagina, seteaza deviz_key+deviz_header]
4. fallback deviz_key din extract_deviz_headers() pt articole INCOMPLETE
5. match_devize_by_3layer() [Strategy 4, pt devize nemapate dupa Strategy 0-3]
6. compare_and_report() → match_global() + compare_by_groups() + generate_word()
```

### compare_by_groups()
- Grupeaza articole dupa deviz_key (nu deviz_cod)
- Same-code deviz: verifica similitudine 3-layer inainte de pairing
- match_devize_by_3layer: strip prefix numeric in _3layer_sim (robustete OCR)
- ref-only → ARTICOL_LIPSA, oferta-only → ARTICOL_EXTRA
- _lipsa_neconf/_extra_neconf: copiaza is_component, parent_cod, source_pages

### Raport Word holistic
- _generate_word_holistic(): sectiuni matched/ref-only/oferta-only/ungrouped
- Nr.crt: pag.ref/pag.of + (nr_ordine_ref/nr_ordine_of)
- display_parent_cod: afisat pt is_component=True SI $-coduri cu parinte
- $-coduri: NU mai mostenesc UM de la parinte

## Known Issues (activ in sesiunea urmatoare)

| # | Client | Issue | Status |
|---|--------|-------|--------|
| 1 | SSR | holistic=0 grupuri — header F3 SSR format incompatibil | **PRIORITAR** |
| 2 | BR O2 | DEVIZ_MISMATCH ridicat | Neinvestigat |
| 3 | CM O2 | 6 ref-only, 22 oferta-only | Neinvestigat |
| 4 | General | SSR: _extract_from_lines nu gaseste Obiectul/Categoria in paginile SSR | Cauza probabala issue 1 |

## Bug SSR (de investigat la urmatoarea sesiune)

SSR are 0 grupuri holistic matched. Cauza: `_extract_from_lines()` nu extrage
obj2/cat din headerele F3 ale SSR. Paginile SSR au format diferit — probabil
"Stadiul fizic: XXXX DENUMIRE" pe o singura linie (fara "Obiectivul:" si "Obiectul:" separate).

**Start de debugging:**
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
        if obj2 or cat:
            print(f'pag {pc[\"page_number\"]}: obj2={obj2} cat={cat}')
            break
        else:
            print(f'pag {pc[\"page_number\"]}: FAILED. lines[:5]={lines[:5]}')
            break
"
```

## Comenzi utile

```bash
# Pipeline
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | rtk log

# Holistic JSON
python3 -c "
import json; from pathlib import Path
h = json.loads(Path('output_AO/Scoala Dragomiresti/holistic_oferta_1.json').read_text())
s = h['sumar']
print(s)
"

# Push (necesita SSH)
# git push origin refactor/v10 && git push origin v11.0

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py
```
