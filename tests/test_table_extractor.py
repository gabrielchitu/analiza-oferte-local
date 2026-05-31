import pytest
from shared.table_extractor import TableExtractor

def test_extract_simple_table():
    """Extract articles from simple 4-column table"""
    mock_table = {
        "cells": [
            {"rowIndex": 0, "columnIndex": 0, "content": "NR"},
            {"rowIndex": 0, "columnIndex": 1, "content": "DESCRIERE"},
            {"rowIndex": 0, "columnIndex": 2, "content": "UM"},
            {"rowIndex": 0, "columnIndex": 3, "content": "CANT"},
            {"rowIndex": 1, "columnIndex": 0, "content": "1"},
            {"rowIndex": 1, "columnIndex": 1, "content": "CIMENT CEM II/A-S 42.5"},
            {"rowIndex": 1, "columnIndex": 2, "content": "T"},
            {"rowIndex": 1, "columnIndex": 3, "content": "125"},
        ]
    }

    extractor = TableExtractor()
    articles, hierarchy, confidence = extractor.extract(mock_table)

    assert len(articles) == 1, f"Expected 1 article, got {len(articles)}"
    assert articles[0]["nr"] == "1"
    assert articles[0]["descriere"] == "CIMENT CEM II/A-S 42.5"
    assert articles[0]["um"] == "t"  # normalized to lowercase
    assert articles[0]["cant_numeric"] == 125.0
    assert confidence > 0.8, f"Confidence too low: {confidence}"

def test_extract_with_subcomponents():
    """Extract articles with parent-child hierarchy"""
    mock_table = {
        "cells": [
            {"rowIndex": 0, "columnIndex": 0, "content": "NR"},
            {"rowIndex": 0, "columnIndex": 1, "content": "DESCRIERE"},
            {"rowIndex": 0, "columnIndex": 2, "content": "UM"},
            {"rowIndex": 0, "columnIndex": 3, "content": "CANT"},
            {"rowIndex": 1, "columnIndex": 0, "content": "1"},
            {"rowIndex": 1, "columnIndex": 1, "content": "CIMENT"},
            {"rowIndex": 1, "columnIndex": 2, "content": "T"},
            {"rowIndex": 1, "columnIndex": 3, "content": "125"},
            {"rowIndex": 2, "columnIndex": 0, "content": "1.1"},
            {"rowIndex": 2, "columnIndex": 1, "content": "Transport"},
            {"rowIndex": 2, "columnIndex": 2, "content": "T"},
            {"rowIndex": 2, "columnIndex": 3, "content": "10"},
        ]
    }

    extractor = TableExtractor()
    articles, hierarchy, confidence = extractor.extract(mock_table)

    assert len(articles) == 2, f"Expected 2 articles, got {len(articles)}"
    assert articles[0]["parent_nr"] is None
    assert articles[1]["parent_nr"] == "1", f"Expected parent=1, got {articles[1].get('parent_nr')}"
    assert articles[1]["is_component"] is True
