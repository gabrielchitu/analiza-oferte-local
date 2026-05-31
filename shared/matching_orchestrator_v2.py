"""Orchestrator for v2 set-based matching pipeline.

Provides MatchingOrchestratorV2 class that integrates extracted reference
and offer data into a holistic JSON result with matching statistics.

Entry point: orchestrator.match(ref_extracted, oferta_extracted)
"""

from typing import Dict
from shared.holistic_generator import generate_holistic_v2


class MatchingOrchestratorV2:
    """Orchestrator for v2 set-based matching pipeline.

    Coordinates group and article matching from v2 extraction output
    into a single holistic JSON with matched/ref_only/oferta_only groups.

    Workflow:
    1. Accept ref_extracted and oferta_extracted (output from ExtractionOrchestrator)
    2. Call generate_holistic_v2() to perform set-based matching
    3. Extract and cache matching statistics
    4. Return v1-compatible holistic JSON

    Example:
        orchestrator = MatchingOrchestratorV2()
        holistic = orchestrator.match(ref_extracted, oferta_extracted)
        print(orchestrator.stats)  # Access cached statistics
    """

    def __init__(self):
        """Initialize orchestrator with empty statistics."""
        self.stats = {
            "matched_groups": 0,
            "ref_only_groups": 0,
            "oferta_only_groups": 0,
            "matched_articles": 0,
            "ref_only_articles": 0,
            "oferta_only_articles": 0,
        }

    def match(self, ref_extracted: Dict, oferta_extracted: Dict) -> Dict:
        """
        Match extracted reference with offer using set-based matching.

        Performs group-level matching by deviz_cod, then article-level
        matching within each matched group. Returns v1-compatible holistic JSON.

        Args:
            ref_extracted: Extracted reference data from ExtractionOrchestrator.
                          Must have structure:
                          {
                              "client": str,
                              "di_file": str,
                              "extraction_version": "2.0",
                              "grupos": [group_dict, ...]
                          }
            oferta_extracted: Extracted offer data (same structure as ref_extracted)

        Returns:
            Dict with v1-compatible holistic structure:
            {
                "client": str,
                "di_file": str,
                "extraction_version": "2.0",
                "matched_groups": [matched_group_dict, ...],
                "ref_only_groups": [group_dict, ...],
                "oferta_only_groups": [group_dict, ...],
                "stats": {
                    "matched_articles_count": int,
                    "ref_only_articles_count": int,
                    "oferta_only_articles_count": int,
                    "matched_groups_count": int,
                    "ref_only_groups_count": int,
                    "oferta_only_groups_count": int
                }
            }

        Raises:
            KeyError: If ref_extracted or oferta_extracted missing required keys
        """
        # Perform set-based matching
        holistic = generate_holistic_v2(ref_extracted, oferta_extracted)

        # Extract and cache statistics
        stats_dict = holistic.get("stats", {})
        self.stats = {
            "matched_groups": stats_dict.get("matched_groups_count", 0),
            "ref_only_groups": stats_dict.get("ref_only_groups_count", 0),
            "oferta_only_groups": stats_dict.get("oferta_only_groups_count", 0),
            "matched_articles": stats_dict.get("matched_articles_count", 0),
            "ref_only_articles": stats_dict.get("ref_only_articles_count", 0),
            "oferta_only_articles": stats_dict.get("oferta_only_articles_count", 0),
        }

        return holistic

    def get_stats(self) -> Dict:
        """Get cached matching statistics from last match() call.

        Returns:
            Dict with keys: matched_groups, ref_only_groups, oferta_only_groups,
                          matched_articles, ref_only_articles, oferta_only_articles
        """
        return self.stats.copy()
