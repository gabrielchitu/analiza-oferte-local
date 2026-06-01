#!/usr/bin/env python3
"""Run full v2 pipeline: extract → match → report.

Usage:
    python3 run_v2_pipeline.py --client "ClientName"       # All offers
    python3 run_v2_pipeline.py --client "ClientName" --oferta 1  # Single offer
    python3 run_v2_pipeline.py --all                       # All clients, all offers
"""

import sys
import argparse
import logging
from pathlib import Path

from shared.client_config import ClientConfig
from shared.v2_orchestrator import V2EndToEndOrchestrator

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
INPUT_BASE = ROOT / "input_AO"
OUTPUT_BASE = ROOT / "output_AO"


def run_single_client(orchestrator: V2EndToEndOrchestrator, client_name: str, oferta_num: int = None):
    """Run v2 pipeline for single client and offer(s).

    Args:
        orchestrator: V2EndToEndOrchestrator instance
        client_name: Client name
        oferta_num: Specific offer number, or None for all
    """
    # Load client config
    try:
        config = ClientConfig.from_folder(
            client_name=client_name,
            input_base=INPUT_BASE,
            output_base=OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"Failed to load config for {client_name}: {e}")
        return False

    if not config.validate():
        logger.error(f"Reference file not found for {client_name}")
        return False

    # Determine offers
    if oferta_num is not None:
        offers = [oferta_num]
    else:
        # Find all offers
        offer_files = config.list_offer_files()
        offers = []
        for f in offer_files:
            # Extract offer number from "di_oferta_N.json"
            try:
                num = int(f.name.split("_")[2].split(".")[0])
                offers.append(num)
            except (ValueError, IndexError):
                pass
        offers = sorted(set(offers))

    if not offers:
        logger.error(f"No offers found for {client_name}")
        return False

    # Run pipeline for each offer
    success = True
    for offer in offers:
        try:
            logger.info(f"Processing {client_name} oferta {offer}...")

            result = orchestrator.run(config, offer)

            logger.info(f"  ✓ Extracted reference: {len(result['extracted_ref'].get('grupos', []))} groups")
            logger.info(f"  ✓ Extracted offer: {len(result['extracted_offer'].get('grupos', []))} groups")

            stats = result["stats"]
            logger.info(f"  ✓ Matching complete: {stats.get('matched_articles_count', 0)} matched articles")
            logger.info(f"  ✓ Report saved to {result['holistic_json_path']}")

            if result["report_path"]:
                logger.info(f"  ✓ Word report saved to {result['report_path']}")
            else:
                logger.warning(f"  ⚠ Report generation skipped")

        except Exception as e:
            logger.error(f"Failed to process {client_name} oferta {offer}: {e}")
            success = False
            continue

    return success


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run full v2 pipeline (extract → match → report)",
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--client", help="Client name")
    group.add_argument("--all", action="store_true", help="Run all clients")

    parser.add_argument("--oferta", type=int, help="Specific offer number (only with --client)")

    args = parser.parse_args()

    # Initialize orchestrator
    orchestrator = V2EndToEndOrchestrator()

    # Determine which clients to run
    if args.all:
        clients = ClientConfig.detect_clients(INPUT_BASE)
        if not clients:
            logger.error(f"No clients found in {INPUT_BASE}")
            sys.exit(1)
    else:
        clients = [args.client]

    # Run pipeline for each client
    logger.info(f"Running v2 pipeline for {len(clients)} client(s)...")
    logger.info("")

    all_success = True
    for client in clients:
        success = run_single_client(orchestrator, client, args.oferta)
        if not success:
            all_success = False
        logger.info("")

    # Summary
    if all_success:
        logger.info("✓ All pipelines completed successfully")
        sys.exit(0)
    else:
        logger.info("✗ Some pipelines failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
