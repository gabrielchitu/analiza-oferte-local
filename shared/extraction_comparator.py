from typing import List, Dict, Tuple
from difflib import SequenceMatcher


class ExtractionComparator:
    """Compare table vs regex extractions, pick best match."""

    def compare(
        self, table_articles: List[Dict], regex_articles: List[Dict]
    ) -> Tuple[List[Dict], str, float]:
        """
        Compare extractions and pick best.

        Returns: (best_articles, source_method, confidence)
        """
        table_count = len(table_articles)
        regex_count = len(regex_articles)

        # If only one source has articles, use it
        if table_count > 0 and regex_count == 0:
            return table_articles, "TABLE", self._avg_confidence(table_articles)

        if regex_count > 0 and table_count == 0:
            return regex_articles, "REGEX", self._avg_confidence(regex_articles)

        if table_count == 0 and regex_count == 0:
            return [], "NONE", 0.0

        # Both present: compare quality
        similarity = self._calculate_similarity(table_articles, regex_articles)

        if similarity > 0.85:
            # Counts are similar, pick higher confidence
            table_conf = self._avg_confidence(table_articles)
            regex_conf = self._avg_confidence(regex_articles)

            if table_conf >= regex_conf:
                return table_articles, "TABLE", table_conf
            else:
                return regex_articles, "REGEX", regex_conf
        else:
            # Counts differ, prefer table (more structured)
            return table_articles, "TABLE", self._avg_confidence(table_articles)

    def _avg_confidence(self, articles: List[Dict]) -> float:
        """Calculate average confidence across articles."""
        if not articles:
            return 0.0
        confidences = [a.get("confidence", 0.5) for a in articles]
        return sum(confidences) / len(confidences)

    def _calculate_similarity(
        self, table_articles: List[Dict], regex_articles: List[Dict]
    ) -> float:
        """Calculate similarity between two extractions."""
        # Compare by count first
        count_diff = abs(len(table_articles) - len(regex_articles))
        if count_diff > 2:
            return 0.0  # Too different in count

        # Compare by description similarity
        if not table_articles or not regex_articles:
            return 0.0

        # Match articles by NR
        matched = 0
        for table_art in table_articles:
            for regex_art in regex_articles:
                if table_art["nr"] == regex_art["nr"]:
                    # Check description similarity using SequenceMatcher
                    desc_sim = SequenceMatcher(
                        None,
                        table_art.get("descriere_normalized", ""),
                        regex_art.get("descriere_normalized", ""),
                    ).ratio()

                    if desc_sim > 0.85:
                        matched += 1
                    break

        if len(table_articles) == 0:
            return 0.0

        return matched / len(table_articles)
