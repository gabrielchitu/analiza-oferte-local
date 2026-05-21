# Session State — 2026-05-22

## Ce s-a făcut în sesiunea 2026-05-21/22

### Fix 1: Layer 2.5 N:M cod similar (commit 70e67b9)
- `AgentComparator_local.py:629` — `oferta_map[ok]` → `oferta_by_key[ok]`
- Layer 2.5 vedea 1 instanță per cheie ofertă; acum vede toate instanțele din N:M group
- Impact: +6 matched BR O1 (308→314), +25 BR O3 (370→395)

### Fix 2: Parser `{nr} {UM}` în READING state (commit 38e0b6f)
- `shared/f3_regex_parser.py` — guard în NR_ALPHA_INLINE_RE check
- Dacă "codul" din `{nr} {cod}` e UM valid + articol curent fără UM → tratează ca NR+UM
- Rezolvă formatul `82 M` din oferta 3 Blocuri Racari (izolat); context cumulativ nerezo;vat

### Feature: Diagnostics Pipeline (commits 2eda4ee – 7d6b5ec)
- `run_diagnostics.py` + `shared/diagnostics_builder.py` + `shared/diagnostics_word.py`
- Phase 0 (calitate ref) + Phase 1 (EXTRA) + Phase 2 (LIPSA)
- 17 teste; toate pass
- Output: `output_AO/diagnostics.json` + `output_AO/diagnostics.docx`

## Rezultate baseline (actualizat)

| Client | Ofertă | matched | LIPSA | EXTRA | DEVIZ_MM |
|--------|--------|---------|-------|-------|----------|
| Blocuri Racari | O1 | 314 | 47 | 0 | 20 |
| Blocuri Racari | O2 | 551 | 2 | 0 | 28 |
| Blocuri Racari | O3 | 395 | 25 | 4 | 19 |
| Blocuri Racari | O4 | 316 | 49 | 1 | 9 |
| Camin Maneciu | O1 | 1056 | 1 | 36 | 2 |
| Camin Maneciu | O2 | 1066 | 84 | 41 | 5 |
| Scoala Dragomiresti | O1 | 651 | 6 | 0 | 624 |
| Scoala Dragomiresti | O2 | 691 | 6 | 1 | 602 |
| Scoala Sportiva Racari | O1 | 2153 | 2 | 122 | 11 |
| Scoala Sportiva Racari | O2 | 1148 | 4 | 55 | 328 |
| Scoala Sportiva Racari | O3 | 2244 | 6 | 315 | 325 |

## Probleme cunoscute / ce urmează

### 1. Scoala Dragomiresti — DEVIZ_MISMATCH=600+
**Root cause:** Referința folosește coduri text (ex. "4.1-01 STRUCTURA"), oferta folosește coduri eDevize numerice. `deviz_matcher` (`match_devize_by_denomination`) nu reușește să mapeze complet din cauza diferențelor de nomenclatură.
**Direcție fix:** Îmbunătățire `deviz_matcher` — matching mai agresiv pe cod articol (dacă cod există în ref deviz X, remapează oferta deviz Y → X chiar și fără match de denumire).

### 2. Camin Maneciu O2 — LIPSA=84
**Status:** Neinvestigat. Probabil mix de $codes (material sub-resources) + deviz mismatch.
**Acțiune:** Analizează breakdown LIPSA pe deviz. Filtrează $codes (sunt așteptate întotdeauna).

### 3. Scoala Sportiva Racari O3 — EXTRA=315
**Status:** Neinvestigat. Oferta are 315 articole extra față de referință. SSR ref are 154 componente orfane (Phase 0 = red).
**Acțiune:** Verifică dacă sunt articole legitim extra sau deviz mismatch nerezolvat.

### 4. Blocuri Racari — IZDO3D1 OCR (known issue, acceptat)
**Root cause:** Ref extrage `IZDO3D1` (litera O, OCR) + `IZD03D1` (real). Layer 1 consumă cheia IZD03D1 cu ref-ul real → IZDO3D1 rămâne LIPSA.
**Status:** Acceptat. Fix necesită normalizare O↔0 globală (risc) sau refactor Layer 2 să re-consume excesul din N:M.

### 5. Layer 2.5 fix (2026-05-22)
**Fix aplicat:** `oferta_by_key[ok]` în loc de `oferta_map[ok]`. +6 BR O1, +25 BR O3.

### 6. Parser `82 M` format (2026-05-22)
**Fix aplicat:** Guard NR_ALPHA_INLINE_RE în READING state.
**Problema reziduală:** BR O3 articole EA02A1/RPCT49C1/H1B02A3/RPCE34A1 tot cant=0 (state cumulativ din paginile 1-5). Root cause neidentificat complet.

## Variabile tehnice relevante

```
Branch: main
Tag: 8.0 (multi-client pipeline)
Commits ahead origin/main: 11 (push blocat SSH)
Clienți: Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari
Input dir: input_AO/<ClientName>/
Output dir: output_AO/<ClientName>/
Checkpoint dir: output_AO/<ClientName>/checkpoints/
```

## Cum să rulezi

```bash
# Un client fresh
rm -f "output_AO/<Client>/checkpoints/"*.json
python3 multi_client_run.py --client "<Client>"

# Toți clienții
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  python3 multi_client_run.py --client "$c"
done

# Diagnostics (nu re-rulează pipeline)
python3 run_diagnostics.py
python3 run_diagnostics.py --client "Blocuri Racari"

# Teste
.venv/bin/python -m pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py

# Push (SSH agent)
# ! git push origin main
```

## Fișiere cheie modificate în sesiunea curentă

- `AgentComparator_local.py:629` — Layer 2.5 N:M fix
- `shared/f3_regex_parser.py:1294-1301` — Parser 82M guard
- `run_diagnostics.py` — NOU
- `shared/diagnostics_builder.py` — NOU
- `shared/diagnostics_word.py` — NOU
- `tests/test_diagnostics.py` — NOU
- `.claude/state.md` — actualizat
- `docs/SESSION_HANDOFF.md` — actualizat
