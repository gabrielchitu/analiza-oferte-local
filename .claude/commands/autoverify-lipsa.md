# Autoverificare ARTICOL_LIPSA — Loop autonom

Executa loop autonom de depanare extractie pentru coduri ARTICOL_LIPSA din raportul holistic al unui client.

**Nu intreba nimic. Nu te opri intre iteratii. Fixeaza si continua pana la 0 LIPSA rezolvabile.**

## Input

Argumentul optional: numele clientului (ex: `Drum Tatarani`). Daca lipseste, intreaba o singura data.

## Algoritmul

### Pas 1 — Identifica LIPSA din holistic

Citeste `output_AO/<client>/holistic_oferta_1.json` (si oferta_2, oferta_3 etc.).
Extrage toate NC-urile cu `tip == "ARTICOL_LIPSA"`.
Retine: `ref_cod`, `deviz_cod`, `ref_denumire`.

Prioritizeaza oferta cu cele mai multe LIPSA. Lucreaza pe o singura oferta la un moment dat.

### Pas 2 — Verifica daca codul exista in di_oferta

Pentru fiecare `ref_cod`:
1. Cauta in `input_AO/<client>/di_oferta_N.json` (N = numarul ofertei din holistic_oferta_N.json) — in continutul raw al paginilor (`pages[N].lines[M].content` sau similar).
2. Daca codul (fara `$`) apare in di_oferta: **eroare de extractie** → du-te la Pas 3.
3. Daca NU apare: articol genuinely absent din oferta → noteaza si treci la urmatorul.

**Atentie:** Cauta codul fara prefixul `$`. Ex: `ref_cod = "$2100916"` → cauta `2100916` in paginile raw.

### Pas 3 — Gaseste contextul raw

Localizeaza pagina si liniile din di_oferta_N.json care contin codul.
Afiseaza ~10 linii de context (inainte si dupa).
Identifica formatul: L: prefix, bare numeric, NR+COD inline, codul pe linie separata, etc.

Verifica si:
- Ce deviz_cod/pagina contine codul (poate fi intr-un grup diferit decat cel din referinta)
- Daca codul apare in mai multe pagini

### Pas 4 — Testeaza extractia curenta

```python
from shared.f3_regex_parser import extract_articles_regex, SKIP_RE
lines = [...]  # liniile raw din di_oferta_N in jurul codului
arts = extract_articles_regex(lines, deviz_cod='...', deviz_den='...')
# Verifica daca codul apare in arts
for a in arts:
    print(a.get('cod'), a.get('cantitate'), a.get('is_component'))
```

Daca nu apare: adauga debug pentru a identifica unde se pierde:
- `SKIP_RE.search(line)` pentru fiecare linie relevanta
- `_merge_split_l_lines` output
- State machine trace cu `logging.DEBUG`
- Verifica daca `_finalize()` skip-uieste articolul (slash, spec tehnica, deviz-sumar)

### Pas 5 — Root cause + fix

Pattern-uri comune de cauze:
- `SKIP_RE` filtreaza linia cu codul (verifica range-uri prea largi)
- UM necunoscut (nu e in `UM_KNOWN`) → codul nu se finalizeaza cu UM corect
- L: split pe 2-3 linii → `_merge_split_l_lines` nu recunoaste formatul
- `_finalize()` skip condition gresita (slash, spec tehnica, deviz-sumar filter)
- Cod OCR corupt in di_oferta (ex: `O` in loc de `0`, `I` in loc de `1`) → verifica `_normalize_cod` in AgentComparator si ocr_patterns_knowledge.json
- Format specific clientului nesuportat (ex: codul pe linie separata fata de cantitate)

Aplica fix minimal in `shared/f3_regex_parser.py`. Daca e OCR mismatch (nu extractie), adauga pattern in `shared/ocr_patterns_knowledge.json`.
Adauga test minimal daca fix-ul e non-trivial.

### Pas 6 — Reruleaza si verifica

```bash
python3 multi_client_run.py --client "<client>"
```

Verifica `output_AO/<client>/oferta_N.json` — codul trebuie sa apara acum cu cantitate > 0.
Verifica `holistic_oferta_N.json` — codul nu mai trebuie sa fie LIPSA.

### Pas 7 — Commit si continua

```bash
git add shared/f3_regex_parser.py  # sau fisierul modificat
git commit -m "fix(parser): <descriere scurta a root cause-ului>"
```

Treci la urmatorul LIPSA si repeta de la Pas 2.

### Pas 8 — Stop conditions

Opreste loop-ul cand:
- Toate LIPSA-urile verificate sunt: fie fixate, fie genuinely absent din di_oferta
- Sau dupa 5 iteratii fara progres (acelasi set de LIPSA ramane)

### Pas 9 — Raport final

Afiseaza:
- Cate LIPSA au fost rezolvate prin fix
- Cate sunt genuinely absent (diferente reale oferta vs referinta — ofertantul nu a inclus articolul)
- Cate sunt OCR mismatch (cod diferit in oferta, nu extractie bug)
- Commit hash-ul ultimului fix

## Note importante

- `holistic_oferta_N.json` are cheia `neconformitati` (nu `nonconformities`)
- NC-urile au `tip` (nu `type`), `ref_cod` si `ref_denumire` pentru LIPSA
- `di_oferta_N.json` — liniile sunt in `pages[N]` ca lista de dicts `{"content": "..."}`
- `oferta_N.json` — articolele extrase din di_oferta_N, folosit pentru matching
- Regula: cod 7 cifre = articol catalog; cod 4-6 cifre = capitol/deviz; cod 8+ cifre = CPV
- SKIP_RE foloseste `re.search()` — pattern-urile fara ancore matchuiesc oriunde in linie
- Dupa fix, re-run pipeline **complet** (`multi_client_run.py`), nu doar extractia
- LIPSA ≠ neaparat bug extractie: ofertantul poate sa nu fi inclus articolul intentionat
- Daca codul din referinta apare cu OCR diferit in oferta (ex: `TRA01A5O` vs `TRA01A50`), nu e extractie bug — e COD_SIMILAR match miss; fix in `ocr_patterns_knowledge.json` sau `AgentComparator_local.py`
