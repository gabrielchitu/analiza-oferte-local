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
