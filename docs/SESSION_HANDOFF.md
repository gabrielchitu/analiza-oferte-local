# Session Handoff — Analizator Oferte Construcții

> Citeste acest fisier la inceputul unei sesiuni noi.
> Da-l lui Claude ca prim mesaj: *"Citeste docs/SESSION_HANDOFF.md si reia de unde am ramas."*

---

## Ce este acest proiect

Pipeline Python care:
1. Primeste documente PDF de oferta pentru lucrari de constructii, procesate prin **Azure Document Intelligence** → JSON
2. Extrage articolele din formularele **F3** (Lista cu cantitati de lucrari)
3. Compara articolele din fiecare oferta cu o **referinta** (caiet de sarcini)
4. Genereaza rapoarte de neconformitate in format **DOCX**

**Client:** Autoritati publice care evalueaza oferte de constructii
**Domeniu:** Devize de constructii romanesti (ISDP, eDevize format)

---

## Starea la 2026-05-22 (branch: main, v8.0)

**Branch activ:** `main`
**Tag stabil:** `8.0` (multi-client pipeline)
**Repo local:** `/Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local`
**Commits ahead origin/main:** 11+ (SSH push blocat — necesita `! git push origin main`)

### Clienti disponibili

| Client | Oferte |
|--------|--------|
| Blocuri Racari | 4 |
| Camin Maneciu | 2 |
| Scoala Dragomiresti | 2 |
| Scoala Sportiva Racari | 3 |

### Metrici baseline (2026-05-22, post-fix)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | Note |
|--------|---|---------|-------|-------|----------|------|
| Blocuri Racari | 1 | 308 | 47 | 0 | 20 | curata (46 $-cod + 1 OCR) |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | curata |
| Blocuri Racari | 3 | 414 | 21 | 5 | - | curata (16$+4gen+1OCR) |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | curata (47$+1MDTC+1OCR) |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | EXTRA neinvestigat |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | LIPSA=84 neinvestigat |
| Scoala Dragomiresti | 1 | **910** | **2** | 0 | **2** | ✅ fix DEVIZ_MM 624→2 |
| Scoala Dragomiresti | 2 | **910** | **2** | 1 | **2** | ✅ fix DEVIZ_MM 602→2 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 11 | EXTRA neinvestigat |
| Scoala Sportiva Racari | 2 | 1142 | 4 | 56 | 328 | DEVIZ_MM neinvestigat |
| Scoala Sportiva Racari | 3 | 2260 | 6 | 315 | 325 | EXTRA=315 neinvestigat |

---

## Ce s-a livrat (sesiunile 2026-05-21/22)

### 1. Diagnostics Pipeline (nou)

```bash
python3 run_diagnostics.py                        # toti clientii
python3 run_diagnostics.py --client "Blocuri Racari"
python3 run_diagnostics.py --no-docx              # JSON only
```

Output: `output_AO/diagnostics.json` + `output_AO/diagnostics.docx`

Faze:
- **Phase 0:** Calitate referinta (fara_deviz, componente_orfane, incomplete)
- **Phase 1:** EXTRA analysis per deviz ($-coduri vs principale)
- **Phase 2:** LIPSA analysis (genuine vs DEVIZ_MISMATCH)

### 2. Fix Layer 2.5 (matching)

`AgentComparator_local.py:629`: `oferta_map[ok]` → `oferta_by_key[ok]`
Layer 2.5 OCR vedea 1 instanta per cheie oferta; acum vede toate instantele N:M.
Impact: +6 BR O1, +25 BR O3 (la momentul fix-ului; baseline s-a recalculat).

### 3. Fix Parser scatter format BR O3 (2026-05-22)

`shared/f3_regex_parser.py:535` — `is_f3_um` in `_preprocess_scattered_format`

**Root cause:** `'Art. asimilat'` detectat ca UM valid (ART in UM_KNOWN, primul token).
Lua NR_CRT urmator drept QTY. Articole extrase cu cant=0 → LIPSA false.

**Fix:** `len(_f3_um_tokens) == 1` — single-token UM only.
**Impact:** BR O3: matched 395→414 (+19), LIPSA 25→21 (-4).

### 4. Fix SD DEVIZ_MM 624→2 (2026-05-22) — două fix-uri

**Fix 4a:** `shared/f3_page_classifier.py:107` — `_CATEGORIA_OPT_RE`

`[0-9]{0,4}` → `[0-9]{0,4}(?:\.[0-9]{0,2})?`

"Stadiul fizic: 1.4 INSTALATII" → cat_num=`1.4` (nu `1`).
Toate stadiile unui obiect obtin coduri distincte: `1.0-1.1`, `1.0-1.2`, `1.0-1.3`, `1.0-1.4`.

**Fix 4b:** `shared/deviz_matcher.py` — Strategy 0 numeric structural (înainte de fuzzy text)

Extrage `(obj_int, cat_int)` din compus: `001-004` → `(1,4)`, `1.0-1.4` → `(1,4)`.
Fuzzy text eșua deoarece "INSTALATII SANITARE" identic în obiectele 1, 2, 3, 4.

**Impact:** SD O1: matched 651→910 (+259), DEVIZ_MM 624→2. SD O2: matched 692→910 (+218).

### 5. Skill f3-domain-rules creat

`.claude/skills/f3-domain-rules/SKILL.md` — referință regex, UM, deviz, matching layers.

---

## Known Issues Active

### 1. IZDO3D1 — OCR O/0 (BR toate ofertele)
**Status:** Acceptat.

### 2. BR O3 — EXTRA=5
**Status:** Neinvestigat.

### 3. Scoala Dragomiresti — DEVIZ_MM=2 (REZOLVAT)
~~DEVIZ_MM=600+~~ → 2 ramase (probabil genuine LIPSA).
**Status:** ✅ Fix livrat.

### 4. Camin Maneciu O2 — LIPSA=84
Probabil mix $-coduri + deviz mismatch.
**Status:** Neinvestigat.

### 5. Scoala Sportiva Racari O3 — EXTRA=315
SSR ref are 154 componente orfane (Phase 0 = red).
**Status:** Neinvestigat.

### 6. SSR O2/O3 — DEVIZ_MM=328/325
**Status:** Neinvestigat.

---

## Ce urmeaza: Refactorizare

Utilizatorul a cerut refactorizare. Baseline arhitectural documentat in `ARCHITECTURE.md`.
**Citeste ARCHITECTURE.md inainte de a propune orice refactorizare.**

---

## Arhitectura rapida

```
multi_client_run.py       ← Entry point (v8.0)
run_diagnostics.py        ← Diagnostics (nu re-ruleaza pipeline)
local_run.py              ← Orchestration + matching + report
│
├── shared/client_config.py          ← ClientConfig, detect_clients
├── shared/f3_page_classifier.py     ← Clasificare pagini (local + LLM)
├── shared/f3_extractor.py           ← Extragere articole + grupare
├── shared/f3_regex_parser.py        ← State machine + preprocess
│   ├── _preprocess_scattered_format ← Combina format scatter (FIX: single-token UM)
│   ├── _preprocess_compound_um      ← Combina NR+UM separate
│   └── _merge_wrapped_codes         ← Uneste coduri rupte
├── AgentComparator_local.py         ← match_global (Layer 1-3)
│   ├── Layer 1: N:M exact (deviz, cod)
│   ├── Layer 2: normalized cod (AUT6752 ↔ $6752)
│   ├── Layer 2.1: trailing digit (IC35D ↔ IC35D1)
│   ├── Layer 2.5: cod similar OCR ≥ 0.80 (FIX: N:M complet)
│   └── Layer 3: LLM fuzzy (disabled)
├── shared/deviz_matcher.py          ← Deviz mapping (fuzzy)
├── shared/report_builder.py         ← build_raport_ierarhic
├── shared/report_word.py            ← generate_word (tabel 11 col)
├── shared/diagnostics_builder.py    ← Phase 0/1/2 + JSON
└── shared/diagnostics_word.py       ← DOCX diagnostic
```

---

## Comenzi utile

```bash
# Pipeline client
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari"

# Toti clientii
for c in "Blocuri Racari" "Camin Maneciu" "Scoala Dragomiresti" "Scoala Sportiva Racari"; do
  .venv/bin/python3 multi_client_run.py --client "$c"
done

# Diagnostics
.venv/bin/python3 run_diagnostics.py

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

# Reset checkpoints
find "output_AO/<Client>/checkpoints" -name "*.json" -delete

# Push (necesita SSH agent activ)
# ! git push origin main
```

---

## Commits sesiune 2026-05-21/22

```
shared/f3_regex_parser.py:535 — is_f3_um single-token fix (NECOMMITAT)
38e0b6f fix(parser): treat NR+UM line (e.g. '82 M') as UM in READING state
6fdff85 docs: document IZDO3D1 known issue and Layer 2.5 fix in state.md
70e67b9 fix(matching): Layer 2.5 uses all offer instances per key in N:M
7d6b5ec feat(diagnostics): CLI entry point run_diagnostics.py
6e58813 fix(diagnostics): remove unused imports
aac05ac feat(diagnostics): DOCX generator
6046f07 fix(diagnostics): error handling in discover/load
2eda4ee feat(diagnostics): discover/load/JSON builder with tests
3b23c68 feat(diagnostics): Phase 0/1/2 analysis functions with tests
```

**11+ commits ahead origin/main.** Push necesita SSH agent:
```bash
# ! ssh-add && git push origin main
```

---

## Teste preexistente esuate (nu regresii)

- `tests/test_compound_deviz_extraction.py` — ImportError (functie stearsa)
- `tests/test_subcomponent_matching.py` — ImportError (functie redenumita)
- `tests/shared/test_f3_regex_parser_multiline.py` — 4 teste format vechi
- `tests/test_normalize_cod.py` — 1 test normalizare cod
