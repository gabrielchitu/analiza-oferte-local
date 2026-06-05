# Fix Gap-uri Extractor — Loop autonom

Ruleaza `verify_gaps.py`, analizeaza gap-urile de tip bug extractor, fixeaza parser-ul.

**Nu intreba nimic. Nu te opri intre iteratii. Fixeaza si continua pana la 0 gap-uri rezolvabile.**

## Input

Argumentul optional: numele clientului (ex: `CAV Maneciu`). Daca lipseste, intreaba o singura data.

## Algoritmul

### Pas 1 — Ruleaza verify_gaps

```bash
python3 verify_gaps.py --client "<client>"
```

Parseaza output-ul. Clasifica fiecare gap dupa tag-ul afisat:
- `GĂSIT în raw DI (bug extractor)` → **fixabil** — du-te la Pas 3
- `GĂSIT pe alte pagini (deviz greșit?)` → skip (problema matching, nu parser)
- `NU există în raw DI` → skip (salt de numerotare legitim sau articol absent)

Noteaza pentru fiecare gap fixabil: client, oferta N, grup (Obiectul | Categoria), nr gap, pagina raw DI, linia, contextul afisat.

### Pas 2 — Prioritizeaza

Proceseaza gap-urile fixabile in ordine: cele cu context mai clar primul.
Daca acelasi nr apare in mai multe oferte → probabil acelasi bug → fixeaza o data, verifica toate.

### Pas 3 — Identifica formatul raw

Din contextul afisat de `verify_gaps.py` (±4 linii), identifica pattern-ul:

**Pattern A — NR standalone / descriere fara cod / subcomponent:**
```
'3'
'Echipamente platforma carosabila'
'3.1'
'SZ2f01#'
```
→ articol principal fara cod propriu; are doar subcomponente cu cod.

**Pattern B — NR + COD pe aceeasi linie (inline) dar parser in starea gresita:**
```
'3 TSD06XA'
```
→ posibil stare machine stuck.

**Pattern C — NR pe linie, COD pe linia urmatoare (split OCR):**
```
'3'
'TSD06XA'
'Descriere...'
```
→ parser asteapta cod dupa NR dar il rateza.

**Pattern D — Alt format** → adauga in lista si analizeaza.

### Pas 4 — Testeaza extractia curenta

Extrage liniile brute din `input_AO/<client>/di_oferta_N.json` in jurul gap-ului (pagina si linia din Pas 1, ±10 linii).

```python
import json, logging
from shared.f3_regex_parser import extract_articles_regex, SKIP_RE

# Citeste di_oferta_N.json
data = json.load(open('input_AO/<client>/di_oferta_N.json', encoding='utf-8'))
page = data['pages'][PAGE_IDX]  # 0-indexed
lines = [ln['content'] for ln in page['lines']]
context_lines = lines[START:END]

# Verifica SKIP_RE pe fiecare linie
for i, l in enumerate(context_lines):
    m = SKIP_RE.search(l)
    print(f"[{i}] SKIP={bool(m)!s:5} | {l!r}")

# Ruleaza parser
logging.basicConfig(level=logging.DEBUG)
arts = extract_articles_regex(context_lines, deviz_cod='TEST', deviz_den='TEST')
print("Articole extrase:", [(a['nr_ordine'], a.get('cod'), a.get('denumire')) for a in arts])
```

Identifica unde se pierde articolul: SKIP_RE, stare _WAITING fara tranzitie, _finalize() skip.

### Pas 5 — Root cause + fix in f3_regex_parser.py

**Cauze comune:**

**Pattern A (NR standalone / descriere / subcomp):**
- Parser in `_WAITING` primeste linie fara cod (e.g. `'Echipamente platforma carosabila'`)
- Nu stie sa emita articol cu denumire dar fara cod propriu
- Fix: in starea `_WAITING`, daca linia e text pur (nu cod, nu NR), accepta ca denumire si treci in `_READING` cu cod=None; la `_finalize` emite articolul daca are denumire + subcomponente

**Spec tehnica false positive:**
- Codul sau descrierea matchuieste `[A-Z]{1,2}\d{2}` si e filtrat
- Fix: extinde exceptia `Y[A-Z]\d` sau adauga exceptie specifica

**UM necunoscut:**
- Parser nu poate finaliza articolul fara UM valid
- Fix: adauga UM in `UM_KNOWN`

**_finalize() skip:**
- Conditie slash, spec tehnica, deviz-sumar filter prea larga
- Fix: ingustare conditie

Aplica fix **minimal** in `shared/f3_regex_parser.py`. Un singur root cause per commit.

### Pas 6 — Verifica fix izolat

```python
# Re-ruleaza testul din Pas 4 dupa fix
arts = extract_articles_regex(context_lines, deviz_cod='TEST', deviz_den='TEST')
# nr gap trebuie sa apara acum in arts
assert any(str(a['nr_ordine']) == str(GAP_NR) for a in arts), "Inca lipseste!"
print("OK — articolul extras")
```

Daca assert pica: reintoarce-te la Pas 4, root cause gresit.

### Pas 7 — Reruleaza pipeline complet

```bash
rtk proxy python3 multi_client_run.py --client "<client>" 2>&1 | rtk log
```

### Pas 8 — Reruleaza verify_gaps

```bash
python3 verify_gaps.py --client "<client>"
```

Verifica: gap-ul fixat nu mai apare. Numara gap-uri fixabile ramase.

### Pas 9 — Ruleaza teste

```bash
pytest --tb=short -q
```

Baseline: 214/230 pass (16 pre-existing failures). Daca vreo noua eroare apare: nu comite, investiga.

### Pas 10 — Commit

```bash
git add shared/f3_regex_parser.py
git commit -m "fix(parser): <root cause scurt — ex: articol fara cod propriu, NR standalone + descriere>"
```

Treci la urmatorul gap fixabil si repeta de la Pas 3.

### Pas 11 — Stop conditions

Opreste cand:
- Toate gap-urile fixabile rezolvate (verify_gaps nu mai arata "bug extractor")
- Sau dupa 5 iteratii fara progres (acelasi set de gap-uri ramane)

### Pas 12 — Raport final

```
=== RAPORT FIXGAPS — <client> ===
Gap-uri fixate:   N (lista: grup | nr | commit)
Gap-uri skip:     M (deviz greșit — matching issue)
Gap-uri absente:  K (NU există în raw DI — salt numerotare)
Baseline teste:   214/230 (neschimbat) sau <nou>/230
```

## Note importante

- `verify_gaps.py` foloseste `holistic_oferta_N.json` (nu `_v2`) — nu analiza V2
- Sursa de adevăr: raw DI JSON (`input_AO/<client>/di_oferta_N.json`), nu output extras
- `pages` in DI JSON sunt 1-indexed in `page_number`, dar lista `pages` e 0-indexed
- Gap "pe alte pagini" = articolul exista dar e asociat alt grup → problema matching, nu parser
- Gap "NU există" = numerotare cu salt (1, 2, 4 — unde 3 nu a existat) → normal in F3
- Nu modifica `verify_gaps.py` — e tool de diagnostic, nu pipeline
- Pattern A (NR standalone / descriere / subcomp): cel mai frecvent in CAV Maneciu O2/O4
- SKIP_RE foloseste `re.search()` — pattern fara ancore matchuiesc oriunde in linie
- Dupa orice fix in f3_regex_parser.py: re-run pipeline complet, nu doar extractia
