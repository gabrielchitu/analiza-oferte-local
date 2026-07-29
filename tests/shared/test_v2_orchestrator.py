"""Tests for V2EndToEndOrchestrator.

Validates full v2 pipeline: extract → match → report.
"""

import json
import pytest
import tempfile
from pathlib import Path
from typing import Dict

from shared.v2_orchestrator import V2EndToEndOrchestrator
from shared.client_config import ClientConfig


# Test fixtures

@pytest.fixture
def mock_di_json() -> Dict:
    """Create mock DI JSON structure."""
    return {
        "pages": [
            {
                "page_number": 1,
                "text": "Article 1 - BUC\nArticle 2 - M\n",
            }
        ],
        "tables": [],
    }


@pytest.fixture
def test_client_config(tmp_path) -> ClientConfig:
    """Create test ClientConfig with temporary directories."""
    input_base = tmp_path / "input_AO"
    output_base = tmp_path / "output_AO"

    input_dir = input_base / "TestClient"
    output_dir = output_base / "TestClient"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    config = ClientConfig.from_folder(
        client_name="TestClient",
        input_base=input_base,
        output_base=output_base,
    )
    return config


@pytest.fixture
def orchestrator(tmp_path):
    """Create V2EndToEndOrchestrator with temp cache."""
    cache_dir = tmp_path / "cache"
    return V2EndToEndOrchestrator(cache_dir=cache_dir)


# Tests

def test_orchestrator_initialization(orchestrator):
    """Test orchestrator initializes with all sub-components."""
    assert orchestrator.extraction_orch is not None
    assert orchestrator.matching_orch is not None
    assert orchestrator.cache_dir.exists()


def test_load_di_json_success(orchestrator, tmp_path, mock_di_json):
    """Test loading valid DI JSON file."""
    test_file = tmp_path / "test_di.json"
    with open(test_file, "w") as f:
        json.dump(mock_di_json, f)

    result = orchestrator._load_di_json(test_file)
    assert result == mock_di_json
    assert "pages" in result


def test_load_di_json_missing_file(orchestrator, tmp_path):
    """Test loading missing DI JSON raises FileNotFoundError."""
    missing_file = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError):
        orchestrator._load_di_json(missing_file)


def test_save_holistic_json(orchestrator, test_client_config):
    """Test saving holistic JSON to output directory."""
    holistic = {
        "client": "TestClient",
        "matched_groups": [],
        "ref_only_groups": [],
        "oferta_only_groups": [],
        "stats": {"matched_articles_count": 5},
    }

    path = orchestrator._save_holistic_json(holistic, test_client_config, 1)

    assert path.exists()
    assert path.name == "holistic_oferta_1_v2.json"
    assert path.parent == test_client_config.output_dir

    # Verify saved content
    with open(path) as f:
        saved = json.load(f)
    assert saved == holistic


def test_cached_extraction_first_time(orchestrator, tmp_path, mock_di_json):
    """Test extraction caches result on first run."""
    di_ref = mock_di_json

    # First call should extract and cache
    result1 = orchestrator._cached_extraction(
        "test_key_1", di_ref, "TestClient", is_offer=False
    )

    # Cache file should exist. Numele poarta hash-ul sursei clasificatorului:
    # extractia depinde de gruparea lui, deci un clasificator nou nu are voie sa
    # refoloseasca extractia veche.
    cache_file = orchestrator.cache_dir / f"test_key_1_extracted_{orchestrator._clf_hash()}.json"
    assert cache_file.exists()

    # Content should be valid extraction result
    assert "client" in result1 or "grupos" in result1


def test_cached_extraction_second_time(orchestrator, tmp_path, mock_di_json):
    """Test extraction loads from cache on second run."""
    cache_file = orchestrator.cache_dir / f"test_key_2_extracted_{orchestrator._clf_hash()}.json"
    cached_data = {
        "client": "TestClient",
        "di_file": "test",
        "grupos": [],
    }

    # Pre-populate cache
    with open(cache_file, "w") as f:
        json.dump(cached_data, f)

    # Call should load from cache
    result = orchestrator._cached_extraction(
        "test_key_2", mock_di_json, "TestClient", is_offer=True
    )

    assert result == cached_data


def test_run_missing_input_files(orchestrator, test_client_config):
    """Test run() raises FileNotFoundError if input files missing."""
    # config points to files that don't exist
    with pytest.raises(FileNotFoundError):
        orchestrator.run(test_client_config, 1)


def test_run_creates_output_structure(
    orchestrator, test_client_config, mock_di_json, tmp_path
):
    """Test run() creates correct output files and structure."""
    # Create minimal input files
    with open(test_client_config.reference_file, "w") as f:
        json.dump(mock_di_json, f)
    # Create offer_1.json
    offer_file = test_client_config.input_dir / "di_oferta_1.json"
    with open(offer_file, "w") as f:
        json.dump(mock_di_json, f)

    # Recreate config so offer_files is updated
    config = ClientConfig.from_folder(
        client_name="TestClient",
        input_base=test_client_config.input_dir.parent,
        output_base=test_client_config.output_dir.parent,
    )

    result = orchestrator.run(config, 1)

    # Verify result structure
    assert result["client"] == "TestClient"
    assert result["oferta_num"] == 1
    assert "extracted_ref" in result
    assert "extracted_offer" in result
    assert "holistic_json" in result
    assert "holistic_json_path" in result
    assert "stats" in result

    # Verify holistic JSON file exists
    assert result["holistic_json_path"].exists()


def test_run_returns_valid_holistic_structure(
    orchestrator, test_client_config, mock_di_json
):
    """Test run() returns v1-compatible holistic JSON structure."""
    # Create input files
    with open(test_client_config.reference_file, "w") as f:
        json.dump(mock_di_json, f)
    offer_file = test_client_config.input_dir / "di_oferta_1.json"
    with open(offer_file, "w") as f:
        json.dump(mock_di_json, f)

    # Recreate config so offer_files is updated
    config = ClientConfig.from_folder(
        client_name="TestClient",
        input_base=test_client_config.input_dir.parent,
        output_base=test_client_config.output_dir.parent,
    )

    result = orchestrator.run(config, 1)
    holistic = result["holistic_json"]

    # Verify v1-compatible structure
    assert "client" in holistic
    assert "di_file" in holistic
    assert "extraction_version" in holistic
    assert "matched_groups" in holistic
    assert "ref_only_groups" in holistic
    assert "oferta_only_groups" in holistic
    assert "stats" in holistic

    # Verify stats
    stats = holistic["stats"]
    assert "matched_articles_count" in stats
    assert "ref_only_articles_count" in stats
    assert "oferta_only_articles_count" in stats


def test_run_multiple_offers_separate_results(
    orchestrator, test_client_config, mock_di_json
):
    """Test run() with multiple offers produces separate results."""
    # Create input files for 2 offers
    with open(test_client_config.reference_file, "w") as f:
        json.dump(mock_di_json, f)
    offer_1 = test_client_config.input_dir / "di_oferta_1.json"
    with open(offer_1, "w") as f:
        json.dump(mock_di_json, f)
    offer_2 = test_client_config.input_dir / "di_oferta_2.json"
    with open(offer_2, "w") as f:
        json.dump(mock_di_json, f)

    # Recreate config so offer_files is updated
    config = ClientConfig.from_folder(
        client_name="TestClient",
        input_base=test_client_config.input_dir.parent,
        output_base=test_client_config.output_dir.parent,
    )

    result1 = orchestrator.run(config, 1)
    result2 = orchestrator.run(config, 2)

    # Results should be separate
    assert result1["oferta_num"] == 1
    assert result2["oferta_num"] == 2
    assert result1["holistic_json_path"] != result2["holistic_json_path"]

    # Both files should exist
    assert result1["holistic_json_path"].exists()
    assert result2["holistic_json_path"].exists()


def test_orchestrator_result_keys_complete(
    orchestrator, test_client_config, mock_di_json
):
    """Test run() returns all expected result keys."""
    with open(test_client_config.reference_file, "w") as f:
        json.dump(mock_di_json, f)
    offer_file = test_client_config.input_dir / "di_oferta_1.json"
    with open(offer_file, "w") as f:
        json.dump(mock_di_json, f)

    # Recreate config so offer_files is updated
    config = ClientConfig.from_folder(
        client_name="TestClient",
        input_base=test_client_config.input_dir.parent,
        output_base=test_client_config.output_dir.parent,
    )

    result = orchestrator.run(config, 1)

    expected_keys = {
        "client",
        "oferta_num",
        "extracted_ref",
        "extracted_offer",
        "holistic_json",
        "holistic_json_path",
        "report_path",
        "stats",
        "cache_hit",
    }

    assert set(result.keys()) == expected_keys
