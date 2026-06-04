#!/usr/bin/env python3
"""
multi_client_run_v2.py — Multi-client orchestrator for v2 table-aware extraction pipeline.

Usage:
    python3 multi_client_run_v2.py              # Interactive menu
    python3 multi_client_run_v2.py --client "Blocuri Racari"  # Direct client

Detects clients from input_AO/, shows menu or uses --client arg,
runs extraction via ExtractionOrchestrator (table-aware pipeline).

Outputs to: output_AO/<client>/*_v2.json (parallel with v1 multi_client_run.py)
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from shared.extraction_v2 import ExtractionOrchestrator
from shared.client_config import ClientConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
INPUT_BASE = ROOT / "input_AO"
OUTPUT_BASE = ROOT / "output_AO"


def show_client_menu(clients: list) -> str:
    """
    Display interactive menu for client selection.

    Args:
        clients: List of client names

    Returns:
        Selected client name
    """
    if not clients:
        logger.error("No clients found in input_AO/")
        sys.exit(1)

    print("\n" + "="*60)
    print("Multi-Client V2 Extraction Pipeline (Table-Aware)")
    print("="*60)
    print("\nAvailable clients:\n")

    for i, client in enumerate(clients, 1):
        print(f"  {i}. {client}")

    while True:
        try:
            choice = input(f"\nSelect client (1-{len(clients)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(clients):
                return clients[idx]
            else:
                print(f"Invalid choice. Please enter 1-{len(clients)}")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-client v2 table-aware extraction pipeline"
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Client name (skip menu if provided)",
    )
    return parser.parse_args()


def process_client(client_config: ClientConfig) -> bool:
    """
    Extract reference and all offers for one client using v2 pipeline.

    Args:
        client_config: ClientConfig object

    Returns:
        True if successful, False otherwise
    """
    client_config.ensure_output_dirs()

    logger.info("\n" + "=" * 60)
    logger.info("  ExtractionOrchestrator v2 (Table-Aware Pipeline)")
    logger.info("=" * 60)
    logger.info(f"Client: {client_config.name}")
    logger.info(f"Input:  {client_config.input_dir}")
    logger.info(f"Output: {client_config.output_dir}")

    # Process reference
    logger.info("\n--- Extraction Reference (v2) ---")

    try:
        with open(client_config.reference_file) as f:
            ref_di = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load reference: {e}")
        return False

    try:
        orchestrator = ExtractionOrchestrator()
        ref_extracted = orchestrator.extract_from_di(
            ref_di, client_name=client_config.name
        )

        # Save reference v2 output
        ref_output_path = client_config.output_dir / "referinta_v2.json"
        with open(ref_output_path, "w", encoding="utf-8") as f:
            json.dump(ref_extracted, f, indent=2, ensure_ascii=False)

        # Save extraction log
        ref_log_path = client_config.output_dir / "extraction_log_referinta_v2.json"
        orchestrator.save_extraction_log(str(ref_log_path))

        ref_article_count = sum(
            len(g.get("articole", [])) for g in ref_extracted.get("grupos", [])
        )
        logger.info(f"✓ Reference extracted: {ref_output_path}")
        logger.info(f"  Template: {ref_extracted.get('template_id', 'UNKNOWN')}")
        logger.info(f"  Articles: {ref_article_count}")
        logger.info(f"  Log: {ref_log_path}")

    except Exception as e:
        logger.error(f"Failed to extract reference: {e}")
        return False

    # Process offers
    offer_files = client_config.list_offer_files()
    logger.info(f"\n--- Extraction Offers (v2) --- ({len(offer_files)} files)")

    for offer_file in offer_files:
        try:
            offer_num = int(offer_file.stem.replace("di_oferta_", ""))
        except ValueError:
            logger.warning(
                f"Could not extract offer number from {offer_file.name}, skipping"
            )
            continue

        try:
            with open(offer_file) as f:
                offer_di = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load offer {offer_num}: {e}")
            continue

        try:
            orchestrator_offer = ExtractionOrchestrator()
            offer_extracted = orchestrator_offer.extract_from_di(
                offer_di, client_name=client_config.name
            )

            # Save offer v2 output
            offer_output_path = (
                client_config.output_dir / f"oferta_{offer_num}_v2.json"
            )
            with open(offer_output_path, "w", encoding="utf-8") as f:
                json.dump(offer_extracted, f, indent=2, ensure_ascii=False)

            # Save log
            offer_log_path = (
                client_config.output_dir / f"extraction_log_oferta_{offer_num}_v2.json"
            )
            orchestrator_offer.save_extraction_log(str(offer_log_path))

            offer_article_count = sum(
                len(g.get("articole", [])) for g in offer_extracted.get("grupos", [])
            )
            logger.info(f"✓ Oferta {offer_num} extracted: {offer_output_path}")
            logger.info(f"  Template: {offer_extracted.get('template_id', 'UNKNOWN')}")
            logger.info(f"  Articles: {offer_article_count}")
            logger.info(f"  Log: {offer_log_path}")

        except Exception as e:
            logger.error(f"Failed to extract offer {offer_num}: {e}")
            return False

    logger.info("\n" + "=" * 60)
    logger.info("  ✅ Extraction v2 complete")
    logger.info("=" * 60)
    logger.info(f"Output directory: {client_config.output_dir}")
    logger.info("\nCompare with v1 output:")
    logger.info("  v1: referinta.json, oferta_N.json")
    logger.info("  v2: referinta_v2.json, oferta_N_v2.json")
    logger.info("\nExtraction logs:")
    logger.info("  v2: extraction_log_referinta_v2.json, extraction_log_oferta_N_v2.json")

    return True


def main():
    """Main orchestrator logic."""
    args = parse_args()

    # Detect clients
    logger.info(f"Scanning for clients in {INPUT_BASE}/")
    clients = ClientConfig.detect_clients(INPUT_BASE)

    if not clients:
        logger.error(f"No clients found in {INPUT_BASE}/")
        logger.info("Expected folder structure: input_AO/ClientName/di_referinta.json")
        sys.exit(1)

    logger.info(f"Found {len(clients)} client(s): {', '.join(clients)}")

    # Get client selection
    if args.client:
        if args.client not in clients:
            logger.error(f"Client '{args.client}' not found.")
            logger.info(f"Available clients: {', '.join(clients)}")
            sys.exit(1)
        selected_client = args.client
        logger.info(f"Using client from --client arg: {selected_client}")
    else:
        selected_client = show_client_menu(clients)

    # Create client config
    try:
        client_config = ClientConfig.from_folder(
            client_name=selected_client,
            input_base=INPUT_BASE,
            output_base=OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"Failed to create client config: {e}")
        sys.exit(1)

    # Validate
    if not client_config.validate():
        logger.error(
            f"Client validation failed: di_referinta.json not found at {client_config.reference_file}"
        )
        sys.exit(1)

    # Run extraction
    try:
        success = process_client(client_config)

        if success:
            logger.info(f"\n{'='*60}")
            logger.info(f"✓ V2 extraction completed successfully for: {selected_client}")
            logger.info(f"Results saved to: {client_config.output_dir}")
            logger.info(f"{'='*60}\n")
            sys.exit(0)
        else:
            logger.error(f"\n{'='*60}")
            logger.error(f"✗ V2 extraction failed for: {selected_client}")
            logger.error(f"{'='*60}\n")
            sys.exit(1)

    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"✗ V2 extraction failed for: {selected_client}")
        logger.error(f"Error: {e}")
        logger.error(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
