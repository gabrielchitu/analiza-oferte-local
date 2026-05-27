# tests/shared/test_ocr_patterns_knowledge.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_normalize_cod_applies_learned_substitution(tmp_path):
    """Learned pattern B→8 applied on top of hardcoded rules."""
    patterns = {
        "char_substitutions": [
            {"from": "B", "to": "8", "source": "llm", "confidence": 0.9,
             "example": "BC35A vs 8C35A", "client": "Test", "added": "2026-05-27"}
        ],
        "suffix_patterns": []
    }
    ocr_file = tmp_path / "ocr_patterns_knowledge.json"
    ocr_file.write_text(json.dumps(patterns))

    with patch("AgentComparator_local._OCR_PATTERNS_FILE", ocr_file):
        # reload learned dict
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("BC35A")
    assert result == "8C35A"


def test_normalize_cod_learned_does_not_override_hardcoded(tmp_path):
    """Learned pattern cannot override hardcoded I→1."""
    patterns = {
        "char_substitutions": [
            {"from": "I", "to": "9", "source": "llm", "confidence": 0.9,
             "example": "bad idea", "client": "Test", "added": "2026-05-27"}
        ],
        "suffix_patterns": []
    }
    ocr_file = tmp_path / "ocr_patterns_knowledge.json"
    ocr_file.write_text(json.dumps(patterns))

    with patch("AgentComparator_local._OCR_PATTERNS_FILE", ocr_file):
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("IC35D")
    # I must still → 1 (hardcoded), not 9 (learned)
    assert result == "1C35D"


def test_normalize_cod_missing_ocr_file(tmp_path):
    """Missing ocr_patterns_knowledge.json → behaves exactly as before."""
    missing = tmp_path / "nonexistent.json"
    with patch("AgentComparator_local._OCR_PATTERNS_FILE", missing):
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("SA13I")
    assert result == "SA131"
