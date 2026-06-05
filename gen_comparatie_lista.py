"""Generate side-by-side Referinta vs Oferta comparison DOCX.

Usage:
    python3 gen_comparatie_lista.py --client "CAV Maneciu" --oferta 5
    python3 gen_comparatie_lista.py --client "CAV Maneciu"   # all offers
"""
import argparse
import json
import re
from pathlib import Path

from shared.comparatie_lista_writer import build_comparatie_docx


def _run(client: str, oferta_nr: int) -> None:
    holistic_path = Path("output_AO") / client / f"holistic_oferta_{oferta_nr}.json"
    output_path   = Path("output_AO") / client / f"Comparatie_Lista_Oferta_{oferta_nr}.docx"

    if not holistic_path.exists():
        print(f"[SKIP] {holistic_path} not found")
        return

    holistic = json.loads(holistic_path.read_text(encoding="utf-8"))
    build_comparatie_docx(holistic, client, oferta_nr, str(output_path))
    print(f"Saved: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate comparison lista DOCX")
    parser.add_argument("--client", required=True)
    parser.add_argument("--oferta", type=int, help="Oferta number (omit = all)")
    args = parser.parse_args()

    out_dir = Path("output_AO") / args.client
    if not out_dir.exists():
        print(f"[ERROR] {out_dir} not found — run pipeline first")
        return

    if args.oferta:
        _run(args.client, args.oferta)
    else:
        files = sorted(out_dir.glob("holistic_oferta_*.json"))
        for f in files:
            if "_v2" in f.name:
                continue
            m = re.search(r"holistic_oferta_(\d+)\.json", f.name)
            if m:
                _run(args.client, int(m.group(1)))


if __name__ == "__main__":
    main()
