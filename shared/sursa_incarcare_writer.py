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
                center: bool = False, color: str | None = None) -> None:
    cell.text = ''
    p = cell.paragraphs[0]
    p.clear()
    run = p.add_run(text)
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER if center else WD_ALIGN_PARAGRAPH.LEFT


def _add_header_rows(tbl, obiectivul: str, obiectul: str, categoria: str) -> None:
    row0 = tbl.rows[0]
    for i in range(1, 6):
        row0.cells[0].merge(row0.cells[i])
    _cell_write(row0.cells[0], f"{obiectivul} / {obiectul} / {categoria}",
                bold=True, size=9)

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
        _cell_write(row.cells[i], v, size=8, center=(i in {0, 2, 3, 4, 5}))


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
        _cell_write(row.cells[4], _fmt_num(bd.get('pret', 0)), size=7, center=True)
        _cell_write(row.cells[5], _fmt_num(bd.get('total', 0)), size=7, center=True)


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
        _cell_write(row.cells[i], v, size=7.5, center=(i in {0, 2, 3, 4, 5}))


def _add_total_capitol_row(tbl, titlu: str, total: float) -> None:
    row = tbl.add_row()
    for i in range(1, 5):
        row.cells[0].merge(row.cells[i])
    _cell_write(row.cells[0], f'TOTAL {titlu}', bold=True, size=8)
    _cell_write(row.cells[5], _fmt_num(total), bold=True, size=8, center=True)


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
                    center=True, color='FFFFFF')
    else:
        for cell in row.cells:
            _shade_cell(cell, _YELLOW_HEX)
        _cell_write(row.cells[0], 'TOTAL 1 (Cheltuieli directe)', bold=True, size=9)
        _cell_write(row.cells[5], _fmt_num(total), bold=True, size=9, center=True)


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
        cell = ws.cell(r, 1,
                       value=f"{deviz.get('obiectivul','')} / {deviz.get('obiectul','')} / {deviz.get('categoria','')}")
        cell.font = _XLS_BOLD
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
                ws.cell(r, 4, value=art.get('cantitate', 0)).alignment = _XLS_CENTER
                ws.cell(r, 5, value=art.get('pret_unitar', 0)).alignment = _XLS_CENTER
                ws.cell(r, 6, value=art.get('total', 0)).alignment = _XLS_CENTER
                r += 1

                if art.get('breakdown'):
                    for key in ('material', 'manopera', 'utilaj', 'transport'):
                        bd = art['breakdown'].get(key, {})
                        ws.cell(r, 2, value=f"  {key}:").font = _XLS_SMALL
                        ws.cell(r, 5, value=bd.get('pret', 0)).font = _XLS_SMALL
                        ws.cell(r, 6, value=bd.get('total', 0)).font = _XLS_SMALL
                        r += 1

                for sub in art.get('sub_items', []):
                    cod_den_s = f"{sub['cod']} - {sub['denumire']}" if sub['cod'] else sub['denumire']
                    ws.cell(r, 1, value=sub['nr_crt']).alignment = _XLS_CENTER
                    ws.cell(r, 2, value=cod_den_s).font = _XLS_SUBITEM
                    ws.cell(r, 3, value=sub.get('um', '')).alignment = _XLS_CENTER
                    ws.cell(r, 4, value=sub.get('cantitate', 0)).alignment = _XLS_CENTER
                    ws.cell(r, 5, value=sub.get('pret_unitar', 0)).alignment = _XLS_CENTER
                    ws.cell(r, 6, value=sub.get('total', 0)).alignment = _XLS_CENTER
                    r += 1

            if cap.get('total_capitol') is not None:
                for ci in range(1, 6):
                    c = ws.cell(r, ci, value=f'TOTAL {cap["titlu"]}' if ci == 1 else '')
                    c.font = _XLS_BOLD
                ws.cell(r, 6, value=cap['total_capitol']).font = _XLS_BOLD
                r += 1

        # Total deviz row
        is_red = deviz.get('status') == 'RED'
        total_label = 'TOTAL NECONFIRMAT — verificare manuală necesară' if is_red else 'TOTAL 1 (Cheltuieli directe)'
        fill = _XLS_RED if is_red else _XLS_YELLOW
        font = _XLS_BOLD_WHITE if is_red else _XLS_BOLD
        for ci in range(1, 7):
            ws.cell(r, ci).fill = fill
        ws.cell(r, 1, value=total_label).font = font
        ws.cell(r, 6, value=deviz.get('total_deviz', 0)).font = font

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
