#!/usr/bin/env python3
"""
Debug SSR ghost groups (oferta_only unmatched groups).

Task 1: Identify why certain oferta groups are not matching to reference groups.

Findings:
1. Ghost groups have deviz_cod='oferta' (invalid)
2. Ghost groups have empty deviz_cod/deviz_den in output
3. Ghost groups have articles but source_pages is empty
4. This means they're being created OUTSIDE the normal group extraction

Goal: Trace where these groups come from in the pipeline.
"""
import json
import sys

def analyze_oferta_only_groups(oferta_num):
    """Analyze oferta_only groups from holistic output."""
    hol_path = f"output_AO/Scoala Sportiva Racari/holistic_oferta_{oferta_num}.json"
    try:
        with open(hol_path, "r") as f:
            hol = json.load(f)
    except FileNotFoundError:
        print(f"File not found: {hol_path}")
        return

    oferta_only = hol.get('oferta_only_groups', [])
    print(f"\n=== Oferta {oferta_num}: {len(oferta_only)} oferta_only (ghost) groups ===\n")

    # Categorize by characteristic
    categories = {
        'invalid_header': [],  # deviz_cod='oferta'
        'with_articles': [],   # have articles but no deviz_cod
        'empty': []            # completely empty
    }

    for i, group in enumerate(oferta_only):
        oferta_header = group.get('oferta_header', '')
        deviz_cod = group.get('oferta_deviz_cod', '')  # Note: not 'deviz_cod'
        deviz_den = group.get('deviz_denumire', '')
        articles = group.get('articles', [])

        if "deviz_cod='oferta'" in str(oferta_header):
            categories['invalid_header'].append(i)
        elif articles and not deviz_cod:
            categories['with_articles'].append(i)
        else:
            categories['empty'].append(i)

    # Report
    for cat, indices in categories.items():
        if indices:
            print(f"{cat}: {len(indices)} groups")
            for idx in indices[:3]:
                g = oferta_only[idx]
                print(f"  Group {idx}:")
                print(f"    oferta_header (first 100): {str(g.get('oferta_header', ''))[:100]}")
                print(f"    deviz_denumire: {g.get('deviz_denumire', '')[:80]}")
                print(f"    articles: {len(g.get('articles', []))}")


def check_extraction_stages(oferta_num):
    """Check where these groups appear in the extraction pipeline."""
    print(f"\n=== Extraction stage check for Oferta {oferta_num} ===\n")

    # Step 1: Check di_oferta pages
    di_path = f"input_AO/Scoala Sportiva Racari/di_oferta_{oferta_num}.json"
    try:
        with open(di_path, "r") as f:
            di = json.load(f)
        print(f"✓ di_oferta_{oferta_num}: {len(di.get('pages', []))} pages with OCR content")
    except FileNotFoundError:
        print(f"✗ di_oferta_{oferta_num}: NOT FOUND")

    # Step 2: Check raw oferta.json output
    oferta_path = f"output_AO/Scoala Sportiva Racari/oferta_{oferta_num}.json"
    try:
        with open(oferta_path, "r") as f:
            oferta_raw = json.load(f)
        print(f"✓ oferta_{oferta_num}.json: {list(oferta_raw.keys())}")
        if 'articole' in oferta_raw:
            print(f"  - articole: {len(oferta_raw['articole'])} items")
        if 'grupos' in oferta_raw:
            print(f"  - grupos: {len(oferta_raw['grupos'])} items")
    except FileNotFoundError:
        print(f"✗ oferta_{oferta_num}.json: NOT FOUND")

    # Step 3: Check comparatie_oferta (grouped by deviz)
    comp_path = f"output_AO/Scoala Sportiva Racari/comparatie_oferta_{oferta_num}.json"
    try:
        with open(comp_path, "r") as f:
            comp = json.load(f)
        print(f"✓ comparatie_oferta_{oferta_num}.json: {list(comp.keys())}")
    except FileNotFoundError:
        print(f"✗ comparatie_oferta_{oferta_num}.json: NOT FOUND")

    # Step 4: Check matching_debug (before final holistic assembly)
    debug_path = f"output_AO/Scoala Sportiva Racari/matching_debug_oferta_{oferta_num}.json"
    try:
        with open(debug_path, "r") as f:
            debug = json.load(f)
        print(f"✓ matching_debug_oferta_{oferta_num}.json:")
        print(f"  - ref_groups: {len(debug.get('ref_groups', []))}")
        print(f"  - oferta_groups: {len(debug.get('oferta_groups', []))}")
        print(f"  - matched: {len(debug.get('matched', []))}")
        print(f"  - oferta_only: {len(debug.get('oferta_only', []))}")
    except FileNotFoundError:
        print(f"✗ matching_debug_oferta_{oferta_num}.json: NOT FOUND")


if __name__ == "__main__":
    # Analyze O1, O2, O3
    for oferta_num in [1, 2, 3]:
        analyze_oferta_only_groups(oferta_num)
        check_extraction_stages(oferta_num)

    print("\n=== Summary ===")
    print("Ghost groups likely come from articles that don't match any reference group.")
    print("They accumulate under a generic 'oferta_only' grouping with empty metadata.")
    print("Next: Check why group matching LLM fails for these oferta groups.")
