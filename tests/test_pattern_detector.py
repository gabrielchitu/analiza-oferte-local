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
