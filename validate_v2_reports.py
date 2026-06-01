#!/usr/bin/env python3
"""Validate v2 reports match v1 reports.

Runs both pipelines and compares output to ensure v2 produces identical results.

Usage:
    python3 validate_v2_reports.py --client "ClientName"
    python3 validate_v2_reports.py --all
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Dict, Tuple

from shared.client_config import ClientConfig
from shared.v2_orchestrator import V2EndToEndOrchestrator
from compare_reports import extract_report_text, extract_metrics, compare_reports

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
INPUT_BASE = ROOT / "input_AO"
OUTPUT_BASE = ROOT / "output_AO"


def validate_client_reports(client_name: str) -> Tuple[bool, Dict]:
    """Validate v2 reports match v1 reports for a client.

    Args:
        client_name: Client name

    Returns:
        (all_valid: bool, results: dict with detailed comparison)
    """
    logger.info(f"Validating {client_name}...")

    results = {
        "client": client_name,
        "offers": {},
        "summary": {
            "total_offers": 0,
            "matching_offers": 0,
            "mismatched_offers": 0,
        }
    }

    # Load client config
    try:
        config = ClientConfig.from_folder(
            client_name=client_name,
            input_base=INPUT_BASE,
            output_base=OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
        return False, results

    if not config.validate():
        logger.error(f"Reference not found")
        return False, results

    # Generate v2 reports
    orchestrator = V2EndToEndOrchestrator()
    offer_files = config.list_offer_files()

    offers = []
    for f in offer_files:
        try:
            num = int(f.name.split("_")[2].split(".")[0])
            offers.append(num)
        except (ValueError, IndexError):
            pass
    offers = sorted(set(offers))

    if not offers:
        logger.warning("No offers found")
        return True, results

    # Validate each offer
    all_valid = True

    for offer_num in offers:
        try:
            logger.info(f"  Generating v2 report for oferta {offer_num}...")

            # Run v2 pipeline
            v2_result = orchestrator.run(config, offer_num)

            # Compare with v1
            v1_path = config.output_dir / f"Raport_Oferta_{offer_num}.docx"
            v2_path = v2_result["report_path"]

            if not v2_path or not v2_path.exists():
                logger.warning(f"    V2 report not generated")
                results["offers"][offer_num] = {
                    "status": "skip",
                    "reason": "V2 report missing",
                }
                continue

            is_identical, diffs = compare_reports(v1_path, v2_path)

            results["offers"][offer_num] = {
                "status": "match" if is_identical else "mismatch",
                "differences": diffs,
            }

            if is_identical:
                logger.info(f"    ✓ V1 and V2 reports match")
                results["summary"]["matching_offers"] += 1
            else:
                logger.warning(f"    ✗ Reports differ")
                for key, diff in diffs.items():
                    if "error" not in key:
                        logger.warning(f"      {key}: v1={diff['v1']}, v2={diff['v2']}")
                results["summary"]["mismatched_offers"] += 1
                all_valid = False

            results["summary"]["total_offers"] += 1

        except Exception as e:
            logger.error(f"    Failed to process: {e}")
            results["offers"][offer_num] = {
                "status": "error",
                "reason": str(e),
            }
            all_valid = False

    return all_valid, results


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate v2 reports match v1 reports",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", help="Client name")
    group.add_argument("--all", action="store_true", help="Validate all clients")

    args = parser.parse_args()

    # Determine which clients to validate
    if args.all:
        clients = ClientConfig.detect_clients(INPUT_BASE)
        if not clients:
            logger.error(f"No clients found")
            sys.exit(1)
    else:
        clients = [args.client]

    # Validate each client
    logger.info(f"Validating {len(clients)} client(s)...\n")

    all_results = {}
    all_valid = True

    for client in clients:
        valid, results = validate_client_reports(client)
        all_results[client] = results

        if not valid:
            all_valid = False

        logger.info("")

    # Summary
    logger.info("=" * 60)
    logger.info("VALIDATION SUMMARY")
    logger.info("=" * 60)

    total_offers = 0
    matching = 0
    mismatched = 0

    for client, results in all_results.items():
        summary = results["summary"]
        total_offers += summary["total_offers"]
        matching += summary["matching_offers"]
        mismatched += summary["mismatched_offers"]

        status = "✓" if summary["mismatched_offers"] == 0 else "✗"
        logger.info(
            f"{status} {client}: {summary['matching_offers']}/{summary['total_offers']} matching"
        )

    logger.info("")
    logger.info(f"Total: {matching}/{total_offers} offers match")

    if all_valid:
        logger.info("✓ All validations passed!")
        sys.exit(0)
    else:
        logger.warning("✗ Some validations failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
