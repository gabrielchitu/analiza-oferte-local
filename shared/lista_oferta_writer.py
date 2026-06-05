"""F3-format DOCX list generator for referinta and offer articles."""

import json
from datetime import date
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


def _write_article_row(row, seq_nr: int, article: Dict) -> None:
    """Write article data into a 15-cell table row.

    Args:
        row: docx table row with 15 cells
        seq_nr: sequential article number (1, 2, 3...)
        article: article dict with cod, denumire, um, cantitate, nr_ordine, is_component,
                 parent_code, pret_*, val_*
    """
    nr_crt = _fmt_nr_crt(article.get("nr_ordine", ""))
    parent_code = article.get("parent_code") or ""
    cantitate = article.get("cantitate", 0)

    values = [
        str(seq_nr),
        nr_crt,
        article.get("cod", ""),
        parent_code,
        article.get("denumire", ""),
        article.get("um", ""),
        f"{cantitate:.3f}" if cantitate else "",
        _fmt_price(article.get("pret_material", 0.0)),
        _fmt_price(article.get("pret_manopera", 0.0)),
        _fmt_price(article.get("pret_utilaj", 0.0)),
        _fmt_price(article.get("pret_transport", 0.0)),
        _fmt_price(article.get("val_material", 0.0)),
        _fmt_price(article.get("val_manopera", 0.0)),
        _fmt_price(article.get("val_utilaj", 0.0)),
        _fmt_price(article.get("val_transport", 0.0)),
    ]

    font_size = 7 if article.get("is_component") else 8

    for i, (cell, val) in enumerate(zip(row.cells, values)):
        cell.text = ""
        p = cell.paragraphs[0]
        # Center cols: 0, 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14 (all except 2, 3, 4 = Cod, Cod principal, Denumire)
        if i in (0, 1, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14):
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = p.add_run(val)
        run.font.size = Pt(font_size)
        if article.get("is_component"):
            run.font.color.rgb = RGBColor(0x44, 0x44, 0x44)


def _write_group_section(doc: Document, header: Dict, articles: List[Dict], seq_start: int) -> int:
    """Write group title paragraph + F3 table. Returns next seq_nr.

    Args:
        doc: Document to write to
        header: Dict with obiectivul, obiectul, categoria
        articles: List of article dicts
        seq_start: Starting sequential number for articles

    Returns:
        Next sequential number after all articles written
    """
    # Group title paragraph
    obiectivul = header.get("obiectivul", "")
    obiectul = header.get("obiectul", "")
    categoria = header.get("categoria", "")
    title_parts = [p for p in [obiectivul, obiectul, categoria] if p]
    title = " | ".join(title_parts)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(6)
    run = p.add_run(title)
    run.bold = True
    run.font.size = Pt(9)

    # Count main vs subcomponent articles
    main_count = sum(1 for a in articles if not a.get("is_component"))
    sub_count = sum(1 for a in articles if a.get("is_component"))

    # Table: 2 header rows + N article rows + 1 total row
    n_rows = 2 + len(articles) + 1
    tbl = doc.add_table(rows=n_rows, cols=15)
    tbl.style = "Table Grid"

    _build_table_header(tbl)

    seq = seq_start
    for i, art in enumerate(articles):
        row = tbl.rows[2 + i]
        _write_article_row(row, seq_nr=seq, article=art)
        seq += 1

    # Total row
    total_row = tbl.rows[-1]
    total_row.cells[0].merge(total_row.cells[14])
    total_cell = total_row.cells[0]
    total_cell.text = ""
    run = total_cell.paragraphs[0].add_run(
        f"Total grup: {main_count} articole principale"
        + (f" / {sub_count} subcomponente" if sub_count else "")
    )
    run.bold = True
    run.font.size = Pt(8)
    _shade_cell(total_cell, "F2F2F2")

    return seq


def build_docx_for_source(
    holistic: Dict,
    source: str,
    entity_name: str,
    client_name: str,
    label: str,
    output_path: str,
) -> None:
    """Generate full F3-format DOCX lista for given source ('oferta' or 'referinta').

    Args:
        holistic: loaded holistic_oferta_N.json dict
        source: "oferta" or "referinta"
        entity_name: ofertant or proiectant name
        client_name: display client name
        label: "Oferta 1" or "Referinta"
        output_path: where to save the .docx
    """
    doc = Document()

    # Document header
    entity_label = "Ofertant" if source == "oferta" else "Proiectant"
    for line, bold, size in [
        (f"Lista articole — {label}", True, 14),
        (f"Client: {client_name}", False, 11),
        (f"{entity_label}: {entity_name}", False, 11),
        (f"Generat: {date.today().isoformat()}", False, 9),
    ]:
        p = doc.add_paragraph()
        run = p.add_run(line)
        run.bold = bold
        run.font.size = Pt(size)

    doc.add_paragraph()  # spacer

    seq = 1
    for header, articles in _iter_source_groups(holistic, source=source):
        seq = _write_group_section(doc, header, articles, seq_start=seq)
        doc.add_paragraph()  # spacer between groups

    doc.save(output_path)
