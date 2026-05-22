---
name: f3-domain-rules
description: Use when writing, modifying, or debugging any code that touches article code parsing, UM detection, deviz code extraction, matching keys, or denomination comparison in this project. Load before editing f3_regex_parser.py, AgentComparator_local.py, deviz_matcher.py, or shared/comparator.py.
---

# F3 Domain Rules — Sursa de Adevăr

Reguli definitive pentru coduri articole, UM, devize. Actualizează acest fișier la orice schimbare structurală în parser sau matcher.

---

## 1. Coduri Articole — Tipuri și Regex

### Normativ (tipul cel mai comun)
```
[A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?\d?
```
Exemple: `CA01A`, `CK26A`, `TCB40B1`, `TSA02F1`, `IC19XB1`
Regex în cod: `COD_NORM_RE`, `COD_NORM_STANDALONE_RE`

### Extended (2-5L + 1-2D + 1-3L + 2-4D)
```
[A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}[A-Z]?\d?
```
Exemple: `TRI1AA01C2`, `RPCB02E99`
Regex: `COD_NORM_EXTENDED_RE`, `COD_NORM_EXTENDED_STANDALONE_RE`

### Single-letter start (L + D + 1-3L + 2-4D)
```
[A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}
```
Exemple: `W2F05C01`, `H1V06H`, `H1B02A3`, `EA02A1`
Regex: `COD_NORM_SINGLE_RE`, `NR_SINGLE_INLINE_RE`

### Digit-Letter-Digit (3-5D + L + 1-3D)
```
\d{3,5}[A-Z]\d{1,3}(?!\d)
```
Exemple: `00106B011`, `01311A1`, `02012A1`
Regex: `COD_DIGIT_LETTER_DIGIT_RE`

### Breviar cu $ prefix
```
\$[A-Z0-9]{4,}
```
Exemple: `$2200012`, `$16508`, `$100014394`
Regex: `COD_BREVIAR_RE`

### Numeric pur (convertit intern la $ prefix)
```
\d{4,9}(?!\d)
```
Exemple: `6701362` → `$6701362`, `5102437` → `$5102437`
Regex: `COD_NUMERIC_RE`, `COD_NUMERIC_BARE_RE`

### Sufixe strippuite automat
```
[-@%>#*^+]+$   →  strip
\s*\[\d*\]?\s*$  →  strip  (ex: [1], [2])
(?:ASIM|TSCH)$   →  strip  (designatori normativi)
```

---

## 2. Unitate de Măsură — Whitelist și Blacklist

### UM_KNOWN (acceptate)
```python
{
    # Lungime / arie / volum
    'M', 'ML', 'MP', 'MPC', 'MC', 'KM', 'DM',
    # Masă
    'KG', 'T', 'TO', 'TON', 'TONA', 'TONE', 'G', 'MG',
    # Electric
    'KW', 'KWH', 'KVA', 'W',
    # Bucăți
    'BUC', 'BUCATA', 'BUCAT',
    # Timp
    'ORA', 'ORE', 'OREI', 'ZI', 'ZILE', 'SCHIMB', 'LUNA', 'LUNI', 'SAPT',
    # Misc construcții
    'SET', 'PERECHE', 'ROLA', 'PAG', 'ART', 'ROT',
    # Financiar
    'LEI', 'MII', 'H', 'L',
}
```

### UM_SKIP (respinse explicit, deși sunt scurte)
```python
{'ASIM', 'TSCH', 'SCH', 'UM', 'NR', 'CRT', 'TOTAL', 'PU', 'VAL'}
```

### Anti-digit rule
```python
if re.search(r'\d', token) and token not in ('M3', 'M2'):
    return False  # linia cu cifre nu e coloana UM
```
**Excepție:** `M3`, `M2` sunt variante pentru `mc`/`mp`.

### KM — întotdeauna distanță, nu UM de lucru
```python
if um_candidate == 'KM':
    continue  # skip — "20 KM transport" nu e cantitate de lucru
```

### MM, CM — absente intenționat din UM_KNOWN
`8 MM` din OCR = continuare denumire (ex: "OB 37 D = 6-8 MM"), nu UM real.

### Normalizări canonice
```python
'BUCATA', 'BUCAT'  →  'buc'
'TONE'             →  'tona'
'ORE', 'OREI'      →  'ora'
'M CUB', 'M3'      →  'mc'
'M2', 'M²'         →  'mp'
'ML' (echivalent)  →  'M'  # via _UM_EQUIV
```

---

## 3. Detectie UM în _READING state (prioritate)

```
1. NR_ALPHA_INLINE guard: "82 M" matches NR+COD pattern →
      dacă "codul" e UM valid și articol fără UM → setează UM, nu articol nou

2. _is_valid_um(line): token singur pe linie
      UM_KNOWN + nu conține cifre + nu în UM_SKIP

3. "ZECI M" / "SUTE M" standalone → um = 'm'

4. "82 M" via m_um_norm:  r'^(\d+)\s+([A-Z]{1,6})\.?\s*$'
      group(2) = UM candidat. Dacă single-letter și next_line e UM valid → skip.

5. "M CUB" / "M3" / "M²" → 'mc'
```

---

## 4. _preprocess_scattered_format — Regula Critică

**Detectează:** counter(bare digit) + cod + (desc…) + UM + QTY pe linii separate.

**Branch A** (counter + cod + UM + QTY consecutive):
```
lines[i]   = "6"         ← bare counter
lines[i+1] = "EA02A1"    ← cod valid
lines[i+2] = "BUCATA"    ← UM valid
lines[i+3] = "170,00000" ← QTY
→ Combina: "6 EA02A1 - " + description
```

**Branch B** (F3-order: counter + cod + descriere... + UM + QTY):
```python
# ⚠ REGULA CRITICA — is_f3_um TREBUIE single-token
is_f3_um = (
    len(candidate) < 20 and
    re.match(r'^[A-Za-z\s\.]+$', candidate) and
    len(_f3_um_tokens) == 1 and        # ← OBLIGATORIU single-token
    _f3_um_tokens[0].rstrip('.') in UM_KNOWN
)
```

**De ce single-token obligatoriu:**
`"Art. asimilat"` → 2 tokeni → primul token `ART` e în UM_KNOWN → false positive.
Fără această regulă, preprocess lua NR_CRT-ul articolului următor drept QTY,
producând articole cu `cantitate=0` (bug rezolvat 2026-05-22, commit: scatter-fix).

---

## 5. Cheie Matching

```python
key = (deviz_cod, article_cod)
# ex: ("BLC2", "EA02A1"), ("1-02", "$2200012")
```

### Deviz cod formate valide
| Format | Exemplu | Sursa |
|--------|---------|-------|
| BLC prefix | `BLC1`, `BLC2`, `BLC7` | Oferte cu bloc separate |
| Numeric compus | `1-01`, `2-03`, `4.1-01` | ISDP/eDevize (Obiectul-Categoria) |
| Numeric pur | `226208`, `226428` | eDevize cod intern |
| Text | `001-001`, `002-002` | Variante eDevize |

### Normalizare deviz cod
```python
U→0  (OCR)
_normalize_deviz_cod(cod): strip leading zeros, uppercase
```

---

## 6. Matching Layers — Ordine și Reguli

| Layer | Mecanism | Fișier | Activ |
|-------|----------|--------|-------|
| 1 | Exact `(deviz, cod)` N:M | AgentComparator_local.py | ✅ |
| 2 | Normalized cod (strip `$`, AUT→$) | article_matcher.py | ✅ |
| 2.1 | Trailing digit (IC35D↔IC35D1) | article_matcher.py | ✅ |
| 2.5 | OCR similar SequenceMatcher ≥ 0.80 N:M | article_matcher.py | ✅ |
| 3 | LLM fuzzy | - | ❌ disabled |

**Layer 2.5 — Regula N:M:**
```python
# CORECT: include TOATE instantele per cheie
oferta_by_deviz[ok[0]].extend(oferta_by_key[ok])
# GRESIT (bug rezolvat): oferta_map[ok] — doar prima instanta
```

**Post-processing Lenient UM:**
```python
# $ coduri EXTRA cu cod in ref same deviz și ref.um == ''
# → Convert EXTRA → matched + UM_DIFERIT
```

---

## 7. Tipuri Neconformitate

| Tip | Definitie |
|-----|-----------|
| `ARTICOL_LIPSA` | Cod in ref, absent din oferta (sau deviz gresit) |
| `ARTICOL_EXTRA` | Cod in oferta, absent din ref |
| `DEVIZ_MISMATCH` | Cod gasit in oferta dar alt deviz vs ref — NU e LIPSA reala |
| `UM_DIFERIT` | Acelasi cod+deviz, UM diferit dupa normalizare |
| `DIFERENTA_CAMP` | Acelasi cod+deviz, cantitate/pret diferit (toleranta 0.5%) |

---

## 8. Known Gotchas

| Situatie | Comportament corect |
|----------|---------------------|
| `82 M` pe linie separata | m_um_norm → um='m', nr 82 ignorat |
| `Art. asimilat` in lookahead | is_f3_um=False (2 tokeni) — nu e UM |
| `IZDO3D1` vs `IZD03D1` | OCR O/0 — Layer 1 consuma cheia reala, varianta OCR ramane LIPSA |
| `TRA01A15P` in 5 devize | Normal — acelasi cod poate aparea in devize multiple |
| `$7650374` cu ref.um='' | Lenient UM post-proc → MATCHED + UM_DIFERIT |
| Continuare pagina (header_only) | Pagina cu doar header nu se proceseaza (is skipped) |
| Bare `82` in READING cu cant=0 | _finalize() + _WAITING (tratata ca NR_CRT nou) |
| Bare `82` in READING cu cant>0 | _is_nr_crt() check: price_count==0 and cant>0 → True → _finalize() |

---

## 8b. DESCRIERE_DIFERITA — Implementare și False Pozitive

**Fișier:** `shared/comparator.py::compare_articles()`

**Logica:** Jaccard pe mulțimi de cuvinte < 0.50, după curățare OCR artifacts.

**Artefacte curatate (`_OCR_ARTIFACTS`):**
- eDevize headers: `antet stanga`, `edevize`, `sectiunea tehnica`, `formular f3`
- Notatie subcomponente: `l: CODE -MATERIAL_ID -...` (orice format)
- Garbage financiar: `io = %`, `po = %`, `vo = +po`, `contrib asig munca`
- Spill din randuri tabel: `executant NNN`, `obiectiv NNN`, `comerciala`

**False pozitive reziduale — abrevieri nerezolvate:**
| Abreviere | Forma completa |
|-----------|---------------|
| `pt` / `pt.` | `pentru` |
| `supr` / `supr.` | `suprafata` |
| `termoizol.` | `termoizolatii` |
| `gr.` | `grosime` |
| `inc.` / `incl.` | `inclusiv` |
| `b.a.` | `beton armat` |

**Fix propus:** Dicționar static `ABREVIERI_F3` aplicat în `_clean_den()` înaintea tokenizării.
**Alternativa LLM:** Trimitere perechi DD sim 0.40-0.50 la Claude Haiku pentru validare DA/NU.

---

## 9. Deviz Matcher — Strategii (în ordine)

| Strategie | Mecanism | Când se aplică |
|-----------|----------|----------------|
| **0** | Numeric structural: `(obj_int, cat_int)` match | Compound codes cu formate diferite (001-004 ↔ 1.0-1.4) |
| **1** | Exact code match | Aceleași coduri în ref și ofertă |
| **2** | Exact denomination match | Text identic după normalizare |
| **3** | Fuzzy SequenceMatcher ≥ 0.70 | Texte similare |

**Strategy 0 — Regula de extracție:**
```python
def _extract_numeric_struct(deviz_code):
    # "001-004" → (1, 4)  |  "1.0-1.4" → (1, 4)
    obj_int = int(float(parts[0].lstrip('0') or '0'))
    if '.' in cat_str:
        cat_int = round((float(cat_str) % 1) * 10)  # frac × 10
    else:
        cat_int = int(float(cat_str.lstrip('0') or '0'))
```

**Fișier:** `shared/deviz_matcher.py`

---

## 10. Fișiere Cheie și Linii de Referință

| Regula | Fișier | Linie aprox. |
|--------|--------|-------------|
| COD_NORM_RE | shared/f3_regex_parser.py | 23 |
| NR_ALPHA_INLINE_RE | shared/f3_regex_parser.py | 97 |
| UM_KNOWN | shared/f3_regex_parser.py | 203 |
| UM_SKIP | shared/f3_regex_parser.py | 221 |
| _is_valid_um | shared/f3_regex_parser.py | 268 |
| _preprocess_scattered_format | shared/f3_regex_parser.py | 413 |
| is_f3_um single-token fix | shared/f3_regex_parser.py | 535 |
| State machine IDLE/WAITING/READING | shared/f3_regex_parser.py | 997+ |
| Layer 2.5 N:M fix | AgentComparator_local.py | 629 |
| Lenient UM post-proc | AgentComparator_local.py | 923 |
| extract_articles_v3 | shared/f3_extractor.py | 807 |
| _CATEGORIA_OPT_RE (decimal cat_num) | shared/f3_page_classifier.py | 106 |
| _extract_numeric_struct (Strategy 0) | shared/deviz_matcher.py | ~98 |
| match_devize_by_denomination | shared/deviz_matcher.py | 157 |

---

**Actualizare obligatorie:** Orice modificare structurală la parsare coduri, UM, devize sau matching → actualizează secțiunile relevante din acest fișier în același commit.
