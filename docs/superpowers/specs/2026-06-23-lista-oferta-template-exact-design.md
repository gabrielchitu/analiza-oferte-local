# Design: Lista Oferta — Format Template Exact

**Data:** 2026-06-23  
**Scope:** Fix `lista_oferta_writer.py` + `write_docx` în `sursa_incarcare_writer.py` să producă output identic cu `docs/Template_exact.docx`.

---

## Context

Clientul a livrat `docs/Template_exact.docx` ca referință exactă de format. Outputul ambelor pipeline-uri trebuie să fie identic cu acesta.

**Pipeline 1 — gen_lista_oferta:** citește `holistic_oferta_N.json` → `lista_oferta_writer.py` → DOCX  
**Pipeline 2 — gen_sursa_incarcare:** citește `sursa_extracted_{stem}.json` → `sursa_incarcare_writer.py` → DOCX  

Ambele produc același format vizual (11 coloane, fara borduri, header pipe-separat). Codul existent în `lista_oferta_writer.py` este deja aproape corect — necesită 5 fix-uri punctuale.

---

## Structura Template (valori exacte din XML)

### Pagina
- A4 Portrait, margini 1.5cm all sides

### Header document (4 paragrafe)
```
Lista articole — Oferta N    [14pt, bold]
Client: {client_name}         [11pt, bold]
Ofertant: {entity_name}       [11pt, bold]
Generat: YYYY-MM-DD           [9pt, bold]
```

### Per grup: Paragraf + Tabel

**Paragraf header grup** (9pt, bold, space_before=6pt):
```
{obiectivul} | {obiectul} | {categoria}
```
Fara label ("Obiectivul:", "Obiectul:" etc.). Un singur `|` ca separator. Dacă `obiectivul` e numeric pur, se foloseste `deviz_denumire` ca în codul existent.

**Tabel** (11 coloane, `tblLayout=fixed`, `tblStyle=Table Grid`, **fara borduri**):

#### Lățimi coloane exacte (twips)
| Col | Label | Twips |
|-----|-------|-------|
| 0 | Nr. | 397 |
| 1 | Nr.crt | 510 |
| 2 | Cod | 1020 |
| 3 | Cod principal | 1020 |
| 4 | Denumire | 3175 |
| 5 | UM | 567 |
| 6 | Cantitate | 1020 |
| 7 | Material | 624 |
| 8 | Manoperă | 624 |
| 9 | Utilaje | 624 |
| 10 | Transport | 624 |
| **Total** | | **10205** |

#### Row 0 (header — 8 celule fizice)
- C0–C6: vMerge=restart, shd=D9D9D9, noWrap (exc C4), text = label coloana
- C7: gridSpan=4, shd=D9D9D9, noWrap, text="Pret unitar (lei/UM)"

#### Row 1 (subheader — 11 celule)
- C0–C6: vMerge=continuation, fara shading, goale
- C7–C10: shd=D9D9D9, noWrap, text = Material/Manoperă/Utilaje/Transport

#### Rows de date
- C0: center (Nr. local secvential, include sub-items)
- C1: right (nr_ordine / nr_crt din sursa)
- C2: left (Cod)
- C3: left (Cod principal — gol pt main, parent.cod pt sub-items)
- C4: left (Denumire)
- C5: center (UM)
- C6: right (Cantitate)
- C7–C10: right (preturi breakdown sau gol)
- Sub-items: font 7pt, gri (RGBColor 0x44,0x44,0x44)

#### Last row (Total grup)
- gridSpan=11, w=10205, shd=F2F2F2
- Text: `Total grup: {N} articole principale` sau `Total grup: {N} articole principale / {M} subcomponente`
- 8pt, bold

#### Fara borduri
`tblPr` include `tblBorders` cu toate laturile = `none`:
```xml
<w:tblBorders>
  <w:top w:val="none" w:sz="0" w:color="auto"/>
  <w:left w:val="none" w:sz="0" w:color="auto"/>
  <w:bottom w:val="none" w:sz="0" w:color="auto"/>
  <w:right w:val="none" w:sz="0" w:color="auto"/>
  <w:insideH w:val="none" w:sz="0" w:color="auto"/>
  <w:insideV w:val="none" w:sz="0" w:color="auto"/>
</w:tblBorders>
```

---

## Fișiere modificate

### 1. `shared/lista_oferta_writer.py` — 5 fix-uri punctuale

| # | Unde | Ce se schimbă |
|---|------|---------------|
| F1 | `COL_WIDTHS_CM` | Înlocuit cu `_COL_WIDTHS_TWIPS = [397,510,1020,1020,3175,567,1020,624,624,624,624]`; lățimi setate via XML `tcW` în twips (nu `Cm`) |
| F2 | `_write_group_section` → paragraf header | Format nou: `{obiectivul} \| {obiectul} \| {categoria}` (fara label); fallback la `deviz_denumire` păstrat |
| F3 | `build_docx_for_source` → header doc | Toate 4 linii → `bold=True` |
| F4 | `build_docx_for_source` → margini | `top_margin=Cm(1.5)`, `bottom_margin=Cm(1.5)` |
| F5 | `_write_group_section` → tabel | Adaugat `_suppress_table_borders(tbl)` după `add_table()` |

Functie nouă în writer:
```python
def _suppress_table_borders(tbl) -> None:
    # Inject tblBorders with all sides = none into tblPr
```

Functie actualizată `_build_table_header`:
```python
# Set cell widths via tcW in twips (not Cm)
```

### 2. `shared/sursa_incarcare_writer.py` — `write_docx` v2

Adaugat `write_docx_v2(devize, output_path, metadata=None)` care produce același format vizual ca template, adaptând modelul de date `capitole > articole > sub_items`:
- Flatten articole din toate capitolele (capitolele NU apar ca rânduri)
- `nr_local` = secvential per grup (main + sub-items)
- `nr_crt` = art.get('nr_crt') din extras
- `cod_principal` = `''` pt main, `parent.cod` pt sub-items
- Preturi: din `breakdown.{material,manopera,utilaj,transport}.pret` când există
- Duplicate `_COL_WIDTHS_TWIPS` și `_suppress_table_borders` local în `sursa_incarcare_writer.py` (nu shared module — evitam dependenta circulara)

`metadata = {offer_num, client, ofertant, date}` — pasat din `gen_sursa_incarcare.py`.

### 3. `gen_sursa_incarcare.py`
- Adaugat `--ofertant` CLI arg (optional, default `''`)
- `_run_pipeline` apeleaza `write_docx_v2` in loc de `write_docx`
- `write_docx` v1 ramas nemodificat

---

## Ce NU se schimbă
- Logica de extracție (`f3_price_extractor.py`, `lista_verifier.py`)
- `write_xlsx`, `write_pdf_native` în `sursa_incarcare_writer.py`
- `gen_lista_oferta.py` CLI interface
- Toate testele existente (nu testează format DOCX visual)

---

## Criterii de acceptare
1. `python3 gen_lista_oferta.py --client "CAV Maneciu" --oferta 1` → DOCX fara borduri, header pipe-separat, lățimi identice cu template
2. `python3 gen_sursa_incarcare.py --client "CAV Maneciu" --json di_oferta_1` → același format vizual
3. Deschis în Word/LibreOffice: tabelele arata identic cu `Template_exact.docx`
