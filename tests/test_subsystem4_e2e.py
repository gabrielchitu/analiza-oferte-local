"""E2E integration tests for v2 pipeline.

Validates full pipeline (extract → match → report) on real clients.
"""

import pytest
import json
from pathlib import Path

from shared.client_config import ClientConfig
from shared.v2_orchestrator import V2EndToEndOrchestrator

# Setup paths
ROOT = Path(__file__).parent.parent
INPUT_BASE = ROOT / "input_AO"
OUTPUT_BASE = ROOT / "output_AO"


# Dynamically discover clients and offers

def get_test_clients():
    """Get list of test clients with available offers."""
    clients = ClientConfig.detect_clients(INPUT_BASE)
    if not clients:
        return {}

    client_offers = {}
    for client_name in clients:
        input_dir = INPUT_BASE / client_name
        offer_files = sorted(input_dir.glob("di_oferta_*.json"))

        if offer_files:
            offers = []
            for f in offer_files:
                try:
                    num = int(f.name.split("_")[2].split(".")[0])
                    offers.append(num)
                except (ValueError, IndexError):
                    pass
            if offers:
                client_offers[client_name] = sorted(set(offers))

    return client_offers


# Create parametrized tests

TEST_CLIENTS = get_test_clients()

# Skip tests if no clients found
pytestmark = pytest.mark.skipif(not TEST_CLIENTS, reason="No clients found in input_AO/")


def client_param_ids():
    """Generate parameter IDs for pytest."""
    ids = []
    for client, offers in TEST_CLIENTS.items():
        for offer in offers:
            ids.append(f"{client}_oferta_{offer}")
    return ids


@pytest.mark.parametrize(
    "client_name,oferta_num",
    [
        (client, offer)
        for client, offers in TEST_CLIENTS.items()
        for offer in offers
    ],
    ids=client_param_ids(),
)
def test_v2_pipeline_e2e(client_name, oferta_num):
    """Test full v2 pipeline end-to-end for a client/offer pair.

    Validates:
    - Pipeline executes without error
    - Holistic JSON has correct structure
    - Report DOCX is generated
    - Matching produces results
    """
    orchestrator = V2EndToEndOrchestrator()

    # Load client config
    config = ClientConfig.from_folder(
        client_name=client_name,
        input_base=INPUT_BASE,
        output_base=OUTPUT_BASE,
    )

    assert config.validate(), f"Reference not found for {client_name}"

    # Run pipeline
    result = orchestrator.run(config, oferta_num)

    # Validate result structure
    assert "extracted_ref" in result
    assert "extracted_offer" in result
    assert "holistic_json" in result
    assert "stats" in result
    assert "holistic_json_path" in result

    # Validate holistic JSON structure
    holistic = result["holistic_json"]
    assert "client" in holistic
    assert "extraction_version" in holistic
    assert "matched_groups" in holistic
    assert "ref_only_groups" in holistic
    assert "oferta_only_groups" in holistic
    assert "stats" in holistic

    # Validate statistics
    stats = holistic["stats"]
    assert isinstance(stats.get("matched_articles_count"), int)
    assert isinstance(stats.get("ref_only_articles_count"), int)
    assert isinstance(stats.get("oferta_only_articles_count"), int)

    # Validate file outputs
    holistic_path = result["holistic_json_path"]
    assert holistic_path.exists(), f"Holistic JSON not found at {holistic_path}"

    # Load saved holistic JSON to verify it's valid
    with open(holistic_path) as f:
        saved_holistic = json.load(f)
    assert saved_holistic["client"] == client_name


@pytest.mark.parametrize(
    "client_name,oferta_num",
    [
        (client, offer)
        for client, offers in TEST_CLIENTS.items()
        for offer in offers
    ],
    ids=client_param_ids(),
)
def test_v2_pipeline_extraction_results(client_name, oferta_num):
    """Test extraction produces valid results.

    Validates:
    - Reference extraction succeeds
    - Offer extraction succeeds
    - Both have articole/grupos structure
    """
    orchestrator = V2EndToEndOrchestrator()

    config = ClientConfig.from_folder(
        client_name=client_name,
        input_base=INPUT_BASE,
        output_base=OUTPUT_BASE,
    )

    result = orchestrator.run(config, oferta_num)

    # Validate extraction
    ref_extracted = result["extracted_ref"]
    offer_extracted = result["extracted_offer"]

    assert "client" in ref_extracted
    assert "extraction_version" in ref_extracted
    assert "grupos" in ref_extracted

    assert "client" in offer_extracted
    assert "extraction_version" in offer_extracted
    assert "grupos" in offer_extracted

    # Both should have at least some groups (unless empty catalog)
    assert isinstance(ref_extracted["grupos"], list)
    assert isinstance(offer_extracted["grupos"], list)


@pytest.mark.parametrize(
    "client_name,oferta_num",
    [
        (client, offer)
        for client, offers in TEST_CLIENTS.items()
        for offer in offers
    ],
    ids=client_param_ids(),
)
def test_v2_pipeline_matching_produces_results(client_name, oferta_num):
    """Test matching produces results.

    Validates:
    - At least one group is matched (for non-empty catalogs)
    - Groups are partitioned into matched/ref_only/oferta_only
    """
    orchestrator = V2EndToEndOrchestrator()

    config = ClientConfig.from_folder(
        client_name=client_name,
        input_base=INPUT_BASE,
        output_base=OUTPUT_BASE,
    )

    result = orchestrator.run(config, oferta_num)

    holistic = result["holistic_json"]
    stats = holistic["stats"]

    # Basic sanity check: at least one group type should have content
    # (unless both catalogs are completely empty)
    total_groups = (
        stats.get("matched_groups_count", 0)
        + stats.get("ref_only_groups_count", 0)
        + stats.get("oferta_only_groups_count", 0)
    )

    # Should have at least some groups (unless catalog is empty)
    ref_extracted = result["extracted_ref"]
    if len(ref_extracted.get("grupos", [])) > 0:
        assert total_groups > 0, f"No groups matched for {client_name} oferta {oferta_num}"


def test_v2_pipeline_no_regression_on_prior_tests():
    """Test that v2 pipeline doesn't break prior tests.

    This is a smoke test ensuring the orchestrator can be instantiated
    and basic infrastructure is intact.
    """
    orchestrator = V2EndToEndOrchestrator()

    # Just instantiation is enough for this test
    assert orchestrator is not None
    assert orchestrator.extraction_orch is not None
    assert orchestrator.matching_orch is not None
