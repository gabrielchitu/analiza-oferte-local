"""Generate F3 landscape DOCX from verified extracted sursa-incarcare data."""

import re
import subprocess
from pathlib import Path

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment

# Column widths in cm: Nr | Denumire | UM | Cant | Pret | Total
_COL_W = [1.2, 9.0, 1.5, 2.5, 2.8, 3.0]

_STOPWORDS = {'DE', 'LA', 'PE', 'SI', 'IN', 'CU', 'DIN', 'A', 'AL', 'SA', 'O', 'UN'}

_GRAY_HEX = 'EEEEEE'
_YELLOW_HEX = 'FFF2CC'
_RED_HEX = 'FF0000'
_HEADER_GRAY = 'D9D9D9'

_XLS_GRAY = PatternFill('solid', fgColor='EEEEEE')
_XLS_YELLOW = PatternFill('solid', fgColor='FFF2CC')
_XLS_RED = PatternFill('solid', fgColor='FF0000')
_XLS_HEADER = PatternFill('solid', fgColor='D9D9D9')
_XLS_BOLD = Font(bold=True)
_XLS_BOLD_WHITE = Font(bold=True, color='FFFFFF')
_XLS_SMALL = Font(size=8, italic=True)
_XLS_SUBITEM = Font(size=8)
_XLS_CENTER = Alignment(horizontal='center', vertical='center')
_XLS_RIGHT = Alignment(horizontal='right', vertical='center')


def make_acronym(obiectivul: str) -> str:
    """Generate max-6-char acronym from OBIECTIVUL string.

    Leading numeric tokens (e.g. '0232 000000232') are stripped before processing.

    Examples:
        '0232 000000232 DRUMURI TATARANI'               -> 'DT'
        'CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE'     -> 'CUCT'
    """
    # Strip leading numeric-only tokens (codes like '0232 000000232')
    text = re.sub(r'^\d[\d\s]+', '', obiectivul).strip()
    # Keep only Romanian-alphabet letters and spaces (drop punctuation/hyphens)
    text = re.sub(r'[^A-ZĂÂÎȘȚ ]', '', text.upper())
    words = text.split()
    letters = [w[0] for w in words if w and w not in _STOPWORDS and len(w) >= 2]
    return ''.join(letters[:6])


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _set_landscape(doc: Document) -> None:
    section = doc.sections[0]
    section.orientation = WD_ORIENT.LANDSCAPE
    section.page_width, section.page_height = section.page_height, section.page_width
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.5)
    section.bottom_margin = Cm(1.5)


def _set_tbl_grid(tbl) -> None:
    tblGrid = OxmlElement('w:tblGrid')
    for w_cm in _COL_W:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(int(round(w_cm * 567))))
        tblGrid.append(gc)
    tbl_el = tbl._tbl
    tbl_pr = tbl_el.find(qn('w:tblPr'))
    if tbl_pr is not None:
        tbl_pr.addnext(tblGrid)
    else:
        tbl_el.insert(0, tblGrid)


def _set_cell_margins(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    tblCellMar = OxmlElement('w:tblCellMar')
    for side, twips in [('top', 28), ('left', 57), ('bottom', 28), ('right', 57)]:
        elem = OxmlElement(f'w:{side}')
        elem.set(qn('w:w'), str(twips))
        elem.set(qn('w:type'), 'dxa')
        tblCellMar.append(elem)
    tblPr.append(tblCellMar)


def _repeat_header_rows(tbl, n_rows: int = 2) -> None:
    for row in tbl.rows[:n_rows]:
        tr = row._tr
        trPr = tr.find(qn('w:trPr'))
        if trPr is None:
            trPr = OxmlElement('w:trPr')
            tr.insert(0, trPr)
        trPr.append(OxmlElement('w:tblHeader'))


def _shade_cell(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _fmt_num(value: float, decimals: int = 2) -> str:
    if value == 0.0:
        return '0.00'
    return f'{value:,.{decimals}f}'


def _cell_write(cell, text: str, bold: bool = False, size: float = 8,
                center: bool = False, right: bool = False,
                color: str | None = None) -> None:
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    if right:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT


def _add_header_rows(tbl, obiectivul: str, obiectul: str, categoria: str) -> None:
    row0 = tbl.rows[0]
    for i in range(1, 6):
        row0.cells[0].merge(row0.cells[i])
    cell = row0.cells[0]
    cell.text = ''
    for label, value in [('Obiectivul', obiectivul), ('Obiectul', obiectul), ('Categoria', categoria)]:
        p = cell.add_paragraph()
        run = p.add_run(f'{label}: {value}')
        run.font.size = Pt(9)
        run.font.bold = True
    # remove the empty first paragraph that python-docx adds by default
    first_p = cell.paragraphs[0]._p
    first_p.getparent().remove(first_p)

    row1 = tbl.rows[1]
    headers = [
        'Nr.',
        'Capitol de lucrări',
        'U.M.',
        'Cantitatea',
        'Preț unitar (fără TVA) — Lei',
        'TOTALUL (fără TVA) — Lei',
    ]
    for i, h in enumerate(headers):
        _shade_cell(row1.cells[i], _HEADER_GRAY)
        _cell_write(row1.cells[i], h, bold=True, size=7.5, center=True)


def _add_capitol_row(tbl, titlu: str) -> None:
    row = tbl.add_row()
    for i in range(2, 6):
        row.cells[1].merge(row.cells[i])
    _shade_cell(row.cells[0], _GRAY_HEX)
    _shade_cell(row.cells[1], _GRAY_HEX)
    _cell_write(row.cells[0], '', bold=True, size=8)
    _cell_write(row.cells[1], titlu, bold=True, size=8.5)


def _add_article_row(tbl, art: dict) -> None:
    row = tbl.add_row()
    cod_den = (f"{art['cod']} - {art['denumire']}"
               if art.get('cod') else art.get('denumire', ''))
    vals = [
        art.get('nr_crt', ''),
        cod_den,
        art.get('um', ''),
        _fmt_num(art.get('cantitate', 0), 3),
        _fmt_num(art.get('pret_unitar', 0)),
        _fmt_num(art.get('total', 0)),
    ]
    for i, v in enumerate(vals):
        _cell_write(row.cells[i], v, size=8,
                    center=(i in {0, 2}), right=(i in {3, 4, 5}))


def _add_breakdown_rows(tbl, breakdown: dict) -> None:
    for key in ('material', 'manopera', 'utilaj', 'transport'):
        bd = breakdown.get(key, {})
        row = tbl.add_row()
        _cell_write(row.cells[0], '', size=7)
        cell1 = row.cells[1]
        cell1.text = ''
        p = cell1.paragraphs[0]
        p.paragraph_format.left_indent = Cm(0.5)
        run = p.add_run(f"{key}:")
        run.font.size = Pt(7)
        run.font.italic = True
        _cell_write(row.cells[2], '', size=7)
        _cell_write(row.cells[3], '', size=7)
        _cell_write(row.cells[4], _fmt_num(bd.get('pret', 0)), size=7, right=True)
        _cell_write(row.cells[5], _fmt_num(bd.get('total', 0)), size=7, right=True)


def _add_sub_item_row(tbl, sub: dict) -> None:
    row = tbl.add_row()
    cod_den = (f"{sub['cod']} - {sub['denumire']}"
               if sub.get('cod') else sub.get('denumire', ''))
    vals = [
        sub.get('nr_crt', ''),
        cod_den,
        sub.get('um', ''),
        _fmt_num(sub.get('cantitate', 0), 3),
        _fmt_num(sub.get('pret_unitar', 0)),
        _fmt_num(sub.get('total', 0)),
    ]
    for i, v in enumerate(vals):
        _cell_write(row.cells[i], v, size=7.5,
                    center=(i in {0, 2}), right=(i in {3, 4, 5}))


def _add_total_capitol_row(tbl, titlu: str, total: float) -> None:
    row = tbl.add_row()
    for i in range(1, 5):
        row.cells[0].merge(row.cells[i])
    _cell_write(row.cells[0], f'TOTAL {titlu}', bold=True, size=8)
    _cell_write(row.cells[5], _fmt_num(total), bold=True, size=8, right=True)


def _add_total_deviz_row(tbl, total: float, is_red: bool = False) -> None:
    row = tbl.add_row()
    for i in range(1, 5):
        row.cells[0].merge(row.cells[i])
    if is_red:
        for cell in row.cells:
            _shade_cell(cell, _RED_HEX)
        _cell_write(row.cells[0],
                    'TOTAL NECONFIRMAT — verificare manuală necesară',
                    bold=True, size=8, color='FFFFFF')
        _cell_write(row.cells[5], _fmt_num(total), bold=True, size=8,
                    right=True, color='FFFFFF')
    else:
        for cell in row.cells:
            _shade_cell(cell, _YELLOW_HEX)
        _cell_write(row.cells[0], 'TOTAL 1 (Cheltuieli directe)', bold=True, size=9)
        _cell_write(row.cells[5], _fmt_num(total), bold=True, size=9, right=True)


def _build_table(doc: Document, deviz: dict) -> None:
    tbl = doc.add_table(rows=2, cols=6)
    tbl.style = 'Table Grid'
    _set_tbl_grid(tbl)
    _set_cell_margins(tbl)
    _repeat_header_rows(tbl, n_rows=2)
    _add_header_rows(tbl,
                     deviz.get('obiectivul', ''),
                     deviz.get('obiectul', ''),
                     deviz.get('categoria', ''))

    for cap in deviz.get('capitole', []):
        _add_capitol_row(tbl, cap['titlu'])
        for art in cap.get('articole', []):
            _add_article_row(tbl, art)
            if art.get('breakdown'):
                _add_breakdown_rows(tbl, art['breakdown'])
            for sub in art.get('sub_items', []):
                _add_sub_item_row(tbl, sub)
        if cap.get('total_capitol') is not None:
            _add_total_capitol_row(tbl, cap['titlu'], cap['total_capitol'])

    is_red = deviz.get('status') == 'RED'
    _add_total_deviz_row(tbl, deviz.get('total_deviz', 0.0), is_red)


def write_docx(devize: list[dict], output_path: Path) -> None:
    """Write F3 landscape DOCX with one table per deviz."""
    doc = Document()
    _set_landscape(doc)
    for idx, deviz in enumerate(devize):
        if idx > 0:
            doc.add_page_break()
        _build_table(doc, deviz)
    doc.save(str(output_path))


def write_xlsx(devize: list[dict], output_path: Path) -> None:
    """Write F3 XLS with same row structure as DOCX (one sheet per deviz)."""
    wb = Workbook()
    wb.remove(wb.active)

    col_widths = [8, 55, 8, 14, 16, 16]

    for deviz in devize:
        sheet_name = (deviz.get('categoria') or 'Deviz')[:31]
        ws = wb.create_sheet(title=sheet_name)

        for ci, w in enumerate(col_widths, 1):
            ws.column_dimensions[ws.cell(1, ci).column_letter].width = w

        r = 1
        # Deviz header row
        ws.merge_cells(start_row=r, start_column=1, end_row=r, end_column=6)
        header_val = (
            f"Obiectivul: {deviz.get('obiectivul', '')}\n"
            f"Obiectul: {deviz.get('obiectul', '')}\n"
            f"Categoria: {deviz.get('categoria', '')}"
        )
        cell = ws.cell(r, 1, value=header_val)
        cell.font = _XLS_BOLD
        cell.alignment = Alignment(wrap_text=True, vertical='top')
        ws.row_dimensions[r].height = 48
        r += 1

        # Column headers
        headers = ['Nr.', 'Capitol de lucrări', 'U.M.', 'Cantitatea',
                   'Preț unitar (fără TVA) — Lei', 'TOTALUL (fără TVA) — Lei']
        for ci, h in enumerate(headers, 1):
            c = ws.cell(r, ci, value=h)
            c.fill = _XLS_HEADER
            c.font = _XLS_BOLD
            c.alignment = _XLS_CENTER
        r += 1

        for cap in deviz.get('capitole', []):
            ws.cell(r, 1, value='').fill = _XLS_GRAY
            c = ws.cell(r, 2, value=cap['titlu'])
            c.font = _XLS_BOLD
            c.fill = _XLS_GRAY
            for ci in range(3, 7):
                ws.cell(r, ci).fill = _XLS_GRAY
            r += 1

            for art in cap.get('articole', []):
                cod_den = f"{art['cod']} - {art['denumire']}" if art['cod'] else art['denumire']
                ws.cell(r, 1, value=art['nr_crt']).alignment = _XLS_CENTER
                ws.cell(r, 2, value=cod_den)
                ws.cell(r, 3, value=art.get('um', '')).alignment = _XLS_CENTER
                ws.cell(r, 4, value=art.get('cantitate', 0)).alignment = _XLS_RIGHT
                ws.cell(r, 5, value=art.get('pret_unitar', 0)).alignment = _XLS_RIGHT
                ws.cell(r, 6, value=art.get('total', 0)).alignment = _XLS_RIGHT
                r += 1

                if art.get('breakdown'):
                    for key in ('material', 'manopera', 'utilaj', 'transport'):
                        bd = art['breakdown'].get(key, {})
                        ws.cell(r, 2, value=f"  {key}:").font = _XLS_SMALL
                        c5 = ws.cell(r, 5, value=bd.get('pret', 0))
                        c5.font = _XLS_SMALL
                        c5.alignment = _XLS_RIGHT
                        c6 = ws.cell(r, 6, value=bd.get('total', 0))
                        c6.font = _XLS_SMALL
                        c6.alignment = _XLS_RIGHT
                        r += 1

                for sub in art.get('sub_items', []):
                    cod_den_s = f"{sub['cod']} - {sub['denumire']}" if sub['cod'] else sub['denumire']
                    ws.cell(r, 1, value=sub['nr_crt']).alignment = _XLS_CENTER
                    ws.cell(r, 2, value=cod_den_s).font = _XLS_SUBITEM
                    ws.cell(r, 3, value=sub.get('um', '')).alignment = _XLS_CENTER
                    ws.cell(r, 4, value=sub.get('cantitate', 0)).alignment = _XLS_RIGHT
                    ws.cell(r, 5, value=sub.get('pret_unitar', 0)).alignment = _XLS_RIGHT
                    ws.cell(r, 6, value=sub.get('total', 0)).alignment = _XLS_RIGHT
                    r += 1

            if cap.get('total_capitol') is not None:
                for ci in range(1, 6):
                    c = ws.cell(r, ci, value=f'TOTAL {cap["titlu"]}' if ci == 1 else '')
                    c.font = _XLS_BOLD
                c = ws.cell(r, 6, value=cap['total_capitol'])
                c.font = _XLS_BOLD
                c.alignment = _XLS_RIGHT
                r += 1

        # Total deviz row
        is_red = deviz.get('status') == 'RED'
        total_label = 'TOTAL NECONFIRMAT — verificare manuală necesară' if is_red else 'TOTAL 1 (Cheltuieli directe)'
        fill = _XLS_RED if is_red else _XLS_YELLOW
        font = _XLS_BOLD_WHITE if is_red else _XLS_BOLD
        for ci in range(1, 7):
            ws.cell(r, ci).fill = fill
        ws.cell(r, 1, value=total_label).font = font
        c = ws.cell(r, 6, value=deviz.get('total_deviz', 0))
        c.font = font
        c.alignment = _XLS_RIGHT

    wb.save(str(output_path))


def write_pdf(docx_path: Path, output_dir: Path) -> bool:
    """Convert DOCX to PDF via LibreOffice CLI. Returns True on success, False if unavailable."""
    try:
        result = subprocess.run(
            ['soffice', '--headless', '--convert-to', 'pdf',
             '--outdir', str(output_dir), str(docx_path)],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def write_pdf_native(devize: list[dict], output_path: Path) -> bool:
    """Generate searchable PDF with reportlab (no LibreOffice needed). Returns True on success."""
    try:
        import os
        from reportlab.lib.pagesizes import A4, landscape as rl_landscape
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, PageBreak,
        )
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
    except ImportError:
        return False

    # -- Font (Arial with Romanian character support, fallback Helvetica) --
    _FONT = 'Helvetica'
    _FONT_BOLD = 'Helvetica-Bold'
    _arial_r = '/System/Library/Fonts/Supplemental/Arial.ttf'
    _arial_b = '/System/Library/Fonts/Supplemental/Arial Bold.ttf'
    if os.path.exists(_arial_r):
        try:
            pdfmetrics.registerFont(TTFont('_PdfArial', _arial_r))
            _FONT = '_PdfArial'
            if os.path.exists(_arial_b):
                pdfmetrics.registerFont(TTFont('_PdfArialBold', _arial_b))
                _FONT_BOLD = '_PdfArialBold'
            else:
                _FONT_BOLD = '_PdfArial'
        except Exception:
            pass

    # -- Paragraph styles --
    def _ps(name, font, size, leading_mult=1.25):
        return ParagraphStyle(name, fontName=font, fontSize=size,
                              leading=size * leading_mult, spaceAfter=0, spaceBefore=0)

    ps_normal  = _ps('N',  _FONT,      7)
    ps_bold    = _ps('B',  _FONT_BOLD, 7)
    ps_header  = _ps('H',  _FONT_BOLD, 8.5, 1.3)
    ps_colhdr  = _ps('CH', _FONT_BOLD, 7,   1.2)
    ps_small   = _ps('S',  _FONT,      6.5)
    ps_total   = _ps('T',  _FONT_BOLD, 8)
    ps_total_w = _ps('TW', _FONT_BOLD, 8)
    ps_total_w.textColor = colors.white

    # -- Column widths: scaled proportionally to fill A4 landscape (26.7 cm usable) --
    COL_W = [w * cm for w in (1.6, 12.0, 2.0, 3.2, 3.6, 4.3)]

    # -- Colors --
    C_GRAY    = colors.HexColor('#EEEEEE')
    C_DGRAY   = colors.HexColor('#D9D9D9')
    C_YELLOW  = colors.HexColor('#FFF2CC')
    C_RED     = colors.HexColor('#FF0000')

    def _esc(s: str) -> str:
        return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    def _p(text, style):
        return Paragraph(_esc(text), style)

    def _build_table(deviz: dict) -> Table:
        rows = []
        cmds = [
            ('GRID',          (0, 0), (-1, -1), 0.4,  colors.black),
            ('FONTNAME',      (0, 0), (-1, -1), _FONT),
            ('FONTSIZE',      (0, 0), (-1, -1), 7),
            ('TOPPADDING',    (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('LEFTPADDING',   (0, 0), (-1, -1), 3),
            ('RIGHTPADDING',  (0, 0), (-1, -1), 3),
            ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ]

        # Row 0: deviz header (spans all 6 cols)
        hdr = (
            f"<b>Obiectivul:</b> {_esc(deviz.get('obiectivul', ''))}<br/>"
            f"<b>Obiectul:</b> {_esc(deviz.get('obiectul', ''))}<br/>"
            f"<b>Categoria:</b> {_esc(deviz.get('categoria', ''))}"
        )
        rows.append([Paragraph(hdr, ps_header), '', '', '', '', ''])
        cmds += [
            ('SPAN',          (0, 0), (5, 0)),
            ('BACKGROUND',    (0, 0), (5, 0), C_DGRAY),
            ('TOPPADDING',    (0, 0), (5, 0), 5),
            ('BOTTOMPADDING', (0, 0), (5, 0), 5),
        ]

        # Row 1: column headers
        col_labels = [
            'Nr.', 'Capitol de lucrări', 'U.M.',
            'Cantitatea', 'Preț unitar\n(fără TVA) Lei', 'TOTALUL\n(fără TVA) Lei',
        ]
        rows.append([Paragraph(h, ps_colhdr) for h in col_labels])
        cmds += [
            ('BACKGROUND', (0, 1), (5, 1), C_DGRAY),
            ('ALIGN',      (0, 1), (5, 1), 'CENTER'),
            ('TOPPADDING', (0, 1), (5, 1), 3),
            ('BOTTOMPADDING', (0, 1), (5, 1), 3),
        ]

        ri = 2

        for cap in deviz.get('capitole', []):
            # Chapter header row: col 0 empty, cols 1-5 merged
            rows.append(['', _p(cap['titlu'], ps_bold), '', '', '', ''])
            cmds += [
                ('SPAN',       (1, ri), (5, ri)),
                ('BACKGROUND', (0, ri), (5, ri), C_GRAY),
                ('FONTNAME',   (0, ri), (5, ri), _FONT_BOLD),
            ]
            ri += 1

            for art in cap.get('articole', []):
                cod_den = (f"{_esc(art['cod'])} - {_esc(art['denumire'])}"
                           if art.get('cod') else _esc(art.get('denumire', '')))
                rows.append([
                    art.get('nr_crt', ''),
                    Paragraph(cod_den, ps_normal),
                    art.get('um', ''),
                    _fmt_num(art.get('cantitate', 0), 3),
                    _fmt_num(art.get('pret_unitar', 0)),
                    _fmt_num(art.get('total', 0)),
                ])
                cmds += [
                    ('ALIGN', (0, ri), (0, ri), 'CENTER'),
                    ('ALIGN', (2, ri), (2, ri), 'CENTER'),
                    ('ALIGN', (3, ri), (5, ri), 'RIGHT'),
                ]
                ri += 1

                if art.get('breakdown'):
                    for key in ('material', 'manopera', 'utilaj', 'transport'):
                        bd = art['breakdown'].get(key, {})
                        rows.append([
                            '', Paragraph(f'<i>  {key}:</i>', ps_small), '', '',
                            _fmt_num(bd.get('pret', 0)),
                            _fmt_num(bd.get('total', 0)),
                        ])
                        cmds += [
                            ('FONTSIZE', (0, ri), (5, ri), 6.5),
                            ('ALIGN',    (4, ri), (5, ri), 'RIGHT'),
                        ]
                        ri += 1

                for sub in art.get('sub_items', []):
                    cod_den_s = (f"{_esc(sub['cod'])} - {_esc(sub['denumire'])}"
                                 if sub.get('cod') else _esc(sub.get('denumire', '')))
                    rows.append([
                        sub.get('nr_crt', ''),
                        Paragraph(cod_den_s, ps_small),
                        sub.get('um', ''),
                        _fmt_num(sub.get('cantitate', 0), 3),
                        _fmt_num(sub.get('pret_unitar', 0)),
                        _fmt_num(sub.get('total', 0)),
                    ])
                    cmds += [
                        ('FONTSIZE', (0, ri), (5, ri), 6.5),
                        ('ALIGN', (0, ri), (0, ri), 'CENTER'),
                        ('ALIGN', (2, ri), (2, ri), 'CENTER'),
                        ('ALIGN', (3, ri), (5, ri), 'RIGHT'),
                    ]
                    ri += 1

            if cap.get('total_capitol') is not None:
                rows.append([
                    _p(f'TOTAL {cap["titlu"]}', ps_bold),
                    '', '', '', '',
                    _fmt_num(cap['total_capitol']),
                ])
                cmds += [
                    ('SPAN',     (0, ri), (4, ri)),
                    ('FONTNAME', (0, ri), (5, ri), _FONT_BOLD),
                    ('ALIGN',    (5, ri), (5, ri), 'RIGHT'),
                ]
                ri += 1

        # Deviz total row
        is_red = deviz.get('status') == 'RED'
        total_label = ('TOTAL NECONFIRMAT — verificare manuală necesară'
                       if is_red else 'TOTAL 1 (Cheltuieli directe)')
        bg = C_RED if is_red else C_YELLOW
        lbl_style = ps_total_w if is_red else ps_total

        rows.append([
            Paragraph(_esc(total_label), lbl_style),
            '', '', '', '',
            _fmt_num(deviz.get('total_deviz', 0.0)),
        ])
        cmds += [
            ('SPAN',       (0, ri), (4, ri)),
            ('BACKGROUND', (0, ri), (5, ri), bg),
            ('FONTNAME',   (0, ri), (5, ri), _FONT_BOLD),
            ('FONTSIZE',   (0, ri), (5, ri), 8),
            ('ALIGN',      (5, ri), (5, ri), 'RIGHT'),
            ('TOPPADDING', (0, ri), (5, ri), 3),
            ('BOTTOMPADDING', (0, ri), (5, ri), 3),
        ]
        if is_red:
            cmds.append(('TEXTCOLOR', (5, ri), (5, ri), colors.white))

        tbl = Table(rows, colWidths=COL_W, repeatRows=2)
        tbl.setStyle(TableStyle(cmds))
        return tbl

    # -- Build document --
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=rl_landscape(A4),
        leftMargin=1.5 * cm, rightMargin=1.5 * cm,
        topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )
    story = []
    for idx, deviz in enumerate(devize):
        if idx > 0:
            story.append(PageBreak())
        story.append(_build_table(deviz))

    doc.build(story)
    return True


# ── V2: Template-exact format ──────────────────────────────────────────────

_COL_WIDTHS_TWIPS_V2 = [397, 510, 1020, 1020, 3175, 567, 1020, 624, 624, 624, 624]
_NO_WRAP_COLS_V2 = {0, 1, 2, 3, 5, 6, 7, 8, 9, 10}
_HEADER_FILL_V2 = 'D9D9D9'
_TOTAL_FILL_V2 = 'F2F2F2'


def _set_cell_width_twips_v2(cell, twips: int) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    existing = tcPr.find(qn('w:tcW'))
    if existing is not None:
        tcPr.remove(existing)
    tcW = OxmlElement('w:tcW')
    tcW.set(qn('w:w'), str(twips))
    tcW.set(qn('w:type'), 'dxa')
    tcPr.insert(0, tcW)


def _set_cell_no_wrap_v2(cell) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    tcPr.append(OxmlElement('w:noWrap'))


def _suppress_borders_v2(tbl) -> None:
    tblPr = tbl._tbl.tblPr
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        el.set(qn('w:sz'), '0')
        el.set(qn('w:color'), 'auto')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _set_tbl_grid_v2(tbl) -> None:
    tbl_el = tbl._tbl
    existing = tbl_el.find(qn('w:tblGrid'))
    if existing is not None:
        tbl_el.remove(existing)
    tblGrid = OxmlElement('w:tblGrid')
    for w in _COL_WIDTHS_TWIPS_V2:
        gc = OxmlElement('w:gridCol')
        gc.set(qn('w:w'), str(w))
        tblGrid.append(gc)
    tblPr = tbl_el.find(qn('w:tblPr'))
    if tblPr is not None:
        tblPr.addnext(tblGrid)
    else:
        tbl_el.insert(0, tblGrid)


def _shade_cell_v2(cell, hex_color: str) -> None:
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement('w:shd')
    shd.set(qn('w:val'), 'clear')
    shd.set(qn('w:color'), 'auto')
    shd.set(qn('w:fill'), hex_color)
    tcPr.append(shd)


def _cell_write_v2(cell, text: str, bold: bool = False, size: float = 8,
                   center: bool = False, right: bool = False) -> None:
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if right:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    elif center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER


def _fmt_price_ro(value) -> str:
    """None/0 → ''; else Romanian locale: 1.234,50."""
    if not value:
        return ''
    formatted = f'{value:,.2f}'
    return formatted.replace(',', 'X').replace('.', ',').replace('X', '.')


def _build_sursa_table_header(tbl) -> None:
    """Write 2-row F3 header (same structure as Template_exact.docx)."""
    row0 = tbl.rows[0].cells
    row1 = tbl.rows[1].cells

    for ci in range(11):
        _set_cell_width_twips_v2(row0[ci], _COL_WIDTHS_TWIPS_V2[ci])
        _set_cell_width_twips_v2(row1[ci], _COL_WIDTHS_TWIPS_V2[ci])
        if ci in _NO_WRAP_COLS_V2:
            _set_cell_no_wrap_v2(row0[ci])
            _set_cell_no_wrap_v2(row1[ci])

    labels = ["Nr.", "Nr.crt", "Cod", "Cod principal", "Denumire", "UM", "Cantitate"]
    for i, label in enumerate(labels):
        tbl.cell(0, i).merge(tbl.cell(1, i))
        _cell_write_v2(row0[i], label, bold=True, center=True)
        _shade_cell_v2(row0[i], _HEADER_FILL_V2)

    row0[7].merge(row0[10])
    _cell_write_v2(row0[7], "Pret unitar (lei/UM)", bold=True, center=True)
    _shade_cell_v2(row0[7], _HEADER_FILL_V2)

    for i, label in enumerate(["Material", "Manoperă", "Utilaje", "Transport"]):
        _cell_write_v2(row1[7 + i], label, bold=True, center=True)
        _shade_cell_v2(row1[7 + i], _HEADER_FILL_V2)


def _write_sursa_row_v2(row, seq_nr: int, art: dict, is_sub: bool, parent_cod: str) -> None:
    bd = art.get('breakdown') or {}
    font_size = 7 if is_sub else 8

    values = [
        str(seq_nr),
        str(art.get('nr_crt', '')),
        art.get('cod', '') or '',
        parent_cod or '',
        art.get('denumire', ''),
        art.get('um', ''),
        f"{art.get('cantitate', 0):.2f}" if art.get('cantitate') else '',
        _fmt_price_ro(bd.get('material', {}).get('pret')),
        _fmt_price_ro(bd.get('manopera', {}).get('pret')),
        _fmt_price_ro(bd.get('utilaj', {}).get('pret')),
        _fmt_price_ro(bd.get('transport', {}).get('pret')),
    ]
    right_cols = {1, 6, 7, 8, 9, 10}
    center_cols = {0, 5}

    for ci, (cell, val) in enumerate(zip(row.cells, values)):
        cell.text = ''
        p = cell.paragraphs[0]
        if ci in right_cols:
            p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        elif ci in center_cols:
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(val)
        run.font.size = Pt(font_size)
        if is_sub:
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)


def _build_sursa_group(doc, deviz: dict) -> None:
    """Add group header paragraph + 11-col table for one deviz."""
    obiectivul = deviz.get('obiectivul', '')
    obiectul   = deviz.get('obiectul', '')
    categoria  = deviz.get('categoria', '')

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    parts = [s.strip() for s in [obiectivul, obiectul, categoria] if s.strip()]
    run = p.add_run(' | '.join(parts))
    run.bold = True
    run.font.size = Pt(9)

    # Flatten capitole → articole + sub_items
    flat: list[tuple[bool, dict, str]] = []  # (is_sub, art, parent_cod)
    for cap in deviz.get('capitole', []):
        for art in cap.get('articole', []):
            flat.append((False, art, ''))
            for sub in art.get('sub_items', []):
                flat.append((True, sub, art.get('cod', '') or ''))

    main_count = sum(1 for is_sub, _, _ in flat if not is_sub)
    sub_count  = sum(1 for is_sub, _, _ in flat if is_sub)

    n_rows = 2 + len(flat) + 1
    tbl = doc.add_table(rows=n_rows, cols=11)
    tbl.style = 'Table Grid'
    _set_tbl_grid_v2(tbl)
    tblPr_el = tbl._tbl.find(qn('w:tblPr'))
    if tblPr_el is not None:
        tblLayout = OxmlElement('w:tblLayout')
        tblLayout.set(qn('w:type'), 'fixed')
        tblPr_el.append(tblLayout)

    _build_sursa_table_header(tbl)

    for i, (is_sub, art, parent_cod) in enumerate(flat):
        _write_sursa_row_v2(tbl.rows[2 + i], seq_nr=i + 1,
                            art=art, is_sub=is_sub, parent_cod=parent_cod)

    total_row = tbl.rows[-1]
    total_row.cells[0].merge(total_row.cells[10])
    cell = total_row.cells[0]
    cell.text = ''
    suffix = f' / {sub_count} subcomponente' if sub_count else ''
    run = cell.paragraphs[0].add_run(
        f'Total grup: {main_count} articole principale{suffix}'
    )
    run.bold = True
    run.font.size = Pt(8)
    _shade_cell_v2(cell, _TOTAL_FILL_V2)


def write_docx_v2(devize: list, output_path, metadata: dict | None = None) -> None:
    """Write F3-format DOCX identical with Template_exact.docx."""
    from datetime import date as _date
    meta = metadata or {}

    doc = Document()
    section = doc.sections[0]
    section.page_width = Cm(21)
    section.page_height = Cm(29.7)
    section.left_margin = Cm(1.5)
    section.right_margin = Cm(1.5)
    section.top_margin = Cm(1.8)
    section.bottom_margin = Cm(1.8)

    offer_label = meta.get('offer_label', 'Oferta')
    client_name = meta.get('client', '')
    ofertant    = meta.get('ofertant', '')
    gen_date    = meta.get('date', _date.today().isoformat())

    for line, bold, size in [
        (f'Lista articole — {offer_label}', True, 14),
        (f'Client: {client_name}', False, 11),
        (f'Ofertant: {ofertant}', False, 11),
        (f'Generat: {gen_date}', False, 9),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.bold = bold
        run.font.size = Pt(size)

    for deviz in devize:
        _build_sursa_group(doc, deviz)

    doc.save(str(output_path))
