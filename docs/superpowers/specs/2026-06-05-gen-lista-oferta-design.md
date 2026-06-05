# Design: gen_lista_oferta.py — Lista articole DOCX

**Data:** 2026-06-05  
**Status:** Aprobat

## Scop

Script standalone care generează documente Word (DOCX) în format Formular F3 pentru referința și fiecare ofertă dintr-un client. Conține: numele ofertantului/proiectantului, toate grupurile cu articolele lor (cod, cod principal, denumire, cant, um, prețuri defalcate).

## Surse de date

| Document generat | Sursă articole | Sursă ofertant |
|---|---|---|
| `Lista_Referinta.docx` | `output_AO/<client>/referinta.json` | `input_AO/<client>/di_referinta.json` (linia după "PROIECTANT") |
| `Lista_Oferta_N.docx` | `output_AO/<client>/oferta_N.json` | `input_AO/<client>/di_oferta_N.json` (linia după "CONTRACTANT (OFERTANT)") |

## Structura DOCX

### Header document
```
Lista articole — Oferta N          (sau "Referință")
Client: <client_name>
Ofertant: SC. KATO SERVICE SRL     (sau "Proiectant: ..." pt referință)
Generat: 2026-06-05
```

### Per grup (obiectivul | obiectul | categoria)

Titlu grup: bold, fundal gri deschis.

Tabel cu header pe 2 rânduri (merge_cells):

```
┌──────┬────────┬──────────┬───────────────┬────────────────────┬─────┬──────────┬─────────────────────────────────────┬─────────────────────────────────────┐
│      │        │          │               │                    │     │          │       Pret unitar (lei/UM)           │            Valoare (lei)             │
│ Nr.  │Nr.crt  │   Cod    │ Cod principal │     Denumire       │ UM  │Cantitate ├─────────┬──────────┬───────┬─────────┼─────────┬──────────┬───────┬─────────┤
│      │        │          │               │                    │     │          │Material │Manoperă  │Utilaje│Transport│Material │Manoperă  │Utilaje│Transport│
└──────┴────────┴──────────┴───────────────┴────────────────────┴─────┴──────────┴─────────┴──────────┴───────┴─────────┴─────────┴──────────┴───────┴─────────┘
```

**Total 15 coloane.**

### Câmpuri articol → coloane

| Coloană | Câmp JSON | Observații |
|---|---|---|
| Nr. | secvențial | 1, 2, 3... per grup, resetat per grup |
| Nr.crt | `nr_ordine` | pt subcomp: `parent_nr_ordine.seq` (ex: `2.1`) |
| Cod | `cod` | |
| Cod principal | `parent_code` | gol dacă `is_component=False` |
| Denumire | `denumire` | |
| UM | `um` | |
| Cantitate | `cantitate` | 3 zecimale |
| Pret Material | `pret_material` | gol dacă 0 |
| Pret Manoperă | `pret_manopera` | gol dacă 0 |
| Pret Utilaje | `pret_utilaj` | gol dacă 0 |
| Pret Transport | `pret_transport` | gol dacă 0 |
| Val Material | `val_material` | gol dacă 0 |
| Val Manoperă | `val_manopera` | gol dacă 0 |
| Val Utilaje | `val_utilaj` | gol dacă 0 |
| Val Transport | `val_transport` | gol dacă 0 |

**TVA:** nu se afișează niciodată.

### Rând total grup
```
[Total grup: N articole principale / M subcomponente]
```

## Extragere ofertant/proiectant

```python
def extract_entity_name(di_json_path: str, is_referinta: bool) -> str:
    """Caută în primele 5 pagini linia după marcajul relevant."""
    marker = "PROIECTANT" if is_referinta else "CONTRACTANT (OFERTANT)"
    # Returnează linia imediat următoare marcajului (strip, skip SRL standalone)
```

Fallback dacă nu găsește: `"Necunoscut"`.

## CLI

```bash
python3 gen_lista_oferta.py --client "CAV Maneciu"             # referinta + toate ofertele
python3 gen_lista_oferta.py --client "CAV Maneciu" --oferta 1  # oferta 1 doar
python3 gen_lista_oferta.py --client "CAV Maneciu" --referinta # referinta doar
```

## Output

```
output_AO/<client>/Lista_Referinta.docx
output_AO/<client>/Lista_Oferta_1.docx
output_AO/<client>/Lista_Oferta_2.docx
...
```

## Arhitectură internă

```
gen_lista_oferta.py          ← CLI entry point (argparse)
shared/
  lista_oferta_writer.py     ← generare DOCX (python-docx)
    - extract_entity_name()
    - build_docx_for_source()
    - _write_group_table()
    - _build_table_header()   ← 2-row merged header
    - _write_article_row()
```

Separare: CLI în root, logica DOCX în `shared/` (consistent cu `report_word.py`, `report_word_v2.py`).

## Dependențe

- `python-docx` (deja instalat)
- `shared/client_config.py` (ClientConfig, detect_clients)

## Fișiere modificate/create

- `gen_lista_oferta.py` — nou
- `shared/lista_oferta_writer.py` — nou
- `tests/shared/test_lista_oferta_writer.py` — nou (unit tests)
