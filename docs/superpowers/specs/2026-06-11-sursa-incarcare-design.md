# Sursa de Încărcare — Design Spec

> **For agentic workers:** Use `superpowers:subagent-driven-development` to implement this spec.

**Goal:** Pipeline nou care transformă un `di_*.json` (Azure DI output) într-un set de fișiere `Lista-proiect-XXX.docx/xlsx/pdf` — sursă de încărcare F3 pentru software-ul clientului.

**Date:** 2026-06-11  
**Status:** APPROVED — ready for implementation  
**Branch:** main

---

## Context

Pipeline existent (multi-client) compară referință vs. ofertă → holistic JSON → raport NC.  
Pipeline nou: un singur `di_*.json` → extrage articole **cu prețuri** → verificare automată → output F3.

Client de referință pentru UAT: `EuroProject` (`input_AO/EuroProject/di_referinta.json`).  
Format sursă: eDevize, 14 pagini, 1 deviz (`3.1 ARHITECTURA`), 90 articole principale.
Formatul sursa poate fi diferit; dar conceptele raman aceleasi.
---

## Arhitectură

```
gen_sursa_incarcare.py
        ↓
[ClientConfig.detect_clients()]        ← existent, neatins
        ↓
[f3_page_classifier]                   ← existent, LLM-cached (checkpoint)
        ↓
[deviz_header_extractor]               ← existent, neatins
        ↓
[f3_price_extractor]                   ← NOU: shared/f3_price_extractor.py
  → sursa_extracted_<json_name>.json   (checkpoint)
        ↓
[lista_verifier]                       ← NOU: shared/lista_verifier.py
  → sursa_verified_<json_name>.json    (checkpoint)
        ↓
[sursa_incarcare_writer]               ← NOU: shared/sursa_incarcare_writer.py
  → Lista-proiect-{ACRONIM}-{json}.docx
  → Lista-proiect-{ACRONIM}-{json}.xlsx
  → Lista-proiect-{ACRONIM}-{json}.pdf  (via LibreOffice CLI)
```

**Principiu cheie:** pipeline existent (`local_run.py`, `AgentComparator_local.py`, `f3_regex_parser.py`) rămâne **neatins**. Zero risc de regresie pe cei 214/230 teste existente.

---

## Fișiere noi / modificate

| Fișier | Tip | Responsabilitate |
|--------|-----|-----------------|
| `gen_sursa_incarcare.py` | NOU | CLI entry point |
| `shared/f3_price_extractor.py` | NOU | Extrage articole+prețuri+breakdown+capitole din pagini clasificate |
| `shared/lista_verifier.py` | NOU | Autoverificare: gaps nr_crt, total deviz, retry loop |
| `shared/sursa_incarcare_writer.py` | NOU | DOCX + XLS output (F3 format landscape) |
| `tests/shared/test_f3_price_extractor.py` | NOU | Unit tests extractor |
| `tests/shared/test_lista_verifier.py` | NOU | Unit tests verifier |
| `tests/shared/test_sursa_incarcare_writer.py` | NOU | Unit tests writer |

Fișiere existente neatinse: `f3_regex_parser.py`, `f3_page_classifier.py`, `deviz_header_extractor.py`, `local_run.py`, `AgentComparator_local.py`.

---

## Secțiunea 1: f3_price_extractor

### Input
- `classified_pages`: dict `{page_nr: {lines: [...], type: "F3"|...}}` — output f3_page_classifier
- `deviz_headers`: list of `DevizHeader` objects — output deviz_header_extractor

### Output — `sursa_extracted_<json_name>.json`

```json
[
  {
    "deviz_key": "md5(obiectivul|obiectul|categoria)",
    "obiectivul": "CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE",
    "obiectul": "3 ARHITECTURA",
    "categoria": "3.1 ARHITECTURA",
    "capitole": [
      {
        "titlu": "INFRASTRUCTURA",
        "articole": [
          {
            "nr_crt": "1",
            "cod": "CF38A*",
            "denumire": "Tencuiala pe baza de ciment",
            "um": "mp",
            "cantitate": 225.0,
            "pret_unitar": 33.22,
            "total": 7473.71,
            "breakdown": {
              "material":  {"pret": 13.22, "total": 2973.71},
              "manopera":  {"pret": 20.00, "total": 4500.00},
              "utilaj":    {"pret": 0.00,  "total": 0.00},
              "transport": {"pret": 0.00,  "total": 0.00},
              "control_ok": true
            },
            "sub_items": [
              {
                "nr_crt": "1.1",
                "cod": "2101121",
                "denumire": "Mortar de zidarie M 10 nisip S1030",
                "um": "mc",
                "cantitate": 1.939,
                "pret_unitar": 385.0,
                "total": 746.62
              }
            ]
          }
        ],
        "total_capitol": 24220.05
      }
    ],
    "total_deviz": 1935400.77
  }
]
```

### Patternuri regex

| Linie sursă | Clasificare | Regex |
|-------------|-------------|-------|
| `INFRASTRUCTURA` | capitol header | `^[A-ZĂÂÎȘȚÀÁÂ/ ]{4,}$` fără cifre, fără prefix NR |
| `TOTAL INFRASTRUCTURA 24,220.05` | total capitol | `^TOTAL\s+(.+?)\s+([\d,\.]+)$` |
| `1 CF38A* - Tencuiala...` | articol NR+COD | `^(\d+)\s+([A-Z0-9$.+*#%^>@<]+)\s*-\s*(.+)$` |
| `mp 225.000 33.22 7,473.71` | câmpuri articol | `^(\S+)\s+([\d,\.]+)\s+([\d,\.]+)\s+([\d,\.]+)$` |
| `material: 13.22 2,973.71` | breakdown | `^(material|manopera|utilaj|transport):\s*([\d,\.]+)\s+([\d,\.]+)$` |
| `1.1 2101121 - Mortar...` | sub-item | `^(\d+\.\d+)\s+(.+)$` |

### Control breakdown
```python
control_ok = abs(
    breakdown["material"]["pret"] +
    breakdown["manopera"]["pret"] +
    breakdown["utilaj"]["pret"] +
    breakdown["transport"]["pret"]
    - pret_unitar
) < 0.02
```

Dacă `control_ok = False` → articol marcat `"suspect": true` → lista_verifier îl notează.

### Checkpoint
`output_AO/{client}/sursa_extracted_{json_name}.json` — dacă există și nu e stale, skip re-extragere.

---

## Secțiunea 2: lista_verifier

> **Notă (2026-09-04):** secțiunea de mai jos descrie designul inițial, cu 5 checkuri.
> Implementarea are acum 9 — s-au adăugat `LAST_NR_CRT`, `HOLLOW_ARTICLES`,
> `TOTAL_1_DOC` și `FOOTER`. Cel mai important: `TOTAL_DEVIZ`, așa cum e specificat
> aici, nu poate eșua (`total_deviz` e calculat ca aceeași sumă pe care o verifică),
> iar `TOTAL_1_DOC` e cel care leagă extracția de totalul tipărit în document.
> Lista curentă: `docs/MANUAL_UTILIZARE.md` §7.

### Checks (în ordine)

| Check ID | Logică | Severitate |
|----------|--------|-----------|
| `COUNT_DEVIZE` | len(devize_extrase) vs. len(deviz_headers) | INFO |
| `NR_CRT_GAPS` | per deviz: nr_crt integer consecutive fără salt | HIGH |
| `TOTAL_CAPITOL` | sum(articol.total per capitol) ≈ total_capitol (toleranță 0.05 Lei) | HIGH |
| `TOTAL_DEVIZ` | sum(total_capitol) ≈ total_deviz (toleranță 0.05 Lei) | HIGH |
| `BREAKDOWN_CONTROL` | articole cu `control_ok=False` | WARN |

### Retry loop

```python
for iteration in range(1, 6):
    results = run_checks(extracted_data)
    high_failures = [c for c in results if c.severity == "HIGH" and not c.ok]
    if not high_failures:
        status = "OK" if no WARN else "WARN"
        break
    # identifică paginile cu articole suspecte
    suspect_pages = get_suspect_pages(high_failures, extracted_data)
    # re-extrage doar paginile afectate cu logică mai permisivă
    extracted_data = reextract_pages(extracted_data, suspect_pages, permissive=True)
else:
    status = "RED"
```

**Logică permisivă** la re-extragere: relaxează toleranța număr, acceptă linii parțiale, loghează ce a schimbat.

### Output — `sursa_verified_<json_name>.json`

```json
{
  "status": "OK" | "WARN" | "RED",
  "iterations": 1,
  "checks": {
    "COUNT_DEVIZE":      {"ok": true,  "found": 1, "expected": 1},
    "NR_CRT_GAPS":       {"ok": true,  "gaps": []},
    "TOTAL_CAPITOL":     {"ok": true,  "failures": []},
    "TOTAL_DEVIZ":       {"ok": true,  "extracted": 1935400.77, "computed": 1935400.77},
    "BREAKDOWN_CONTROL": {"ok": false, "suspect_articles": ["3", "17"]}
  }
}
```

---

## Secțiunea 3: sursa_incarcare_writer

### DOCX — landscape A4

**Coloane (6), lățimi fixe via `tblGrid`:**

| Col | Conținut | Lățime |
|-----|----------|--------|
| 0 | Nr. | 1.2 cm |
| 1 | Capitol de lucrări (COD + DENUMIRE) | 9.0 cm |
| 2 | U.M. | 1.5 cm |
| 3 | Cantitatea | 2.5 cm |
| 4 | Prețul unitar (fără TVA) — Lei | 2.8 cm |
| 5 | TOTALUL (fără TVA) — Lei | 3.0 cm |

**Tipuri rânduri:**

| Tip | Format |
|-----|--------|
| HEADER_DEVIZ | merge 6 cols, bold 10pt: "OBIECTIVUL / OBIECTUL / CATEGORIA" |
| ANTET_TABEL | bold 8pt, fundal gri #D9D9D9, repeat pe fiecare pagină (`tblHeader`) |
| CAPITOL | merge cols 1-5, bold 9pt, fundal #EEEEEE: "INFRASTRUCTURA" |
| ARTICOL | 8pt normal: NR \| COD - DENUMIRE \| UM \| cantitate \| preț \| total |
| BREAKDOWN | col1 indent 0.5cm, 7pt, italic: "" \| "material: ..." \| \| \| preț \| total |
| SUB_ITEM | 7.5pt, nr decimal: "1.1" \| COD - DENUMIRE \| UM \| cant \| preț \| total |
| TOTAL_CAPITOL | bold 8pt: "TOTAL INFRASTRUCTURA" \| \| \| \| \| 24,220.05 |
| TOTAL_DEVIZ | bold 9pt, fundal #FFF2CC: "TOTAL 1 (Cheltuieli directe)" \| \| \| \| \| total |
| RED_FLAG | fundal #FF0000, alb bold: "TOTAL NECONFIRMAT — verificare manuală necesară" |

Breakdown rows afișate **doar dacă** `breakdown` prezent în articol. Dacă `status=RED`, rândul TOTAL_DEVIZ înlocuit cu RED_FLAG.

Numere formatate: `1,234,567.89` (separator mii = `,`, zecimale = `.`). Cantități: 3 zecimale. Prețuri: 2 zecimale.

### XLS — openpyxl

Aceleași rânduri ca DOCX, fără merge-uri. Culori de fundal identice (hex). Lățimi coloane proporționale. Sheet name = categoria devizului (max 31 chars). Un sheet per deviz dacă JSON are multiple devize.

### PDF — LibreOffice CLI

```python
import subprocess
result = subprocess.run(
    ["soffice", "--headless", "--convert-to", "pdf",
     "--outdir", str(output_dir), str(docx_path)],
    capture_output=True, timeout=60
)
if result.returncode != 0:
    logger.warning("LibreOffice unavailable — PDF skipped")
```

Dacă `--no-pdf` flag sau LibreOffice absent → skip silențios, log warning.

### Naming fișiere

```python
def make_acronym(obiectivul: str) -> str:
    STOPWORDS = {"DE", "LA", "PE", "SI", "IN", "CU", "DIN", "PE", "A", "AL", "SA"}
    # strip prefix numeric (ex: "0232 000000232")
    text = re.sub(r'^\d[\d\s]+', '', obiectivul).strip()
    words = re.sub(r'[^A-ZĂÂÎȘȚ ]', '', text.upper()).split()
    letters = [w[0] for w in words if w not in STOPWORDS and len(w) >= 2]
    return ''.join(letters[:6])

# Output:
# Lista-proiect-{acronim}-{json_name_without_ext}.docx/xlsx/pdf
# Exemplu: Lista-proiect-CUCT-di_referinta.docx
```

---

## Secțiunea 4: CLI — gen_sursa_incarcare.py

### Mod interactiv

```
$ python3 gen_sursa_incarcare.py

Clienți disponibili:
  1. Blocuri Racari
  2. CAV Maneciu
  3. EuroProject
Client [număr]: 3

Fișiere JSON disponibile în input_AO/EuroProject/:
  1. di_referinta.json
JSON [număr]: 1

Procesare EuroProject / di_referinta.json...
  [1/4] Clasificare pagini (cached)...        ✓ 14 pagini F3
  [2/4] Extragere devize...                   ✓ 1 deviz (3.1 ARHITECTURA)
  [3/4] Extragere articole + prețuri...       ✓ 90 articole, 38 cu breakdown
  [4/4] Verificare (iterații: 1)...           ✓ OK

Output generat:
  output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.docx  ✓
  output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.xlsx  ✓
  output_AO/EuroProject/Lista-proiect-CUCT-di_referinta.pdf   ✓
```

### Mod CLI direct

```bash
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --no-pdf
```

### Argumente

| Argument | Tip | Default | Descriere |
|----------|-----|---------|-----------|
| `--client` | str | None (interactive) | Numele clientului |
| `--json` | str | None (interactive) | Numele JSON fără extensie |
| `--no-pdf` | flag | False | Skip generare PDF |
| `--force` | flag | False | Ignoră checkpoint, re-extrage |

---

## Autoverificare — Reguli Business

1. **Fiecare articol are preț** — `pret_unitar > 0` și `total > 0`. Excepție legitimă: utilaj/transport = 0.
2. **nr_crt consecutiv** — articolele principale (întreg) fără goluri. Sub-itemele (decimal) nu intră în secvență principală.
3. **Total capitol = sum articole** — toleranță 0.05 Lei (rotunjiri eDevize).
4. **Total deviz = sum totaluri capitole** — toleranță 0.05 Lei.
5. **Control breakdown** — `material+manopera+utilaj+transport ≈ pret_unitar` (toleranță 0.02 Lei).

---

## Testing

### Unit tests — `tests/shared/test_f3_price_extractor.py`
- Parsare articol simplu (fără breakdown)
- Parsare articol cu breakdown complet + control_ok=True
- Parsare articol cu breakdown incorect + control_ok=False
- Parsare sub-item decimal
- Detectare capitol header
- Parsare total capitol
- Articol cu DENUMIRE multi-linie

### Unit tests — `tests/shared/test_lista_verifier.py`
- Deviz fără gaps → status OK
- Deviz cu gap nr_crt 3→5 → HIGH failure
- Total capitol mismatch → HIGH failure → retry → fix → OK
- 5 iterații eșuate → status RED
- Breakdown suspect → WARN, nu RED

### Unit tests — `tests/shared/test_sursa_incarcare_writer.py`
- DOCX generat cu numărul corect de rânduri
- Rând RED_FLAG prezent când status=RED
- Rânduri breakdown absente dacă articol fără breakdown
- Acronim generat corect din OBIECTIVUL
- Naming fișiere corect

---

## Constrângeri cunoscute

- **Format variabil** — PDFs de la softuri diferite. Extractor-ul poate necesita ajustare regex per client nou (același pattern ca `SKIP_RE` în f3_regex_parser).
- **LibreOffice** — PDF opțional; dacă absent, skip fără eroare. - incercam sa il instalam totusi
- **LLM cost** — page classifier face LLM calls la primul run per JSON. Cache-ul evită re-rularea.
- **Multi-deviz** — JSON cu multiple devize (ex: Blocuri Racari) generează un fișier DOCX/XLS per deviz, cu același acronim în nume.
