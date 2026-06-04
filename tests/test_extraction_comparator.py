import pytest
from shared.extraction_comparator import ExtractionComparator


def test_pick_table_when_regex_fails():
    """When regex returns 0 articles, pick table extraction"""
    table_articles = [
        {
            "nr": "1",
            "descriere": "CIMENT",
            "um": "T",
            "cant": "125",
            "extraction_source": "TABLE",
            "confidence": 0.95,
            "cant_numeric": 125.0,
            "descriere_normalized": "ciment",
            "um_normalized": "t",
            "comparison_key": "1_ciment",
        }
    ]
    regex_articles = []

    comparator = ExtractionComparator()
    best_articles, source, confidence = comparator.compare(table_articles, regex_articles)

    assert len(best_articles) == 1, f"Expected 1 article, got {len(best_articles)}"
    assert source == "TABLE", f"Expected source=TABLE, got {source}"
    assert confidence >= 0.90, f"Confidence too low: {confidence}"


def test_pick_higher_confidence():
    """When both extractions present, pick higher confidence"""
    table_articles = [
        {
            "nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125",
            "extraction_source": "TABLE", "confidence": 0.95,
            "cant_numeric": 125.0, "descriere_normalized": "ciment",
            "um_normalized": "t", "comparison_key": "1_ciment",
        }
    ]
    regex_articles = [
        {
            "nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125",
            "extraction_source": "REGEX", "confidence": 0.70,
            "cant_numeric": 125.0, "descriere_normalized": "ciment",
            "um_normalized": "t", "comparison_key": "1_ciment",
        }
    ]

    comparator = ExtractionComparator()
    best_articles, source, confidence = comparator.compare(table_articles, regex_articles)

    assert source == "TABLE", f"Expected source=TABLE (higher confidence), got {source}"
    assert len(best_articles) == 1
