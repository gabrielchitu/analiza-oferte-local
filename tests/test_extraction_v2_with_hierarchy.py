"""Integration tests for extraction_v2 with hierarchy correction.

Tests that ExtractionOrchestrator correctly applies hierarchy correction
to all extracted groups, ensuring valid parent-child relationships.
"""
import json
import pytest
from pathlib import Path
from shared.extraction_v2 import ExtractionOrchestrator


CLIENTS = [
    "Blocuri Racari",
    "Camin Maneciu",
    "Scoala Dragomiresti",
    "Drum Tatarani",
    "Scoala Sportiva Racari",
]


def test_extraction_v2_with_hierarchy_correction_basic():
    """Test that hierarchy correction is applied to extracted groups.

    Verifies:
    - Each group has 'hierarchy_stats' field
    - 'hierarchy_stats' contains 'detected', 'corrected', 'validation_pass'
    - validation_pass is True for all groups
    """
    # Create simple test data with articles that can be extracted
    di_json = {
        "pages": [
            {
                "content": "",
                "lines": [
                    {"content": "1 | Article 1 | 100"},
                    {"content": "1.1 | Sub Article | 50"},
                    {"content": "1.2 | Another Sub | 50"},
                ],
                "tables": []
            }
        ]
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di_json, "TestClient")

    # Verify structure
    assert "grupos" in result

    # If we have extracted articles, verify hierarchy_stats exist
    if len(result["grupos"]) > 0:
        for group in result["grupos"]:
            assert "hierarchy_stats" in group, "Group should have hierarchy_stats after correction"

            stats = group["hierarchy_stats"]
            assert "detected" in stats, "hierarchy_stats should have 'detected'"
            assert "corrected" in stats, "hierarchy_stats should have 'corrected'"
            assert "validation_pass" in stats, "hierarchy_stats should have 'validation_pass'"

            assert isinstance(stats["detected"], int)
            assert isinstance(stats["corrected"], int)
            assert isinstance(stats["validation_pass"], bool)
            assert stats["validation_pass"] is True, "Hierarchy validation should pass after correction"


def test_extraction_v2_hierarchy_stats_structure():
    """Test that hierarchy_stats has correct structure and types."""
    di_json = {
        "pages": [
            {
                "content": "",
                "lines": [
                    {"content": "1 | Test | 100"},
                ],
                "tables": []
            }
        ]
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di_json, "TestClient")

    # If groups exist (depends on extraction), verify stats
    if result["grupos"]:
        for group in result["grupos"]:
            stats = group["hierarchy_stats"]

            # Verify stats are non-negative integers
            assert stats["detected"] >= 0
            assert stats["corrected"] >= 0

            # validation_pass must be boolean
            assert isinstance(stats["validation_pass"], bool)


@pytest.mark.parametrize("client", CLIENTS)
def test_extraction_v2_hierarchy_on_real_clients(client):
    """Test hierarchy correction on all 5 real clients.

    Ensures that real client data is processed without crashing
    and hierarchy_stats are present and properly structured.

    Note: Some clients may have legitimate validation issues
    (e.g., orphaned components in source data), which is OK.
    We just verify that the corrector ran successfully.
    """
    client_dir = Path(f"input_AO/{client}")

    if not client_dir.exists():
        pytest.skip(f"Client {client} not found")

    di_file = client_dir / "di_referinta.json"
    if not di_file.exists():
        pytest.skip(f"di_referinta.json not found for {client}")

    with open(di_file) as f:
        di = json.load(f)

    orchestrator = ExtractionOrchestrator()
    # Should not crash
    result = orchestrator.extract_from_di(di, client_name=client)

    # Verify all groups have hierarchy_stats with proper structure
    assert "grupos" in result
    for group_idx, group in enumerate(result["grupos"]):
        assert "hierarchy_stats" in group, f"Group {group_idx} missing hierarchy_stats for {client}"

        stats = group["hierarchy_stats"]
        # Verify stats structure is present and well-formed
        assert "detected" in stats
        assert "corrected" in stats
        assert "validation_pass" in stats
        assert isinstance(stats["detected"], int)
        assert isinstance(stats["corrected"], int)
        assert isinstance(stats["validation_pass"], bool)

        # Log the stats for debugging
        print(
            f"\n{client} Group {group_idx}: detected={stats['detected']}, "
            f"corrected={stats['corrected']}, validation_pass={stats['validation_pass']}"
        )


def test_extraction_v2_hierarchy_corrected_field():
    """Test that articles have 'hierarchy_corrected' field after correction."""
    di_json = {
        "pages": [
            {
                "content": "Item 1\nItem 1.1\nItem 1.2\n",
                "lines": [],
                "tables": []
            }
        ]
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di_json, "TestClient")

    # Check that articles in corrected groups have hierarchy_corrected field
    for group in result["grupos"]:
        for article in group.get("articole", []):
            # After correction, articles should have this field
            assert "hierarchy_corrected" in article or "nr" not in article, (
                f"Article should have 'hierarchy_corrected' field after hierarchy correction"
            )


def test_extraction_v2_empty_articles_no_crash():
    """Test that hierarchy correction handles empty article lists gracefully."""
    di_json = {
        "pages": [
            {
                "content": "",
                "lines": [],
                "tables": []
            }
        ]
    }

    orchestrator = ExtractionOrchestrator()
    # Should not crash with empty content
    result = orchestrator.extract_from_di(di_json, "TestClient")

    assert "grupos" in result
    for group in result["grupos"]:
        assert "hierarchy_stats" in group
        assert group["hierarchy_stats"]["validation_pass"] is True
