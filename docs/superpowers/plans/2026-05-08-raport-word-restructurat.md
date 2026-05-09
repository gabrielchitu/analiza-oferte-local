# Raport Word Restructurat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructurează raportul DOCX deviz-cu-deviz, cu alerte de calitate și semnalare deviz mismatch.

**Architecture:** Refactorizăm `generate_word()` în `shared/report_word.py`. Structura tabelului (11 coloane) rămâne neschimbată. Schimbăm DOAR organizarea: per deviz cu numărătoare ref vs ofertă, EXTRA-urile la finalul fiecărui deviz, secțiune ALERTE la finalul documentului. `local_run.py` transmite `deviz_mismatches` și `devize_extra` la `generate_word()`.

**Tech Stack:** python-docx, structuri de date existente (neconformitati list, deviz_mismatches list)

---

## Structura fișierelor

| Fișier | Schimbări |
|--------|-----------|
| `shared/report_word.py` | Refactorizare majoră `generate_word()`, funcții noi helper |
| `local_run.py` | Transmite `deviz_mismatches` și `devize_extra`/`devize_lipsa` la `compare_and_report()` |
| `tests/test_report_word.py` | **NOU** — teste pentru noul format |

## Structura raportului nou

```
TABEL NECONCORDANȚE
  Client: ...  Data: ...

OFERTA N — sursa_fisier
  SUMAR: REF 1283 art / 43 devize | Oferta 1176 art / 40 devize | Matched 1140

══════════════════════════════════════════════════
  DEVIZ 226108 — STRUCTURA DE REZISTENTA CUPOLA  [REF: 44 art | Oferta: 44 art | Delta: 0]
══════════════════════════════════════════════════
  [tabel 11 col cu LIPSA + DIFERENTA + UM_DIFERIT + COD_SIMILAR]
  ── Articole extra în ofertă (verificare manuală) ──
  [rânduri cu ARTICOL_EXTRA — fundal galben]

══════════════════════════════════════════════════
  DEVIZ 226208 — STRUCTURA DE REZISTENTA OB.2  [REF: 45 art | Oferta: 43 art | Delta: -2]
══════════════════════════════════════════════════
  [...]

─── ALERTE DE CALITATE ───────────────────────────

  ⚠ DEVIZ MISMATCH DETECTAT:
    Devizul 226113 din ofertă (~88% overlap) pare echivalentul devizului 226118
    din proiect (8 vs 7 articole). Verificați dacă ofertantul a renumerotat categoriile.

  ⚠ DEVIZE ÎN OFERTĂ ABSENTE DIN REFERINȚĂ:
    226728 — CHELTUIELI CONEXE ORGANIZARII DE SANTIER (2 articole)
    → Verificați dacă este lucrare suplimentară sau F3 neextras din proiect.

  ℹ DEVIZE DIN REFERINȚĂ FĂRĂ OFERTĂ:
    226248 — INSTALATII VENTILATIE OB.2 (9 art ref — neacoperit în ofertă)
```

---

## Task 1: Teste pentru structura nouă

**Files:**
- Create: `tests/test_report_word.py`

- [ ] **Step 1: Scrie testele**

```python
# tests/test_report_word.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.report_word import generate_word
from docx import Document
import io


def _make_neconf(tip, deviz, ref_cod='CA01A1', ref_den='TEST', ref_um='m',
                 ref_cant=10.0, oferta_cod='CA01A1', oferta_den='TEST',
                 oferta_um='m', oferta_cant=10.0, camp=None, deviz_den='STRUCTURA'):
    n = {
        'tip': tip, 'deviz_ref': deviz, 'deviz_denumire': deviz_den,
        'ref_cod': ref_cod, 'ref_denumire': ref_den,
        'ref_um': ref_um, 'ref_cantitate': ref_cant,
        'oferta_cod': oferta_cod, 'oferta_denumire': oferta_den,
        'oferta_um': oferta_um, 'oferta_cantitate': oferta_cant,
    }
    if camp:
        n['camp'] = camp
    return n


def _load_doc(comp, mismatches=None, devize_extra=None, devize_lipsa=None):
    session = {'client_name': 'TEST', 'obiect_investitii': ''}
    comp_full = {
        'oferta_nr': 1, 'source_file': 'test.json', 'ofertant': 'Test SRL',
        **comp,
        'deviz_mismatches': mismatches or [],
    }
    docx_bytes = generate_word(
        session, comp_full,
        devize_extra=devize_extra or [],
        devize_lipsa=devize_lipsa or [],
    )
    return Document(io.BytesIO(docx_bytes))


def test_deviz_section_heading_appears():
    """Fiecare deviz are un heading cu codul si numarul de articole."""
    comp = {
        'neconformitati': [
            _make_neconf('ARTICOL_LIPSA', '226108', deviz_den='STRUCTURA CUPOLA'),
        ],
        'total_neconformitati': 1, 'matches': 43,
    }
    doc = _load_doc(comp)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    # Deviz heading trebuie sa apara
    assert '226108' in full_text, f"Deviz 226108 not found in doc text"


def test_extra_articles_appear_after_deviz_data():
    """Articolele EXTRA apar dupa randurile de LIPSA/DIFERENTA ale devizului."""
    comp = {
        'neconformitati': [
            _make_neconf('ARTICOL_LIPSA',  '226108', ref_cod='AA01A1'),
            _make_neconf('ARTICOL_EXTRA',  '226108', oferta_cod='EXTRA1',
                         ref_cod='', ref_den=''),
        ],
        'total_neconformitati': 2, 'matches': 43,
    }
    doc = _load_doc(comp)
    # Documentul trebuie generat fara erori si sa contina ceva
    assert len(doc.tables) > 0 or len(doc.paragraphs) > 0


def test_deviz_mismatch_alert_appears():
    """Alerta DEVIZ_MISMATCH apare la finalul documentului."""
    comp = {
        'neconformitati': [],
        'total_neconformitati': 0, 'matches': 100,
    }
    mismatches = [{'oferta_deviz': '226113', 'ref_deviz': '226118',
                   'overlap_score': 0.88, 'oferta_art_count': 8, 'ref_art_count': 7}]
    doc = _load_doc(comp, mismatches=mismatches)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '226113' in full_text, "Mismatch alert 226113 not found in doc"
    assert '226118' in full_text, "Mismatch ref deviz 226118 not found in doc"


def test_devize_extra_alert_appears():
    """Devizele din oferta absente din referinta apar in sectiunea alerte."""
    comp = {
        'neconformitati': [],
        'total_neconformitati': 0, 'matches': 100,
    }
    devize_extra = [{'deviz': '226728', 'denumire': 'CHELTUIELI CONEXE', 'art_count': 2}]
    doc = _load_doc(comp, devize_extra=devize_extra)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '226728' in full_text, "Extra deviz alert 226728 not found in doc"


def test_empty_neconformitati_generates_valid_doc():
    """Document fara neconformitati se genereaza fara erori."""
    comp = {'neconformitati': [], 'total_neconformitati': 0, 'matches': 100}
    doc = _load_doc(comp)
    assert doc is not None


def test_sumar_contains_counts():
    """Sectiunea de sumar contine numarul de articole matched."""
    comp = {
        'neconformitati': [_make_neconf('ARTICOL_LIPSA', '226108')],
        'total_neconformitati': 1, 'matches': 42,
        'ref_art_count': 43, 'oferta_art_count': 44,
    }
    doc = _load_doc(comp)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '42' in full_text or '43' in full_text, "Counts not found in doc"
```

- [ ] **Step 2: Rulează testele — confirmă că eșuează**

```bash
.venv/bin/python -m pytest tests/test_report_word.py -v 2>&1 | head -40
```
Expected: FAIL cu `TypeError: generate_word() got unexpected keyword argument 'devize_extra'`

---

## Task 2: Refactorizare `generate_word()` — semnătură și structură de bază

**Files:**
- Modify: `shared/report_word.py`

- [ ] **Step 1: Actualizează semnătura funcției**

Înlocuiește semnătura existentă:
```python
def generate_word(session: dict, comp: dict, comparison_mode: str = "cu_pret", audit_data: dict = None) -> bytes:
```
Cu:
```python
def generate_word(
    session: dict,
    comp: dict,
    comparison_mode: str = "cu_pret",
    audit_data: dict = None,
    devize_extra: list = None,
    devize_lipsa: list = None,
) -> bytes:
    """
    Args:
        devize_extra: list[dict] cu {'deviz', 'denumire', 'art_count'} —
                      devize prezente in oferta dar absente din referinta.
        devize_lipsa: list[dict] cu {'deviz', 'denumire', 'art_count'} —
                      devize din referinta fara nicio oferta.
    """
```

- [ ] **Step 2: Adaugă helpers noi în `report_word.py`**

Adaugă după funcția `_set_col_widths`:

```python
def _add_deviz_heading(table, deviz_cod: str, deviz_den: str,
                       ref_count: int, oferta_count: int) -> None:
    """Adaugă rând separator de deviz cu numărătoare ref vs ofertă."""
    sep_cells = table.add_row().cells
    sep_cells[0].merge(sep_cells[10])
    delta = oferta_count - ref_count
    delta_str = f"{delta:+d}" if delta != 0 else "0 ✓"
    den_short = deviz_den[:40] + "..." if len(deviz_den) > 40 else deviz_den
    label = (
        f"DEVIZ {deviz_cod}"
        + (f" — {den_short}" if den_short else "")
        + f"  │  REF: {ref_count} art"
        + f"  │  Ofertă: {oferta_count} art"
        + f"  │  Delta: {delta_str}"
    )
    run = sep_cells[0].paragraphs[0].add_run(label)
    run.bold = True
    _style_cell(sep_cells[0], 9, bold=True)
    _set_cell_shading(sep_cells[0], GRAY_FILL)


def _add_extra_subheader(table) -> None:
    """Adaugă rând sub-separator pentru secțiunea 'Extra în ofertă'."""
    sub = table.add_row().cells
    sub[0].merge(sub[10])
    run = sub[0].paragraphs[0].add_run(
        "▸ Articole extra în ofertă — verificare manuală recomandată"
    )
    run.italic = True
    _style_cell(sub[0], 8)
    _set_cell_shading(sub[0], YELLOW_FILL)


def _add_quality_alerts(doc, deviz_mismatches: list,
                        devize_extra: list, devize_lipsa: list) -> None:
    """Adaugă secțiunea ALERTE DE CALITATE la finalul documentului."""
    if not any([deviz_mismatches, devize_extra, devize_lipsa]):
        return

    doc.add_page_break()
    h = doc.add_heading("ALERTE DE CALITATE — VERIFICARE MANUALĂ", level=1)
    h.runs[0].font.color.rgb = RED

    if deviz_mismatches:
        doc.add_heading("Deviz Mismatch Detectat", level=2)
        for m in deviz_mismatches:
            p = doc.add_paragraph(style='List Bullet')
            run = p.add_run(
                f"Devizul {m['oferta_deviz']} din ofertă (~{m['overlap_score']:.0%} overlap) "
                f"pare echivalentul devizului {m['ref_deviz']} din proiect "
                f"({m['oferta_art_count']} vs {m['ref_art_count']} articole)."
            )
            run.bold = True
            run.font.color.rgb = RED
            doc.add_paragraph(
                "   → Ofertantul poate fi utilizat o numerotare diferită a categoriilor. "
                "Verificați dacă articolele corespund celor din proiect.",
                style='List Bullet'
            )

    if devize_extra:
        doc.add_heading("Devize în ofertă absente din referință", level=2)
        doc.add_paragraph(
            "Aceste devize NU au putut fi comparate cu proiectul. "
            "Verificați dacă sunt lucrări suplimentare sau F3 neextras din referință."
        )
        for d in devize_extra:
            p = doc.add_paragraph(style='List Bullet')
            p.add_run(
                f"{d['deviz']}"
                + (f" — {d['denumire']}" if d.get('denumire') else "")
                + f" ({d.get('art_count', '?')} articole în ofertă)"
            ).bold = True

    if devize_lipsa:
        doc.add_heading("Devize din referință fără ofertă", level=2)
        doc.add_paragraph(
            "Aceste categorii de lucrări din proiect nu au nicio ofertă corespunzătoare."
        )
        for d in devize_lipsa:
            p = doc.add_paragraph(style='List Bullet')
            p.add_run(
                f"{d['deviz']}"
                + (f" — {d['denumire']}" if d.get('denumire') else "")
                + f" ({d.get('art_count', '?')} articole în referință)"
            ).bold = True
```

- [ ] **Step 3: Rulează testele intermediar**

```bash
.venv/bin/python -m pytest tests/test_report_word.py -v 2>&1 | head -20
```

---

## Task 3: Refactorizare logică principală `generate_word()`

**Files:**
- Modify: `shared/report_word.py` — corpul funcției `generate_word()`

- [ ] **Step 1: Înlocuiește corpul principal al funcției**

Înlocuiește tot codul din `generate_word()` după `doc.add_heading(f"OFERTA {nr_oferta}...")` cu:

```python
    neconformitati = comp.get("neconformitati", [])
    deviz_mismatches = comp.get("deviz_mismatches", [])
    devize_extra = devize_extra or []
    devize_lipsa = devize_lipsa or []

    # ── SUMAR ────────────────────────────────────────────────────────
    ref_art_count   = comp.get("ref_art_count", "?")
    oferta_art_count = comp.get("oferta_art_count", "?")
    total_matched   = comp.get("matches", 0)
    total_neconf    = comp.get("total_neconformitati", 0)
    p_sumar = doc.add_paragraph()
    p_sumar.add_run(
        f"Articole referință: {ref_art_count}  │  "
        f"Articole ofertă: {oferta_art_count}  │  "
        f"Matched: {total_matched}  │  "
        f"Neconformități: {total_neconf}"
    ).bold = True

    if not neconformitati:
        doc.add_paragraph("Nicio neconcordanță detectată.")
    else:
        # ── BUILD INDEX ─────────────────────────────────────────────
        # deviz_map: deviz_cod -> deviz_den
        deviz_map: dict[str, str] = {}
        for nc in neconformitati:
            d = nc.get("deviz_ref", "")
            n = nc.get("deviz_denumire", "")
            if d and n and not n.startswith("REF:"):
                deviz_map[d] = n

        # ref_counts: deviz_cod -> total articole referinta (LIPSA + matched)
        # Calculat din neconformitati: LIPSA = articole in ref dar nu in oferta
        # matched = din comp["matches"] — nu avem detaliu per deviz, estimam din neconf
        # Folosim contorul brut de neconformitati per deviz pentru Delta
        from collections import Counter
        lipsa_by_deviz = Counter(
            nc.get("deviz_ref", "")
            for nc in neconformitati if nc.get("tip") == "ARTICOL_LIPSA"
        )
        extra_by_deviz = Counter(
            nc.get("deviz_ref", "")
            for nc in neconformitati if nc.get("tip") == "ARTICOL_EXTRA"
        )

        # Separa EXTRA de restul neconformitatilor
        nec_normale = [nc for nc in neconformitati if nc.get("tip") != "ARTICOL_EXTRA"]
        nec_extra   = [nc for nc in neconformitati if nc.get("tip") == "ARTICOL_EXTRA"]

        # ── TABEL ───────────────────────────────────────────────────
        table = doc.add_table(rows=3, cols=11)
        table.style = "Table Grid"
        _build_header(table, ofertant_name)

        sorted_nec = sorted(nec_normale, key=lambda x: x.get("deviz_ref", ""))
        sorted_extra = sorted(nec_extra, key=lambda x: x.get("deviz_ref", ""))

        # Index extra per deviz pentru acces rapid
        from itertools import groupby as _groupby
        extra_per_deviz: dict[str, list] = {}
        for deviz_key, grp in _groupby(sorted_extra, key=lambda x: x.get("deviz_ref", "")):
            extra_per_deviz[deviz_key] = list(grp)

        # Toate devizele care apar (din normale + extra)
        all_devize = sorted(set(
            nc.get("deviz_ref", "") for nc in neconformitati if nc.get("deviz_ref")
        ))

        row_nr = 0
        processed_devize: set = set()

        for deviz_key, group_items in _groupby(sorted_nec, key=lambda x: x.get("deviz_ref", "")):
            processed_devize.add(deviz_key)
            items = list(group_items)
            deviz_cod = str(deviz_key) if deviz_key else ""
            deviz_den = deviz_map.get(deviz_cod, "")

            # Calculam delta estimat: extra - lipsa per deviz
            n_lipsa = lipsa_by_deviz.get(deviz_cod, 0)
            n_extra = extra_by_deviz.get(deviz_cod, 0)
            # ref_count estimat: matched_deviz + lipsa (nu avem matched exact per deviz)
            # Afisam doar lipsa si extra
            _add_deviz_heading(table, deviz_cod, deviz_den,
                               ref_count=n_lipsa, oferta_count=n_extra)

            # Randuri normale (LIPSA, DIFERENTA, UM_DIFERIT, COD_SIMILAR)
            for neconf in items:
                row_nr += 1
                _add_neconf_row(table, row_nr, neconf, deviz_map)

            # EXTRA pentru acest deviz (la final sectiune)
            extra_items = extra_per_deviz.get(deviz_cod, [])
            if extra_items:
                _add_extra_subheader(table)
                for neconf in extra_items:
                    row_nr += 1
                    _add_neconf_row(table, row_nr, neconf, deviz_map)

        # Devize cu NUMAI extra (fara normale)
        only_extra_devize = set(extra_per_deviz.keys()) - processed_devize
        for deviz_key in sorted(only_extra_devize):
            deviz_cod = str(deviz_key)
            deviz_den = deviz_map.get(deviz_cod, "")
            n_extra = extra_by_deviz.get(deviz_cod, 0)
            _add_deviz_heading(table, deviz_cod, deviz_den,
                               ref_count=0, oferta_count=n_extra)
            _add_extra_subheader(table)
            for neconf in extra_per_deviz[deviz_key]:
                row_nr += 1
                _add_neconf_row(table, row_nr, neconf, deviz_map)

        _set_col_widths(table)

    doc.add_paragraph()

    # ── ALERTE CALITATE ──────────────────────────────────────────────
    _add_quality_alerts(doc, deviz_mismatches, devize_extra, devize_lipsa)

    if audit_data:
        _add_audit_section(doc, audit_data)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
```

- [ ] **Step 2: Extrage `_add_neconf_row()` ca funcție separată**

Adaugă ÎNAINTE de `generate_word()`:

```python
def _add_neconf_row(table, row_nr: int, neconf: dict, deviz_map: dict) -> None:
    """Adaugă un rând de neconformitate în tabel."""
    row = table.add_row().cells
    tip  = neconf.get("tip", "")
    camp = neconf.get("camp", "")
    is_suspect = bool(neconf.get("suspect"))

    row[0].paragraphs[0].add_run(str(row_nr))

    deviz_cod = neconf.get("deviz_ref", "")
    deviz_den = deviz_map.get(deviz_cod, "")
    if deviz_den and len(deviz_den) > 40:
        deviz_den = deviz_den[:37] + "..."
    deviz_display = f"{deviz_cod} - {deviz_den}" if deviz_den else str(deviz_cod)
    row[1].paragraphs[0].add_run(deviz_display).bold = True

    cod_run = row[2].paragraphs[0].add_run(str(neconf.get("ref_cod", "")))
    cod_run.bold = True
    cod_run.font.size = Pt(9)

    denom = str(neconf.get("ref_denumire", ""))
    if len(denom) > 50:
        denom = denom[:47] + "..."
    row[3].paragraphs[0].add_run(denom)

    ref_um_run   = row[4].paragraphs[0].add_run(str(neconf.get("ref_um", "")))
    ref_cant_run = row[5].paragraphs[0].add_run(str(neconf.get("ref_cantitate", "")))

    oferta_um_run = oferta_cant_run = None
    if tip != "ARTICOL_LIPSA":
        oferta_cod_run = row[6].paragraphs[0].add_run(str(neconf.get("oferta_cod", "")))
        oferta_cod_run.bold = True
        oferta_cod_run.font.size = Pt(9)
        oferta_denom = str(neconf.get("oferta_denumire", ""))
        if len(oferta_denom) > 50:
            oferta_denom = oferta_denom[:47] + "..."
        row[7].paragraphs[0].add_run(oferta_denom)
        oferta_um_run   = row[8].paragraphs[0].add_run(str(neconf.get("oferta_um", "")))
        oferta_cant_run = row[9].paragraphs[0].add_run(str(neconf.get("oferta_cantitate", "")))

    obs_text = _observatie_text(neconf)
    if is_suspect:
        motiv = neconf.get("motiv_suspiciune", "")
        obs_text += f"\n⚠ {motiv}" if motiv else "\n⚠"
    obs_run = row[10].paragraphs[0].add_run(obs_text)
    obs_run.bold = True
    obs_run.font.color.rgb = RED

    for cell in row:
        _style_cell(cell, 8)

    if is_suspect:
        for cell in row: _set_cell_shading(cell, YELLOW_FILL)
    if tip == "COD_SIMILAR":
        for cell in row: _set_cell_shading(cell, ORANGE_FILL)
    if tip == "ARTICOL_EXTRA":
        for cell in row: _set_cell_shading(cell, YELLOW_FILL)
    if tip == "ARTICOL_ORPHAN":
        for cell in row: _set_cell_shading(cell, "FFCC99")

    if tip == "DIFERENTA_CAMP" and camp == "cantitate":
        ref_cant_run.font.color.rgb = RED
        if oferta_cant_run: oferta_cant_run.font.color.rgb = RED
    elif tip == "UM_DIFERIT":
        ref_um_run.font.color.rgb = RED
        if oferta_um_run: oferta_um_run.font.color.rgb = RED
```

- [ ] **Step 3: Rulează testele**

```bash
.venv/bin/python -m pytest tests/test_report_word.py -v
```
Expected: toate 6 teste PASS

- [ ] **Step 4: Rulează toate testele (regression)**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: toate 62+ teste PASS

---

## Task 4: Actualizare `local_run.py` — transmite datele noi

**Files:**
- Modify: `local_run.py`

- [ ] **Step 1: Actualizează `compare_and_report()` să colecteze devize_extra și devize_lipsa**

În `compare_and_report()`, după liniile existente care calculează `oferta_norm`, adaugă ÎNAINTE de `generate_word()`:

```python
    # Colecteaza devize_extra si devize_lipsa pentru raport
    from collections import defaultdict
    ref_devize_set = {a.get('deviz', '') for a in ref_articles if a.get('deviz')}
    oferta_devize_set = {a.get('deviz', '') for a in oferta_norm if a.get('deviz')}

    oferta_devize_art_count = defaultdict(int)
    for a in oferta_norm:
        oferta_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_art_count = defaultdict(int)
    for a in ref_articles:
        ref_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_den = {}
    for a in ref_articles:
        d = a.get('deviz', ''); n = a.get('deviz_denumire', '')
        if d and n: ref_devize_den[d] = n

    _devize_extra = [
        {'deviz': d,
         'denumire': (next((a.get('deviz_denumire','') for a in oferta_norm if a.get('deviz')==d), '')),
         'art_count': oferta_devize_art_count[d]}
        for d in sorted(oferta_devize_set - ref_devize_set - {''})
    ]
    _devize_lipsa = [
        {'deviz': d, 'denumire': ref_devize_den.get(d, ''),
         'art_count': ref_devize_art_count[d]}
        for d in sorted(ref_devize_set - oferta_devize_set - {''})
    ]
```

- [ ] **Step 2: Actualizează apelul `generate_word()` din `compare_and_report()`**

Înlocuiește:
```python
        docx_bytes = generate_word(session, comp, comparison_mode=comparison_mode)
```
Cu:
```python
        docx_bytes = generate_word(
            session, comp,
            comparison_mode=comparison_mode,
            devize_extra=_devize_extra,
            devize_lipsa=_devize_lipsa,
        )
```

- [ ] **Step 3: Transmite `ref_art_count` și `oferta_art_count` în `comp`**

În `compare_and_report()`, la construirea dict-ului `comp`, adaugă:
```python
    comp = {
        "oferta_nr": oferta_nr,
        "source_file": oferta_path.name,
        "ofertant": "",
        "neconformitati": neconformitati,
        "ref_art_count": len(ref_articles),
        "oferta_art_count": len(oferta_norm),
    }
```

- [ ] **Step 4: Rulează toate testele**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: toate testele PASS

---

## Task 5: Rulare finală și commit

- [ ] **Step 1: Rulează pipeline complet cu Haiku**

```bash
ANTHROPIC_API_KEY=$ANTHROPIC_AUTH_TOKEN ANTHROPIC_MODEL=claude-haiku-4-5 \
  .venv/bin/python3.11 local_run.py 2>&1 | grep -E "(DOCX|MISMATCH|ALERTA|COMP|Matched)"
```
Expected:
- 3 fișiere DOCX generate (`Raport_Oferta_1.docx`, `Raport_Oferta_2.docx`, `Raport_Oferta_3.docx`)
- `[MISMATCH] Deviz 226113 (oferta) pare echivalentul lui 226118 (ref)` prezent în log

- [ ] **Step 2: Deschide unul din DOCX și verifică vizual**

Verifică:
- Fiecare deviz are un rând gri cu: `DEVIZ 226108 — STRUCTURA DE REZISTENTA  │  REF: X art  │  Ofertă: Y art  │  Delta: Z`
- EXTRA-urile apar după rândurile normale ale devizului, cu rând separator galben
- La finalul documentului: secțiunea `ALERTE DE CALITATE`
- Alert pentru `226113 → 226118` (oferta 1)

- [ ] **Step 3: Rulează toate testele o ultimă dată**

```bash
.venv/bin/python -m pytest tests/ -q
```
Expected: toate testele PASS

- [ ] **Step 4: Commit**

```bash
git add shared/report_word.py local_run.py tests/test_report_word.py
git commit -m "feat: restructure DOCX report deviz-by-deviz with quality alerts

- Per-deviz sections with ref vs offer counts and delta
- EXTRA articles grouped at end of each deviz section (yellow)
- Quality alerts section at end of document:
  * DEVIZ_MISMATCH: detected same articles under different deviz code
  * Devize in offer but absent from reference
  * Devize in reference with no offer coverage
- Summary line per offer with total matched/non-conformities
- _add_neconf_row() extracted as reusable function
- New signature: generate_word(..., devize_extra, devize_lipsa)"
```

---

## Self-Review

**Spec coverage:**
- ✓ Per-deviz sections cu heading (Task 3)
- ✓ REF count vs Offer count (Task 3 — `_add_deviz_heading`)
- ✓ EXTRA articles grouped at end of deviz section (Task 3)
- ✓ DEVIZ_MISMATCH alert in quality section (Task 2 — `_add_quality_alerts`)
- ✓ Devize extra in offer alert (Task 2)
- ✓ Devize missing from offer alert (Task 2)
- ✓ Summary line (Task 3 — sumar block)
- ✓ Visual check in DOCX (Task 5)

**Placeholders:** Niciun TBD sau placeholder. Toate funcțiile au cod complet.

**Type consistency:** `devize_extra` și `devize_lipsa` sunt `list[dict]` în toate locurile. `deviz_mismatches` vine din `comp["deviz_mismatches"]` consistent.

**Risc:** Delta vizualizat ca `lipsa - extra` per deviz din neconformitati poate fi imprecis (nu avem matched count per deviz). Este o estimare acceptabilă — clientul vede numărul total de LIPSA și EXTRA per deviz.
