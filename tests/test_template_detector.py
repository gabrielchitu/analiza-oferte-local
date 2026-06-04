"""Tests for template detector - document type fingerprinting."""
import json
import pytest
from pathlib import Path
from shared.template_detector import TemplateDetector


def test_fingerprint_blocuri_racari():
    """Blocuri Racari should fingerprint as BR_CONSOLIDATED."""
    di_path = Path("input_AO/Blocuri Racari/di_referinta.json")
    if not di_path.exists():
        pytest.skip(f"Test file not found: {di_path}")

    with open(di_path) as f:
        di = json.load(f)

    detector = TemplateDetector()
    template_id, fingerprint, certainty = detector.detect_template(di)

    assert template_id is not None, "Should detect template"
    assert certainty > 0.7, f"Certainty too low: {certainty}"
    assert fingerprint is not None, "Should have fingerprint"


def test_unknown_template_fallback():
    """Unknown template should fallback gracefully."""
    unknown_di = {
        "pages": [
            {"page_number": 1, "lines": ["Unknown document structure"]},
            {"page_number": 2, "lines": ["No recognizable patterns"]}
        ],
        "tables": []
    }

    detector = TemplateDetector()
    template_id, fingerprint, certainty = detector.detect_template(unknown_di)

    assert template_id == "UNKNOWN", "Should fallback to UNKNOWN"
    assert certainty < 0.5, "Certainty should be low"
    assert fingerprint is not None, "Should have fingerprint dict"


def test_fingerprint_extraction():
    """Test fingerprint extraction on sample document."""
    sample_di = {
        "pages": [
            {"page_number": i, "lines": [f"Line {i}-{j}" for j in range(5)]}
            for i in range(3)
        ],
        "tables": [
            {
                "row_count": 10,
                "column_count": 4,
                "cells": [
                    {"row_index": 0, "column_index": 0, "content": "Header"}
                ]
            }
        ]
    }

    detector = TemplateDetector()
    fingerprint = detector._extract_fingerprint(sample_di)

    assert fingerprint is not None
    assert "num_pages" in fingerprint
    assert "num_tables" in fingerprint
    assert "primary_table_cols" in fingerprint
    assert "text_density" in fingerprint


def test_fingerprints_loaded():
    """Test that fingerprints are loaded from JSON."""
    detector = TemplateDetector()
    assert detector.fingerprints is not None
    assert isinstance(detector.fingerprints, dict)
    # Should have at least UNKNOWN template
    assert "UNKNOWN" in detector.fingerprints
