#!/usr/bin/env python3
"""
Verify EXTRA codes: search DI referinta for articles that exist only in offer.

For each EXTRA code in comparison report, search referinta_oferta for:
1. Exact code match → report deviz + context + extraction pattern
2. Parent article (if subcomponent) → report parent code + context
3. No match → report as GENUINE EXTRA

Usage:
    python3 tests/verify_extra_codes.py [--oferta 1|2] [--verbose]
"""

import json
import sys
import argparse
import re
from pathlib import Path
from collections import Counter

BASE = Path(__file__).parent.parent
OUTPUT = BASE / "output_AO"
INPUT = BASE / "input_AO"


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_code(code):
    """Normalize code for comparison."""
    return re.sub(r"[#\-\s]+$", "", code.strip()).upper()


def search_di_pages_raw(di_data, code_pattern, max_results=3):
    """Search pages for code pattern (raw search, case-insensitive).

    Returns list of match results with context.
    """
    results = []
    code_upper = code_pattern.upper()

    # Generate variants to search
    search_patterns = [code_upper]
    if code_upper.startswith('$'):
        search_patterns.append(code_upper[1:])
    elif code_upper[0].isdigit() or code_upper[0].isalpha():
        search_patterns.append('$' + code_upper)

    for page in di_data.get("pages", []):
        pnum = page["page_number"]
        lines = page.get("lines", [])
        for i, line in enumerate(lines):
            content = line.get("content", "")
            for pattern in search_patterns:
                if pattern in content.upper():
                    # Extract context: 3 lines before and after
                    start = max(0, i - 3)
                    end = min(len(lines), i + 4)
                    ctx = [(j + 1, lines[j].get("content", "")) for j in range(start, end)]
                    results.append({
                        "page": pnum,
                        "line": i + 1,
                        "match": content,
                        "context": ctx,
                        "pattern_found": pattern,
                    })
                    break

    return results[:max_results]


def find_parent_code(di_data, subcomp_code):
    """Find parent article code if this is a subcomponent.

    Looks for patterns like: PARENT_CODE[variant] SUBCOMP_CODE
    or: PARENT_CODE with subcomponents listed below.
    """
    parents = []
    code_pattern = r'([A-Z]{2,5}\d{2,4}[A-Z]?\d{0,2})'

    for page in di_data.get("pages", []):
        lines = page.get("lines", [])
        for i, line in enumerate(lines):
            content = line.get("content", "").upper()

            # Check if this line contains both parent pattern and our subcomponent
            if subcomp_code.upper() in content:
                # Look backward for parent code
                for j in range(max(0, i - 5), i):
                    prev_line = lines[j].get("content", "").upper()
                    matches = re.findall(code_pattern, prev_line)
                    if matches:
                        # Found potential parent
                        parent = matches[0]
                        if parent != subcomp_code.upper():
                            parents.append({
                                "parent_code": parent,
                                "page": page["page_number"],
                                "parent_line": j + 1,
                                "subcomp_line": i + 1,
                                "context_line": content[:80]
                            })

    return parents


def extract_article_pattern(di_data, code, match_result):
    """Extract the full article pattern from referinta for comparison."""
    page_num = match_result["page"]
    start_line = match_result["line"] - 1

    # Find the page
    page_data = None
    for p in di_data.get("pages", []):
        if p["page_number"] == page_num:
            page_data = p
            break

    if not page_data:
        return None

    lines = page_data.get("lines", [])

    # Extract article block: from current code to next code or metadata
    article_lines = []
    i = start_line

    # Collect lines for this article
    while i < len(lines):
        line = lines[i].get("content", "")
        article_lines.append((i + 1, line))

        # Stop at next article code or metadata marker
        if i > start_line:  # Don't stop at first line
            if re.match(r'^\s*[A-Z]{2,5}\d{2,4}', line.upper()) or \
               re.match(r'^\s*(material|manopera|utilaj|transport):', line.lower()):
                break

        i += 1
        if len(article_lines) > 10:  # Max 10 lines per article
            break

    return article_lines


def verify_extra_code(oferta_code, deviz_ref, di_referinta, oferta_num, verbose=False):
    """Verify if EXTRA code exists in referinta DI source."""
    print(f"\n{'='*80}")
    print(f"[EXTRA] {oferta_code:20s} deviz={deviz_ref}")

    # Search 1: Exact code match
    exact_matches = search_di_pages_raw(di_referinta, oferta_code)

    if exact_matches:
        print(f"  ✓ FOUND IN REFERINTA")
        match = exact_matches[0]
        print(f"    Page {match['page']}, line {match['line']}: {match['match'][:70]}")
        print(f"    Pattern found as: {match.get('pattern_found')}")

        # Extract full article
        article_pattern = extract_article_pattern(di_referinta, oferta_code, match)
        if article_pattern:
            print(f"    Full article pattern:")
            for line_num, content in article_pattern[:5]:
                print(f"      {line_num}: {content[:70]}")
            if len(article_pattern) > 5:
                print(f"      ... ({len(article_pattern) - 5} more lines)")

        return "FOUND_EXACT"

    # Search 2: Check if this is a subcomponent of a parent code
    print(f"  ✗ No exact match. Checking for parent/subcomponent relationship...")
    parents = find_parent_code(di_referinta, oferta_code)

    if parents:
        print(f"  ✓ FOUND AS SUBCOMPONENT:")
        for parent_info in parents[:3]:
            print(f"    Parent: {parent_info['parent_code']}")
            print(f"      Page {parent_info['page']}, parent line {parent_info['parent_line']}, subcomp line {parent_info['subcomp_line']}")
            print(f"      Context: {parent_info['context_line'][:70]}")

        # Now search for parent code to understand structure
        parent_code = parents[0]['parent_code']
        parent_matches = search_di_pages_raw(di_referinta, parent_code, max_results=1)
        if parent_matches:
            print(f"    Parent article pattern:")
            parent_match = parent_matches[0]
            article_pattern = extract_article_pattern(di_referinta, parent_code, parent_match)
            if article_pattern:
                for line_num, content in article_pattern[:5]:
                    print(f"      {line_num}: {content[:70]}")

        return "FOUND_AS_SUBCOMPONENT"

    # Search 3: No match at all
    print(f"  ✗ NO MATCH FOUND in referinta")
    print(f"  → GENUINE EXTRA: {oferta_code} in oferta {oferta_num} only")
    return "GENUINE_EXTRA"


def main():
    parser = argparse.ArgumentParser(description="Verify EXTRA codes in referinta source")
    parser.add_argument("--oferta", type=int, choices=[1, 2], default=1, help="Oferta number")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--limit", type=int, default=20, help="Limit number of codes to check")
    parser.add_argument("--analyze-gaps", action="store_true", help="Analyze extraction gaps")
    args = parser.parse_args()

    oferta_num = args.oferta
    comp_path = OUTPUT / f"comparatie_oferta_{oferta_num}.json"
    di_referinta_path = INPUT / "di_referinta.json"
    referinta_path = OUTPUT / "referinta.json"

    print(f"Loading comparison: {comp_path}")
    comp = load_json(comp_path)
    print(f"Loading DI referinta:  {di_referinta_path}")
    di_referinta = load_json(di_referinta_path)
    print(f"Loading referinta:     {referinta_path}")
    referinta = load_json(referinta_path)

    # Extract EXTRA codes
    extra_codes = [n for n in comp["neconformitati"] if n["tip"] == "ARTICOL_EXTRA"]
    print(f"\nFound {len(extra_codes)} EXTRA articles in OFERTA {oferta_num}")
    print(f"Processing first {min(args.limit, len(extra_codes))} codes...")
    print(f"{'='*80}")

    results = {}
    for nc in extra_codes[:args.limit]:
        oferta_cod = nc.get("oferta_cod", "")
        deviz_ref = nc.get("deviz_ref", "")

        result = verify_extra_code(oferta_cod, deviz_ref, di_referinta, oferta_num, args.verbose)
        results[oferta_cod] = result

    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY — OFERTA {oferta_num} EXTRA CODES:")

    found_exact = sum(1 for r in results.values() if r == "FOUND_EXACT")
    found_subcomp = sum(1 for r in results.values() if r == "FOUND_AS_SUBCOMPONENT")
    genuine_extra = sum(1 for r in results.values() if r == "GENUINE_EXTRA")

    print(f"  {found_exact:2d} codes found in referinta (exact match)")
    print(f"  {found_subcomp:2d} codes found as subcomponents of parents")
    print(f"  {genuine_extra:2d} genuine EXTRA (only in offer)")
    print(f"  {'='*80}")

    # Breakdown by deviz
    print(f"\nDeviz breakdown for EXTRA codes:")
    deviz_counts = Counter()
    for nc in extra_codes[:args.limit]:
        deviz_counts[nc.get("deviz_ref", "UNKNOWN")] += 1

    for deviz, count in sorted(deviz_counts.items()):
        result_count = sum(1 for c, r in results.items() if r == "FOUND_EXACT")
        print(f"  {deviz:10s}: {count:3d} codes")

    # Analysis: extraction gaps
    if args.analyze_gaps:
        print(f"\n{'='*80}")
        print(f"EXTRACTION GAP ANALYSIS:")
        print(f"  Checking which EXTRA codes exist in di_referinta but not in referinta.json...")

        ref_extracted_codes = set()
        for art in referinta.get('articole', []):
            cod = art.get('cod', '').lstrip('$')
            ref_extracted_codes.add(cod)
            ref_extracted_codes.add(cod.lstrip('$'))

        in_di_only = 0
        in_both = 0

        for nc in extra_codes:
            oferta_cod = nc.get("oferta_cod", "").lstrip('$')
            if oferta_cod in ref_extracted_codes:
                in_both += 1
            else:
                # Check if it's in di_referinta pages
                di_matches = search_di_pages_raw(di_referinta, oferta_cod, max_results=1)
                if di_matches:
                    in_di_only += 1

        total = in_both + in_di_only
        print(f"  In referinta.json: {in_both}")
        print(f"  In di_referinta but NOT extracted: {in_di_only}")
        print(f"  Extraction gap: {(in_di_only*100)//total if total > 0 else 0}% of codes found in source")
        print(f"  → Referinta extraction needs improvement to match offer extraction quality")


if __name__ == "__main__":
    main()
