#!/usr/bin/env python3
"""
local_run_v2.py — Extract using v2 table-aware pipeline (ExtractionOrchestrator).

Usage:
    python3 local_run_v2.py

Outputs articles to: output_AO/referinta_v2.json, output_AO/oferta_N_v2.json
Logs extraction metadata to: output_AO/extraction_log_referinta_v2.json, etc.

Allows side-by-side comparison with v1 output (local_run.py).
"""

import json
import logging
import sys
from pathlib import Path

from shared.extraction_v2 import ExtractionOrchestrator
from shared.client_config import ClientConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input_AO"
OUTPUT_DIR = ROOT / "output_AO"


def main():
    """Run extraction_v2 on reference + all offers."""

    # Load client config (interactive or detect)
    clients = ClientConfig.detect_clients(INPUT_DIR)

    if not clients:
        logger.error(f"No clients found in {INPUT_DIR}")
        logger.error("Ensure you have client folders with di_referinta.json files")
        sys.exit(1)

    # Interactive menu
    if len(clients) == 1:
        client_name = clients[0]
        logger.info(f"Using client: {client_name}")
    else:
        print("\n" + "=" * 60)
        print("Available clients:")
        for i, name in enumerate(clients, 1):
            print(f"  {i}. {name}")
        print("=" * 60)
        try:
            choice = input(f"Select client (1-{len(clients)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(clients):
                client_name = clients[idx]
            else:
                logger.error("Invalid choice")
                sys.exit(1)
        except (ValueError, KeyboardInterrupt):
            logger.error("Invalid input")
            sys.exit(1)

    # Build client config
    config = ClientConfig.from_folder(client_name, INPUT_DIR, OUTPUT_DIR)

    if not config.validate():
        logger.error(f"Reference DI not found: {config.reference_file}")
        sys.exit(1)

    config.ensure_output_dirs()

    logger.info("\n" + "=" * 60)
    logger.info("  ExtractionOrchestrator v2 (Table-Aware Pipeline)")
    logger.info("=" * 60)
    logger.info(f"Client: {client_name}")
    logger.info(f"Input:  {config.input_dir}")
    logger.info(f"Output: {config.output_dir}")

    # Process reference
    logger.info("\n--- Extraction Reference (v2) ---")

    try:
        with open(config.reference_file) as f:
            ref_di = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load reference: {e}")
        sys.exit(1)

    orchestrator = ExtractionOrchestrator()
    ref_extracted = orchestrator.extract_from_di(ref_di, client_name=client_name)

    # Save reference v2 output
    ref_output_path = config.output_dir / "referinta_v2.json"
    with open(ref_output_path, "w", encoding="utf-8") as f:
        json.dump(ref_extracted, f, indent=2, ensure_ascii=False)

    # Save extraction log
    ref_log_path = config.output_dir / "extraction_log_referinta_v2.json"
    orchestrator.save_extraction_log(str(ref_log_path))

    ref_article_count = sum(len(g.get('articole', [])) for g in ref_extracted.get('grupos', []))
    logger.info(f"✓ Reference extracted: {ref_output_path}")
    logger.info(f"  Template: {ref_extracted.get('template_id', 'UNKNOWN')}")
    logger.info(f"  Articles: {ref_article_count}")
    logger.info(f"  Log: {ref_log_path}")

    # Process offers
    offer_files = config.list_offer_files()
    logger.info(f"\n--- Extraction Offers (v2) --- ({len(offer_files)} files)")

    for offer_file in offer_files:
        try:
            offer_num = int(offer_file.stem.replace("di_oferta_", ""))
        except ValueError:
            logger.warning(f"Could not extract offer number from {offer_file.name}, skipping")
            continue

        try:
            with open(offer_file) as f:
                offer_di = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load offer {offer_num}: {e}")
            continue

        orchestrator_offer = ExtractionOrchestrator()
        offer_extracted = orchestrator_offer.extract_from_di(offer_di, client_name=client_name)

        # Save offer v2 output
        offer_output_path = config.output_dir / f"oferta_{offer_num}_v2.json"
        with open(offer_output_path, "w", encoding="utf-8") as f:
            json.dump(offer_extracted, f, indent=2, ensure_ascii=False)

        # Save log
        offer_log_path = config.output_dir / f"extraction_log_oferta_{offer_num}_v2.json"
        orchestrator_offer.save_extraction_log(str(offer_log_path))

        offer_article_count = sum(len(g.get('articole', [])) for g in offer_extracted.get('grupos', []))
        logger.info(f"✓ Oferta {offer_num} extracted: {offer_output_path}")
        logger.info(f"  Template: {offer_extracted.get('template_id', 'UNKNOWN')}")
        logger.info(f"  Articles: {offer_article_count}")
        logger.info(f"  Log: {offer_log_path}")

    logger.info("\n" + "=" * 60)
    logger.info("  ✅ Extraction v2 complete")
    logger.info("=" * 60)
    logger.info(f"Output directory: {config.output_dir}")
    logger.info("\nCompare with v1 output:")
    logger.info("  v1: referinta.json, oferta_N.json")
    logger.info("  v2: referinta_v2.json, oferta_N_v2.json")
    logger.info("\nExtraction logs:")
    logger.info("  v2: extraction_log_referinta_v2.json, extraction_log_oferta_N_v2.json")


if __name__ == "__main__":
    main()
