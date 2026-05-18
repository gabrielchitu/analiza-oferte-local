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


def _normalize_denom(text: str) -> str:
    """Normalizeaza DENUMIRE: lowercase, spații, caractere speciale."""
    if not text:
        return text
    text = text.lower()
    text = text.replace('"', "'").replace('"', "'").replace('"', "'")
    text = re.sub(r'([A-Z])\.\s+', r'\1 ', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _normalize_deviz_cod_table(cod: str) -> str:
    """Normalizeaza cod deviz: 226U38 → 226038 (U→0 for consistency)."""
    if not cod:
        return cod
    return cod.replace('U', '0')

logger = logging.getLogger(__name__)


def _clean_article_code(code: str) -> str:
    """Remove OCR artifacts and variant suffixes from article codes.

    Examples:
    - SE56A# → SE56A (OCR artifact)
    - SC07A-1# → SC07A (variant suffix)
    - SC14A# → SC14A
    """
    if not code:
        return code
    # Remove variant suffix: -\d+# (e.g., -1#, -2#)
    code = re.sub(r'([-]\d+)[#@!]*$', '', code)
    # Remove trailing OCR artifacts: #, @, etc. that appear after valid code
    code = re.sub(r'([A-Z0-9])[#@!]+$', r'\1', code)
    return code


def _parse_article_cell(cell_content: str) -> tuple:
    """
    Parse article cell content: 'CODE - DENOMINATION'
    Returns: (code, denomination) or (None, None)
    """
    if not cell_content or not isinstance(cell_content, str):
        return None, None

    # Match: "CODE - DENOMINATION" with optional code suffix like "-1#"
    # Use " - " (with spaces) to distinguish from "-1#" (part of code without spaces)
    # Pattern: CODE(-SUFFIX#)? - DESCRIPTION
    m = re.match(r'^(\$?\d{4,8}|[A-Z]{2,5}\d{1,4}[A-Z]?(?:-\d+)?(?:#)?|[A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?(?:-\d+)?(?:#)?)\s*[-–]\s*(.+)',
                 cell_content.strip(), re.IGNORECASE)
    if m:
        code = m.group(1).upper()
        # Add $ prefix to numeric codes
        if re.match(r'^\d+$', code):
            code = '$' + code
        denom = m.group(2).strip()
        return code, denom

    # Fallback: try to extract code even without perfect dash separation
    # Handles: "SE56A# - Filtru...", "SC07A-1# - Description..." with various separators
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

    Handles two formats:
    - Format 1 (Reference): Nr. | CODE - NAME | U.M. | Cantitate | Price | Total
    - Format 2 (Oferta 2): Nr. | CODE | NAME | U.M. | Cantitate | Price | Total

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
        col_denom = None  # For format 2 where code and denom are separate

        for col_idx, header in header_row.items():
            if 'NR' in header or header == '0':
                col_nr = col_idx
            elif 'CAPITOL' in header or 'DENUMIRE' in header:
                col_capitol = col_idx
            elif 'U.M' in header or 'UM' in header:
                col_um = col_idx
            elif 'CANTITAT' in header or header == '3':
                col_cant = col_idx

        # Extract data rows BEFORE heuristic check (rows variable used in heuristic)
        rows = {}
        for cell in cells:
            row_idx = cell.get('row_index')
            if row_idx <= 2:
                continue

            if row_idx not in rows:
                rows[row_idx] = {}
            rows[row_idx][cell.get('column_index')] = cell.get('content', '')

        # Fallback: If standard columns not found, try heuristic detection
        # Some tables have sparse headers without explicit CANTITATE/UM labels
        if col_capitol is None or col_um is None or col_cant is None:
            # Try fallback: col_capitol=1, col_cant=3, col_um=4 (if they have data)
            # This handles tables with: Nr. | Code | Empty | Qty | Unit | Empty | Price
            sample_row = rows.get(min(rows.keys())) if rows else {}
            if sample_row and col_capitol is None:
                # Check if col 1 has codes and col 3 has numeric qty
                col_1_content = sample_row.get(1, '')
                col_3_content = sample_row.get(3, '')

                # If col 1 looks like a code (starts with letter or digit) and col 3 has a number
                if col_1_content and re.match(r'^[A-Z0-9]', col_1_content.upper()):
                    if col_3_content and re.search(r'\d', col_3_content):
                        # Likely: col 1 = code, col 3 = qty, col 4 = unit
                        col_capitol = 1
                        col_cant = 3
                        col_um = 4
                        col_denom = None  # Description might be multi-row
                        logger.debug(f"[TABLE] Using heuristic columns: code={col_capitol}, cant={col_cant}, um={col_um}")

            if col_capitol is None or col_um is None or col_cant is None:
                continue

        # Handle case where header has empty columns before actual content
        # Some tables have header col 1 empty, col 2 = "CAPITOLUL", but data in col 1 = code, col 2 = denom
        # Check if column before capitol is empty (has no header content)
        code_col = col_capitol
        has_empty_header_before = False
        if col_capitol > 0:
            prev_header = header_row.get(col_capitol - 1, '')
            if not prev_header or prev_header.strip() == '':
                has_empty_header_before = True
                code_col = col_capitol - 1

        # Detect format 2: Check if code and denom are in separate columns
        # This happens when code is in code_col and denom in the next column
        is_format_2 = False
        col_denom = None

        if rows and code_col is not None:
            first_row = rows.get(min(rows.keys())) if rows else {}
            next_col = code_col + 1

            # Format 2 case 1: empty header before capitol, code in code_col, denom in code_col+1
            if has_empty_header_before and next_col in first_row and first_row[next_col].strip():
                is_format_2 = True
                col_denom = next_col
            # Format 2 case 2: code_col at capitol but denom in col_capitol+1 (DI parser split)
            elif code_col == col_capitol and next_col not in header_row and next_col in first_row and first_row[next_col].strip():
                is_format_2 = True
                col_denom = next_col

        # Process each article row (rows with article codes)
        for row_idx in sorted(rows.keys()):
            row_data = rows[row_idx]

            code = None
            denom = None

            if is_format_2 and col_denom is not None:
                # Format 2: Code and denomination in separate columns
                code_cell = row_data.get(code_col, '').strip() if code_col is not None else ''
                denom_cell = row_data.get(col_denom, '').strip()

                # Extract code from code_cell (may contain extra text like "[1]" or "ASIM")
                code = None
                if code_cell:
                    # Try to extract just the code part, ignoring trailing artifacts
                    # Match: numeric codes (2100910) or alphanumeric codes (IA22C1, TCB40A1)
                    m = re.match(r'^(\$?\d{4,8}|[A-Z]{1,3}\d{1,4}[A-Z]?\d{0,2})\b', code_cell.upper())
                    if m:
                        code = m.group(1)
                        # Add $ prefix to numeric codes (like _parse_article_cell does)
                        if re.match(r'^\d+$', code):
                            code = '$' + code
                    else:
                        # Fallback: clean and use entire cell
                        code = _clean_article_code(code_cell.upper())
                        if code and re.match(r'^\d+$', code):
                            code = '$' + code

                # Use denomination as-is
                if code and denom_cell:
                    denom = denom_cell
            else:
                # Format 1: Combined "CODE - DENOMINATION" in col_capitol
                capitol_cell = row_data.get(col_capitol, '')
                code, denom = _parse_article_cell(capitol_cell)
                # Clean suffix variants: SC07A-1# → SC07A, SE56A# → SE56A
                if code:
                    code = _clean_article_code(code)

            if not code:
                continue

            # Get quantity string (might include unit prefix like "99 M")
            cant_str = row_data.get(col_cant, '').strip()

            # Extract numeric quantity, handling "99 M" format
            # Pattern: one or more digits, optional decimal, optional spaces, optional letters
            cant_match = re.match(r'^([\d,\.]+)\s*[A-Za-z]*', cant_str)
            if cant_match:
                cant_numeric = cant_match.group(1)
            else:
                cant_numeric = cant_str

            try:
                # Handle formats like "198.000" or "198,000" or "99" or "99 M"
                cant_normalized = cant_numeric.replace(',', '.').replace('.', '', 1) if '.' in cant_numeric and ',' in cant_numeric else cant_numeric.replace(',', '.')
                cantitate = float(cant_normalized) if cant_normalized else 0.0
            except ValueError:
                cantitate = 0.0

            # Get UM and normalize (remove dots: "m.c." → "mc")
            # Combine col_um with any unit prefix in cant_str
            um = row_data.get(col_um, '').strip().upper()

            # If cant_str has letters (like "99 M"), add them to the unit
            um_from_cant = re.search(r'([A-Za-z]+)$', cant_str)
            if um_from_cant:
                um = (um_from_cant.group(1) + ' ' + um).strip()

            um = um.replace('.', '')  # Remove dots: M.C. → MC, m.c. → mc
            if not um or um in ('0', '1', '2', '3', '4', '5'):
                um = ''

            # Build article
            art = {
                'cod': code,
                'denumire': _normalize_denom(denom),
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

        deviz_found = None

        # Format 1 (Reference): "Stadiul fizic:" in row 5, col 0 → deviz in row 5, col 1
        for cell in cells:
            if cell.get('row_index') == 5 and cell.get('column_index') == 0:
                content = cell.get('content', '').strip()
                if 'STADIUL' in content.upper():
                    # Extract deviz from row 5, col 1
                    for c in cells:
                        if c.get('row_index') == 5 and c.get('column_index') == 1:
                            content = c.get('content', '').strip()
                            # Parse "226U18 CANALIZARE"
                            m = re.match(r'^([A-Z0-9]{5,8})\s+(.+)$', content)
                            if m:
                                deviz_cod = _normalize_deviz_cod_table(m.group(1).upper())
                                deviz_den = m.group(2).strip()
                                deviz_found = (deviz_cod, deviz_den)
                                logger.debug(f"[TABLE] Tabel {table_idx}: Metadata (format 1) deviz {deviz_cod}")
                            break
                    break

        # Format 2 (Oferta 2): "oferta XXXXX" pattern in ANY cell
        if not deviz_found:
            for cell in cells:
                content = cell.get('content', '').strip().upper()
                if 'OFERTA' in content:
                    # Parse "oferta 226238 MONTAT BOILER"
                    m = re.search(r'oferta\s+([A-Z0-9]{5,8})\s+(.+)', content, re.IGNORECASE)
                    if m:
                        deviz_cod = _normalize_deviz_cod_table(m.group(1).upper())
                        deviz_den = m.group(2).strip()
                        deviz_found = (deviz_cod, deviz_den)
                        logger.debug(f"[TABLE] Tabel {table_idx}: Metadata (format 2 - oferta) deviz {deviz_cod}")
                        break

        if deviz_found:
            metadata_to_deviz[table_idx] = deviz_found

    # Second pass: Find F3 data tables and extract articles
    processed_tables = set()

    for table_idx, table in enumerate(tables):
        cells = table.get('cells', [])
        if not cells:
            continue

        if table_idx in processed_tables:
            continue

        # Check if this is an F3 data table ("SECTIUNEA TEHNICA" OR reference format with "Capitolul" header)
        is_f3_data = False
        for cell in cells:
            if cell.get('row_index') == 0:
                content = cell.get('content', '').strip()
                # Format 1: Standard "SECTIUNEA TEHNICA" header
                if 'SECTIUNEA' in content.upper():
                    is_f3_data = True
                    break
                # Format 2: Reference format with "CAPITOLUL" or "CANTITATEA" header
                if 'CAPITOLUL' in content.upper() or 'CANTITATE' in content.upper():
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
