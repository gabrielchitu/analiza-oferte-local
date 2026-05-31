"""ExtractionOrchestrator - unified extraction pipeline v2.

Coordinates all extraction components (TemplateDetector, TableExtractor,
RegexExtractor, ExtractionComparator, DevizHeaderExtractor) into a single
entry point for article extraction from DI JSON files.
"""

import json
import logging
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from shared.template_detector import TemplateDetector
from shared.table_extractor import TableExtractor
from shared.extraction_comparator import ExtractionComparator
from shared.f3_regex_parser import extract_articles_regex
from shared.deviz_header_extractor import extract_deviz_headers
from shared.hierarchy_corrector import HierarchyCorrector

logger = logging.getLogger(__name__)


class ExtractionOrchestrator:
    """Orchestrate full extraction pipeline (v2).

    Workflow:
    1. Detect template (document type fingerprinting)
    2. Extract headers (deviz_cod, categoria)
    3. Per-page extraction (table + regex)
    4. Compare and pick best source
    5. Consolidate by group
    6. Return unified result
    """

    def __init__(self):
        """Initialize all sub-components."""
        self.template_detector = TemplateDetector()
        self.table_extractor = TableExtractor()
        self.extraction_comparator = ExtractionComparator()
        self.hierarchy_corrector = HierarchyCorrector()
        self.extraction_log = {"client": "", "pages": []}

    def extract_from_di(self, di_json: Dict, client_name: str) -> Dict:
        """Extract articles from DI JSON file.

        Args:
            di_json: Document info dict with 'pages' and optional 'tables'
            client_name: Name of client (for logging and result metadata)

        Returns:
            Dict with structure:
            {
                "client": str,
                "di_file": str,
                "extraction_version": "2.0",
                "template_id": str,
                "grupos": [
                    {
                        "deviz_cod": str,
                        "deviz_den": str,
                        "source_pages": [int],
                        "articole": [article_dict],
                        ...
                    }
                ]
            }
        """
        self.extraction_log = {"client": client_name, "pages": []}

        # Step 1: Detect template
        template_id, fingerprint, certainty = self.template_detector.detect_template(
            di_json
        )
        logger.info(
            f"Template detection: {template_id} (certainty={certainty:.2f})"
        )

        # Step 2: Extract headers (deviz_cod, categoria)
        # extract_deviz_headers expects page_classifications list
        # For now, we'll use a simpler approach: extract all articles first, then group
        pages = di_json.get("pages", [])

        # Step 3: Extract articles per page and log
        all_best_articles = []
        source_pages = []

        for page_idx, page in enumerate(pages):
            page_articles_table = []
            page_articles_regex = []

            # Try table extraction
            if "tables" in page and page.get("tables"):
                for table in page["tables"]:
                    table_articles, _, _ = self.table_extractor.extract(table)
                    page_articles_table.extend(table_articles)

            # Try regex extraction
            page_text = page.get("content", "")
            page_lines = page.get("lines", [])

            # Convert lines from dict format to strings
            # Lines in DI JSON are dicts with 'content' key
            lines_to_parse = []
            if page_lines:
                for line_item in page_lines:
                    if isinstance(line_item, dict):
                        # Extract content from dict
                        content = line_item.get("content", "")
                        if content:
                            lines_to_parse.append(content)
                    elif isinstance(line_item, str):
                        # Already a string
                        if line_item.strip():
                            lines_to_parse.append(line_item)

            # Fallback to page content if no lines
            if not lines_to_parse and page_text:
                lines_to_parse = page_text.split("\n")

            if lines_to_parse:
                # Use a generic deviz_cod for regex extraction
                page_deviz_cod = page.get("deviz_cod", f"PAGE_{page_idx}")
                page_deviz_den = page.get("deviz_den", "")
                page_articles_regex = extract_articles_regex(
                    lines_to_parse, page_deviz_cod, page_deviz_den
                )

            # Step 4: Compare and pick best
            best_articles, source, confidence = self.extraction_comparator.compare(
                page_articles_table, page_articles_regex
            )

            all_best_articles.extend(best_articles)
            if best_articles:
                source_pages.append(page_idx)

            # Log extraction
            self.extraction_log["pages"].append(
                {
                    "page_idx": page_idx,
                    "template_id": template_id,
                    "source_won": source,
                    "table_article_count": len(page_articles_table),
                    "regex_article_count": len(page_articles_regex),
                    "best_article_count": len(best_articles),
                    "confidence": confidence,
                }
            )

        # Step 5: Consolidate by group
        # For simplicity, create a single group with all articles
        # A more sophisticated approach would group by deviz_cod
        grupos = []

        if all_best_articles:
            # Step 5a: Apply hierarchy correction to articles in the group
            corrected_articles, hierarchy_stats = self.hierarchy_corrector.correct(
                all_best_articles
            )

            grupo = {
                "deviz_cod": "CONSOLIDATED",
                "deviz_den": "",
                "source_pages": source_pages,
                "articole": corrected_articles,
                "article_count": len(corrected_articles),
                "hierarchy_stats": hierarchy_stats,
            }
            grupos.append(grupo)

        # Step 6: Return unified result
        return {
            "client": client_name,
            "di_file": "unknown",
            "extraction_version": "2.0",
            "template_id": template_id,
            "template_certainty": certainty,
            "grupos": grupos,
        }

    def get_extraction_log(self) -> Dict:
        """Return extraction metadata log."""
        return self.extraction_log

    def save_extraction_log(self, filepath: str) -> None:
        """Save extraction log to JSON file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.extraction_log, f, indent=2, ensure_ascii=False)
        logger.info(f"Extraction log saved to {filepath}")
