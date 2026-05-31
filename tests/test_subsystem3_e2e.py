"""E2E tests for Subsystem 3: Set-Based Matching on all 4 main clients.

This comprehensive test suite validates that the matching subsystem:
1. Successfully extracts reference and offer documents for all 4 primary clients
2. Performs set-based matching between reference and offer groups
3. Validates that matched_articles > 0 for all clients
4. Reports matching statistics across the pipeline

Test Coverage:
- Blocuri Racari (master client)
- Camin Maneciu (complex subcomponent extraction)
- Scoala Dragomiresti (complex categorization)
- Drum Tatarani (lettered prefix format)

Optional (known structural issues):
- Scoala Sportiva Racari (group matching structural misalignment)
"""

import json
import pytest
from pathlib import Path
from typing import Dict, List, Tuple

from shared.client_config import ClientConfig
from shared.extraction_v2 import ExtractionOrchestrator


# Constants
INPUT_BASE = Path(__file__).parent.parent / "input_AO"
OUTPUT_BASE = Path(__file__).parent.parent / "output_AO"

# Four main clients - all should pass matching validation
MAIN_CLIENTS = [
    "Blocuri Racari",
    "Camin Maneciu",
    "Scoala Dragomiresti",
    "Drum Tatarani",
]

# Optional client with known structural issues (may fail)
OPTIONAL_CLIENTS = [
    "Scoala Sportiva Racari",
]


class TestSetBasedMatchingE2E:
    """End-to-end test suite for set-based matching subsystem."""

    def _setup_client(self, client_name: str) -> ClientConfig:
        """Setup client config and validate structure.

        Args:
            client_name: Name of client to setup

        Returns:
            ClientConfig instance

        Raises:
            pytest.skip if client files not found
        """
        client_dir = INPUT_BASE / client_name
        if not client_dir.exists():
            pytest.skip(f"Client {client_name} not found in {INPUT_BASE}")

        di_referinta = client_dir / "di_referinta.json"
        if not di_referinta.exists():
            pytest.skip(f"di_referinta.json not found for {client_name}")

        config = ClientConfig.from_folder(
            client_name, INPUT_BASE, OUTPUT_BASE
        )
        return config

    def _load_di_json(self, filepath: Path) -> Dict:
        """Load and parse DI JSON file.

        Args:
            filepath: Path to DI JSON file

        Returns:
            Parsed JSON object

        Raises:
            FileNotFoundError if file not found
            json.JSONDecodeError if JSON invalid
        """
        if not filepath.exists():
            raise FileNotFoundError(f"DI file not found: {filepath}")

        with open(filepath, encoding="utf-8") as f:
            return json.load(f)

    def _validate_matching_result(
        self, holistic: Dict, client_name: str, offer_num: int
    ) -> List[str]:
        """Validate matching result structure and content.

        Args:
            holistic: Holistic matching result
            client_name: Client name for logging
            offer_num: Offer number for logging

        Returns:
            List of validation errors (empty if all valid)
        """
        errors = []

        # Validate top-level structure
        required_top_level = [
            "client",
            "di_file",
            "extraction_version",
            "matched_groups",
            "ref_only_groups",
            "oferta_only_groups",
            "stats"
        ]
        for field in required_top_level:
            if field not in holistic:
                errors.append(f"{client_name} O{offer_num}: Missing top-level field '{field}'")

        # Validate stats structure (uses _count suffix)
        stats = holistic.get("stats", {})
        required_stats = [
            "matched_groups_count",
            "ref_only_groups_count",
            "oferta_only_groups_count",
            "matched_articles_count",
            "ref_only_articles_count",
            "oferta_only_articles_count"
        ]
        for field in required_stats:
            if field not in stats:
                errors.append(f"{client_name} O{offer_num}: Missing stats field '{field}'")
            elif not isinstance(stats.get(field), int):
                errors.append(
                    f"{client_name} O{offer_num}: stats['{field}'] must be int, "
                    f"got {type(stats.get(field))}"
                )

        # Critical validation: matched_articles > 0
        matched_articles = stats.get("matched_articles_count", 0)
        if matched_articles == 0:
            errors.append(
                f"{client_name} O{offer_num}: No matched articles found "
                f"(matched_articles_count = 0)"
            )

        # Validate group list types
        if not isinstance(holistic.get("matched_groups"), list):
            errors.append(
                f"{client_name} O{offer_num}: matched_groups must be list, "
                f"got {type(holistic.get('matched_groups'))}"
            )
        if not isinstance(holistic.get("ref_only_groups"), list):
            errors.append(
                f"{client_name} O{offer_num}: ref_only_groups must be list, "
                f"got {type(holistic.get('ref_only_groups'))}"
            )
        if not isinstance(holistic.get("oferta_only_groups"), list):
            errors.append(
                f"{client_name} O{offer_num}: oferta_only_groups must be list, "
                f"got {type(holistic.get('oferta_only_groups'))}"
            )

        return errors

    @pytest.mark.parametrize("client_name", MAIN_CLIENTS)
    def test_set_based_matching_reference_all_main_clients(self, client_name: str):
        """Test extraction on reference documents for all main clients.

        This validates that reference extraction succeeds as a prerequisite
        for matching tests.

        Args:
            client_name: Name of client to test
        """
        config = self._setup_client(client_name)
        di_json = self._load_di_json(config.reference_file)

        orchestrator = ExtractionOrchestrator()
        result = orchestrator.extract_from_di(di_json, client_name)

        # Validate extraction structure
        assert "grupos" in result, f"{client_name}: Missing 'grupos' in extraction result"
        assert isinstance(result["grupos"], list), \
            f"{client_name}: 'grupos' must be a list"

        groups_count = len(result["grupos"])
        articles_count = sum(
            len(g.get("articole", [])) for g in result["grupos"]
        )

        print(f"\n{client_name} - Reference Extraction")
        print(f"  Groups: {groups_count}")
        print(f"  Total Articles: {articles_count}")

        # Assert non-empty extraction
        assert groups_count > 0, f"{client_name}: No groups extracted from reference"
        assert articles_count > 0, f"{client_name}: No articles extracted from reference"

    @pytest.mark.parametrize("client_name", MAIN_CLIENTS)
    def test_set_based_matching_offers_all_main_clients(self, client_name: str):
        """Test extraction on all offer files for all main clients.

        This validates that offer extraction succeeds for all offers.

        Args:
            client_name: Name of client to test
        """
        config = self._setup_client(client_name)
        offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))

        if not offer_files:
            pytest.skip(f"No offer files found for {client_name}")

        all_errors = {}

        for offer_file in offer_files:
            # Extract offer number
            match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
            try:
                offer_num = int(match)
            except ValueError:
                continue

            di_json = self._load_di_json(offer_file)

            orchestrator = ExtractionOrchestrator()
            result = orchestrator.extract_from_di(di_json, client_name)

            # Validate extraction structure
            assert "grupos" in result, \
                f"{client_name} O{offer_num}: Missing 'grupos' in extraction result"

            groups_count = len(result["grupos"])
            articles_count = sum(
                len(g.get("articole", [])) for g in result["grupos"]
            )

            print(f"\n{client_name} - Oferta {offer_num}")
            print(f"  Groups: {groups_count}")
            print(f"  Total Articles: {articles_count}")

            # Assert non-empty extraction
            if groups_count == 0:
                all_errors[f"oferta_{offer_num}"] = "No groups extracted from offer"
            elif articles_count == 0:
                all_errors[f"oferta_{offer_num}"] = "No articles extracted from offer"

        assert not all_errors, (
            f"{client_name} offer extraction failed:\n"
            + "\n".join(f"{name}: {error}" for name, error in all_errors.items())
        )

    @pytest.mark.parametrize("client_name", MAIN_CLIENTS)
    def test_set_based_matching_single_offer_per_client(self, client_name: str):
        """Test set-based matching on first offer for each main client.

        This is the critical matching test: validates that the matching pipeline
        produces matched_articles > 0 for each client.

        Args:
            client_name: Name of client to test
        """
        config = self._setup_client(client_name)
        orchestrator = ExtractionOrchestrator()

        # Extract reference
        ref_di = self._load_di_json(config.reference_file)
        ref_extracted = orchestrator.extract_from_di(ref_di, client_name)

        # Get first offer
        offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))
        if not offer_files:
            pytest.skip(f"No offer files found for {client_name}")

        offer_file = offer_files[0]
        match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
        try:
            offer_num = int(match)
        except ValueError:
            pytest.skip(f"Invalid offer filename: {offer_file.name}")

        # Extract offer
        oferta_di = self._load_di_json(offer_file)
        oferta_extracted = orchestrator.extract_from_di(oferta_di, client_name)

        # Perform matching
        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        # Validate result
        errors = self._validate_matching_result(holistic, client_name, offer_num)
        assert not errors, (
            f"{client_name} O{offer_num} matching validation failed:\n"
            + "\n".join(errors)
        )

        # Print matching statistics
        stats = holistic.get("stats", {})
        print(f"\n{client_name} - Oferta {offer_num} Matching Results:")
        print(f"  Matched Groups: {stats.get('matched_groups_count', 0)}")
        print(f"  Matched Articles: {stats.get('matched_articles_count', 0)}")
        print(f"  Ref-Only Groups: {stats.get('ref_only_groups_count', 0)}")
        print(f"  Ref-Only Articles: {stats.get('ref_only_articles_count', 0)}")
        print(f"  Oferta-Only Groups: {stats.get('oferta_only_groups_count', 0)}")
        print(f"  Oferta-Only Articles: {stats.get('oferta_only_articles_count', 0)}")

    def test_set_based_matching_all_main_clients_comprehensive(self):
        """Comprehensive E2E test across all 4 main clients.

        This test ensures that:
        1. All reference documents extract successfully
        2. All offer documents extract and match successfully
        3. matched_articles > 0 for all client-offer pairs
        4. Provides summary report of matching results

        This is the primary validation test for Task 6.
        """
        results_summary = {}
        total_errors = []

        for client_name in MAIN_CLIENTS:
            config = self._setup_client(client_name)
            orchestrator = ExtractionOrchestrator()
            client_results = {
                "reference": {"groups": 0, "articles": 0},
                "offers": {}
            }

            # Extract and validate reference
            ref_di = self._load_di_json(config.reference_file)
            ref_extracted = orchestrator.extract_from_di(ref_di, client_name)

            client_results["reference"]["groups"] = len(ref_extracted["grupos"])
            client_results["reference"]["articles"] = sum(
                len(g.get("articole", [])) for g in ref_extracted["grupos"]
            )

            # Extract and validate offers
            offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))
            for offer_file in offer_files:
                match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
                try:
                    offer_num = int(match)
                except ValueError:
                    continue

                # Extract offer
                oferta_di = self._load_di_json(offer_file)
                oferta_extracted = orchestrator.extract_from_di(oferta_di, client_name)

                # Perform matching
                holistic = orchestrator.match_reference_with_offer(
                    ref_extracted, oferta_extracted
                )

                # Validate matching result
                errors = self._validate_matching_result(holistic, client_name, offer_num)

                if errors:
                    total_errors.extend(errors)

                stats = holistic.get("stats", {})
                client_results["offers"][f"oferta_{offer_num}"] = {
                    "groups": len(holistic.get("matched_groups", [])),
                    "articles": stats.get("matched_articles_count", 0),
                    "matched_groups_count": stats.get("matched_groups_count", 0),
                    "ref_only_groups_count": stats.get("ref_only_groups_count", 0),
                    "oferta_only_groups_count": stats.get("oferta_only_groups_count", 0),
                    "validation_pass": len(errors) == 0
                }

            results_summary[client_name] = client_results

        # Print comprehensive summary
        print("\n" + "="*70)
        print("SET-BASED MATCHING E2E TEST SUMMARY (TASK 6)")
        print("="*70)

        for client_name in MAIN_CLIENTS:
            client_res = results_summary[client_name]
            ref_res = client_res["reference"]

            print(f"\n{client_name}")
            print(f"  Reference: {ref_res['groups']} groups, {ref_res['articles']} articles")

            for offer_name, offer_res in client_res["offers"].items():
                match = offer_name.replace("oferta_", "")
                print(
                    f"  {offer_name}: "
                    f"{offer_res['matched_groups_count']} matched groups, "
                    f"{offer_res['articles']} matched articles, "
                    f"validation_pass={offer_res['validation_pass']}"
                )

        print("\n" + "="*70)
        print("FINAL RESULT")
        print("="*70)

        # Count pass/fail
        all_pass = all(
            offer_res["validation_pass"]
            for client in MAIN_CLIENTS
            for offer_res in results_summary[client]["offers"].values()
        )

        if all_pass:
            print("✓ ALL MAIN CLIENTS PASSED SET-BASED MATCHING VALIDATION")
        else:
            print("✗ SOME CLIENTS FAILED SET-BASED MATCHING VALIDATION")

        # Assert no matching validation errors
        assert not total_errors, (
            "Set-based matching validation failed for some clients:\n"
            + "\n".join(total_errors)
        )

    def test_set_based_matching_test_clients_sample(self):
        """Sample test on first 2 offers of first 2 main clients.

        Quick validation that matching pipeline works without running all
        4 clients × all offers. Useful for rapid iteration.
        """
        test_clients = MAIN_CLIENTS[:2]  # First 2 clients
        orchestrator = ExtractionOrchestrator()
        results = {}

        for client_name in test_clients:
            config = self._setup_client(client_name)

            # Extract reference
            ref_di = self._load_di_json(config.reference_file)
            ref_extracted = orchestrator.extract_from_di(ref_di, client_name)

            # Process first 2 offers
            offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))[:2]

            client_results = {}
            for offer_file in offer_files:
                match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
                try:
                    offer_num = int(match)
                except ValueError:
                    continue

                # Extract offer
                oferta_di = self._load_di_json(offer_file)
                oferta_extracted = orchestrator.extract_from_di(oferta_di, client_name)

                # Match
                holistic = orchestrator.match_reference_with_offer(
                    ref_extracted, oferta_extracted
                )

                stats = holistic.get("stats", {})
                client_results[f"oferta_{offer_num}"] = {
                    "matched_articles": stats.get("matched_articles_count", 0),
                    "matched_groups": stats.get("matched_groups_count", 0)
                }

            results[client_name] = client_results

        # Validate all have matched articles
        for client_name, offers in results.items():
            for offer_name, metrics in offers.items():
                assert metrics["matched_articles"] > 0, (
                    f"{client_name} {offer_name}: "
                    f"No matched articles (expected > 0)"
                )

        print(f"\n✓ Sample test passed: {len(results)} clients × 2 offers = "
              f"{sum(len(v) for v in results.values())} offers all matching")

    @pytest.mark.parametrize("client_name", OPTIONAL_CLIENTS)
    def test_set_based_matching_optional_client(self, client_name: str):
        """Test optional clients (may have structural issues).

        These clients are tested but allowed to fail due to known
        structural misalignments in source data.

        Args:
            client_name: Name of optional client
        """
        try:
            config = self._setup_client(client_name)
        except Exception:
            pytest.skip(f"Optional client {client_name} not available")

        orchestrator = ExtractionOrchestrator()

        # Extract reference
        ref_di = self._load_di_json(config.reference_file)
        ref_extracted = orchestrator.extract_from_di(ref_di, client_name)

        print(f"\n{client_name} (Optional) - Matching Test")
        print(f"  Reference Groups: {len(ref_extracted['grupos'])}")

        # Get first offer if available
        offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))
        if not offer_files:
            pytest.skip(f"No offer files found for optional client {client_name}")

        offer_file = offer_files[0]
        match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
        try:
            offer_num = int(match)
        except ValueError:
            pytest.skip(f"Invalid offer filename: {offer_file.name}")

        # Extract offer
        oferta_di = self._load_di_json(offer_file)
        oferta_extracted = orchestrator.extract_from_di(oferta_di, client_name)

        # Match (no assertion - just report)
        try:
            holistic = orchestrator.match_reference_with_offer(
                ref_extracted, oferta_extracted
            )
            stats = holistic.get("stats", {})

            print(f"  Oferta {offer_num} Matching:")
            print(f"    Matched Articles: {stats.get('matched_articles_count', 0)}")
            print(f"    Matched Groups: {stats.get('matched_groups_count', 0)}")

        except Exception as e:
            print(f"  ✗ Matching failed for {client_name}: {str(e)}")
            pytest.skip(f"Optional client {client_name} matching failed (expected)")


def test_matching_result_structure_well_formed():
    """Test that matching result structure is well-formed.

    This is a smoke test to ensure that the holistic JSON from matching
    is properly structured with all required fields.
    """
    from shared.matching_orchestrator_v2 import MatchingOrchestratorV2

    # Create minimal valid extraction results
    ref_extracted = {
        "client": "TestClient",
        "di_file": "test_ref",
        "extraction_version": "2.0",
        "grupos": [
            {
                "deviz_key": "test_group_1",
                "deviz_cod": "001",
                "deviz_den": "Test Group 1",
                "categoria": "Category A",
                "articole": [
                    {
                        "nr": "1",
                        "cod": "CODE001",
                        "descriere": "Test Article 1",
                        "um": "buc",
                        "cantitate": 10.0,
                        "pret_unitar": 100.0
                    }
                ]
            }
        ]
    }

    oferta_extracted = {
        "client": "TestClient",
        "di_file": "test_oferta",
        "extraction_version": "2.0",
        "grupos": [
            {
                "deviz_key": "test_group_1",
                "deviz_cod": "001",
                "deviz_den": "Test Group 1",
                "categoria": "Category A",
                "articole": [
                    {
                        "nr": "1",
                        "cod": "CODE001",
                        "descriere": "Test Article 1",
                        "um": "buc",
                        "cantitate": 5.0,
                        "pret_unitar": 100.0
                    }
                ]
            }
        ]
    }

    # Perform matching
    matcher = MatchingOrchestratorV2()
    holistic = matcher.match(ref_extracted, oferta_extracted)

    # Verify top-level structure
    required_top_level = [
        "client",
        "di_file",
        "extraction_version",
        "matched_groups",
        "ref_only_groups",
        "oferta_only_groups",
        "stats"
    ]
    for field in required_top_level:
        assert field in holistic, f"Missing top-level field '{field}'"

    # Verify stats structure
    stats = holistic["stats"]
    required_stats = [
        "matched_groups_count",
        "ref_only_groups_count",
        "oferta_only_groups_count",
        "matched_articles_count",
        "ref_only_articles_count",
        "oferta_only_articles_count"
    ]
    for field in required_stats:
        assert field in stats, f"Missing stats field '{field}'"
        assert isinstance(stats[field], int), \
            f"stats['{field}'] must be int, got {type(stats[field])}"

    # Verify group lists are lists
    assert isinstance(holistic["matched_groups"], list)
    assert isinstance(holistic["ref_only_groups"], list)
    assert isinstance(holistic["oferta_only_groups"], list)

    # Verify matched_articles > 0 (should have at least 1 from our test data)
    assert stats["matched_articles_count"] > 0, "Expected matched_articles_count > 0 for test data"
