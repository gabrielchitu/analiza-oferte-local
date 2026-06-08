# Pipeline QA — Loop autonom complet

Orchestreaza toate verificarile si fix-urile de calitate pentru un client: pipeline V1 + V2, autoverify, gaps, EXTRA, LIPSA.
Ruleaza ciclic pana la convergenta (niciun fix nou posibil) sau maxim 3 iteratii.

**Nu intreba nimic intre iteratii. Nu te opri pana la convergenta sau max iteratii.**

## Input

Argumentul: numele clientului (ex: `CAV Maneciu`). Daca lipseste, intreaba o singura data.

---

## Algoritmul principal

### FAZA 0 — Setup

Initializeaza contoarele:
```
iter = 0
max_iter = 3
total_fixes_this_cycle = 0
```

Afiseaza:
```
=== PIPELINE QA — <client> ===
Pornire ciclu de convergenta (max 3 iteratii)
```

---

### FAZA 1 — Ruleaza pipeline V1

```bash
rtk proxy python3 multi_client_run.py --client "<client>" 2>&1 | rtk log
```

Verifica ca nu exista erori fatale in output. Daca pipeline esueaza complet → stop, raporteaza.

Noteaza din output:
- Nr grupuri matchate / ref-only / oferta-only
- Nr neconformitati total

---

### FAZA 2 — Ruleaza pipeline V2

```bash
python3 -c "
from shared.client_config import ClientConfig
from shared.v2_orchestrator import V2EndToEndOrchestrator
cfg = ClientConfig.from_name('<client>')
orch = V2EndToEndOrchestrator()
import glob, re
offers = sorted([int(re.search(r'_(\d+)\.json', f).group(1))
    for f in glob.glob(f'input_AO/<client>/di_oferta_*.json')])
for n in offers:
    result = orch.run(cfg, n)
    print(f'V2 oferta_{n}: {result}')
" 2>&1 | rtk log
```

Sau mai simplu daca exista CLI:
```bash
python3 gen_comparatie_lista.py --client "<client>" 2>&1 | rtk log
```

---

### FAZA 3 — Autoverify structural

```bash
python3 verify_agent.py --client "<client>" --verify-only 2>&1 | rtk log
```

Parseaza output-ul. Clasifica fiecare finding:
- `CRITICAL` / `HIGH` cu `SILENT_VIOLATION` → **blocant** — investigheaza si raporteaza, nu continua automat
- `HIGH` cu `ARTICOL_EXTRA` / `ARTICOL_LIPSA` → noteaza count, va fi tratat in Faza 5-6
- `MEDIUM` / `LOW` → noteaza, nu blocheaza

Daca exista `SILENT_VIOLATION` (ref_main_count != off_main_count in grup matched) → **STOP**, raporteaza ca blocant si cere interventie manuala.

---

### FAZA 4 — Verificare gaps de nr_crt

Ruleaza `verify_gaps.py` si clasifica:

```bash
python3 verify_gaps.py --client "<client>" 2>&1
```

**Clasifica fiecare gap:**
- `GĂSIT în raw DI (bug extractor)` → **fixabil** — du-te la Pas 4a
- `GĂSIT pe alte pagini (deviz greșit?)` → skip (matching issue, nu parser)
- `NU există în raw DI` → skip (salt de numerotare normal)

#### Pas 4a — Fixeaza gap-urile extractorului (repetat per gap)

Pentru fiecare gap fixabil:

1. **Identifica contextul raw** din `input_AO/<client>/di_oferta_N.json` (pagina si liniile indicate de verify_gaps):
```python
import json
data = json.load(open('input_AO/<client>/di_oferta_N.json', encoding='utf-8'))
page = data['pages'][PAGE_IDX]  # 0-indexed
lines = [ln['content'] for ln in page['lines']]
context = lines[START:END]  # ±10 linii in jurul gap-ului
for i, l in enumerate(context):
    print(f"[{START+i}] {repr(l)}")
```

2. **Testeaza extractia curenta:**
```python
from shared.f3_regex_parser import extract_articles_regex, SKIP_RE
for l in context:
    print(f"SKIP={bool(SKIP_RE.search(l)):5} | {repr(l)}")
arts = extract_articles_regex(context, deviz_cod='TEST', deviz_den='TEST')
print([(a['nr_ordine'], a.get('cod'), a.get('denumire','')[:40]) for a in arts])
```

3. **Identifica root cause** (pattern frecvente):
   - `SKIP_RE` filtreaza linia corecta
   - UM necunoscut → articolul nu se finalizeaza
   - Format split (NR pe o linie, COD pe alta) nerecunoscut
   - Stare machine blocata (articol anterior neincheiat)

4. **Aplica fix minimal** in `shared/f3_regex_parser.py`

5. **Verifica fix izolat:**
```python
arts = extract_articles_regex(context, deviz_cod='TEST', deviz_den='TEST')
assert any(str(a['nr_ordine']) == str(GAP_NR) for a in arts), "Inca lipseste!"
```

6. Incrementeaza `total_fixes_this_cycle += 1`

7. **Commit imediat:**
```bash
git add shared/f3_regex_parser.py
git commit -m "fix(parser): <root cause scurt>"
```

8. Treci la urmatorul gap fixabil.

Daca gap-ul NU poate fi fixat dupa investigare → noteaza ca `SKIP (format necunoscut)` si continua.

---

### FAZA 5 — Autoverify EXTRA

Citeste `output_AO/<client>/holistic_oferta_N.json` pentru toate ofertele.
Extrage NC-uri cu `tip == "ARTICOL_EXTRA"`.

Pentru fiecare `oferta_cod`:

1. **Cauta in `di_referinta.json`:**
```python
import json
data = json.load(open('input_AO/<client>/di_referinta.json', encoding='utf-8'))
cod_bare = oferta_cod.lstrip('$')
found = any(cod_bare in ln['content']
    for page in data['pages']
    for ln in page.get('lines', []))
```

2. Daca `found=True` → **bug extractie referinta** → du-te la Pas 5a
3. Daca `found=False` → articol genuinely absent din referinta → noteaza si continua

#### Pas 5a — Fix extractie referinta pentru EXTRA

1. Gaseste contextul in di_referinta (pagina + linii)
2. Testeaza `extract_articles_regex` pe context
3. Identifica root cause (SKIP_RE, UM necunoscut, format split)
4. Aplica fix minimal in `shared/f3_regex_parser.py`
5. Verifica: `extract_articles_regex` produce articolul
6. Incrementeaza `total_fixes_this_cycle += 1`
7. Commit:
```bash
git add shared/f3_regex_parser.py
git commit -m "fix(parser): <root cause>"
```

**Stop condition EXTRA:** Dupa 5 iteratii fara progres (acelasi set EXTRA ramane) → trece la Faza 6.

---

### FAZA 6 — Autoverify LIPSA

Citeste `output_AO/<client>/holistic_oferta_N.json` pentru toate ofertele.
Extrage NC-uri cu `tip == "ARTICOL_LIPSA"`.
Prioritizeaza oferta cu cele mai multe LIPSA.

Pentru fiecare `ref_cod`:

1. **Cauta in `di_oferta_N.json`:**
```python
import json
data = json.load(open('input_AO/<client>/di_oferta_N.json', encoding='utf-8'))
cod_bare = ref_cod.lstrip('$')
found_pages = [pi+1 for pi, page in enumerate(data['pages'])
    for ln in page.get('lines', [])
    if cod_bare in ln['content']]
```

2. Daca `found_pages` nu e gol → **bug extractie oferta** → du-te la Pas 6a
3. Daca gol → articol genuinely absent din oferta → noteaza si continua

**Verifica si OCR mismatch:** daca codul din ref apare cu diferenta de 1 caracter (I↔1, O↔0) in oferta → nu e extractie bug, e COD_SIMILAR miss → adauga in `ocr_patterns_knowledge.json`, nu modifica parser.

#### Pas 6a — Fix extractie oferta pentru LIPSA

1. Gaseste contextul in di_oferta (pagina + linii)
2. Testeaza `extract_articles_regex` pe context
3. Identifica root cause
4. Aplica fix minimal
5. Verifica fix
6. Incrementeaza `total_fixes_this_cycle += 1`
7. Commit

**Stop condition LIPSA:** Dupa 5 iteratii fara progres → trece la Faza 7.

---

### FAZA 7 — Teste de regresie

```bash
python3 -m pytest tests/ -q --tb=short 2>&1 | tail -10
```

**Baseline asteptat:** 214/230 pass (16 pre-existing failures cunoscute).

Daca apar **noi** erori fata de baseline → **STOP**, investigheaza inainte de a continua.
Daca baseline intact → continua.

---

### FAZA 8 — Decizie convergenta

```
iter += 1
```

**Daca `total_fixes_this_cycle > 0` SI `iter < max_iter`:**
- Reseteaza `total_fixes_this_cycle = 0`
- Afiseaza: `[ITER {iter}] {N} fix-uri aplicate — re-rulez pipeline pentru convergenta`
- Du-te la FAZA 1 (re-pipeline + re-verificare)

**Daca `total_fixes_this_cycle == 0` SAU `iter >= max_iter`:**
- Du-te la FAZA 9 (raport final)

---

### FAZA 9 — Genereaza rapoarte finale

```bash
python3 gen_comparatie_lista.py --client "<client>"
python3 gen_lista_oferta.py --client "<client>"
```

---

### FAZA 10 — Raport final

```
=== RAPORT PIPELINE QA — <client> ===
Iteratii: {iter} / {max_iter}

Fixes aplicate:
  Gaps parser:     N
  EXTRA rezolvate: M (K genuine absente din referinta)
  LIPSA rezolvate: P (Q genuine absente din oferta)
  OCR mismatch:    R (adaugate in ocr_patterns_knowledge.json)

Stare finala:
  CRITICAL/HIGH structural: 0 (sau lista)
  MEDIUM findings: X (HIGH_EXTRA/LIPSA genuine)
  LOW findings: Y

Fisiere generate:
  Raport_Oferta_N.docx (N oferte)
  Comparatie_Lista_Oferta_N.docx
  Lista_Oferta_N.docx
  Lista_Referinta.docx

Commit-uri noi: {lista commit hash-uri}
```

---

## Note critice

- **Ordinea fazelor e intentionata**: gaps → EXTRA → LIPSA → re-pipeline. Nu sari faze.
- **SILENT_VIOLATION** blocheaza tot: invariantul `ref_main_count == off_main_count` trebuie sa fie 0 violari. Daca apare dupa un fix → revert fix-ul, investigheaza.
- **Nu modifica niciodata** `verify_gaps.py`, `verify_agent.py` sau `shared/pipeline_verifier.py` — sunt tool-uri de diagnostic.
- **SKIP_RE foloseste `re.search()`** — pattern-urile fara ancore (`^`, `$`) matchuiesc oriunde in linie.
- **Dupa orice fix in `f3_regex_parser.py`**: re-run pipeline complet, nu doar extractia izolata.
- **Baseline teste**: 214/230 (16 pre-existing failures: `test_compound_deviz_extraction.py` si `test_subcomponent_matching.py` — safe to ignore).
- **`pages` in DI JSON**: 0-indexed in lista, dar `page_number` e 1-indexed.
- **Codul `$XXX`**: `$` e prefix intern; cauta fara `$` in raw DI.
- **RTK**: foloseste `rtk proxy python3 ...` pentru output comprimat si `rtk git` pentru git.
