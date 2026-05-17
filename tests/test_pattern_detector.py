"""Tests for pattern detector."""
import json
from pathlib import Path
from shared import pattern_detector


def test_load_pattern_library():
    """Load pattern library from JSON."""
    library = pattern_detector.load_pattern_library()
    assert "patterns" in library
    assert isinstance(library["patterns"], list)
    assert len(library["patterns"]) > 0


def test_get_pattern_by_name():
    """Retrieve pattern by name."""
    pattern = pattern_detector.get_pattern_by_name("MANECIU")
    assert pattern is not None
    assert pattern["name"] == "MANECIU"
    assert "component_indicators" in pattern


def test_detect_pattern_maneciu():
    """Detect MANECIU pattern from text."""
    chapter_text = """1 SA14J - TEAVA DIN MATERIAL PLASTIC PE, D = 110MM M 2.00
material:
manopera:
utilaj:
transport:
1.1 6717077 - TEAVA POLIETILENA
L:SL05 -0020:6717077 -teava polietilena inalta densitate
ml 2.00"""

    result = pattern_detector.detect_pattern(chapter_text, min_confidence=0.30)
    assert result is not None
    assert result["pattern_name"] == "MANECIU"
    assert result["confidence"] >= 0.30


def test_detect_pattern_dragomiresti():
    """Detect DRAGOMIRESTI pattern from text."""
    chapter_text = """1 SA14J - TEAVA DIN MATERIAL PLASTIC PE, D = 110MM M 2.00
1.1 6717077 - TEAVA POLIETILENA M 2.00
1.2 6719428 - MUFA POLIETILENA BUC 2.00"""

    result = pattern_detector.detect_pattern(chapter_text, min_confidence=0.30)
    assert result is not None
    assert result["pattern_name"] == "DRAGOMIRESTI"
    assert result["confidence"] >= 0.30


def test_generate_pattern_template_with_llm():
    """Generate pattern template from unknown format using LLM."""
    from unittest.mock import patch

    unknown_text = """1 UNKNOWN - NEW FORMAT WITH UNKNOWN NOTATION X 1.00
some unique indicators
that don't match known patterns"""

    mock_template = {
        "name": "UNKNOWN_NEW",
        "description": "Auto-generated from unknown format",
        "parent_indicators": ["^\\d+\\s+[A-Z]"],
        "component_indicators": [],
        "quantity_rule": "inherit_from_parent"
    }

    with patch('shared.pattern_detector.generate_pattern_with_llm',
               return_value=mock_template):
        result = pattern_detector.generate_pattern_template(
            unknown_text,
            pattern_name="UNKNOWN_NEW"
        )
        assert result["name"] == "UNKNOWN_NEW"
        assert "parent_indicators" in result
