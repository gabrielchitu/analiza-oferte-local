#!/usr/bin/env python3
"""Generate F3-format DOCX article lists for referinta and/or offers.

Usage:
    python3 gen_lista_oferta.py --client "CAV Maneciu"             # referinta + all offers
    python3 gen_lista_oferta.py --client "CAV Maneciu" --oferta 1  # offer 1 only
    python3 gen_lista_oferta.py --client "CAV Maneciu" --referinta # referinta only
"""

import argparse
import json
import sys
from pathlib import Path

from shared.client_config import ClientConfig
from shared.lista_oferta_writer import build_docx_for_source, extract_entity_name

INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")


def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def generate_referinta(client_name: str, output_dir: Path, input_dir: Path) -> None:
    holistic_candidates = list(output_dir.glob("holistic_oferta_1.json"))
    if not holistic_candidates:
        print(f"  [SKIP] No holistic_oferta_1.json found — run pipeline first.")
        return
    holistic = _load_json(holistic_candidates[0])
    di_path = str(input_dir / "di_referinta.json")
    entity_name = extract_entity_name(di_path, is_referinta=True)
    out_path = str(output_dir / "Lista_Referinta.docx")
    build_docx_for_source(
        holistic=holistic,
        source="referinta",
        entity_name=entity_name,
        client_name=client_name,
        label="Referinta",
        output_path=out_path,
    )
    print(f"  [OK] {out_path}")


def generate_oferta(client_name: str, output_dir: Path, input_dir: Path, oferta_nr: int) -> None:
    holistic_path = output_dir / f"holistic_oferta_{oferta_nr}.json"
    if not holistic_path.exists():
        print(f"  [SKIP] {holistic_path} not found — run pipeline first.")
        return
    holistic = _load_json(holistic_path)
    di_path = str(input_dir / f"di_oferta_{oferta_nr}.json")
    entity_name = extract_entity_name(di_path, is_referinta=False)
    out_path = str(output_dir / f"Lista_Oferta_{oferta_nr}.docx")
    build_docx_for_source(
        holistic=holistic,
        source="oferta",
        entity_name=entity_name,
        client_name=client_name,
        label=f"Oferta {oferta_nr}",
        output_path=out_path,
    )
    print(f"  [OK] {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate F3 article list DOCX")
    parser.add_argument("--client", required=True, help='Client name, e.g. "CAV Maneciu"')
    parser.add_argument("--oferta", type=int, default=None, help="Offer number (default: all)")
    parser.add_argument("--referinta", action="store_true", help="Generate referinta only")
    args = parser.parse_args()

    input_dir = INPUT_BASE / args.client
    output_dir = OUTPUT_BASE / args.client

    if not input_dir.exists():
        print(f"ERROR: input_AO/{args.client}/ not found", file=sys.stderr)
        sys.exit(1)
    if not output_dir.exists():
        print(f"ERROR: output_AO/{args.client}/ not found — run pipeline first", file=sys.stderr)
        sys.exit(1)

    print(f"Client: {args.client}")

    if args.referinta:
        generate_referinta(args.client, output_dir, input_dir)
        return

    if args.oferta is not None:
        generate_oferta(args.client, output_dir, input_dir, args.oferta)
        return

    # Default: referinta + all offers
    generate_referinta(args.client, output_dir, input_dir)
    oferta_nrs = sorted(
        int(p.stem.replace("di_oferta_", ""))
        for p in input_dir.glob("di_oferta_*.json")
    )
    for nr in oferta_nrs:
        generate_oferta(args.client, output_dir, input_dir, nr)


if __name__ == "__main__":
    main()
