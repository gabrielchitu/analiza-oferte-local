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


def generate_word(session: dict, comp: dict, comparison_mode: str = "cu_pret", audit_data: dict = None) -> bytes:
    """Generate a Word document for a single comparatie (oferta).

    Args:
        session: session dict with client_name, obiect_investitii
        comp: single comparatie dict with neconformitati, oferta_nr, source_file, etc.
        comparison_mode: "cu_pret" (default) or "fara_pret" — affects which observations
            appear (price observations only produced by AgentComparator in cu_pret mode).
            Both modes produce the same 11-column table structure.

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
    doc.add_paragraph(f"Total neconcordanțe: {comp.get('total_neconformitati', 0)}")

    neconformitati = comp.get("neconformitati", [])
    if not neconformitati:
        doc.add_paragraph("Nicio neconcordanță detectată.")
    else:
        # 3 header rows
        table = doc.add_table(rows=3, cols=11)
        table.style = "Table Grid"
        _build_header(table, ofertant_name)

        # Group by deviz_denumire (categoria de lucrari) for section separators
        sorted_nec = sorted(neconformitati, key=lambda x: x.get("deviz_denumire", ""))
        row_nr = 0

        for deviz_key, group_items in groupby(sorted_nec, key=lambda x: x.get("deviz_denumire", "")):
            # Separator row for this categoria de lucrari
            sep_cells = table.add_row().cells
            sep_cells[0].merge(sep_cells[10])
            label = f"Categoria de lucrări: {deviz_key}" if deviz_key else "Necategorizat"
            sep_run = sep_cells[0].paragraphs[0].add_run(label)
            sep_run.bold = True
            _style_cell(sep_cells[0], 9, bold=True)
            _set_cell_shading(sep_cells[0], GRAY_FILL)

            for neconf in group_items:
                row_nr += 1
                row = table.add_row().cells

                is_suspect = bool(neconf.get("suspect"))
                tip = neconf.get("tip", "")
                camp = neconf.get("camp", "")

                # Reference columns (always present)
                row[0].paragraphs[0].add_run(str(row_nr))
                row[1].paragraphs[0].add_run(str(neconf.get("deviz_denumire", "")))
                row[2].paragraphs[0].add_run(str(neconf.get("ref_cod", "")))
                row[3].paragraphs[0].add_run(str(neconf.get("ref_denumire", "")))
                ref_um_run = row[4].paragraphs[0].add_run(str(neconf.get("ref_um", "")))
                ref_cant_run = row[5].paragraphs[0].add_run(str(neconf.get("ref_cantitate", "")))

                # Offer columns (empty for ARTICOL_LIPSA)
                oferta_um_run = oferta_cant_run = None
                if tip != "ARTICOL_LIPSA":
                    row[6].paragraphs[0].add_run(str(neconf.get("oferta_cod", "")))
                    row[7].paragraphs[0].add_run(str(neconf.get("oferta_denumire", "")))
                    oferta_um_run = row[8].paragraphs[0].add_run(str(neconf.get("oferta_um", "")))
                    oferta_cant_run = row[9].paragraphs[0].add_run(str(neconf.get("oferta_cantitate", "")))

                # Observation column: human-readable text, red bold
                obs_text = _observatie_text(neconf)
                if is_suspect:
                    motiv = neconf.get("motiv_suspiciune", "")
                    obs_text += f"\n⚠️ {motiv}" if motiv else "\n⚠️"

                obs_run = row[10].paragraphs[0].add_run(obs_text)
                obs_run.bold = True
                obs_run.font.color.rgb = RED

                # Style all data cells: 8pt
                for cell in row:
                    _style_cell(cell, 8)

                # Row-level background colors
                if is_suspect:
                    for cell in row:
                        _set_cell_shading(cell, YELLOW_FILL)
                if tip == "COD_SIMILAR":
                    for cell in row:
                        _set_cell_shading(cell, ORANGE_FILL)

                # Red text on the specific values that differ
                if tip == "DIFERENTA_CAMP" and camp == "cantitate":
                    ref_cant_run.font.color.rgb = RED
                    if oferta_cant_run:
                        oferta_cant_run.font.color.rgb = RED
                elif tip == "UM_DIFERIT":
                    ref_um_run.font.color.rgb = RED
                    if oferta_um_run:
                        oferta_um_run.font.color.rgb = RED

        # Set column widths AFTER all data rows are added
        _set_col_widths(table)

    doc.add_paragraph()

    if audit_data:
        _add_audit_section(doc, audit_data)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
