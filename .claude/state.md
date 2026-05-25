# Session State — 2026-05-25 (post code cleanup: deviz_cod remapping removed)

## Baseline Holistic Results — CURRENT

| Client | O | matched_groups | ref-only | oferta-only | Note |
|--------|---|----------------|----------|-------------|------|
| Blocuri Racari | 1 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 2 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 3 | 35 | 0 | 3 | 3 oferta-only neinvestigate |
| Blocuri Racari | 4 | 32 | 3 | 12 | structura diferita, neinvestigat |
| **Scoala Dragomiresti** | **1** | **22** | **0** | **0** | ✅ perfect (baseline principal) |
| **Scoala Dragomiresti** | **2** | **22** | **0** | **0** | ✅ perfect |
| Camin Maneciu | 1 | — | — | — | neverificat dupa fix |
| Scoala Sportiva Racari | 1-3 | 0 | — | — | ❌ SSR header format incompatibil |

## Arhitectura Curenta

### deviz_key = hash(OBIECTIVUL + OBIECTUL + CATEGORIA)
- Identificator canonic unic per grup de articole
- Generat PER PAGINA F3 (nu per deviz_cod)
- BLC7 cu doua grupuri distincte ("3 ORGANIZARE SANTIER" + "4 ORGANIZARE SANTIER") → 2 deviz_key distincte
- `deviz_cod` string (ex: "BLC7") NU e unic — NICIODATA folosit ca lookup key sau dedup key

### Deduplicare articole (local_run.py)
```python
# CORECT: deviz_key (hash) ca dimensiune grup in dedup
key = (art.get("deviz_key") or art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
# GRESIT (bug rezolvat): art.get("deviz") = deviz_cod string → pierde al 2-lea grup cu acelasi cod
```

### Coloana 1 Raport ("Categoria de lucrari")
```python
# Afisare: ultimele 2 parti din deviz_denumire (Obiectul | Categoria)
# OBIECTIVUL e deja in heading-ul grupului, nu se duplica
parts = [p.strip() for p in deviz_den_full.split(" | ") if p.strip()]
deviz_display = " | ".join(parts[-2:]) if len(parts) >= 2 else deviz_den_full
```

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
- Grupeaza articole dupa deviz_key hash (nu deviz_cod)
- Same-code deviz: verifica similitudine 3-layer inainte de pairing
- match_devize_by_3layer: strip prefix numeric in _3layer_sim (robustete OCR)
- ref-only → ARTICOL_LIPSA, oferta-only → ARTICOL_EXTRA
- _lipsa_neconf/_extra_neconf: copiaza is_component, parent_cod, source_pages
- `group_key` parameter = deviz_key hash (nu deviz_cod string)

### Raport Word holistic
- _generate_word_holistic(): sectiuni matched/ref-only/oferta-only/ungrouped
- Nr.crt: pag.ref/pag.of + (nr_ordine_ref/nr_ordine_of)
- display_parent_cod: afisat pt is_component=True SI $-coduri cu parinte
- $-coduri: NU mai mostenesc UM de la parinte
- Col 1 "Categoria de lucrari": `Obiectul | Categoria` (ultimele 2 parti din deviz_denumire)

## Cleanup (2026-05-25)

Removed dead deviz_cod string remapping code:
- `reconcile_missing_devize()` block — no longer needed for holistic
- `match_devize_by_denomination/3layer` remapping — overridden by compare_by_groups anyway
- Phase 1 inside compare_and_report() — unused art["deviz"] remapping

**~66 lines deleted. Baseline verified unchanged: BR O1/O2=35/0/0, O3=35/0/3, O4=32/3/12**

Modules `shared/deviz_reconciler.py` and `shared/deviz_matcher.py` still exist but unreferenced (dead code, can clean later).

## Known Issues (activ in sesiunea urmatoare)

| # | Client | Issue | Status |
|---|--------|-------|--------|
| 1 | SSR | holistic=0 grupuri — header F3 SSR format incompatibil | **PRIORITAR** |
| 2 | BR O3 | 3 oferta-only | Neinvestigat |
| 3 | BR O4 | 3 ref-only, 12 oferta-only | Neinvestigat — structura diferita |
| 4 | CM | Groups mismatch ref/oferta | Neinvestigat |

## Bug SSR (de investigat)

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
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log

# Holistic JSON sumar
python3 -c "
import json; from pathlib import Path
h = json.loads(Path('output_AO/Blocuri Racari/holistic_oferta_1.json').read_text())
print(h['sumar'])
"

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py
```
