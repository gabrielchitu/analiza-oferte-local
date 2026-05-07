"""
Extract articles from F3 tables in DI JSON.

Tables from Document Intelligence have structured format:
- Cells with row/column indices
- Header row identifies columns (Nr., Capitol, UM, Cantitate, Preturi)
- Data rows contain article information
"""
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)


def _clean_article_code(code: str) -> str:
    """Remove OCR artifacts from article codes: SE56A# → SE56A"""
    if not code:
        return code
    # Remove trailing OCR artifacts: #, @, -, etc. that appear after valid code
    code = re.sub(r'([A-Z0-9])[#@\-!]+$', r'\1', code)
    return code


def _parse_article_cell(cell_content: str) -> tuple:
    """
    Parse article cell content: 'CODE - DENOMINATION'
    Returns: (code, denomination) or (None, None)
    """
    if not cell_content or not isinstance(cell_content, str):
        return None, None

    # Match: "CODE - DENOMINATION"
    m = re.match(r'^(\$?\d{4,8}|[A-Z]{2,5}\d{1,4}[A-Z]?\d{0,2})\s*[-–]\s*(.+)',
                 cell_content.strip(), re.IGNORECASE)
    if m:
        code = m.group(1).upper()
        # Add $ prefix to numeric codes
        if re.match(r'^\d+$', code):
            code = '$' + code
        denom = m.group(2).strip()
        return code, denom

    # Fallback: try to extract code even without perfect dash separation
    # This handles cases like "SE56A# - Filtru..." where we need to clean the code
    m2 = re.match(r'^([A-Z0-9#@\-]{2,10})\s*[-–]\s*(.+)', cell_content.strip(), re.IGNORECASE)
    if m2:
        code = m2.group(1).upper()
        code = _clean_article_code(code)
        if code and len(code) >= 2:  # Valid code
            denom = m2.group(2).strip()
            return code, denom

    return None, None


def extract_articles_from_tables(tables: List[Dict], deviz_cod: str, deviz_den: str) -> List[Dict]:
    """
    Extract articles from F3 format tables.

    Expects tables with structure:
    - Header: Nr. | Capitol de lucrari | U.M. | Cantitate | Price | Total
    - Data rows: 1 | CODE - NAME | UM | QTY | price | total

    Args:
        tables: List of table dicts from DI JSON
        deviz_cod: Deviz code (e.g., "226018")
        deviz_den: Deviz denomination

    Returns:
        List of article dicts in standard format
    """
    articole = []

    for table in tables:
        cells = table.get('cells', [])
        if not cells:
            continue

        # Find header row (row 1) to identify columns
        header_row = {}
        for cell in cells:
            if cell.get('row_index') == 1:
                col_idx = cell.get('column_index')
                content = cell.get('content', '').strip().upper()
                header_row[col_idx] = content

        if not header_row:
            continue

        # Identify column positions
        col_nr = None
        col_capitol = None
        col_um = None
        col_cant = None

        for col_idx, header in header_row.items():
            if 'NR' in header or header == '0':
                col_nr = col_idx
            elif 'CAPITOL' in header or 'DENUMIRE' in header:
                col_capitol = col_idx
            elif 'U.M' in header or 'UM' in header:
                col_um = col_idx
            elif 'CANTITAT' in header or header == '3':
                col_cant = col_idx

        if col_capitol is None or col_um is None or col_cant is None:
            continue

        # Extract data rows (skip header rows 0, 1, 2)
        rows = {}
        for cell in cells:
            row_idx = cell.get('row_index')
            if row_idx <= 2:
                continue

            if row_idx not in rows:
                rows[row_idx] = {}
            rows[row_idx][cell.get('column_index')] = cell.get('content', '')

        # Process each article row (rows with article codes)
        for row_idx in sorted(rows.keys()):
            row_data = rows[row_idx]

            # Column 1 has article code + denomination
            capitol_cell = row_data.get(col_capitol, '')
            code, denom = _parse_article_cell(capitol_cell)

            if not code:
                continue

            # Get UM
            um = row_data.get(col_um, '').strip().upper()
            if not um or um in ('0', '1', '2', '3', '4', '5'):
                um = ''

            # Get quantity (column 3)
            cant_str = row_data.get(col_cant, '').strip()
            try:
                # Handle formats like "198.000" or "198,000"
                cant_normalized = cant_str.replace(',', '.').replace('.', '', 1) if '.' in cant_str and ',' in cant_str else cant_str.replace(',', '.')
                cantitate = float(cant_normalized) if cant_normalized else 0.0
            except ValueError:
                cantitate = 0.0

            # Build article
            art = {
                'cod': code,
                'denumire': denom,
                'um': um.lower() if um else '',
                'cantitate': cantitate,
                'deviz': deviz_cod,
                'deviz_denumire': deviz_den,
                'is_component': False,
                'pret_material': 0.0,
                'val_material': 0.0,
                'pret_manopera': 0.0,
                'val_manopera': 0.0,
                'pret_utilaj': 0.0,
                'val_utilaj': 0.0,
                'pret_transport': 0.0,
                'val_transport': 0.0,
            }
            articole.append(art)
            logger.debug(f"[TABLE] Articol din tabel: {code} | {deviz_cod}")

    if articole:
        logger.info(f"[TABLE] {len(articole)} articole extrase din tabele pentru {deviz_cod}")

    return articole


def extract_articles_from_tables_smart(tables: List[Dict]) -> List[Dict]:
    """
    Smartly extract articles from F3 tables by linking metadata to data tables.

    Two-pass approach:
    1. First pass: Find metadata tables (6 rows, 2 cols, "Stadiul fizic:" in row 5)
       Extract deviz code from row 5, col 1
    2. Second pass: Find F3 data tables (6 cols, "SECTIUNEA TEHNICA" in row 0)
       Extract articles using the deviz from the preceding metadata table

    Ignores non-F3 tables (e.g., materials lists with 8 columns).

    Args:
        tables: List of table dicts from DI JSON

    Returns:
        List of article dicts with correct deviz codes
    """
    all_articole = []

    # First pass: Identify metadata tables and their deviz codes
    metadata_to_deviz = {}  # table_idx -> (deviz_cod, deviz_den)

    for table_idx, table in enumerate(tables):
        cells = table.get('cells', [])
        if not cells:
            continue

        # Look for "Stadiul fizic:" pattern in row 5, col 0
        is_metadata = False
        stadiul_cell = None

        for cell in cells:
            if cell.get('row_index') == 5 and cell.get('column_index') == 0:
                content = cell.get('content', '').strip()
                if 'STADIUL' in content.upper():
                    is_metadata = True
                    break

        if is_metadata:
            # Extract deviz from row 5, col 1
            for cell in cells:
                if cell.get('row_index') == 5 and cell.get('column_index') == 1:
                    content = cell.get('content', '').strip()
                    # Parse "226U18 CANALIZARE"
                    m = re.match(r'^([A-Z0-9]{5,8})\s+(.+)$', content)
                    if m:
                        deviz_cod = m.group(1).upper()
                        deviz_den = m.group(2).strip()
                        metadata_to_deviz[table_idx] = (deviz_cod, deviz_den)
                        logger.debug(f"[TABLE] Tabel {table_idx}: Metadata deviz {deviz_cod} - {deviz_den}")
                        break

    # Second pass: Find F3 data tables and extract articles
    processed_tables = set()

    for table_idx, table in enumerate(tables):
        cells = table.get('cells', [])
        if not cells:
            continue

        if table_idx in processed_tables:
            continue

        # Check if this is an F3 data table (6 columns, "SECTIUNEA TEHNICA" in row 0)
        is_f3_data = False
        for cell in cells:
            if cell.get('row_index') == 0 and cell.get('column_index') == 0:
                content = cell.get('content', '').strip()
                if 'SECTIUNEA' in content.upper():
                    is_f3_data = True
                    break

        if not is_f3_data:
            continue

        # Find the preceding metadata table to get deviz
        deviz_cod = ""
        deviz_den = ""

        for meta_idx in sorted(metadata_to_deviz.keys(), reverse=True):
            if meta_idx < table_idx:
                deviz_cod, deviz_den = metadata_to_deviz[meta_idx]
                logger.debug(f"[TABLE] Tabel {table_idx} (data): Usando deviz from Table {meta_idx}: {deviz_cod}")
                break

        if not deviz_cod:
            logger.debug(f"[TABLE] Tabel {table_idx}: No preceding metadata found")
            continue

        # Extract articles with this deviz
        articole = extract_articles_from_tables([table], deviz_cod, deviz_den)
        all_articole.extend(articole)
        processed_tables.add(table_idx)

        if articole:
            logger.info(f"[TABLE] Tabel {table_idx}: {len(articole)} articole, deviz {deviz_cod}")

    return all_articole
