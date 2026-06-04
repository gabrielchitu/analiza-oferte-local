"""Tests for ExtractionOrchestrator - unified extraction pipeline."""
import pytest
import json
from pathlib import Path
from shared.extraction_v2 import ExtractionOrchestrator


def test_orchestrator_processes_di_file():
    """Orchestrator should process a full DI file."""
    # Load real DI file
    di_path = Path("input_AO/Blocuri Racari/di_referinta.json")
    if not di_path.exists():
        pytest.skip(f"Test file not found: {di_path}")

    with open(di_path) as f:
        di = json.load(f)

    orchestrator = ExtractionOrchestrator()

    # Extract
    result = orchestrator.extract_from_di(di, client_name="Blocuri Racari")

    assert "grupos" in result, "Result should have grupos"
    assert len(result["grupos"]) > 0, "Should extract groups"

    # Check first group structure
    first_group = result["grupos"][0]
    assert "articole" in first_group, "Group should have articole"

    # Check article structure if present
    if first_group["articole"]:
        article = first_group["articole"][0]
        # Articles can use either 'nr'/'descriere' (table format) or 'cod'/'denumire' (regex format)
        assert ("nr" in article or "cod" in article), "Article should have nr or cod"
        assert ("descriere" in article or "denumire" in article), "Article should have descriere or denumire"
        assert "extraction_source" in article, "Article should have extraction_source"
        assert "confidence" in article, "Article should have confidence"


def test_orchestrator_unknown_client():
    """Orchestrator should handle unknown client gracefully."""
    di = {
        "pages": [
            {"page_number": 1, "lines": ["Test content"]}
        ],
        "tables": []
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di, client_name="Unknown Client")

    assert result["client"] == "Unknown Client"
    assert result["extraction_version"] == "2.0"
    assert "template_id" in result


def test_orchestrator_empty_di():
    """Orchestrator should handle empty DI gracefully."""
    di = {"pages": [], "tables": []}

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di, client_name="Test")

    assert result["grupos"] is not None
    assert isinstance(result["grupos"], list)


def test_extraction_log_capture():
    """Orchestrator should capture extraction metadata."""
    di = {
        "pages": [
            {"page_number": 1, "lines": ["Test page 1"]},
            {"page_number": 2, "lines": ["Test page 2"]}
        ],
        "tables": []
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di, client_name="Test")

    log = orchestrator.get_extraction_log()
    assert log["client"] == "Test"
    assert isinstance(log["pages"], list)


def test_orchestrator_result_structure():
    """Orchestrator result should have required structure."""
    di = {
        "pages": [],
        "tables": []
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di, client_name="Test Client")

    # Check required top-level keys
    assert "client" in result
    assert "di_file" in result
    assert "extraction_version" in result
    assert "template_id" in result
    assert "grupos" in result

    # Check structure
    assert result["client"] == "Test Client"
    assert result["extraction_version"] == "2.0"
    assert isinstance(result["grupos"], list)
