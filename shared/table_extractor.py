"""
TableExtractor: Parse Azure Document Intelligence table structures (cells with rowIndex/columnIndex)
to extract articles with hierarchy detection and confidence scoring.

Maps table cells by row/column to standardized article format with optional parent-child relationships.
"""

import re
from typing import List, Dict, Tuple, Optional


# Mapping of unit variations to normalized form
UM_KNOWN = {
    "buc": "buc",
    "bucată": "buc",
    "bucati": "buc",
    "t": "t",
    "ton": "t",
    "tone": "t",
    "ml": "ml",
    "mp": "mp",
    "m2": "m2",
    "m²": "m2",
    "kg": "kg",
    "l": "l",
    "litru": "l",
    "litri": "l",
    "litru/s": "l",
    "mc": "mc",
    "m3": "mc",
    "m³": "mc",
    "m": "m",
    "metru": "m",
    "metri": "m",
    "km": "km",
    "kilometru": "km",
}


class TableExtractor:
    """
    Extract articles from Azure Document Intelligence table structures.

    Expected table format: cells list with rowIndex, columnIndex, content.
    Header row identifies columns: NR, DESCRIERE, UM, CANT (or CANTITATE).
    Article rows follow header, one per row.
    """

    def __init__(self):
        self.header_row = None
        self.column_map = {}

    def extract(self, table: Dict) -> Tuple[List[Dict], Dict, float]:
        """
        Extract articles from table.

        Args:
            table: Dict with 'cells' list, each cell has rowIndex, columnIndex, content

        Returns:
            (articles_list, hierarchy_dict, confidence_float)
            - articles_list: List of article dicts with nr, descriere, um, cant_numeric, etc.
            - hierarchy_dict: Maps article_nr → parent_nr (None if root)
            - confidence_float: Overall extraction confidence (0.0-1.0)
        """
        if not table or "cells" not in table:
            return [], {}, 0.0

        cells = table["cells"]
        if not cells:
            return [], {}, 0.0

        # Organize cells by row
        rows = self._organize_by_row(cells)
        if not rows:
            return [], {}, 0.0

        # Find header row
        header_idx = self._find_header_row(rows)
        if header_idx is None:
            return [], {}, 0.0

        self.header_row = rows[header_idx]
        self._build_column_map(self.header_row)

        # Extract articles from remaining rows
        articles = []
        for row_idx in sorted(rows.keys()):
            if row_idx <= header_idx:
                continue

            row = rows[row_idx]
            article = self._extract_article(row)
            if article:
                articles.append(article)

        # Detect parent-child relationships
        self._detect_hierarchy(articles)

        # Calculate overall confidence
        confidence = self._calculate_confidence(articles)

        # Build hierarchy dict
        hierarchy = {art.get("nr"): art.get("parent_nr") for art in articles}

        return articles, hierarchy, confidence

    def _organize_by_row(self, cells: List[Dict]) -> Dict[int, Dict[int, str]]:
        """
        Organize cells by rowIndex.

        Returns:
            Dict[rowIndex] → Dict[columnIndex] → content_string
        """
        rows = {}
        for cell in cells:
            row_idx = cell.get("rowIndex")
            col_idx = cell.get("columnIndex")
            content = cell.get("content", "").strip()

            if row_idx is None or col_idx is None:
                continue

            if row_idx not in rows:
                rows[row_idx] = {}

            rows[row_idx][col_idx] = content

        return rows

    def _find_header_row(self, rows: Dict[int, Dict[int, str]]) -> Optional[int]:
        """
        Find header row by looking for NR, DESCRIERE, UM, CANT keywords.

        Returns:
            rowIndex of header row, or None if not found
        """
        for row_idx in sorted(rows.keys()):
            row = rows[row_idx]
            row_text = " ".join(row.values()).upper()

            # Check for header keywords
            has_nr = any("NR" in cell.upper() for cell in row.values())
            has_descriere = any("DESCRIERE" in cell.upper() for cell in row.values())
            has_um = any(cell.upper() in ["UM", "U.M."] for cell in row.values())
            has_cant = any(
                cell.upper() in ["CANT", "CANTITATE", "CANT.", "CANT.TATEA"]
                for cell in row.values()
            )

            if has_nr and has_descriere and has_um and has_cant:
                return row_idx

        return None

    def _build_column_map(self, header_row: Dict[int, str]) -> None:
        """
        Build mapping: column_name → columnIndex.

        Populates self.column_map: {nr_col, descriere_col, um_col, cant_col}
        """
        self.column_map = {}

        for col_idx, content in header_row.items():
            upper = content.upper().strip()

            if upper == "NR":
                self.column_map["nr"] = col_idx
            elif upper == "DESCRIERE":
                self.column_map["descriere"] = col_idx
            elif upper in ["UM", "U.M."]:
                self.column_map["um"] = col_idx
            elif upper in ["CANT", "CANTITATE", "CANT.", "CANT.TATEA"]:
                self.column_map["cant"] = col_idx

    def _extract_article(self, row: Dict[int, str]) -> Optional[Dict]:
        """
        Extract one article from table row.

        Returns:
            Dict with: nr, descriere, um, cant_numeric, extraction_source, confidence,
            descriere_normalized, um_normalized, comparison_key, parent_nr, is_component
            Or None if critical fields missing.
        """
        # Get fields from column map
        nr = row.get(self.column_map.get("nr"), "").strip()
        descriere = row.get(self.column_map.get("descriere"), "").strip()
        um_raw = row.get(self.column_map.get("um"), "").strip()
        cant_raw = row.get(self.column_map.get("cant"), "").strip()

        # Require at least NR and DESCRIERE
        if not nr or not descriere:
            return None

        # Normalize UM
        um_normalized = self._normalize_um(um_raw) if um_raw else None
        um = self._map_um(um_raw) if um_raw else None

        # Parse quantity
        cant_numeric = None
        if cant_raw:
            try:
                cant_numeric = float(cant_raw.replace(",", "."))
            except (ValueError, AttributeError):
                pass

        # Normalize description
        descriere_normalized = self._normalize_descriere(descriere)

        # Build comparison key
        comparison_key = (
            f"{nr}#{descriere_normalized}#{um_normalized}" if um_normalized else f"{nr}#{descriere_normalized}"
        )

        return {
            "nr": nr,
            "descriere": descriere,
            "descriere_normalized": descriere_normalized,
            "um": um,
            "um_normalized": um_normalized,
            "cant": cant_raw,
            "cant_numeric": cant_numeric,
            "extraction_source": "TABLE",
            "confidence": 0.95,  # Tables are highly reliable
            "comparison_key": comparison_key,
            "parent_nr": None,
            "is_component": False,
        }

    def _normalize_descriere(self, text: str) -> str:
        """Normalize DENUMIRE for matching: lowercase, spaces, special characters.

        Resolves: "ROBINET 1/2\"" vs "ROBINET 1/2" (quote char variation)
                  "PLASA ZN.MONT. LA" vs "PLASA ZN.MONT.LA" (spaces)
                  "BST500 8 MM" vs "BST500 8 mm" (case)
        """
        if not text:
            return text
        # lowercase
        text = text.lower()
        # normalize quotes: " → ', and other variations
        text = text.replace('"', "'").replace('"', "'").replace('"', "'")
        # remove dots after letters (ex: "INOX." → "INOX", "M." → "M")
        text = re.sub(r'([A-Z])\.\s+', r'\1 ', text, flags=re.IGNORECASE)
        # remove multiple spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _normalize_um(self, um: str) -> str:
        """Normalize unit of measure for comparison.

        Handles common variations:
        - m cub, m3 → mc (cubic meters)
        - mp, m² → mp (square meters)
        - buc, bucata → buc (pieces)
        - ml, litru → ml
        - empty/None → "" (preserve empty)
        """
        if not um:
            return ""

        um = um.lower().strip()

        # Cubic meters: "m cub", "m3", "mc"
        if um in ["m cub", "m3", "mc"]:
            return "mc"
        # Square meters: "mp", "m2", "m²"
        if um in ["mp", "m2", "m²"]:
            return "mp"
        # Pieces: "buc", "bucata", "bucați"
        if um in ["buc", "bucata", "bucati", "bucații"]:
            return "buc"
        # Milliliters: "ml"
        if um in ["ml"]:
            return "ml"
        # Liters: "l", "litru", "litri"
        if um in ["l", "litru", "litri"]:
            return "l"

        return um

    def _map_um(self, um_raw: str) -> Optional[str]:
        """
        Map raw UM string to normalized form using UM_KNOWN.

        Args:
            um_raw: Raw unit string (e.g., "T", "litru", "m2")

        Returns:
            Normalized unit, or original if not in UM_KNOWN
        """
        normalized = um_raw.lower().strip()
        return UM_KNOWN.get(normalized, um_raw)

    def _detect_hierarchy(self, articles: List[Dict]) -> None:
        """
        Mark parent-child relationships based on NR format.

        If NR contains ".", it's a subcomponent (e.g., "1.1" is child of "1").
        """
        nr_to_article = {art["nr"]: art for art in articles}

        for article in articles:
            nr = article["nr"]

            # Check for subcomponent pattern: "N.M" or "N.M.K", etc.
            if "." in nr:
                # Extract parent NR (everything before last dot)
                parts = nr.split(".")
                if len(parts) >= 2:
                    parent_nr = parts[0]
                    if parent_nr in nr_to_article:
                        article["parent_nr"] = parent_nr
                        article["is_component"] = True

    def _calculate_confidence(self, articles: List[Dict]) -> float:
        """
        Calculate overall extraction confidence based on field completeness.

        Returns:
            Confidence score 0.0-1.0. 1.0 = all articles have all fields.
        """
        if not articles:
            return 0.0

        total_score = 0.0

        for article in articles:
            score = 0.0

            # Base: all articles must have nr + descriere (checked in _extract_article)
            score += 0.4

            # +0.2 if UM present
            if article.get("um"):
                score += 0.2

            # +0.2 if CANT present
            if article.get("cant_numeric") is not None:
                score += 0.2

            # +0.2 if comparison_key present
            if article.get("comparison_key"):
                score += 0.2

            total_score += score

        # Average across all articles
        avg_score = total_score / len(articles) if articles else 0.0

        return min(1.0, avg_score)
