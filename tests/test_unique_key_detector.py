"""Tests for unique key detection in set-based matching.

Tests priority: NR → COD → hash(descriere+um+cant)
"""

import pytest
from shared.unique_key_detector import (
    detect_article_key,
    detect_article_keys,
    get_unique_articles,
)


class TestDetectArticleKey:
    """Tests for single article key detection."""

    def test_detect_key_from_nr(self):
        """NR takes priority over all other fields."""
        article = {
            "nr": "1",
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": "ABC123",
        }
        key = detect_article_key(article)
        assert key == "1", "NR should be returned as-is"

    def test_detect_key_from_cod_when_nr_missing(self):
        """COD is fallback when NR is missing."""
        article = {
            "nr": None,
            "descriere": "OTEL",
            "um": "KG",
            "cant": "500",
            "cod": "XYZ789",
        }
        key = detect_article_key(article)
        assert key == "XYZ789", "COD should be returned when NR is None"

    def test_detect_key_from_cod_when_nr_empty_string(self):
        """COD is fallback when NR is empty string."""
        article = {
            "nr": "",
            "descriere": "NISIP",
            "um": "M3",
            "cant": "50",
            "cod": "QWE456",
        }
        key = detect_article_key(article)
        assert key == "QWE456", "COD should be returned when NR is empty"

    def test_detect_key_from_hash_when_nr_cod_missing(self):
        """Hash is fallback when both NR and COD are missing."""
        article = {
            "nr": None,
            "descriere": "NISIP",
            "um": "M3",
            "cant": "50",
            "cod": None,
        }
        key = detect_article_key(article)
        assert len(key) == 8, "Hash should be 8-char hex"
        assert all(c in "0123456789abcdef" for c in key), "Hash should be hex"

    def test_detect_key_hash_deterministic(self):
        """Hash should be deterministic for same inputs."""
        article1 = {
            "nr": None,
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": None,
        }
        article2 = {
            "nr": None,
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": None,
        }
        key1 = detect_article_key(article1)
        key2 = detect_article_key(article2)
        assert key1 == key2, "Same inputs should produce same hash"

    def test_detect_key_hash_differs_for_different_inputs(self):
        """Hash should differ for different inputs."""
        article1 = {
            "nr": None,
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": None,
        }
        article2 = {
            "nr": None,
            "descriere": "OTEL",
            "um": "KG",
            "cant": "500",
            "cod": None,
        }
        key1 = detect_article_key(article1)
        key2 = detect_article_key(article2)
        assert key1 != key2, "Different inputs should produce different hash"

    def test_detect_key_strips_whitespace(self):
        """NR and COD should be stripped of whitespace."""
        article = {
            "nr": "  1  ",
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": "ABC123",
        }
        key = detect_article_key(article)
        assert key == "1", "NR should be stripped"

    def test_detect_key_handles_numeric_nr(self):
        """NR can be numeric."""
        article = {
            "nr": 1,
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": "ABC123",
        }
        key = detect_article_key(article)
        assert key == "1", "Numeric NR should be converted to string"

    def test_detect_key_case_insensitive_hash(self):
        """Hash should be case-insensitive (lowercase)."""
        article = {
            "nr": None,
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "cod": None,
        }
        key = detect_article_key(article)
        assert key == key.lower(), "Hash should be lowercase"


class TestDetectArticleKeys:
    """Tests for detecting keys for multiple articles."""

    def test_detect_keys_for_multiple_articles(self):
        """Should detect keys for list of articles."""
        articles = [
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125", "cod": "ABC123"},
            {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500", "cod": "XYZ789"},
            {"nr": None, "descriere": "NISIP", "um": "M3", "cant": "50", "cod": None},
        ]
        keys = detect_article_keys(articles)
        assert len(keys) == 3, "Should detect 3 keys"
        assert keys[0] == "1", "First key should be NR"
        assert keys[1] == "2", "Second key should be NR"
        assert len(keys[2]) == 8, "Third key should be hash"

    def test_detect_keys_empty_list(self):
        """Should handle empty list."""
        keys = detect_article_keys([])
        assert keys == [], "Empty list should return empty keys"

    def test_detect_keys_preserves_order(self):
        """Keys should be in same order as articles."""
        articles = [
            {"nr": "5", "cod": "X"},
            {"nr": "2", "cod": "Y"},
            {"nr": "10", "cod": "Z"},
        ]
        keys = detect_article_keys(articles)
        assert keys == ["5", "2", "10"], "Keys should maintain order"


class TestGetUniqueArticles:
    """Tests for deduplication and unique article extraction."""

    def test_get_unique_articles_removes_duplicates(self):
        """Occurrence-indexed: duplicate nr=1 gets base key '1' and suffix key '1__1'."""
        articles = [
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},  # second occurrence
            {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500"},
        ]
        unique = get_unique_articles(articles)
        assert len(unique) == 3, "Both occurrences preserved + nr=2"
        assert "1" in unique, "First occurrence at base key"
        assert "1__1" in unique, "Second occurrence at suffix key"
        assert "2" in unique, "Key '2' should exist"

    def test_get_unique_articles_first_occurrence_wins(self):
        """First occurrence of duplicate should be preserved."""
        articles = [
            {"nr": "1", "descriere": "CIMENT_V1", "um": "T", "cant": "125"},
            {"nr": "1", "descriere": "CIMENT_V2", "um": "T", "cant": "150"},  # Duplicate
        ]
        unique = get_unique_articles(articles)
        assert unique["1"]["descriere"] == "CIMENT_V1", "First occurrence should win"
        assert unique["1"]["cant"] == "125", "First values should be preserved"

    def test_get_unique_articles_returns_dict(self):
        """Should return dict with key -> article mapping."""
        articles = [
            {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},
            {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500"},
        ]
        unique = get_unique_articles(articles)
        assert isinstance(unique, dict), "Should return dict"
        assert unique["1"]["nr"] == "1", "Dict values should be articles"

    def test_get_unique_articles_empty_list(self):
        """Should handle empty article list."""
        unique = get_unique_articles([])
        assert unique == {}, "Empty list should return empty dict"

    def test_get_unique_articles_hash_keys(self):
        """Occurrence-indexed: hash-keyed duplicate gets base and suffix key."""
        articles = [
            {"nr": None, "descriere": "NISIP", "um": "M3", "cant": "50", "cod": None},
            {"nr": None, "descriere": "NISIP", "um": "M3", "cant": "50", "cod": None},  # second occurrence
            {"nr": None, "descriere": "PIATRA", "um": "M3", "cant": "100", "cod": None},
        ]
        unique = get_unique_articles(articles)
        assert len(unique) == 3, "Both NISIP occurrences preserved + PIATRA"
        nisip_keys = [k for k in unique if unique[k]["descriere"] == "NISIP"]
        assert len(nisip_keys) == 2, "Two NISIP entries: base + __1 suffix"

    def test_get_unique_articles_mixed_keys(self):
        """Occurrence-indexed: all 4 articles kept; duplicate nr=1 gets suffix key."""
        articles = [
            {"nr": "1", "descriere": "A", "um": "T", "cant": "10", "cod": "C1"},
            {"nr": None, "descriere": "B", "um": "T", "cant": "20", "cod": "C2"},
            {"nr": None, "descriere": "C", "um": "T", "cant": "30", "cod": None},
            {"nr": "1", "descriere": "A_DUP", "um": "T", "cant": "10", "cod": "C1"},  # second occurrence
        ]
        unique = get_unique_articles(articles)
        assert len(unique) == 4, "All 4 articles preserved with occurrence-indexed keys"
        assert "1" in unique, "First nr=1 at base key"
        assert "1__1" in unique, "Second nr=1 at suffix key"
        assert "C2" in unique, "COD key should exist"
        hash_keys = [k for k in unique.keys() if len(k) == 8]
        assert len(hash_keys) == 1, "Should have 1 hash-keyed article"
