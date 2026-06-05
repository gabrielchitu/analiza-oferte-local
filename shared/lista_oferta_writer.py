"""F3-format DOCX list generator for referinta and offer articles."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Generator, Union

from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.table import Table


def extract_entity_name(di_json_path: str, is_referinta: bool) -> str:
    """Extract proiectant/ofertant name from raw DI JSON (first 5 pages)."""
    marker = "PROIECTANT" if is_referinta else "CONTRACTANT (OFERTANT)"
    try:
        with open(di_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return "Necunoscut"

    pages = data.get("pages", [])
    for page in pages[:5]:
        lines = [ln.get("content", "").strip() for ln in page.get("lines", [])]
        for i, line in enumerate(lines):
            if marker in line:
                for candidate in lines[i + 1 :]:
                    if candidate and candidate.upper() != "SRL":
                        return candidate
    return "Necunoscut"


def _get_header_from_articles(articles: List[Dict]) -> Dict:
    """Extract group header from first article's deviz_header dict."""
    for art in articles:
        dh = art.get("deviz_header")
        if isinstance(dh, dict):
            return dh
    return {"obiectivul": "", "obiectul": "", "categoria": ""}


def _fmt_nr_crt(nr_ordine: Union[int, float, str]) -> str:
    """Format nr_ordine for display. Integers show as '1', subcomponents as '9.1'."""
    if nr_ordine is None:
        return ""
    if isinstance(nr_ordine, float) and nr_ordine == int(nr_ordine):
        return str(int(nr_ordine))
    return str(nr_ordine)


def _fmt_price(value: Optional[float]) -> str:
    """Format price: None/0.0 → empty string; else Romanian locale (1.234,50).

    Uses Python's default rounding (round-half-to-even); adequate for DOCX display.
    """
    if not value:
        return ""
    formatted = f"{value:,.2f}"
    # Convert to Romanian locale: swap . and ,
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def _iter_source_groups(holistic: Dict, source: str) -> Generator[Tuple[Dict, List[Dict]], None, None]:
    """Yield (header_dict, articles_list) for each non-empty group.

    Args:
        holistic: holistic JSON structure with matched_groups, ref_only_groups, oferta_only_groups
        source: "oferta" or "referinta"

    Yields:
        (header: Dict, articles: List[Dict]) tuples
    """
    art_key = "oferta_articles" if source == "oferta" else "ref_articles"
    only_key = "oferta_only_groups" if source == "oferta" else "ref_only_groups"

    for group in holistic.get("matched_groups", []):
        articles = group.get(art_key, [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles

    for group in holistic.get(only_key, []):
        articles = group.get("articles", [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles


HEADER_FILL = "D9D9D9"   # light grey for header rows
COL_WIDTHS_CM = [1.0, 1.2, 2.0, 2.2, 6.5, 1.2, 1.8, 2.0, 2.0, 1.8, 2.0, 2.0, 2.0, 1.8, 2.0]


def _shade_cell(cell, fill_hex: str) -> None:
    """Apply background shading to a cell."""
    shading = OxmlElement("w:shd")
    shading.set(qn("w:fill"), fill_hex)
    cell._element.get_or_add_tcPr().append(shading)


def _cell_text(cell, text: str, bold: bool = False, center: bool = False, font_size: int = 8) -> None:
    """Set text content in a cell with optional formatting."""
    cell.text = ""
    p = cell.paragraphs[0]
    if center:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run(text)
    run.bold = bold
    run.font.size = Pt(font_size)


def _merge_vertical(table: Table, col: int, row_start: int = 0, row_end: int = 1) -> None:
    """Merge cells in same column across rows."""
    table.cell(row_start, col).merge(table.cell(row_end, col))


def _build_table_header(table: Table) -> None:
    """Write 2-row F3 header into an existing 2-row, 15-col table."""
    # Set column widths
    for row in table.rows:
        for i, cell in enumerate(row.cells):
            cell.width = Cm(COL_WIDTHS_CM[i])

    row0 = table.rows[0].cells
    row1 = table.rows[1].cells

    # First 7 columns: merge vertically (span 2 rows)
    labels_row0 = ["Nr.", "Nr.crt", "Cod", "Cod principal", "Denumire", "UM", "Cantitate"]
    for i, label in enumerate(labels_row0):
        _merge_vertical(table, i)
        _cell_text(row0[i], label, bold=True, center=True)
        _shade_cell(row0[i], HEADER_FILL)

    # "Pret unitar (lei/UM)" spans cols 7-10
    row0[7].merge(row0[10])
    _cell_text(row0[7], "Pret unitar (lei/UM)", bold=True, center=True)
    _shade_cell(row0[7], HEADER_FILL)

    # "Valoare (lei)" spans cols 11-14
    row0[11].merge(row0[14])
    _cell_text(row0[11], "Valoare (lei)", bold=True, center=True)
    _shade_cell(row0[11], HEADER_FILL)

    # Row 1: sub-labels for price cols
    price_labels = ["Material", "Manoperă", "Utilaje", "Transport",
                    "Material", "Manoperă", "Utilaje", "Transport"]
    for i, label in enumerate(price_labels):
        _cell_text(row1[7 + i], label, bold=True, center=True)
        _shade_cell(row1[7 + i], HEADER_FILL)
