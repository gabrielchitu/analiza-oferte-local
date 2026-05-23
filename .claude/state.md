# Session State — 2026-05-22/23 (FINAL)

## Baseline COMPLET (post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD |
|--------|---|---------|-------|-------|----------|----|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 56 |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 117 |
| Scoala Dragomiresti | 1 | 910 | 2 | 0 | 1 | 0 |
| Scoala Dragomiresti | 2 | 910 | 2 | 1 | 1 | 1 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 |

**SD O1 DD=0, O2 DD=1** (IA35B1: "vas inertial" vs "puffer" — genuina, confirmata de operatori).

## Fix-uri sesiunea 2026-05-22/23 (cronologic)

1. **Parser scatter** — `is_f3_um` single-token. BR O3 +19.
2. **SD DEVIZ_MM 624→1** — `_CATEGORIA_OPT_RE` decimal + Strategy 0 numeric.
3. **Strategy 0 format-aware** — padded-int only, evita CM regresia.
4. **Client + ofertant în raport** — `client_config.name`, `_extract_ofertant_name` rewrite (Executant: prioritar).
5. **COD_SIMILAR mereu** — Layer 2.1, 2.6.
6. **DESCRIERE_DIFERITA** — Jaccard 0.50 pe cuvinte dupa OCR cleanup.
7. **cant=0 filter** — articole capitol excluse din LIPSA/DEVIZ_MM.
8. **DD OCR cleanup** — l: notatie, garbage financiar, vo=+po, header tabel.
9. **Sistem hybrid abrevieri** — dict static ABREVIERI_F3 + LLM learner. SD DD 14→6.
10. **Normalizare diacritice** — ă→a, â→a, î→i, ș→s, ț→t. SD DD 6→0.
11. **Header tabel strip** — "nr capitol de lucrari u.m" → stripped.

## Analiza SD vs Raport Operatori

Articole detectate corect:
- `$6719496` (teu D40mm) CANTITATE GREȘITA ✅
- `$7319034`, `$6704686`, `FG02A01` CANTITATE GREȘITA ✅
- `$7801794` LIPSA ✅ / `$8527072` EXTRA ✅
- `IA35B1` "vas inertial vs puffer" DESCRIERE_DIFERITA ✅ (genuina)

33 DIFERENTA_CAMP = diferențe cantitative la sub-resurse SA04A01 (fitinguri polipropilena). Genuine, confirmate partial de operatori.

## Sistem Abrevieri — Rulare LLM Learner

```bash
.venv/bin/python3 shared/abbreviation_learner.py --show          # preview
.venv/bin/python3 shared/abbreviation_learner.py --client "..."  # validare LLM
```
Perechile confirmate → `output_AO/learned_abbreviations.json` → reload automat.

## Known Issues
1. IZDO3D1 OCR — acceptat
2. CM O2 LIPSA=84 — neinvestigat
3. SSR DEVIZ_MM/EXTRA — neinvestigat
4. DD CM reziduale (56/117) — unele borderline, candidati LLM learner
5. DIFERENTA_CAMP pentru sub-componente is_component=True — de discutat dacă se filtrează

## Ce urmează
Refactorizare. Citește ARCHITECTURE.md + ARCHITECTURE_SCHEMA.md.
