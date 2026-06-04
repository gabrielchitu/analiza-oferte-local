"""E2E tests for Subsystem 2: Hierarchy Correction on all 4 main clients.

This comprehensive test suite validates that the hierarchy correction subsystem:
1. Successfully extracts reference and offer documents for all 4 primary clients
2. Applies hierarchy correction to all extracted groups
3. Validates that hierarchy constraints are satisfied across the pipeline
4. Reports which clients pass or fail validation

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
from typing import List, Dict, Tuple

from shared.client_config import ClientConfig
from shared.extraction_v2 import ExtractionOrchestrator


# Constants
INPUT_BASE = Path(__file__).parent.parent / "input_AO"
OUTPUT_BASE = Path(__file__).parent.parent / "output_AO"

# Four main clients - all should pass validation
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


class TestHierarchyCorrectionE2E:
    """End-to-end test suite for hierarchy correction subsystem."""

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

    def _extract_and_validate(
        self, di_json: Dict, client_name: str
    ) -> Tuple[Dict, List[str]]:
        """Extract articles and validate hierarchy correction.

        Args:
            di_json: Document info JSON
            client_name: Client name for logging

        Returns:
            Tuple of (extraction result, list of validation errors)
        """
        orchestrator = ExtractionOrchestrator()
        result = orchestrator.extract_from_di(di_json, client_name)

        errors = []

        # Validate extraction result structure
        assert "grupos" in result, "Result must have 'grupos' key"

        for group_idx, grupo in enumerate(result["grupos"]):
            # Verify hierarchy_stats exists
            if "hierarchy_stats" not in grupo:
                errors.append(
                    f"Group {group_idx}: Missing 'hierarchy_stats' field"
                )
                continue

            stats = grupo["hierarchy_stats"]

            # Validate stats structure
            required_fields = [
                "detected",
                "corrected",
                "validation_pass",
                "validation_errors",
                "validation_errors_list",
            ]
            for field in required_fields:
                if field not in stats:
                    errors.append(
                        f"Group {group_idx}: hierarchy_stats missing '{field}'"
                    )

            # Validate field types
            if not isinstance(stats.get("detected"), int):
                errors.append(
                    f"Group {group_idx}: 'detected' must be int, got {type(stats.get('detected'))}"
                )

            if not isinstance(stats.get("corrected"), int):
                errors.append(
                    f"Group {group_idx}: 'corrected' must be int, got {type(stats.get('corrected'))}"
                )

            if not isinstance(stats.get("validation_pass"), bool):
                errors.append(
                    f"Group {group_idx}: 'validation_pass' must be bool, got {type(stats.get('validation_pass'))}"
                )

            # Check validation pass status
            if not stats.get("validation_pass", False):
                error_count = stats.get("validation_errors", 0)
                error_list = stats.get("validation_errors_list", [])
                errors.append(
                    f"Group {group_idx}: Validation FAILED "
                    f"(errors: {error_count}, details: {error_list[:3]})"
                )

            # Validate articles have hierarchy_corrected field
            for art_idx, article in enumerate(grupo.get("articole", [])):
                if "nr" in article and "hierarchy_corrected" not in article:
                    errors.append(
                        f"Group {group_idx}, Article {art_idx}: Missing 'hierarchy_corrected' field"
                    )

        return result, errors

    @pytest.mark.parametrize("client_name", MAIN_CLIENTS)
    def test_hierarchy_correction_reference_all_main_clients(
        self, client_name: str
    ):
        """Test hierarchy correction on reference (di_referinta.json) for all main clients.

        Args:
            client_name: Name of client to test
        """
        config = self._setup_client(client_name)
        di_json = self._load_di_json(config.reference_file)

        result, errors = self._extract_and_validate(di_json, client_name)

        # Report results
        print(f"\n{client_name} - Reference Extraction")
        print(f"  Groups: {len(result['grupos'])}")

        if result["grupos"]:
            total_articles = sum(
                len(g.get("articole", [])) for g in result["grupos"]
            )
            print(f"  Total Articles: {total_articles}")

            for idx, grupo in enumerate(result["grupos"]):
                stats = grupo.get("hierarchy_stats", {})
                print(
                    f"  Group {idx}: "
                    f"articles={len(grupo.get('articole', []))}, "
                    f"detected={stats.get('detected', '?')}, "
                    f"corrected={stats.get('corrected', '?')}, "
                    f"validation_pass={stats.get('validation_pass', '?')}"
                )

        # Assert no validation errors
        assert not errors, f"{client_name} reference validation failed:\n" + "\n".join(errors)

    @pytest.mark.parametrize("client_name", MAIN_CLIENTS)
    def test_hierarchy_correction_offers_all_main_clients(self, client_name: str):
        """Test hierarchy correction on all offer files for all main clients.

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
            result, errors = self._extract_and_validate(di_json, client_name)

            # Report results
            print(f"\n{client_name} - Oferta {offer_num}")
            print(f"  Groups: {len(result['grupos'])}")

            if result["grupos"]:
                total_articles = sum(
                    len(g.get("articole", [])) for g in result["grupos"]
                )
                print(f"  Total Articles: {total_articles}")

                for idx, grupo in enumerate(result["grupos"]):
                    stats = grupo.get("hierarchy_stats", {})
                    print(
                        f"  Group {idx}: "
                        f"articles={len(grupo.get('articole', []))}, "
                        f"detected={stats.get('detected', '?')}, "
                        f"corrected={stats.get('corrected', '?')}, "
                        f"validation_pass={stats.get('validation_pass', '?')}"
                    )

            if errors:
                all_errors[f"oferta_{offer_num}"] = errors

        # Assert no validation errors across all offers
        assert not all_errors, (
            f"{client_name} offer validation failed:\n"
            + "\n".join(f"{name}: {errors}" for name, errors in all_errors.items())
        )

    def test_hierarchy_correction_all_main_clients_comprehensive(self):
        """Comprehensive E2E test across all 4 main clients.

        This test ensures that:
        1. All reference documents extract successfully
        2. All offer documents extract successfully
        3. Hierarchy validation passes for all
        4. Provides summary report of results
        """
        results_summary = {}
        total_errors = []

        for client_name in MAIN_CLIENTS:
            config = self._setup_client(client_name)
            client_results = {
                "reference": {"groups": 0, "articles": 0, "validation_pass": False, "errors": []},
                "offers": {}
            }

            # Test reference
            di_json = self._load_di_json(config.reference_file)
            result, errors = self._extract_and_validate(di_json, client_name)

            client_results["reference"]["groups"] = len(result["grupos"])
            client_results["reference"]["articles"] = sum(
                len(g.get("articole", [])) for g in result["grupos"]
            )
            client_results["reference"]["validation_pass"] = len(errors) == 0
            client_results["reference"]["errors"] = errors

            if errors:
                total_errors.append(f"{client_name} - Reference: {errors}")

            # Test offers
            offer_files = sorted(config.input_dir.glob("di_oferta_*.json"))
            for offer_file in offer_files:
                match = offer_file.name.replace("di_oferta_", "").replace(".json", "")
                try:
                    offer_num = int(match)
                except ValueError:
                    continue

                di_json = self._load_di_json(offer_file)
                result, errors = self._extract_and_validate(di_json, client_name)

                client_results["offers"][f"oferta_{offer_num}"] = {
                    "groups": len(result["grupos"]),
                    "articles": sum(len(g.get("articole", [])) for g in result["grupos"]),
                    "validation_pass": len(errors) == 0,
                    "errors": errors
                }

                if errors:
                    total_errors.append(f"{client_name} - Oferta {offer_num}: {errors}")

            results_summary[client_name] = client_results

        # Print comprehensive summary
        print("\n" + "="*70)
        print("HIERARCHY CORRECTION E2E TEST SUMMARY")
        print("="*70)

        for client_name in MAIN_CLIENTS:
            client_res = results_summary[client_name]
            ref_res = client_res["reference"]

            print(f"\n{client_name}")
            print(f"  Reference: {ref_res['groups']} groups, {ref_res['articles']} articles, "
                  f"validation_pass={ref_res['validation_pass']}")

            for offer_name, offer_res in client_res["offers"].items():
                print(
                    f"  {offer_name}: {offer_res['groups']} groups, "
                    f"{offer_res['articles']} articles, "
                    f"validation_pass={offer_res['validation_pass']}"
                )

        print("\n" + "="*70)
        print("FINAL RESULT")
        print("="*70)

        # Count pass/fail
        all_pass = all(
            results_summary[client]["reference"]["validation_pass"]
            and all(
                offer_res["validation_pass"]
                for offer_res in results_summary[client]["offers"].values()
            )
            for client in MAIN_CLIENTS
        )

        if all_pass:
            print("✓ ALL MAIN CLIENTS PASSED HIERARCHY VALIDATION")
        else:
            print("✗ SOME CLIENTS FAILED HIERARCHY VALIDATION")

        # Assert all pass
        assert not total_errors, (
            "Hierarchy validation failed for some clients:\n"
            + "\n".join(total_errors)
        )

    @pytest.mark.parametrize("client_name", OPTIONAL_CLIENTS)
    def test_hierarchy_correction_optional_client(self, client_name: str):
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

        di_json = self._load_di_json(config.reference_file)
        result, errors = self._extract_and_validate(di_json, client_name)

        print(f"\n{client_name} (Optional) - Reference Extraction")
        print(f"  Groups: {len(result['grupos'])}")

        if result["grupos"]:
            total_articles = sum(
                len(g.get("articole", [])) for g in result["grupos"]
            )
            print(f"  Total Articles: {total_articles}")

            for idx, grupo in enumerate(result["grupos"]):
                stats = grupo.get("hierarchy_stats", {})
                print(
                    f"  Group {idx}: "
                    f"articles={len(grupo.get('articole', []))}, "
                    f"detected={stats.get('detected', '?')}, "
                    f"corrected={stats.get('corrected', '?')}, "
                    f"validation_pass={stats.get('validation_pass', '?')}"
                )

        if errors:
            print(f"\n  Validation Errors (expected for optional clients):")
            for error in errors:
                print(f"    - {error}")


def test_hierarchy_validation_stats_well_formed():
    """Test that hierarchy_stats structure is well-formed for all clients.

    This is a smoke test to ensure that the hierarchy_stats dictionary
    is properly structured in all extraction results, even for simple data.
    """
    test_di = {
        "pages": [
            {
                "content": "Test Article",
                "lines": [{"content": "1 | Test | 100"}],
                "tables": []
            }
        ]
    }

    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(test_di, "TestClient")

    # Verify structure even with simple data
    assert "grupos" in result
    for grupo in result["grupos"]:
        assert "hierarchy_stats" in grupo
        stats = grupo["hierarchy_stats"]

        # Required fields must be present
        assert "detected" in stats
        assert "corrected" in stats
        assert "validation_pass" in stats
        assert "validation_errors" in stats
        assert "validation_errors_list" in stats

        # Types must be correct
        assert isinstance(stats["detected"], int)
        assert isinstance(stats["corrected"], int)
        assert isinstance(stats["validation_pass"], bool)
        assert isinstance(stats["validation_errors"], int)
        assert isinstance(stats["validation_errors_list"], list)
