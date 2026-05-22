# Session State — 2026-05-22 (final cu sistem abrevieri)

## Sistem Hybrid Abrevieri (ultima livrare sesiune)

### Fișiere noi
- `shared/abbreviations.py` — dict static `ABREVIERI_F3` + funcții expand/load/save learned
- `shared/abbreviation_learner.py` — LLM validation batch + auto-save `learned_abbreviations.json`

### Integrare în `shared/comparator.py`
- `_clean_den()` apelează `expand_abbreviations()` → pt→pentru, supr.→suprafata, termoizol.→termoizolatii
- Perechi confirmate de LLM ocolesc generarea DESCRIERE_DIFERITA
- Perechi borderline (Jaccard 0.25-0.50) marcate cu `borderline_llm=True`

### Rezultate SD post-abrevieri
SD DD: 14→**6/7** (toate borderline → candidați LLM). 4/6 articole operatori detectate corect în O1.

### Rulare learner (necesită API key sk-...)
```bash
.venv/bin/python3 shared/abbreviation_learner.py --client "Scoala Dragomiresti"
.venv/bin/python3 shared/abbreviation_learner.py --show  # preview fara LLM
```

## Baseline FINAL (după sistem abrevieri, 2026-05-22)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD | Note |
|--------|---|---------|-------|-------|----------|----|------|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 | |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 | |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 | |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 | |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 56 | |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 117 | |
| **Scoala Dragomiresti** | **1** | **910** | **2** | **0** | **1** | **6** | 6 borderline→LLM |
| **Scoala Dragomiresti** | **2** | **910** | **2** | **1** | **1** | **7** | 7 borderline→LLM |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 | |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 | |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 | |

## Verificare vs Raport Operatori SD

### O1 (MANELLI) — detectate de pipeline:
| Articol | Tip pipeline | Tip operator | Status |
|---------|-------------|--------------|--------|
| $6719496 (Teu polipropilena 40mm) | DIFERENTA_CAMP cant | CANTITATE GREȘITA | ✅ |
| $7319034 (Doza patrata) | DIFERENTA_CAMP cant | CANTITATE GREȘITA | ✅ |
| FG02A01 (Termostat) | DIFERENTA_CAMP cant | DESCRIERE (camera≠ventil) | ✅ cant |
| $7801794 (Filtru magnetita) | ARTICOL_LIPSA 2.6 | LIPSA 2.6+3.4 | ✅ (3.4 matched prin Layer 2.6) |
| DC05A% (Ancore Ø vs 0) | Nu detectat | DESCRIERE | ❌ (OCR minor, Jaccard ≈0.95) |
| RSPXE05A (Rezervor incendiu) | DIFERENTA_CAMP | CANTITATE GREȘITA | ✅ |
| AcE1161B1* (Camin Ø lipseste) | Nu detectat | DESCRIERE | ❌ (OCR minor) |

### O2 (TODERICA) — detectate:
$6719496, $7319034, $6704686, FG02A01, $7801794, $8527072 ✅

## Known Issues Active
1. IZDO3D1 OCR — acceptat
2. DD false pozitive reziduale (Ø vs 0 OCR) — sub pragul Jaccard (sim ≈ 0.95)
3. CM O2 LIPSA=84 — neinvestigat
4. SSR DEVIZ_MM/EXTRA — neinvestigat

## Ce urmează
Refactorizare. Citește ARCHITECTURE.md.
