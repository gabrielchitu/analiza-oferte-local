"""Tests for v2 pipeline CLI tool.

Validates pipeline execution, report generation, and file structure.
"""

import pytest
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

from run_v2_pipeline import run_single_client
from shared.v2_orchestrator import V2EndToEndOrchestrator
from shared.client_config import ClientConfig


# Fixtures

@pytest.fixture
def mock_orchestrator():
    """Create mock orchestrator."""
    return MagicMock(spec=V2EndToEndOrchestrator)


@pytest.fixture
def test_input_structure(tmp_path):
    """Create test input structure with DI files."""
    input_dir = tmp_path / "input_AO" / "TestClient"
    input_dir.mkdir(parents=True, exist_ok=True)

    # Create minimal DI files
    ref_file = input_dir / "di_referinta.json"
    with open(ref_file, "w") as f:
        json.dump({"pages": []}, f)

    offer_file = input_dir / "di_oferta_1.json"
    with open(offer_file, "w") as f:
        json.dump({"pages": []}, f)

    return input_dir


# Tests

def test_run_single_client_success(mock_orchestrator, test_input_structure, tmp_path):
    """Test successful pipeline execution."""
    # Mock the orchestrator.run() method
    mock_result = {
        "extracted_ref": {"grupos": [{"name": "Group 1"}]},
        "extracted_offer": {"grupos": [{"name": "Group 1"}]},
        "stats": {"matched_articles_count": 5},
        "holistic_json_path": tmp_path / "holistic.json",
        "report_path": tmp_path / "report.docx",
    }
    mock_orchestrator.run.return_value = mock_result

    # Patch ClientConfig.from_folder
    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_config = MagicMock(spec=ClientConfig)
        mock_config.validate.return_value = True
        mock_config.list_offer_files.return_value = [
            test_input_structure / "di_oferta_1.json"
        ]
        mock_from_folder.return_value = mock_config

        result = run_single_client(mock_orchestrator, "TestClient", 1)

        assert result is True
        mock_orchestrator.run.assert_called_once()


def test_run_single_client_missing_reference(mock_orchestrator, tmp_path):
    """Test failure when reference file is missing."""
    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_config = MagicMock(spec=ClientConfig)
        mock_config.validate.return_value = False  # Reference not found
        mock_from_folder.return_value = mock_config

        result = run_single_client(mock_orchestrator, "TestClient", 1)

        assert result is False


def test_run_single_client_invalid_config(mock_orchestrator):
    """Test failure when client config loading fails."""
    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_from_folder.side_effect = Exception("Config error")

        result = run_single_client(mock_orchestrator, "TestClient", 1)

        assert result is False


def test_run_single_client_orchestrator_failure(mock_orchestrator, test_input_structure):
    """Test failure when orchestrator.run() fails."""
    mock_orchestrator.run.side_effect = Exception("Orchestration failed")

    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_config = MagicMock(spec=ClientConfig)
        mock_config.validate.return_value = True
        mock_config.list_offer_files.return_value = [
            test_input_structure / "di_oferta_1.json"
        ]
        mock_from_folder.return_value = mock_config

        result = run_single_client(mock_orchestrator, "TestClient", 1)

        assert result is False


def test_run_single_client_all_offers(mock_orchestrator, test_input_structure):
    """Test running pipeline for all offers when oferta_num is None."""
    mock_result = {
        "extracted_ref": {"grupos": []},
        "extracted_offer": {"grupos": []},
        "stats": {"matched_articles_count": 0},
        "holistic_json_path": Path("/tmp/holistic.json"),
        "report_path": None,
    }
    mock_orchestrator.run.return_value = mock_result

    # Create additional offer file
    offer_2 = test_input_structure / "di_oferta_2.json"
    with open(offer_2, "w") as f:
        json.dump({"pages": []}, f)

    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_config = MagicMock(spec=ClientConfig)
        mock_config.validate.return_value = True
        mock_config.list_offer_files.return_value = [
            test_input_structure / "di_oferta_1.json",
            test_input_structure / "di_oferta_2.json",
        ]
        mock_from_folder.return_value = mock_config

        result = run_single_client(mock_orchestrator, "TestClient", oferta_num=None)

        assert result is True
        # Should call run() twice (for offers 1 and 2)
        assert mock_orchestrator.run.call_count == 2


def test_run_single_client_partial_failure(mock_orchestrator, test_input_structure):
    """Test handling of partial failures across multiple offers."""
    # First call succeeds, second fails
    mock_result = {
        "extracted_ref": {"grupos": []},
        "extracted_offer": {"grupos": []},
        "stats": {"matched_articles_count": 0},
        "holistic_json_path": Path("/tmp/holistic.json"),
        "report_path": None,
    }

    mock_orchestrator.run.side_effect = [
        mock_result,  # First call succeeds
        Exception("Second offer failed"),  # Second call fails
    ]

    # Create additional offer
    offer_2 = test_input_structure / "di_oferta_2.json"
    with open(offer_2, "w") as f:
        json.dump({"pages": []}, f)

    with patch("run_v2_pipeline.ClientConfig.from_folder") as mock_from_folder:
        mock_config = MagicMock(spec=ClientConfig)
        mock_config.validate.return_value = True
        mock_config.list_offer_files.return_value = [
            test_input_structure / "di_oferta_1.json",
            test_input_structure / "di_oferta_2.json",
        ]
        mock_from_folder.return_value = mock_config

        result = run_single_client(mock_orchestrator, "TestClient")

        # Should return False due to failure on second offer
        assert result is False
