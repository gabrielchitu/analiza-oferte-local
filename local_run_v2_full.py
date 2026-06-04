#!/usr/bin/env python3
"""
Full v2 pipeline: extraction_v2 → v1_matching → v1_reporting

Usage:
    python3 local_run_v2_full.py --client "Drum Tatarani"

Produces: same reports as v1, but using v2 extraction (tables + regex, no LLM)
"""
import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from shared.client_config import ClientConfig
from shared.extraction_v2 import ExtractionOrchestrator
from AgentComparator_local import match_global
from generate_v2_reports import generate_v2_report_from_holistic

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
OUTPUT_BASE = ROOT / "output_AO"

def run_v2_full_pipeline(client_config):
    """Extract (v2) + Match (v1) + Report (v1)"""
    client_name = client_config.name
    client_dir = OUTPUT_BASE / client_name
    client_dir.mkdir(parents=True, exist_ok=True)

    logger.info(f"\n{'='*60}")
    logger.info(f"v2 FULL PIPELINE: {client_name}")
    logger.info(f"{'='*60}\n")

    # Phase 1: Extract reference (v2)
    logger.info("Phase 1: Extract reference (v2 extraction)")
    with open(client_config.reference_file) as f:
        ref_di = json.load(f)

    extractor = ExtractionOrchestrator()
    ref_extracted = extractor.extract_from_di(ref_di, client_name)
    ref_extracted["di_file"] = "di_referinta.json"

    ref_file = client_dir / "referinta_v2_full.json"
    with open(ref_file, "w") as f:
        json.dump(ref_extracted, f, indent=2, ensure_ascii=False)
    logger.info(f"✓ Reference: {ref_file.name}")

    # Extract reference articles (flat list for matching)
    ref_articles = []
    for grupo in ref_extracted.get("grupos", []):
        for art in grupo.get("articole", []):
            art["deviz"] = grupo.get("deviz_cod", "")
            ref_articles.append(art)
    logger.info(f"  {len(ref_articles)} articles\n")

    # Phase 2: Process each offer
    offer_files = sorted(client_config.input_dir.glob("di_oferta_*.json"))
    for oferta_file in offer_files:
        match = oferta_file.name.replace("di_oferta_", "").replace(".json", "")
        try:
            oferta_num = int(match)
        except:
            continue

        logger.info(f"Phase 2.{oferta_num}: Extract + Match Oferta {oferta_num}")

        # Extract (v2)
        with open(oferta_file) as f:
            oferta_di = json.load(f)
        oferta_extracted = extractor.extract_from_di(oferta_di, client_name)
        oferta_extracted["di_file"] = f"di_oferta_{oferta_num}.json"

        # Save extracted
        oferta_file_out = client_dir / f"oferta_{oferta_num}_v2_full.json"
        with open(oferta_file_out, "w") as f:
            json.dump(oferta_extracted, f, indent=2, ensure_ascii=False)

        # Extract articles for matching
        oferta_articles = []
        for grupo in oferta_extracted.get("grupos", []):
            for art in grupo.get("articole", []):
                art["deviz"] = grupo.get("deviz_cod", "")
                oferta_articles.append(art)
        logger.info(f"  Extracted: {len(oferta_articles)} articles")

        # Match (v1 matching logic)
        logger.info(f"  Matching...")
        holistic = match_global(ref_articles, oferta_articles)

        # Count results
        matched = sum(1 for g in holistic.get("matched_groups", []) if g.get("articole"))
        ref_only = len(holistic.get("ref_only_groups", []))
        oferta_only = len(holistic.get("oferta_only_groups", []))
        logger.info(f"  Matched: {matched}, Ref-only: {ref_only}, Oferta-only: {oferta_only}")

        # Save holistic
        holistic_file = client_dir / f"holistic_oferta_{oferta_num}_v2_full.json"
        with open(holistic_file, "w") as f:
            json.dump(holistic, f, indent=2, ensure_ascii=False)

        # Report (v2 format from holistic data)
        logger.info(f"  Generating report...")
        report_file = client_dir / f"Raport_Oferta_{oferta_num}_v2_full.docx"
        try:
            generate_v2_report_from_holistic(holistic, str(report_file), client_name, oferta_num)
            logger.info(f"✓ {report_file.name}\n")
        except Exception as e:
            logger.warning(f"✗ Report failed: {e}\n")

    logger.info(f"{'='*60}")
    logger.info(f"✓ v2 Full Pipeline Complete")
    logger.info(f"{'='*60}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--client", help="Client name")
    args = parser.parse_args()

    INPUT_BASE = ROOT / "input_AO"

    if args.client:
        config = ClientConfig.from_folder(args.client, INPUT_BASE, OUTPUT_BASE)
    else:
        clients = ClientConfig.detect_clients(INPUT_BASE)
        if not clients:
            logger.error("No clients found")
            sys.exit(1)
        for i, c in enumerate(clients, 1):
            print(f"{i}. {c}")
        choice = int(input(f"Select (1-{len(clients)}): ")) - 1
        config = ClientConfig.from_folder(clients[choice], INPUT_BASE, OUTPUT_BASE)

    run_v2_full_pipeline(config)
