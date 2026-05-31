"""Tests for set-based article matching using unique keys.

Tests the match_articles_by_key() function which performs set operations
on article keys to produce matched/ref_only/oferta_only results.
"""

import pytest
from shared.set_based_matcher import match_articles_by_key


class TestMatchArticlesByKey:
    """Tests for set-based article matching."""

    def test_basic_matching(self):
        """Should match articles with identical keys."""
        ref_articles = [
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},
            {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500"},
        ]
        oferta_articles = [
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},
            {"nr": "3", "descriere": "NISIP", "um": "M3", "cant": "50"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert len(result["matched"]) == 1
        assert result["matched"][0]["ref"]["nr"] == "1"
        assert result["matched"][0]["oferta"]["nr"] == "1"
        assert len(result["ref_only"]) == 1
        assert result["ref_only"][0]["nr"] == "2"
        assert len(result["oferta_only"]) == 1
        assert result["oferta_only"][0]["nr"] == "3"

    def test_stats_structure(self):
        """Should return proper statistics."""
        ref_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
        ]
        oferta_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)
        stats = result["stats"]

        assert stats["matched_count"] == 1
        assert stats["ref_only_count"] == 1
        assert stats["oferta_only_count"] == 0
        assert stats["ref_total"] == 2
        assert stats["oferta_total"] == 1
        assert stats["ref_articles_count"] == 2
        assert stats["oferta_articles_count"] == 1

    def test_empty_articles(self):
        """Should handle empty article lists."""
        result = match_articles_by_key([], [])

        assert len(result["matched"]) == 0
        assert len(result["ref_only"]) == 0
        assert len(result["oferta_only"]) == 0
        assert result["stats"]["ref_total"] == 0
        assert result["stats"]["oferta_total"] == 0

    def test_all_matched(self):
        """Should match all articles when lists are identical."""
        articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
        ]

        result = match_articles_by_key(articles, articles)

        assert len(result["matched"]) == 2
        assert len(result["ref_only"]) == 0
        assert len(result["oferta_only"]) == 0
        assert result["stats"]["matched_count"] == 2

    def test_no_matches(self):
        """Should produce no matches for disjoint sets."""
        ref = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]
        oferta = [
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
        ]

        result = match_articles_by_key(ref, oferta)

        assert len(result["matched"]) == 0
        assert len(result["ref_only"]) == 1
        assert len(result["oferta_only"]) == 1
        assert result["ref_only"][0]["nr"] == "1"
        assert result["oferta_only"][0]["nr"] == "2"

    def test_deduplication_ref_duplicates(self):
        """Should deduplicate ref articles by key."""
        ref_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]
        oferta_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert result["stats"]["ref_total"] == 1  # Deduped
        assert len(result["matched"]) == 1

    def test_deduplication_oferta_duplicates(self):
        """Should deduplicate oferta articles by key."""
        ref_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]
        oferta_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert result["stats"]["oferta_total"] == 1  # Deduped
        assert len(result["matched"]) == 1

    def test_deduplication_both_sides(self):
        """Should deduplicate on both ref and oferta."""
        ref_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
        ]
        oferta_articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10"},
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
            {"nr": "2", "descriere": "B", "um": "T", "cant": "20"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert result["stats"]["ref_total"] == 2  # 1 and 2
        assert result["stats"]["oferta_total"] == 2  # 1 and 2
        assert len(result["matched"]) == 2
        assert result["stats"]["ref_articles_count"] == 3  # Original count
        assert result["stats"]["oferta_articles_count"] == 3

    def test_matched_preserve_all_fields(self):
        """Matched articles should preserve all original fields."""
        ref_articles = [
            {
                "nr": "1",
                "descriere": "CIMENT",
                "um": "T",
                "cant": "125",
                "cod": "C001",
                "pret": "100",
            },
        ]
        oferta_articles = [
            {
                "nr": "1",
                "descriere": "CIMENT",
                "um": "T",
                "cant": "125",
                "cod": "C001",
                "pret": "120",
            },
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        matched_pair = result["matched"][0]
        assert matched_pair["ref"]["cod"] == "C001"
        assert matched_pair["ref"]["pret"] == "100"
        assert matched_pair["oferta"]["pret"] == "120"

    def test_result_structure(self):
        """Result should have expected top-level keys."""
        ref_articles = [{"nr": "1", "descriere": "A"}]
        oferta_articles = [{"nr": "2", "descriere": "B"}]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert "matched" in result
        assert "ref_only" in result
        assert "oferta_only" in result
        assert "stats" in result
        assert isinstance(result["matched"], list)
        assert isinstance(result["ref_only"], list)
        assert isinstance(result["oferta_only"], list)
        assert isinstance(result["stats"], dict)

    def test_matched_pairs_structure(self):
        """Matched pairs should have 'ref' and 'oferta' keys."""
        ref_articles = [{"nr": "1", "descriere": "A"}]
        oferta_articles = [{"nr": "1", "descriere": "A"}]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert len(result["matched"]) == 1
        pair = result["matched"][0]
        assert "ref" in pair
        assert "oferta" in pair
        assert pair["ref"]["nr"] == "1"
        assert pair["oferta"]["nr"] == "1"

    def test_matching_with_cod_fallback(self):
        """Should match articles using COD when NR is missing."""
        ref_articles = [
            {"nr": None, "cod": "ABC123", "descriere": "A", "um": "T", "cant": "10"},
        ]
        oferta_articles = [
            {"nr": None, "cod": "ABC123", "descriere": "A", "um": "T", "cant": "10"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert len(result["matched"]) == 1
        assert result["matched"][0]["ref"]["cod"] == "ABC123"

    def test_matching_with_hash_fallback(self):
        """Should match articles using hash when NR and COD are missing."""
        ref_articles = [
            {"nr": None, "cod": None, "descriere": "CIMENT", "um": "T", "cant": "10"},
        ]
        oferta_articles = [
            {"nr": None, "cod": None, "descriere": "CIMENT", "um": "T", "cant": "10"},
        ]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert len(result["matched"]) == 1

    def test_sorted_output(self):
        """Result lists should be sorted by key for consistency."""
        ref_articles = [
            {"nr": "3", "descriere": "C"},
            {"nr": "1", "descriere": "A"},
            {"nr": "2", "descriere": "B"},
        ]
        oferta_articles = []

        result = match_articles_by_key(ref_articles, oferta_articles)

        ref_only = result["ref_only"]
        keys = [art["nr"] for art in ref_only]
        assert keys == ["1", "2", "3"], "ref_only should be sorted by key"

    def test_large_article_set(self):
        """Should handle larger article sets."""
        ref_articles = [{"nr": str(i), "descriere": f"Art{i}"} for i in range(100)]
        oferta_articles = [{"nr": str(i), "descriere": f"Art{i}"} for i in range(50, 150)]

        result = match_articles_by_key(ref_articles, oferta_articles)

        assert len(result["matched"]) == 50  # Keys 50-99
        assert len(result["ref_only"]) == 50  # Keys 0-49
        assert len(result["oferta_only"]) == 50  # Keys 100-149
        assert result["stats"]["matched_count"] == 50
        assert result["stats"]["ref_total"] == 100
        assert result["stats"]["oferta_total"] == 100
