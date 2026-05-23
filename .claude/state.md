# Session State — 2026-05-23 (FINAL)

## Baseline COMPLET (post toate fix-urile sesiunii 2026-05-23)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD |
|--------|---|---------|-------|-------|----------|----|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 56 |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 117 |
| **Scoala Dragomiresti** | **1** | **904** | **2** | **0** | **1** | **0** |
| **Scoala Dragomiresti** | **2** | **904** | **2** | **1** | **1** | **1** |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 |

**SD matched 910→904**: 6 articole false (D20MM/D25MM/D32MM/D40MM) eliminate din ref+oferte.
**SD O2 DD=1** = IA35B1 "vas inertial" vs "puffer" — genuina.

## Fix-uri sesiunea 2026-05-22/23 (cronologic)

1. **Parser scatter** — `is_f3_um` single-token. BR O3 +19.
2. **SD DEVIZ_MM 624→1** — `_CATEGORIA_OPT_RE` decimal + Strategy 0 numeric.
3. **Strategy 0 format-aware** — padded-int only, evita CM regresia.
4. **Client + ofertant în raport** — `client_config.name`, `_extract_ofertant_name`.
5. **COD_SIMILAR mereu** — Layer 2.1, 2.6.
6. **DESCRIERE_DIFERITA** — Jaccard 0.50 pe cuvinte dupa OCR cleanup.
7. **cant=0 filter** — articole capitol excluse din LIPSA/DEVIZ_MM.
8. **DD OCR cleanup** — l: notatie, garbage financiar, vo=+po, header tabel.
9. **Sistem hybrid abrevieri** — dict static ABREVIERI_F3 + LLM learner. SD DD 14→6.
10. **Normalizare diacritice** — ă→a, â→a, î→i, ș→s, ț→t. SD DD 6→0.
11. **Header tabel strip** — "nr capitol de lucrari u.m" → stripped.

## Fix-uri sesiunea 2026-05-23 (subcomponent mode)

12. **`--subcomponents {full,fields,summary}`** — CLI param in `multi_client_run.py`.
    - `full` (default): tot vizibil, filename normal `Raport_Oferta_N.docx`
    - `fields`: suprima DIFERENTA_CAMP + UM_DIFERIT pt sub-componente, filename `_fields`
    - `summary`: suprima tot pt sub-componente matched, filename `_summary`
    - Filtru in `_generate_word_hierarchical` — JSON neatins
    - Filtru pe: `is_component=True` SAU `cod.startswith('$')`

13. **Fix D20MM/D25MM extrase gresit** — `shared/f3_extractor.py`
    - Root cause: OCR wrapeaza "SA04A01> - Teava PN16, D20mm" pe 2 linii
    - "D20mm" pe linie separata → parser crea articol D20MM cu cant din linia urmatoare
    - Fix: filtru `^D\d+MM$` cu denumire goala, INAINTE de `_apply_parent_inheritance`
    - Rezultat: `display_parent_cod` pt `$`-coduri = SA04A01 (corect), nu D20MM
    - 6 articole false eliminate per rulare

## Sistem Abrevieri — Rulare LLM Learner

```bash
.venv/bin/python3 shared/abbreviation_learner.py --show          # preview
.venv/bin/python3 shared/abbreviation_learner.py --client "..."  # validare LLM
```

## Comenzi utile

```bash
# Mod summary (fara diferente sub-componente)
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" --subcomponents summary

# Mod fields (fara diferente cantitate/UM sub-componente)
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" --subcomponents fields

# Mod complet (default)
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti"
```

## Known Issues
1. IZDO3D1 OCR — acceptat
2. CM O2 LIPSA=84 — neinvestigat
3. SSR DEVIZ_MM/EXTRA — neinvestigat
4. DD CM reziduale (56/117) — candidati LLM learner
5. BR O3 DD=46 — unele borderline

## Ce urmează
Refactorizare sau investigare SSR/CM.
