#!/usr/bin/env python3
"""
Verify LIPSA codes: search DI source for missing articles.

For each LIPSA code in comparison report, search DI_oferta for:
1. Exact code match → report deviz + context
2. Variant matches (prefix/suffix variants) → alert programmer
3. No match → report as GENUINE LIPSA

Usage:
    python3 tests/verify_lipsa_codes.py [--oferta 1|2] [--verbose]
"""

import json
import sys
import argparse
import re
from pathlib import Path

BASE = Path(__file__).parent.parent
OUTPUT = BASE / "output_AO"
INPUT = BASE / "input_AO"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_code(code):
    """Normalize code for comparison."""
    return re.sub(r"[#\-\s]+$", "", code.strip()).upper()


def search_di_pages_raw(di_data, code_pattern):
    """Search pages for code pattern (raw search, case-insensitive)."""
    results = []
    code_upper = code_pattern.upper()
    for page in di_data.get("pages", []):
        pnum = page["page_number"]
        lines = page.get("lines", [])
        for i, line in enumerate(lines):
            content = line.get("content", "")
            if code_upper in content.upper():
                # Extract context: 2 lines before and after
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                ctx = [(j + 1, lines[j].get("content", "")) for j in range(start, end)]
                results.append({
                    "page": pnum,
                    "line": i + 1,
                    "match": content,
                    "context": ctx,
                })
    return results


def find_variants(di_data, code, threshold=0.8):
    """Find codes similar to the search code (prefix/suffix variants, OCR errors)."""
    variants = []
    code_clean = re.sub(r"[#\-\s]+$", "", code.upper())

    # Extract all codes from DI
    all_codes = set()
    for page in di_data.get("pages", []):
        lines = page.get("lines", [])
        for line in lines:
            content = line.get("content", "").strip()
            # Look for code patterns: Letter+Digit or Digit patterns
            matches = re.findall(r'\b([A-Z]\d+[A-Z0-9]*)\b', content, re.IGNORECASE)
            all_codes.update(matches)

    # Find variants: same prefix or suffix
    for c in all_codes:
        c_upper = c.upper()
        # Check: starts with same prefix (first 3 chars)
        if c_upper.startswith(code_clean[:3]) and c_upper != code_clean:
            variants.append(c_upper)
        # Check: OCR variants (O→0, I→1, etc.)
        c_normalized = re.sub(r'[OI]', lambda m: '0' if m.group() == 'O' else '1', c_upper)
        if c_normalized == code_clean and c_upper != code_clean:
            variants.append(c_upper)

    return list(set(variants))


def extract_code_context(pages, code_match_line):
    """Extract surrounding lines to understand deviz/stage info."""
    # Look for patterns like "4.1-01" or stage indicators in nearby lines
    deviz_pattern = r'(\d+\.\d+(?:-\d+)?)'
    context_info = []

    for line_num, content in code_match_line.get("context", []):
        if re.search(deviz_pattern, content):
            match = re.search(deviz_pattern, content)
            if match:
                context_info.append(("deviz", match.group(1)))
        if any(word in content.upper() for word in ["LUCRARI", "CONSTRUCTII", "INCARCARE", "INLOCUIRE", "MONTARE"]):
            context_info.append(("stage", content[:80]))

    return context_info


def verify_lipsa_code(ref_code, deviz_ref, di_oferta, oferta_num, verbose=False):
    """Verify if LIPSA code exists in oferta DI source."""
    print(f"\n{'='*80}")
    print(f"[LIPSA] {ref_code:15s} deviz={deviz_ref}")

    # Search 1: Exact code match
    exact_matches = search_di_pages_raw(di_oferta, ref_code)

    if exact_matches:
        print(f"  ✓ FOUND (exact match)")
        for match in exact_matches[:2]:  # Show max 2 matches
            print(f"    Page {match['page']}, line {match['line']}: {match['match'][:70]}")
            # Try to extract deviz from context
            context_info = extract_code_context(di_oferta["pages"], match)
            if context_info:
                for info_type, info_val in context_info:
                    print(f"      {info_type}: {info_val[:60]}")
        return "FOUND_EXACT"

    # Search 2: Check for variants (prefix/suffix)
    print(f"  ✗ No exact match. Searching variants...")
    variants = find_variants(di_oferta, ref_code)

    if variants:
        print(f"  ⚠ FOUND VARIANTS (similar codes):")
        for var in variants[:5]:  # Max 5 variants
            matches = search_di_pages_raw(di_oferta, var)
            if matches:
                print(f"    {var} — {matches[0]['match'][:60]}")
        print(f"  → ALERT PROGRAMMER: Check if {ref_code} is OCR variant or code misclassification")
        return "FOUND_VARIANT"

    # Search 3: No match at all
    print(f"  ✗ NO MATCH FOUND")
    print(f"  → GENUINE LIPSA: {ref_code} not in oferta {oferta_num} source")
    return "GENUINE_LIPSA"


def main():
    parser = argparse.ArgumentParser(description="Verify LIPSA codes in DI source")
    parser.add_argument("--oferta", type=int, choices=[1, 2], default=1, help="Oferta number")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    args = parser.parse_args()

    oferta_num = args.oferta
    comp_path = OUTPUT / f"comparatie_oferta_{oferta_num}.json"
    di_oferta_path = INPUT / f"di_oferta_{oferta_num}.json"

    print(f"Loading comparison: {comp_path}")
    comp = load_json(comp_path)
    print(f"Loading DI oferta:  {di_oferta_path}")
    di_oferta = load_json(di_oferta_path)

    # Extract LIPSA codes
    lipsa_codes = [n for n in comp["neconformitati"] if n["tip"] == "ARTICOL_LIPSA"]
    print(f"\nFound {len(lipsa_codes)} LIPSA articles in OFERTA {oferta_num}")
    print(f"{'='*80}")

    results = {}
    for nc in lipsa_codes:
        ref_cod = nc.get("ref_cod", "")
        deviz_ref = nc.get("deviz_ref", "")

        result = verify_lipsa_code(ref_cod, deviz_ref, di_oferta, oferta_num, args.verbose)
        results[ref_cod] = result

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — OFERTA {oferta_num}:")
    found_exact = sum(1 for r in results.values() if r == "FOUND_EXACT")
    found_variant = sum(1 for r in results.values() if r == "FOUND_VARIANT")
    genuine_lipsa = sum(1 for r in results.values() if r == "GENUINE_LIPSA")

    print(f"  {found_exact:2d} codes found (exact match)")
    print(f"  {found_variant:2d} codes with variants (OCR/misclassification suspects)")
    print(f"  {genuine_lipsa:2d} genuine LIPSA (not in offer source)")
    print(f"  {'='*80}")


if __name__ == "__main__":
    main()
