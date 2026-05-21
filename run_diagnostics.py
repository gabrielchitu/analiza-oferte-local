#!/usr/bin/env python3
"""Diagnostic runner — reads output_AO/<client>/ and generates diagnostics.json + diagnostics.docx"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from shared.diagnostics_builder import build_diagnostics_json, discover_clients
from shared.diagnostics_word import generate_diagnostics_docx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generează raport diagnostic pentru toți clienții")
    parser.add_argument("--client", help="Rulează doar pentru un client specific")
    parser.add_argument("--no-docx", action="store_true", help="Generează doar JSON, fără DOCX")
    parser.add_argument("--output-dir", default="output_AO", help="Director output (default: output_AO)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if args.client:
        client_ref = output_dir / args.client / "referinta.json"
        if not client_ref.exists():
            print(f"EROARE: Nu există output pentru '{args.client}' în {output_dir}", file=sys.stderr)
            return 1
        clients = [args.client]
    else:
        clients = discover_clients(base_dir=output_dir)
        if not clients:
            print(f"EROARE: Niciun client cu output în {output_dir}", file=sys.stderr)
            return 1

    print(f"Clienți analizați: {', '.join(clients)}")

    data = build_diagnostics_json(clients, base_dir=output_dir)

    json_path = output_dir / "diagnostics.json"
    json_path.write_text(json.dumps(
        {k: v for k, v in data.items() if not k.startswith("_")},
        ensure_ascii=False, indent=2
    ))
    print(f"JSON: {json_path}")

    if not args.no_docx:
        docx_path = output_dir / "diagnostics.docx"
        generate_diagnostics_docx(data, docx_path)
        print(f"DOCX: {docx_path}")

    sg = data["sumar_global"]
    print(f"\nSumar global:")
    print(f"  matched={sg['total_matched']} LIPSA={sg['total_lipsa']} "
          f"EXTRA={sg['total_extra']} DEVIZ_MM={sg['total_deviz_mismatch']}")
    if sg["clienti_cu_alarme_ref"]:
        print(f"  Alarme Phase 0: {', '.join(sg['clienti_cu_alarme_ref'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
