#!/usr/bin/env python3
"""
multi_client_run.py — Multi-client orchestrator for offer analysis pipeline.

Usage:
    python3 multi_client_run.py              # Interactive menu
    python3 multi_client_run.py --client "Blocuri Racari"  # Direct client

Detects clients from input_AO/, shows menu or uses --client arg,
runs pipeline via local_run.run_pipeline(client_config).
"""
import argparse
import logging
import sys
from pathlib import Path

from shared.client_config import ClientConfig
from local_run import run_pipeline

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
    print("Multi-Client Offer Analysis Pipeline")
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
        description="Multi-client offer analysis pipeline"
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Client name (skip menu if provided)",
    )
    return parser.parse_args()


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
        logger.error(f"Client validation failed: di_referinta.json not found at {client_config.reference_file}")
        sys.exit(1)

    # Run pipeline
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting pipeline for: {client_config.name}")
        logger.info(f"Input:  {client_config.input_dir}")
        logger.info(f"Output: {client_config.output_dir}")
        logger.info(f"{'='*60}\n")

        run_pipeline(client_config)

        logger.info(f"\n{'='*60}")
        logger.info(f"✓ Pipeline completed successfully for: {client_config.name}")
        logger.info(f"Results saved to: {client_config.output_dir}")
        logger.info(f"{'='*60}\n")

    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"✗ Pipeline failed for: {client_config.name}")
        logger.error(f"Error: {e}")
        logger.error(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
