"""Document type detection via fingerprinting.

Analyzes document structure (tables, pages, text density) to identify
document type (e.g., BR_CONSOLIDATED, DT_STREETS, CM_HIERARCHICAL).
"""
import json
import logging
from pathlib import Path
from typing import Dict, Tuple, Optional

logger = logging.getLogger(__name__)

FINGERPRINTS_PATH = Path(__file__).parent / "extraction_fingerprints.json"


class TemplateDetector:
    """Fingerprints document structure to identify document type.

    Extracts features from first 5 pages:
    - num_pages: total page count
    - num_tables: total table count
    - primary_table_cols: column count of largest table
    - primary_table_rows: row count of largest table
    - text_density: average lines per page
    - has_multicolumn_primary: whether largest table has 4+ columns
    """

    def __init__(self):
        """Initialize with fingerprints from JSON."""
        self.fingerprints = self._load_fingerprints()

    def _load_fingerprints(self) -> Dict:
        """Load known fingerprints from extraction_fingerprints.json."""
        if not FINGERPRINTS_PATH.exists():
            logger.warning(f"Fingerprints file not found: {FINGERPRINTS_PATH}")
            return {
                "UNKNOWN": {
                    "description": "Fallback template for unknown documents",
                    "features": {},
                    "accuracy": 0.0
                }
            }

        try:
            with open(FINGERPRINTS_PATH, 'r', encoding='utf-8') as f:
                templates = json.load(f)
                return templates if isinstance(templates, dict) else {"UNKNOWN": {}}
        except Exception as e:
            logger.error(f"Failed to load fingerprints: {e}")
            return {
                "UNKNOWN": {
                    "description": "Fallback template for unknown documents",
                    "features": {},
                    "accuracy": 0.0
                }
            }

    def detect_template(self, di_json: Dict) -> Tuple[str, Dict, float]:
        """Detect document type from di structure.

        Args:
            di_json: Document info dict with 'pages' and 'tables'

        Returns:
            (template_id, fingerprint_dict, certainty_score)
            - template_id: str (e.g., "BR_CONSOLIDATED", "UNKNOWN")
            - fingerprint_dict: extracted features
            - certainty_score: float in [0.0, 1.0]
        """
        fingerprint = self._extract_fingerprint(di_json)

        # Try to match against known templates
        best_match = None
        best_score = 0.0

        for template_id, template_def in self.fingerprints.items():
            if template_id == "UNKNOWN":
                continue

            score = self._calculate_match_score(
                fingerprint,
                template_def.get("features", {})
            )

            if score > best_score:
                best_score = score
                best_match = template_id

        # Use best match if certainty >= 0.7, else UNKNOWN
        if best_match and best_score >= 0.7:
            return best_match, fingerprint, best_score

        return "UNKNOWN", fingerprint, best_score

    def _extract_fingerprint(self, di_json: Dict) -> Dict:
        """Extract structural features from document.

        Features extracted from first 5 pages:
        - num_pages: total page count
        - num_tables: total table count in document
        - primary_table_cols: max column count
        - primary_table_rows: max row count
        - text_density: average lines per page (first 5)
        - has_multicolumn_primary: primary table has 4+ cols
        """
        pages = di_json.get("pages", [])
        tables = di_json.get("tables", [])

        # Count total pages
        num_pages = len(pages)

        # Count tables
        num_tables = len(tables)

        # Find primary (largest) table
        primary_table_cols = 0
        primary_table_rows = 0
        if tables:
            largest_table = max(tables, key=lambda t: t.get("row_count", 0) * t.get("column_count", 0))
            primary_table_cols = largest_table.get("column_count", 0)
            primary_table_rows = largest_table.get("row_count", 0)

        # Calculate text density (lines per page on first 5 pages)
        first_5_pages = pages[:5]
        total_lines = 0
        for page in first_5_pages:
            lines = page.get("lines", [])
            total_lines += len([l for l in lines if isinstance(l, str) and l.strip()])

        text_density = total_lines / len(first_5_pages) if first_5_pages else 0.0

        has_multicolumn_primary = primary_table_cols >= 4

        return {
            "num_pages": num_pages,
            "num_tables": num_tables,
            "primary_table_cols": primary_table_cols,
            "primary_table_rows": primary_table_rows,
            "text_density": round(text_density, 2),
            "has_multicolumn_primary": has_multicolumn_primary
        }

    def _calculate_match_score(self, fingerprint: Dict, template_features: Dict) -> float:
        """Calculate similarity between extracted fingerprint and template features.

        Uses feature-by-feature comparison with weighted thresholds.
        Score in [0.0, 1.0].
        """
        if not template_features:
            return 0.0

        scores = []
        weights = []

        # num_pages: within ±20% range
        if "num_pages" in template_features:
            exp_pages = template_features["num_pages"]
            actual_pages = fingerprint.get("num_pages", 0)
            if exp_pages > 0:
                page_ratio = actual_pages / exp_pages
                page_score = max(0.0, 1.0 - abs(page_ratio - 1.0) / 0.2)
                scores.append(min(1.0, page_score))
                weights.append(0.15)

        # num_tables: exact match or within 1
        if "num_tables" in template_features:
            exp_tables = template_features["num_tables"]
            actual_tables = fingerprint.get("num_tables", 0)
            table_diff = abs(exp_tables - actual_tables)
            table_score = 1.0 if table_diff <= 1 else max(0.0, 1.0 - (table_diff - 1) / 5.0)
            scores.append(table_score)
            weights.append(0.15)

        # primary_table_cols: within ±1 column
        if "primary_table_cols" in template_features:
            exp_cols = template_features["primary_table_cols"]
            actual_cols = fingerprint.get("primary_table_cols", 0)
            col_diff = abs(exp_cols - actual_cols)
            col_score = 1.0 if col_diff <= 1 else max(0.0, 1.0 - col_diff / 3.0)
            scores.append(col_score)
            weights.append(0.20)

        # primary_table_rows: within ±10%
        if "primary_table_rows" in template_features:
            exp_rows = template_features["primary_table_rows"]
            actual_rows = fingerprint.get("primary_table_rows", 0)
            if exp_rows > 0:
                row_ratio = actual_rows / exp_rows
                row_score = max(0.0, 1.0 - abs(row_ratio - 1.0) / 0.1)
                scores.append(min(1.0, row_score))
                weights.append(0.15)

        # text_density: within ±30%
        if "text_density" in template_features:
            exp_density = template_features["text_density"]
            actual_density = fingerprint.get("text_density", 0.0)
            if exp_density > 0.0:
                density_ratio = actual_density / exp_density
                density_score = max(0.0, 1.0 - abs(density_ratio - 1.0) / 0.3)
                scores.append(min(1.0, density_score))
                weights.append(0.15)

        # has_multicolumn_primary: boolean match
        if "has_multicolumn_primary" in template_features:
            exp_multicolumn = template_features["has_multicolumn_primary"]
            actual_multicolumn = fingerprint.get("has_multicolumn_primary", False)
            multicolumn_score = 1.0 if exp_multicolumn == actual_multicolumn else 0.0
            scores.append(multicolumn_score)
            weights.append(0.20)

        # Weighted average
        if not scores:
            return 0.0

        total_weight = sum(weights)
        if total_weight == 0:
            return 0.0

        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        return weighted_sum / total_weight
