# Session State — 2026-05-22 (actualizat)

## Fix sesiunea curentă: Parser Scatter Format

**Bug:** `_preprocess_scattered_format` în `shared/f3_regex_parser.py:535`
**Root cause:** In ramura F3-order, scana ahead pentru UM. Gasea `'Art. asimilat'` drept UM
(deoarece `'ART'` e in `UM_KNOWN` si verifica `_f3_um_tokens[0].rstrip('.') in UM_KNOWN`).
Lua NR_CRT-ul articolului urmator (`'7'`) drept QTY.
Crea linie merged `"6 EA02A1 - 82 M 170,00000 TUB IZOLANT..."` fara UM/QTY reale.
Articolele afectate: EA02A1, RPCT49C1, H1B02A3, RPCE34A1 (BR O3).

**Fix aplicat:** `len(_f3_um_tokens) == 1` — UM single-token only.
**Impact:** BR O3: matched 395→414 (+19), LIPSA 25→21 (-4).

## Baseline REAL (post-fix, fresh checkpoints)

| Client | Ofertă | matched | LIPSA | EXTRA | DEVIZ_MM |
|--------|--------|---------|-------|-------|----------|
| Blocuri Racari | O1 | **308** | 47 | 0 | 20 |
| Blocuri Racari | O2 | 551 | 2 | 0 | 28 |
| Blocuri Racari | O3 | **414** | 21 | 5 | - |
| Blocuri Racari | O4 | 316 | 49 | 1 | 9 |
| Camin Maneciu | O1 | 1056 | 1 | 36 | 2 |
| Camin Maneciu | O2 | 1066 | 84 | 41 | 5 |
| Scoala Dragomiresti | O1 | 651 | 6 | 0 | 624 |
| Scoala Dragomiresti | O2 | 691 | 6 | 1 | 602 |
| Scoala Sportiva Racari | O1 | 2152 | 2 | 122 | 11 |
| Scoala Sportiva Racari | O2 | 1142 | 4 | 56 | 328 |
| Scoala Sportiva Racari | O3 | 2260 | 6 | 315 | 325 |

**Nota:** BR O1=308 e baseline real. State.md anterior zicea 314 — era din checkpoints vechi.

## DEVIZ_MISMATCH — Explicat

Articol gasit in oferta cu acelasi cod, dar in deviz diferit fata de referinta.
Nu e LIPSA reala. Ofertantul a structurat devizele diferit.
Fix propus: deviz_matcher mai agresiv pe baza codului articolului.

## BR LIPSA Breakdown (post-fix)

**O1 (47):** 46 $-cod + 1 IZDO3D1 OCR
**O2 (2):** 1 RPCE21A1 genuina + 1 IZDO3D1
**O3 (21):** 16 $-cod + 4 genuine absente + 1 IZDO3D1
**O4 (49):** 47 $-cod + 1 MDTC5506025 genuina + 1 IZDO3D1

## Commits sesiune curentă (total fata de origin/main)

```
38e0b6f fix(parser): treat NR+UM line (e.g. '82 M') as UM in READING state
6fdff85 docs: document IZDO3D1 known issue and Layer 2.5 fix in state.md
70e67b9 fix(matching): Layer 2.5 uses all offer instances per key in N:M
7d6b5ec feat(diagnostics): CLI entry point run_diagnostics.py
+ alte diagnostics commits
+ FIX CURENT: scatter format is_f3_um single-token (necommitat inca)
```

**11+ commits ahead origin/main** (SSH push blocat)

## Known Issues Active

1. IZDO3D1 OCR — acceptat
2. BR O3 EXTRA=5 — de investigat
3. SD DEVIZ_MM=600+ — fix propus: deviz_matcher agresiv
4. CM O2 LIPSA=84 — neinvestigat
5. SSR O3 EXTRA=315 — neinvestigat
6. SSR O2/O3 DEVIZ_MM=328/325 — neinvestigat

## Ce urmeaza: Refactorizare

Utilizatorul vrea refactorizare. Baseline arhitectural documentat in ARCHITECTURE.md.
Citeste ARCHITECTURE.md inainte de orice refactorizare.

## Cum sa rulezi

```bash
# Client specific (fresh)
find "output_AO/<Client>/checkpoints" -name "*.json" -delete
.venv/bin/python3 multi_client_run.py --client "<Client>"

# Toti clientii
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  .venv/bin/python3 multi_client_run.py --client "$c"
done

# Diagnostics
.venv/bin/python3 run_diagnostics.py --client "Blocuri Racari"

# Teste
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py

# Metrici rapide
.venv/bin/python3 -c "
import json; from pathlib import Path; from collections import Counter
for client in ['Blocuri Racari', 'Camin Maneciu', 'Scoala Dragomiresti', 'Scoala Sportiva Racari']:
    for i in range(1,5):
        f = Path(f'output_AO/{client}/comparatie_oferta_{i}.json')
        if not f.exists(): continue
        comp = json.loads(f.read_text())
        tips = Counter(n['tip'] for n in comp['neconformitati'])
        print(f'{client} O{i}: matched={comp[\"matches\"]} LIPSA={tips.get(\"ARTICOL_LIPSA\",0)} EXTRA={tips.get(\"ARTICOL_EXTRA\",0)} DEVIZ_MM={tips.get(\"DEVIZ_MISMATCH\",0)}')
"
```
