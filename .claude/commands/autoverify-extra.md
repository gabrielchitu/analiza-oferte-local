# Autoverificare ARTICOL_EXTRA — Loop autonom

Executa loop autonom de depanare extractie pentru coduri ARTICOL_EXTRA din raportul holistic al unui client.

**Nu intreba nimic. Nu te opri intre iteratii. Fixeaza si continua pana la 0 EXTRA rezolvabile.**

## Input

Argumentul optional: numele clientului (ex: `Camin Maneciu`). Daca lipseste, intreaba o singura data.

## Algoritmul

### Pas 1 — Identifica EXTRA din holistic

Citeste `output_AO/<client>/holistic_oferta_1.json` (si oferta_2, oferta_3 etc.).
Extrage toate NC-urile cu `tip == "ARTICOL_EXTRA"`.
Retine: `oferta_cod`, `deviz_cod`, `oferta_denumire`.

### Pas 2 — Verifica daca codul exista in di_referinta

Pentru fiecare `oferta_cod`:
1. Cauta in `input_AO/<client>/di_referinta.json` — in continutul raw al paginilor (`pages[N].lines[M].content` sau similar).
2. Daca codul (fara `$`) apare in di_referinta: **eroare de extractie** → du-te la Pas 3.
3. Daca NU apare: articol genuinely absent din referinta → noteaza si treci la urmatorul.

### Pas 3 — Gaseste contextul raw

Localizeaza pagina si liniile din di_referinta care contin codul.
Afiseaza ~10 linii de context (inainte si dupa).
Identifica formatul: L: prefix, bare numeric, NR+COD inline, etc.

### Pas 4 — Testeaza extractia curenta

```python
from shared.f3_regex_parser import extract_articles_regex, SKIP_RE
lines = [...]  # liniile raw din di_referinta in jurul codului
arts = extract_articles_regex(lines, deviz_cod='...', deviz_den='...')
# Verifica daca codul apare in arts
```

Daca nu apare: adauga debug pentru a identifica unde se pierde:
- `SKIP_RE.search(line)` pentru fiecare linie relevanta
- `_merge_split_l_lines` output
- State machine trace cu `logging.DEBUG`

### Pas 5 — Root cause + fix

Pattern-uri comune de cauze:
- `SKIP_RE` filtreaza linia cu codul (verifica `^\d{4,8}$`, bare `424`, alte pattern-uri broad)
- UM necunoscut (nu e in `UM_KNOWN`) → codul nu se finalizeaza cu UM corect
- L: split pe 2-3 linii → `_merge_split_l_lines` nu recunoaste formatul
- `_finalize()` skip condition gresita (slash, spec tehnica, deviz-sumar filter)

Aplica fix minimal in `shared/f3_regex_parser.py`. Adauga test minimal daca fix-ul e non-trivial.

### Pas 6 — Reruleaza si verifica

```bash
python3 multi_client_run.py --client "<client>"
```

Verifica `output_AO/<client>/referinta.json` — codul trebuie sa apara acum.
Verifica `holistic_oferta_N.json` — codul nu mai trebuie sa fie EXTRA.

### Pas 7 — Commit si continua

```bash
git add shared/f3_regex_parser.py
git commit -m "fix(parser): <descriere scurta a root cause-ului>"
```

Treci la urmatorul EXTRA si repeta de la Pas 2.

### Pas 8 — Stop conditions

Opreste loop-ul cand:
- Toate EXTRA-urile verificate sunt: fie fixate, fie genuinely absent din di_referinta
- Sau dupa 5 iteratii fara progres (acelasi set de EXTRA ramane)

### Pas 9 — Raport final

Afiseaza:
- Cate EXTRA au fost rezolvate prin fix
- Cate sunt genuinely absent (diferente reale referinta vs oferta)
- Commit hash-ul ultimului fix

## Note importante

- `holistic_oferta_N.json` are cheia `neconformitati` (nu `nonconformities`)
- NC-urile au `tip` (nu `type`), `oferta_cod` (nu `offer_cod`)
- `di_referinta.json` — liniile sunt in `pages[N]` ca lista de dicts `{"content": "..."}`
- `referinta.json` — articolele extrase din di_referinta, folosit pentru matching
- Regula: cod 7 cifre = articol catalog; cod 4-6 cifre = capitol/deviz; cod 8+ cifre = CPV
- SKIP_RE foloseste `re.search()` — pattern-urile fara ancore (`^`, `$`, `\b`) matchuiesc oriunde in linie
- Dupa fix, re-run pipeline **complet** (`multi_client_run.py`), nu doar extractia
