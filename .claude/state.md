# Session State — 2026-05-21

## Ce s-a făcut

### Fix 1: IZF12XC false ARTICOL_EXTRA
- `shared/pattern_library.json` — curățat entri invalide din `component_indicators`
- `shared/pattern_detector.py` — validare format indicator în `_calculate_pattern_confidence`
- IZF12XC acum corect matched în BLC1

### Fix 2: Reference partial key fallback (commit c7e6bd2)
- `shared/f3_page_classifier.py` — adăugat `_resolve_partial_keys_fallback()`
- `local_run.py` — apel fallback când ref_deviz_groups sunt tot `__partial__` (cazul Blocuri Racari)
- Referință: articole 58 → 530 (+472 articole recuperate)
- Root cause: eDevize format fără prefix numeric în Obiectul/Categoria

### Fix 3: False ARTICOL_LIPSA → DEVIZ_MISMATCH (commit 093a3a7)
- `AgentComparator_local.py` liniile 825-845
- Înainte de LIPSA, verifică dacă codul există oriunde în ofertă (`_all_offer_codes`)
- Dacă da → DEVIZ_MISMATCH ("Cod gasit in alt deviz din oferta")
- Impact: Dragomirești 163→6 LIPSA, Blocuri Racari 58→49 LIPSA

### Baseline run complet (commit chore outputs)
- Toate 4 clienți rulați, output-uri + checkpoints hash `91f7fbe58dd8` commituite

## Rezultate baseline (de folosit ca referință)

| Client | Ofertă | matched | LIPSA | DEVIZ_MM | EXTRA | total |
|--------|--------|---------|-------|----------|-------|-------|
| Blocuri Racari | O1 | 308 | 47 | 20 | 0 | 69 |
| Blocuri Racari | O2 | 551 | 2 | 28 | 0 | 32 |
| Blocuri Racari | O3 | 370 | 25 | 19 | 4 | 56 |
| Blocuri Racari | O4 | 311 | 49 | 9 | 1 | 60 |
| Camin Maneciu | O1 | 1056 | 1 | 2 | 36 | 65 |
| Camin Maneciu | O2 | 1066 | 84 | 5 | 41 | 177 |
| Scoala Dragomiresti | O1 | 651 | 6 | 624 | 0 | 633 |
| Scoala Dragomiresti | O2 | 691 | 6 | 602 | 1 | 609 |
| Scoala Sportiva Racari | O1 | 2153 | 2 | 11 | 122 | 181 |
| Scoala Sportiva Racari | O2 | 1148 | 4 | 328 | 55 | 411 |
| Scoala Sportiva Racari | O3 | 2244 | 6 | 325 | 315 | 648 |

## Probleme cunoscute / ce urmează

### 1. Scoala Dragomiresti — DEVIZ_MISMATCH=600+
**Root cause:** Referința folosește coduri text (ex. "4.1-01 STRUCTURA"), oferta folosește coduri eDevize numerice. `deviz_matcher` (`match_devize_by_denomination`) nu reușește să mapeze complet din cauza diferențelor de nomenclatură.
**Direcție fix:** Îmbunătățire `deviz_matcher` — matching mai agresiv pe cod articol (dacă cod există în ref deviz X, remapează oferta deviz Y → X chiar și fără match de denumire).

### 2. Camin Maneciu O2 — LIPSA=84
**Status:** Neinvestigat în sesiunea curentă. Probabil mix de $codes (material sub-resources) + deviz mismatch.
**Acțiune:** Analizează breakdown LIPSA pe deviz. Filtrează $codes (sunt așteptate întotdeauna).

### 3. Scoala Sportiva Racari O3 — EXTRA=315
**Status:** Neinvestigat. Oferta are 315 articole extra față de referință.
**Acțiune:** Verifică dacă sunt articole legitim extra sau deviz mismatch nerezolvat.

### 4. Blocuri Racari O1/O4 — LIPSA=47/49
**Cunoscut:** ~39/47 sunt $codes (resurse materiale sub-articole). Nu sunt erori de extragere.
**Genuine LIPSA:** ~8-10 articole reale. Investigat parțial — sunt în ofertă dar în deviz diferit (BLC6 vs 003-001 naming discrepancy).

## Variabile tehnice relevante

```
Checkpoint hash activ: 91f7fbe58dd8  (md5 din sursa f3_page_classifier.py)
Branch: main
Ultima tag: 8.0 (multi-client pipeline)
Clienți: Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari
Input dir: input_AO/<ClientName>/
Output dir: output_AO/<ClientName>/
Checkpoint dir: output_AO/<ClientName>/checkpoints/
```

## Cum să rulezi

```bash
# Un client
python3 multi_client_run.py --client "Blocuri Racari"

# Toți clienții
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  python3 multi_client_run.py --client "$c"
done
```

## Fișiere cheie modificate în această sesiune

- `AgentComparator_local.py:825-845` — LIPSA→DEVIZ_MISMATCH logic
- `shared/f3_page_classifier.py` — `_resolve_partial_keys_fallback()`
- `local_run.py` — apel fallback + filtrare valid_ref_groups
- `shared/pattern_library.json` — curățat component_indicators invalide
