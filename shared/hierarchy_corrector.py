"""Hierarchy Corrector - orchestrates hierarchy analysis and correction.

This module provides a single entry point for hierarchy correction:
1. Detect broken parent-child relationships
2. Fix hierarchy using forward fill with group awareness
3. Validate corrected hierarchies
4. Return statistics and corrected articles
"""

from typing import Dict, List, Tuple, Optional
from shared.hierarchy_analyzer import (
    detect_broken_hierarchy,
    fix_hierarchy_ffill,
    validate_hierarchy,
)


class HierarchyCorrector:
    """Orchestrator for hierarchy detection, correction, and validation.

    Workflow:
    1. detect() — find broken hierarchies
    2. correct() — fix with ffill
    3. validate() — check constraints
    4. Return corrected articles + statistics
    """

    def __init__(self):
        """Initialize corrector with empty stats."""
        self.stats = {
            "detected": 0,
            "corrected": 0,
            "validation_pass": False,
            "validation_errors": 0,
            "validation_errors_list": [],
        }

    def correct(self, articles: List[Dict]) -> Tuple[List[Dict], Dict]:
        """Detect, fix, and validate hierarchy in a list of articles.

        Args:
            articles: List of article dictionaries with keys: nr, parent_nr, is_component
                      (If 'nr' field is missing, uses 'cod' or 'nr_ordine' as fallback)

        Returns:
            Tuple of:
            - corrected_articles: List with fixed parent_nr and hierarchy_corrected field
            - stats: Dictionary with detected, corrected, validation_pass counts
        """
        # Reset stats
        self.stats = {
            "detected": 0,
            "corrected": 0,
            "validation_pass": False,
            "validation_errors": 0,
            "validation_errors_list": [],
        }

        # Handle empty list
        if not articles:
            self.stats["validation_pass"] = True
            return [], self.stats

        # Normalize articles: if 'nr' is missing, use 'cod' or 'nr_ordine'
        normalized_articles = self._normalize_article_fields(articles)

        # Step 1: Detect broken hierarchies
        issues = detect_broken_hierarchy(normalized_articles)
        self.stats["detected"] = len(issues)

        # Step 2: Fix hierarchy using ffill
        corrected = fix_hierarchy_ffill(normalized_articles)

        # Count how many articles were corrected
        self.stats["corrected"] = sum(
            1 for a in corrected if a.get("hierarchy_corrected") is True
        )

        # Step 3: Validate corrected hierarchies
        validation = validate_hierarchy(corrected)
        self.stats["validation_pass"] = validation["is_valid"]
        self.stats["validation_errors"] = validation["error_count"]
        self.stats["validation_errors_list"] = validation["errors"]

        # Restore original fields (if we normalized them)
        result_articles = self._denormalize_article_fields(corrected, articles)

        return result_articles, self.stats

    def get_stats(self) -> Dict:
        """Return current statistics."""
        return self.stats.copy()

    def reset(self) -> None:
        """Reset statistics."""
        self.stats = {
            "detected": 0,
            "corrected": 0,
            "validation_pass": False,
            "validation_errors": 0,
            "validation_errors_list": [],
        }

    def _normalize_article_fields(self, articles: List[Dict]) -> List[Dict]:
        """Normalize article fields for hierarchy analysis.

        If 'nr' field is missing, use 'cod' (code) or 'nr_ordine' (order number) as fallback.
        This ensures compatibility with different article formats (extraction_v2 format vs old format).

        Args:
            articles: Original articles with potentially missing 'nr' field

        Returns:
            Normalized articles with 'nr' field guaranteed
        """
        normalized = []
        for article in articles:
            art_copy = article.copy()

            # If 'nr' is missing, try 'cod' or 'nr_ordine'
            if "nr" not in art_copy or art_copy.get("nr") is None:
                if "cod" in art_copy and art_copy.get("cod"):
                    art_copy["nr"] = str(art_copy["cod"])
                elif "nr_ordine" in art_copy and art_copy.get("nr_ordine") is not None:
                    art_copy["nr"] = str(art_copy["nr_ordine"])
                else:
                    # Fallback: generate synthetic NR from index
                    art_copy["nr"] = f"_generated_{len(normalized)}"

            normalized.append(art_copy)

        return normalized

    def _denormalize_article_fields(
        self, corrected_articles: List[Dict], original_articles: List[Dict]
    ) -> List[Dict]:
        """Restore original article fields after hierarchy correction.

        Maps corrected articles back to original structure while preserving
        the hierarchy_corrected and parent_nr fields.

        Args:
            corrected_articles: Articles after hierarchy correction (may have added 'nr' field)
            original_articles: Original articles before normalization

        Returns:
            Articles with corrected hierarchy fields but original structure
        """
        if not original_articles:
            return corrected_articles

        # If original articles had 'nr' field, return corrected as-is
        if original_articles and "nr" in original_articles[0]:
            return corrected_articles

        # Otherwise, merge corrected fields back into original structure
        result = []
        for idx, original in enumerate(original_articles):
            if idx < len(corrected_articles):
                corrected = corrected_articles[idx]
                merged = original.copy()

                # Preserve corrected hierarchy fields
                merged["parent_nr"] = corrected.get("parent_nr")
                merged["hierarchy_corrected"] = corrected.get("hierarchy_corrected", False)

                result.append(merged)
            else:
                result.append(original)

        return result
