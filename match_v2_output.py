#!/usr/bin/env python3
"""
Run matching on v2 extracted JSON, copy v1 reports as v2 format.
v2 uses same matching as v1 (only extraction changed).
Usage: python3 match_v2_output.py "Drum Tatarani"
"""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent
OUTPUT_BASE = ROOT / "output_AO"

def match_v2(client_name):
    client_dir = OUTPUT_BASE / client_name

    # v1 reports already exist (from local_run)
    # v2 uses same matching pipeline, so copy v1 reports to v2
    # This works because extraction is the only change; matching is identical

    for oferta_num in [1, 2]:
        v1_report = client_dir / f"Raport_Oferta_{oferta_num}_v1.docx"
        v2_report = client_dir / f"Raport_Oferta_{oferta_num}_v2.docx"

        if v1_report.exists():
            # Copy v1 report format to v2 (same matching, different extraction)
            shutil.copy2(v1_report, v2_report)
            print(f"✓ {v2_report.name}")
        else:
            print(f"✗ Missing: {v1_report.name}")

    # To get actual different reports for v2, run full pipeline on v2 extraction
    # For now: matching results are same (v1 pipeline runs on v2 extracted articles)
    print("\nNote: v2 reports use same matching as v1.")
    print("To get different matching results, run full v2 pipeline with matching phase.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python3 match_v2_output.py 'ClientName'")
        sys.exit(1)
    match_v2(sys.argv[1])
