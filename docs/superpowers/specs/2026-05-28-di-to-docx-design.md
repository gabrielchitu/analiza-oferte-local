# DI JSON → DOCX Converter — Design Spec
**Data:** 2026-05-28 | **Status:** Aprobat

---

## Goal

Script standalone care convertește fișierele Azure Document Intelligence JSON (`di_referinta.json`, `di_oferta_N.json`) per client într-un DOCX lizibil de utilizatorul final. Un DOCX per fișier DI.

---

## Invocație

```bash
python3 di_to_docx.py --client "BR BLOC A"
```

---

## Fișiere

| Fișier | Rol |
|--------|-----|
| `di_to_docx.py` | NOU — script standalone, entry point |
| `tests/test_di_to_docx.py` | NOU — unit tests |
| `shared/client_config.py` | EXISTENT — folosit pentru rezolvarea căilor |

---

## Input / Output

```
input_AO/<client>/di_referinta.json   →   output_AO/<client>/DI_Referinta.docx
input_AO/<client>/di_oferta_1.json   →   output_AO/<client>/DI_Oferta_1.docx
input_AO/<client>/di_oferta_2.json   →   output_AO/<client>/DI_Oferta_2.docx
...
```

Dacă un fișier `di_oferta_N.json` lipsește → skip silențios + mesaj stdout. Toți fișierul `di_referinta.json` + toți `di_oferta_*.json` găsiți se procesează la o singură rulare.

---

## Structura DI JSON (input)

```json
{
  "pages": [
    {
      "page_number": 1,
      "lines": [
        {"content": "Beneficiar:"},
        {"content": "Executant: Proiectant:"},
        ...
      ]
    }
  ],
  "tables": [
    {
      "row_count": 6,
      "column_count": 2,
      "cells": [
        {"row_index": 0, "column_index": 0, "kind": "", "content": "Beneficiar:"},
        {"row_index": 3, "column_index": 0, "kind": "", "content": "Obiectivul:"},
        {"row_index": 3, "column_index": 1, "kind": "", "content": "EFICIENTIZARE ENERGETICA..."}
      ]
    },
    {
      "row_count": 37,
      "column_count": 6,
      "cells": [
        {"row_index": 0, "column_index": 0, "kind": "", "content": "SECTIUNEA TEHNICA"},
        {"row_index": 1, "column_index": 0, "kind": "columnHeader", "content": "Nr."},
        {"row_index": 1, "column_index": 1, "kind": "columnHeader", "content": "Capitol de lucrari"},
        ...
      ]
    }
  ]
}
```

`tables[0]` = tabel metadate (2 coloane). `tables[1..N]` = tabele F3 (6 coloane: Nr / Capitol / UM / Cantitate / Pret / Total).

---

## Structura DOCX generat

```
[Heading 0]  <stem fișier>  (ex: "di_referinta")

─── SECȚIUNEA: PAGINI ───────────────────────────────

[Caption]     --- Pagina 1 ---
[Normal]      Beneficiar:
[Normal]      Executant: Proiectant:
[Normal]      Obiectivul:
[Normal]      EFICIENTIZARE ENERGETICA...
              ... (toate liniile paginii)

[Caption]     --- Pagina 2 ---
              ...

─── PAGE BREAK ──────────────────────────────────────

[Heading 1]   Tabele

[Bold para]   Obiectivul:   EFICIENTIZARE ENERGETICA...
[Bold para]   Obiectul:     1 LUCRARI...
[Bold para]   Stadiul fizic: BLC1 ARHITECTURA
              (tabel 0 — metadate, redat key-value)

[Heading 2]   Tabel 1
[DOCX Table]
  | SECTIUNEA TEHNICA (merged, gri, bold) | SECTIUNEA FINANCIARA (merged, gri, bold) |
  | Nr. | Capitol | UM | Cantitate | Pret | Total |
  | 1   | ...     | mc | 120.00    | ...  | ...   |
  | ...                                           |

[Heading 2]   Tabel 2
[DOCX Table]
  ...
```

---

## Logica de Randare

### Metadate (tables[0])

- Grupare celule per `row_index`
- Col 0 = cheie (bold), Col 1 = valoare
- Rânduri cu cheie goală → skip
- Redat ca paragrafuri `"<cheie>   <valoare>"` cu cheia în bold

### Tabele F3 (tables[1..N])

- Creare DOCX table cu `column_count` coloane
- Rândul 0 (`SECTIUNEA TEHNICA` / `SECTIUNEA FINANCIARA`): merged pe 3+3 coloane, fundal gri (`#D9D9D9`), bold, centrat
- Rândul 1 (header coloane): bold, fundal gri deschis (`#F2F2F2`)
- Rânduri 2+: text normal, font 9pt pentru densitate
- Celule cu `kind='columnHeader'` → bold indiferent de rând
- Celule lipsă (gap în `row_index` / `column_index`) → celulă goală

### Pagini raw

- Iterare `pages` în ordine `page_number`
- Separator `"--- Pagina N ---"` cu style `Caption`
- Fiecare `line["content"]` → paragraf `Normal`
- Fără deduplicare față de conținutul tabelelor (documentul e de referință)

---

## Error Handling

| Situație | Comportament |
|----------|-------------|
| `--client` inexistent în `input_AO/` | Mesaj clar + `sys.exit(1)` |
| `di_referinta.json` lipsă | Warning + skip (nu exit) |
| `di_oferta_N.json` lipsă | Skip silențios + stdout |
| Tabel cu 0 celule | Skip tabel + warning |
| Tabel cu < 2 coloane | Skip tabel + warning |
| JSON malformat | Exception cu path + `sys.exit(1)` |
| `output_AO/<client>/` inexistent | Creat automat cu `mkdir -p` |

---

## Teste (tests/test_di_to_docx.py)

### Test 1: `test_metadata_table_rendered`
Input: `tables[0]` cu 6 rânduri (Obiectivul, Obiectul, Stadiul fizic).
Assert: documentul conține paragrafuri cu textul cheilor bold.

### Test 2: `test_f3_table_row_col_count`
Input: tabel F3 cu `row_count=5`, `column_count=6`, celule complete.
Assert: DOCX table are 5 rânduri și 6 coloane.

### Test 3: `test_page_lines_rendered`
Input: 2 pagini cu câte 3 linii fiecare.
Assert: documentul conține separatoarele `--- Pagina 1 ---`, `--- Pagina 2 ---` și toate liniile.

### Test 4: `test_invalid_client_exits`
Input: `--client "ClientInexistent"`.
Assert: `sys.exit(1)` / exit code 1.

### Test 5: `test_missing_di_oferta_skipped`
Input: folder client fără `di_oferta_3.json`.
Assert: scriptul nu ridică excepție, procesează celelalte fișiere.

---

## Dependențe

- `python-docx` — deja în proiect (`shared/report_word.py` îl folosește)
- `shared/client_config.py` — `ClientConfig.from_folder()`
- Python stdlib: `argparse`, `json`, `pathlib`, `sys`

---

## Constrângeri

- Script standalone — nu modifică `local_run.py`, `multi_client_run.py` sau pipeline-ul existent
- Nu șterge / suprascrie fișierele existente din `output_AO/<client>/` (DI_*.docx sunt nume distincte)
- Fără LLM, fără API calls
- `f3_markers_knowledge.json` și `ocr_patterns_knowledge.json` — neutilizate în acest script
