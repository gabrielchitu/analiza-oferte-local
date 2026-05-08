import io
from datetime import date
from itertools import groupby
from docx import Document
from docx.shared import Pt, RGBColor, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import nsdecls
from docx.oxml import parse_xml
from docx.enum.section import WD_ORIENT

RED = RGBColor(0xCC, 0x00, 0x00)
BLACK = RGBColor(0x00, 0x00, 0x00)
YELLOW_FILL = "FFFF99"
ORANGE_FILL = "FFB347"
GRAY_FILL = "D9D9D9"

# Column widths in cm (total ~24cm for landscape A4 with 2cm margins)
COL_WIDTHS_CM = [0.7, 3.0, 1.5, 3.5, 0.8, 1.2, 1.5, 3.5, 0.8, 1.2, 6.3]


def _observatie_text(neconf: dict) -> str:
    """Return human-readable Romanian observation text for a nonconformity."""
    tip = neconf.get("tip", "")
    camp = neconf.get("camp", "")
    CAMP_LABELS = {
        "cantitate": "Cantitate",
        "pret_material": "Preț material",
        "pret_manopera": "Preț manoperă",
        "pret_utilaj": "Preț utilaj",
        "pret_transport": "Preț transport",
        "val_material": "Valoare material",
        "val_manopera": "Valoare manoperă",
        "val_utilaj": "Valoare utilaj",
        "val_transport": "Valoare transport",
    }
    if tip == "ARTICOL_LIPSA":
        return "Articol lipsă din ofertă"
    if tip == "ARTICOL_EXTRA":
        return "Articol suplimentar în ofertă (nu există în referință)"
    if tip == "UM_DIFERIT":
        return (f"Unitate de măsură diferită: referință {neconf.get('ref_um', '')},"
                f" ofertat {neconf.get('oferta_um', '')}")
    if tip == "DIFERENTA_CAMP":
        label = CAMP_LABELS.get(camp, camp)
        ref_val = neconf.get("ref", neconf.get(f"ref_{camp}", ""))
        oferta_val = neconf.get("oferta", neconf.get(f"oferta_{camp}", ""))
        um = neconf.get("ref_um", "") if camp == "cantitate" else "lei"
        return f"{label} diferită: referință {ref_val} {um}, ofertat {oferta_val} {um}".strip()
    if tip == "EROARE_ARITMETICA":
        return (f"Eroare aritmetică: {camp} declarat {neconf.get('declarat', '')} lei"
                f" ≠ calculat {neconf.get('calculat', '')} lei")
    if tip == "COD_SIMILAR":
        ref_cod = neconf.get("ref_cod", "")
        oferta_cod = neconf.get("oferta_cod", "")
        motiv = neconf.get("motiv_similaritate", "")
        return (f"Cod similar — posibilă eroare OCR sau variație: "
                f"referință '{ref_cod}', ofertat '{oferta_cod}'. "
                f"{motiv}. Necesită verificare manuală.")
    if tip == "ARTICOL_ORPHAN":
        ref_deviz = neconf.get("deviz_ref", "")
        cod = neconf.get("ref_cod", "")
        motiv = neconf.get("motiv", "")
        return f"ORPHAN: Cod '{cod}' identic, dar categorii DIFERITE. {motiv}. VERIFICARE MANUALA NECESARA!"
    return tip


def _set_cell_shading(cell, fill_hex: str):
    """Set background color of a cell (e.g. 'FFFF99' for yellow)."""
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    shd = parse_xml(f'<w:shd {nsdecls("w")} w:fill="{fill_hex}" w:val="clear"/>')
    tcPr.append(shd)


def _style_cell(cell, size_pt: float, bold: bool = False,
                color: RGBColor = None, center: bool = False):
    """Apply font size, bold, color, and alignment to all runs in a cell."""
    for para in cell.paragraphs:
        if center:
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in para.runs:
            run.font.size = Pt(size_pt)
            run.bold = bold
            if color:
                run.font.color.rgb = color


def _set_landscape(doc):
    """Set page orientation to landscape A4 with 2cm margins."""
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width = Cm(29.7)
    section.page_height = Cm(21.0)
    for attr in ("left_margin", "right_margin", "top_margin", "bottom_margin"):
        setattr(section, attr, Cm(2.0))


def _set_col_widths(table):
    """Apply fixed column widths to all cells in each column."""
    for i, w in enumerate(COL_WIDTHS_CM):
        for cell in table.columns[i].cells:
            cell.width = Cm(w)


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
        + f"  │  LIPSA: {ref_count}"
        + f"  │  EXTRA: {oferta_count}"
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
    if h.runs:
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


def _build_header(table, ofertant_name: str):
    """Build 3-row merged header for the 11-column table."""
    r0 = table.rows[0].cells
    r1 = table.rows[1].cells
    r2 = table.rows[2].cells

    # Vertical merges (rowspan 3): Nr (col 0), Deviz (col 1), Observatii (col 10)
    r0[0].merge(r2[0])
    r0[1].merge(r2[1])
    r0[10].merge(r2[10])

    # Row 0: horizontal group merges
    r0[2].merge(r0[5])   # CERINTA spans cols 2-5
    r0[6].merge(r0[9])   # CE A OFERTAT spans cols 6-9

    # Row 1: ofertant sub-header under CE A OFERTAT (cols 6-9)
    r1[6].merge(r1[9])

    # Set texts via add_run on fresh paragraphs
    r0[0].paragraphs[0].add_run("Nr.\ncrt.")
    r0[1].paragraphs[0].add_run("Categoria\nde lucrări")
    r0[2].paragraphs[0].add_run("CERINȚĂ")
    r0[6].paragraphs[0].add_run("CE A OFERTAT")
    r0[10].paragraphs[0].add_run("OBSERVAȚII")
    r1[6].paragraphs[0].add_run(ofertant_name)

    for i, txt in enumerate(["Cod", "Denumire", "UM", "Cant."], start=2):
        r2[i].paragraphs[0].add_run(txt)
    for i, txt in enumerate(["Cod", "Denumire", "UM", "Cant."], start=6):
        r2[i].paragraphs[0].add_run(txt)

    # Style header cells — only cells with actual content (not merged continuations)
    for cell in [r0[0], r0[1], r0[2], r0[6], r0[10]]:
        _style_cell(cell, 9, bold=True, center=True)
    _style_cell(r1[6], 9, bold=True, center=True)
    for i in range(2, 10):
        _style_cell(r2[i], 9, bold=True, center=True)


def _add_audit_section(doc, audit_data: dict) -> None:
    """Adaugă secțiunea de audit la finalul documentului Word."""
    from shared.f3_auditor import _is_false_positive
    audit_status = audit_data.get("audit_status", "pending")
    all_disc = audit_data.get("discrepante", [])
    # Filtrăm false pozitive (manoperă $NNNN, totale T2-T9 etc.) — doar discrepanțe reale
    discrepante = [d for d in all_disc if not _is_false_positive(d.get("cod", ""))]

    doc.add_page_break()
    doc.add_heading("Audit extracție articole F3", level=1)

    if audit_status == "pending":
        doc.add_paragraph(
            "Auditul LLM este în curs. Regenerați raportul după finalizare."
        )
        return

    if audit_status == "ok":
        p = doc.add_paragraph("Auditorul AI nu a detectat nicio discrepanta fata de parserul regex.")
        p.runs[0].font.color.rgb = RGBColor(0, 128, 0)
        return

    # discrepante_gasite
    doc.add_paragraph(
        f"Auditorul AI a detectat {len(discrepante)} cod(uri) reale prezente in documentul OCR "
        f"dar neextrase de parser (false pozitive filtrate: {len(all_disc) - len(discrepante)}). "
        f"Verificati manual."
    )
    table = doc.add_table(rows=1, cols=3)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    hdr[0].text = 'Cod'
    hdr[1].text = 'Obiect probabil'
    hdr[2].text = 'Context OCR'
    for d in discrepante:
        row = table.add_row().cells
        row[0].text = d.get('cod', '')
        row[1].text = d.get('deviz_probabil', '')
        ctx = d.get('context', '')
        row[2].text = (ctx[:200] + '...') if len(ctx) > 200 else ctx


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


def generate_word(
    session: dict,
    comp: dict,
    comparison_mode: str = "cu_pret",
    audit_data: dict = None,
    devize_extra: list = None,
    devize_lipsa: list = None,
) -> bytes:
    """Generate a Word document for a single comparatie (oferta).

    Args:
        session: session dict with client_name, obiect_investitii
        comp: comparatie dict with neconformitati, oferta_nr, source_file, deviz_mismatches, etc.
        comparison_mode: "cu_pret" or "fara_pret"
        devize_extra: list[dict] cu {'deviz', 'denumire', 'art_count'} —
                      devize prezente in oferta dar absente din referinta.
        devize_lipsa: list[dict] cu {'deviz', 'denumire', 'art_count'} —
                      devize din referinta fara nicio oferta.

    Returns:
        bytes: DOCX document content
    """
    doc = Document()
    _set_landscape(doc)

    # Document header
    title = doc.add_heading("TABEL NECONCORDANȚE", level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    doc.add_paragraph(f"Client: {session.get('client_name', '')}")
    obiect = session.get("obiect_investitii", "")
    if obiect:
        doc.add_paragraph(f"Obiectul investiției: {obiect}")
    doc.add_paragraph(f"Data: {date.today()}")

    nr_oferta = comp.get("oferta_nr", "?")
    source = comp.get("source_file", "")
    ofertant_name = comp.get("ofertant") or source
    doc.add_heading(f"OFERTA {nr_oferta} — {ofertant_name}", level=1)

    neconformitati = comp.get("neconformitati", [])
    deviz_mismatches_list = comp.get("deviz_mismatches", [])
    devize_extra = devize_extra or []
    devize_lipsa = devize_lipsa or []

    # ── SUMAR ────────────────────────────────────────────────────────
    ref_art_count    = comp.get("ref_art_count", "?")
    oferta_art_count = comp.get("oferta_art_count", "?")
    total_matched    = comp.get("matches", 0)
    total_neconf     = comp.get("total_neconformitati", 0)
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
        from collections import Counter
        from itertools import groupby as _groupby

        # deviz_map: deviz_cod -> deviz_den
        deviz_map: dict = {}
        for nc in neconformitati:
            d = nc.get("deviz_ref", "")
            n = nc.get("deviz_denumire", "")
            if d and n and not n.startswith("REF:"):
                deviz_map[d] = n

        lipsa_by_deviz = Counter(
            nc.get("deviz_ref", "")
            for nc in neconformitati if nc.get("tip") == "ARTICOL_LIPSA"
        )
        extra_by_deviz = Counter(
            nc.get("deviz_ref", "")
            for nc in neconformitati if nc.get("tip") == "ARTICOL_EXTRA"
        )

        nec_normale = [nc for nc in neconformitati if nc.get("tip") != "ARTICOL_EXTRA"]
        nec_extra   = [nc for nc in neconformitati if nc.get("tip") == "ARTICOL_EXTRA"]

        sorted_nec   = sorted(nec_normale, key=lambda x: x.get("deviz_ref", ""))
        sorted_extra = sorted(nec_extra,   key=lambda x: x.get("deviz_ref", ""))

        extra_per_deviz: dict = {}
        for deviz_key, grp in _groupby(sorted_extra, key=lambda x: x.get("deviz_ref", "")):
            extra_per_deviz[deviz_key] = list(grp)

        # Collect all deviz keys in order (normale + only-extra)
        deviz_keys_normale = list(dict.fromkeys(
            nc.get("deviz_ref", "") for nc in sorted_nec
        ))
        only_extra_devize = sorted(set(extra_per_deviz.keys()) - set(deviz_keys_normale))
        all_deviz_keys = deviz_keys_normale + only_extra_devize

        # Paragraph listing deviz codes (visible in doc.paragraphs for navigation)
        if all_deviz_keys:
            p_devize = doc.add_paragraph()
            p_devize.add_run("Devize: " + ", ".join(str(k) for k in all_deviz_keys)).bold = True

        table = doc.add_table(rows=3, cols=11)
        table.style = "Table Grid"
        _build_header(table, ofertant_name)

        row_nr = 0
        processed_devize: set = set()

        for deviz_key, group_items in _groupby(sorted_nec, key=lambda x: x.get("deviz_ref", "")):
            processed_devize.add(deviz_key)
            items = list(group_items)
            deviz_cod = str(deviz_key) if deviz_key else ""
            deviz_den = deviz_map.get(deviz_cod, "")
            n_lipsa = lipsa_by_deviz.get(deviz_cod, 0)
            n_extra = extra_by_deviz.get(deviz_cod, 0)
            _add_deviz_heading(table, deviz_cod, deviz_den,
                               ref_count=n_lipsa, oferta_count=n_extra)
            for neconf in items:
                row_nr += 1
                _add_neconf_row(table, row_nr, neconf, deviz_map)
            extra_items = extra_per_deviz.get(deviz_cod, [])
            if extra_items:
                _add_extra_subheader(table)
                for neconf in extra_items:
                    row_nr += 1
                    _add_neconf_row(table, row_nr, neconf, deviz_map)

        for deviz_key in only_extra_devize:
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
    _add_quality_alerts(doc, deviz_mismatches_list, devize_extra, devize_lipsa)

    if audit_data:
        _add_audit_section(doc, audit_data)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
