"""Integration tests for ExtractionOrchestrator on all 5 real clients.

Tests full extraction_v2 pipeline on real client data:
- Blocuri Racari
- Camin Maneciu
- Scoala Dragomiresti
- Drum Tatarani
- Scoala Sportiva Racari

Verify: zero crashes, valid output structure, extraction_log complete.
"""
import json
import pytest
from shared.extraction_v2 import ExtractionOrchestrator
from pathlib import Path

CLIENTS = [
    "Blocuri Racari",
    "Camin Maneciu",
    "Scoala Dragomiresti",
    "Drum Tatarani",
    "Scoala Sportiva Racari",
]


@pytest.mark.parametrize("client", CLIENTS)
def test_extraction_on_all_clients(client):
    """Extract on all 5 clients — zero crashes, output valid.

    Verifies:
    - Client di_referinta.json can be loaded
    - ExtractionOrchestrator processes without crashing
    - Output structure is correct
    - Articles (if any) have valid structure
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

    # Validate top-level structure
    assert result is not None, f"Result should not be None for {client}"
    assert "grupos" in result, f"Result should have 'grupos' for {client}"
    assert result["extraction_version"] == "2.0", f"extraction_version should be 2.0 for {client}"
    assert result["client"] == client, f"Client name should match for {client}"
    assert "template_id" in result, f"Result should have template_id for {client}"

    # If groups exist, validate article structure
    for group_idx, group in enumerate(result.get("grupos", [])):
        assert "articole" in group, f"Group {group_idx} should have articole for {client}"
        assert isinstance(group["articole"], list), f"articole should be a list in group {group_idx} for {client}"

        for article_idx, article in enumerate(group.get("articole", [])):
            # Articles can use either table format (nr/descriere) or regex format (cod/denumire)
            has_nr_or_cod = "nr" in article or "cod" in article
            assert has_nr_or_cod, (
                f"Article {article_idx} in group {group_idx} should have 'nr' or 'cod' for {client}"
            )

            has_descriere_or_denumire = "descriere" in article or "denumire" in article
            assert has_descriere_or_denumire, (
                f"Article {article_idx} in group {group_idx} should have 'descriere' or 'denumire' for {client}"
            )

            assert "extraction_source" in article, (
                f"Article {article_idx} in group {group_idx} should have extraction_source for {client}"
            )
            assert article["extraction_source"] in ["TABLE", "REGEX", "HYBRID"], (
                f"Article {article_idx} extraction_source should be TABLE, REGEX, or HYBRID for {client}"
            )

            assert "confidence" in article, (
                f"Article {article_idx} in group {group_idx} should have confidence for {client}"
            )
            assert isinstance(article["confidence"], (int, float)), (
                f"Article {article_idx} confidence should be numeric for {client}"
            )
            assert 0.0 <= article["confidence"] <= 1.0, (
                f"Article {article_idx} confidence should be between 0 and 1 for {client}"
            )


@pytest.mark.parametrize("client", CLIENTS)
def test_extraction_log_structure(client):
    """Extraction log should be complete and structured."""
    client_dir = Path(f"input_AO/{client}")

    if not client_dir.exists():
        pytest.skip(f"Client {client} not found")

    di_file = client_dir / "di_referinta.json"
    if not di_file.exists():
        pytest.skip(f"di_referinta.json not found for {client}")

    with open(di_file) as f:
        di = json.load(f)

    orchestrator = ExtractionOrchestrator()
    orchestrator.extract_from_di(di, client_name=client)

    log = orchestrator.get_extraction_log()

    # Top-level log structure
    assert log is not None, f"Extraction log should not be None for {client}"
    assert log["client"] == client, f"Log client should match for {client}"
    assert "pages" in log, f"Log should have pages for {client}"
    assert isinstance(log["pages"], list), f"Log pages should be a list for {client}"

    # Validate each page entry
    for page_idx, page_entry in enumerate(log["pages"]):
        assert "page_idx" in page_entry, f"Page {page_idx} should have page_idx for {client}"
        assert "source_won" in page_entry, f"Page {page_idx} should have source_won for {client}"
        assert page_entry["source_won"] in ["TABLE", "REGEX", "NONE", "HYBRID"], (
            f"Page {page_idx} source_won should be TABLE, REGEX, NONE, or HYBRID for {client}"
        )
        assert "table_article_count" in page_entry, (
            f"Page {page_idx} should have table_article_count for {client}"
        )
        assert "regex_article_count" in page_entry, (
            f"Page {page_idx} should have regex_article_count for {client}"
        )
        assert "best_article_count" in page_entry, (
            f"Page {page_idx} should have best_article_count for {client}"
        )
        assert "confidence" in page_entry, (
            f"Page {page_idx} should have confidence for {client}"
        )
        assert "template_id" in page_entry, (
            f"Page {page_idx} should have template_id for {client}"
        )


def test_extraction_no_crashes_all_clients():
    """Meta test: ensure all 5 clients can be extracted without crashes."""
    results = {}
    errors = {}

    for client in CLIENTS:
        client_dir = Path(f"input_AO/{client}")
        di_file = client_dir / "di_referinta.json"

        if not di_file.exists():
            results[client] = "SKIPPED"
            continue

        try:
            with open(di_file) as f:
                di = json.load(f)

            orchestrator = ExtractionOrchestrator()
            result = orchestrator.extract_from_di(di, client_name=client)

            group_count = len(result.get("grupos", []))
            article_count = sum(
                len(g.get("articole", [])) for g in result.get("grupos", [])
            )

            results[client] = {
                "status": "OK",
                "groups": group_count,
                "articles": article_count,
            }
        except Exception as e:
            import traceback
            errors[client] = traceback.format_exc()
            results[client] = "ERROR"

    # Assert all successful
    failed_clients = []
    for client in CLIENTS:
        status = results.get(client)
        if status not in ["SKIPPED", "OK"] and isinstance(status, dict) is False:
            failed_clients.append((client, errors.get(client, "Unknown error")))

    if failed_clients:
        error_msg = "\n".join(
            f"{client}: {error}" for client, error in failed_clients
        )
        pytest.fail(f"Extraction failed for the following clients:\n{error_msg}")

    # Print summary
    print("\n=== Extraction Integration Test Summary ===")
    for client, status in results.items():
        if isinstance(status, dict):
            print(
                f"  {client}: OK ({status['groups']} groups, {status['articles']} articles)"
            )
        else:
            print(f"  {client}: {status}")
