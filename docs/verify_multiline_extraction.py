#!/usr/bin/env python3
"""
Verification Script for Multi-Line Article Extraction

This script validates that the multi-line article extraction fix is working
correctly in any project. It compares extracted articles against expected
articles and reports completeness metrics.

Usage:
    python verify_multiline_extraction.py <output_file> <expected_file>

Where:
    - output_file: JSON file with extracted articles (list of dicts with 'cod', 'denumire' keys)
    - expected_file: Text file with expected articles (one per line, format: "CODE|EXPECTED_DESCRIPTION")

Example:
    python verify_multiline_extraction.py output.json expected.txt

Output:
    - Verification report with success rate
    - List of missing or incomplete articles
    - Detailed comparison for articles with gaps
"""

import json
import sys
import re
from pathlib import Path
from typing import Dict, List, Tuple


def load_articles_from_json(filepath: str) -> Dict[str, Dict]:
    """
    Load extracted articles from JSON file.

    Expected format: List of dicts with keys:
        - 'cod': article code (string)
        - 'denumire': article description (string)
        - (other fields optional)

    Args:
        filepath: Path to JSON file

    Returns:
        Dict mapping article code -> article dict
    """
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in {filepath}: {e}")
        sys.exit(1)
    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    # Handle both list and dict formats
    if isinstance(data, list):
        articles = {art.get('cod', f'UNKNOWN_{i}'): art for i, art in enumerate(data)}
    elif isinstance(data, dict):
        articles = data
    else:
        print(f"ERROR: Expected list or dict in JSON, got {type(data)}")
        sys.exit(1)

    return articles


def load_expected_articles(filepath: str) -> Dict[str, str]:
    """
    Load expected articles from text file.

    Format: One article per line: "CODE|EXPECTED_DESCRIPTION"
    Lines starting with # are comments and ignored.

    Args:
        filepath: Path to text file

    Returns:
        Dict mapping article code -> expected description
    """
    expected = {}
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue

                # Parse "CODE|DESCRIPTION" format
                if '|' not in line:
                    print(f"WARNING: Line {line_num} has no pipe separator: {line}")
                    continue

                parts = line.split('|', 1)
                code = parts[0].strip()
                description = parts[1].strip()

                if not code or not description:
                    print(f"WARNING: Line {line_num} missing code or description: {line}")
                    continue

                expected[code] = description

    except FileNotFoundError:
        print(f"ERROR: File not found: {filepath}")
        sys.exit(1)

    return expected


def similarity_ratio(s1: str, s2: str) -> float:
    """
    Calculate similarity between two strings (0.0 to 1.0).

    Uses character-level comparison to handle partial matches.

    Args:
        s1: First string
        s2: Second string

    Returns:
        Similarity ratio (0.0 = completely different, 1.0 = identical)
    """
    if len(s1) == 0 and len(s2) == 0:
        return 1.0
    if len(s1) == 0 or len(s2) == 0:
        return 0.0

    # Simple character match ratio
    matches = sum(1 for c1, c2 in zip(s1, s2) if c1 == c2)
    total = max(len(s1), len(s2))
    return matches / total


def normalize_text(text: str) -> str:
    """
    Normalize text for comparison (lowercase, collapse whitespace).

    Args:
        text: Text to normalize

    Returns:
        Normalized text
    """
    # Lowercase
    text = text.lower()
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def verify_article(
    expected_description: str,
    extracted_article: Dict
) -> Tuple[bool, float, str]:
    """
    Verify if an extracted article matches expected description.

    Returns:
        Tuple of (is_complete, similarity, issue_description)
    """
    extracted_description = extracted_article.get('denumire', '').strip()

    # Exact match (case-insensitive)
    if normalize_text(expected_description) == normalize_text(extracted_description):
        return True, 1.0, "PASS"

    # Check if expected is substring of extracted (might have extra text)
    if normalize_text(expected_description) in normalize_text(extracted_description):
        return True, 0.95, "PASS_WITH_EXTRA"

    # Calculate similarity
    similarity = similarity_ratio(
        normalize_text(expected_description),
        normalize_text(extracted_description)
    )

    if similarity >= 0.9:
        return True, similarity, "PASS_PARTIAL"
    elif similarity >= 0.7:
        return False, similarity, "INCOMPLETE"
    else:
        return False, similarity, "MISSING"


def main():
    """Main verification routine."""
    if len(sys.argv) != 3:
        print(__doc__)
        print("Usage: python verify_multiline_extraction.py <output.json> <expected.txt>")
        sys.exit(1)

    output_file = sys.argv[1]
    expected_file = sys.argv[2]

    # Load data
    print("Loading extracted articles...")
    extracted = load_articles_from_json(output_file)
    print(f"  Loaded {len(extracted)} extracted articles")

    print("\nLoading expected articles...")
    expected = load_expected_articles(expected_file)
    print(f"  Loaded {len(expected)} expected articles")

    # Verify
    print("\nVerifying...")
    results = {
        'total_expected': len(expected),
        'found': 0,
        'complete': 0,
        'incomplete': 0,
        'missing': 0,
        'passed': [],
        'failed': [],
    }

    for code, expected_desc in expected.items():
        if code in extracted:
            results['found'] += 1
            is_complete, similarity, status = verify_article(
                expected_desc,
                extracted[code]
            )

            if is_complete:
                results['complete'] += 1
                results['passed'].append({
                    'code': code,
                    'status': status,
                    'similarity': similarity
                })
            else:
                results['incomplete'] += 1
                results['failed'].append({
                    'code': code,
                    'expected': expected_desc,
                    'extracted': extracted[code].get('denumire', ''),
                    'similarity': similarity,
                    'status': status
                })
        else:
            results['missing'] += 1
            results['failed'].append({
                'code': code,
                'expected': expected_desc,
                'extracted': None,
                'similarity': 0.0,
                'status': 'NOT_FOUND'
            })

    # Report
    print("\n" + "=" * 60)
    print("VERIFICATION REPORT")
    print("=" * 60)

    total = results['total_expected']
    success_rate = (results['complete'] / total * 100) if total > 0 else 0

    print(f"\nSummary:")
    print(f"  Total expected: {results['total_expected']}")
    print(f"  Found: {results['found']} ({results['found']/total*100:.1f}%)")
    print(f"  Complete: {results['complete']} ({results['complete']/total*100:.1f}%)")
    print(f"  Incomplete: {results['incomplete']} ({results['incomplete']/total*100:.1f}%)")
    print(f"  Missing: {results['missing']} ({results['missing']/total*100:.1f}%)")

    print(f"\nOverall Success Rate: {success_rate:.1f}%")

    if success_rate >= 95:
        print("STATUS: PASS ✓ (95%+ success rate)")
    elif success_rate >= 85:
        print("STATUS: PASS WITH ISSUES ⚠ (85-95% success rate)")
    else:
        print("STATUS: FAIL ✗ (<85% success rate)")

    # Show failures
    if results['failed']:
        print("\n" + "-" * 60)
        print("Failed Verifications:")
        print("-" * 60)

        for item in sorted(results['failed'], key=lambda x: x['code'])[:20]:  # Show top 20
            code = item['code']
            status = item['status']
            expected = item['expected']
            extracted = item['extracted']
            similarity = item['similarity']

            print(f"\n{code} [{status}] ({similarity:.0%} similarity)")
            print(f"  Expected: {expected[:80]}{'...' if len(expected) > 80 else ''}")
            if extracted:
                print(f"  Got:      {extracted[:80]}{'...' if len(extracted) > 80 else ''}")
            else:
                print(f"  Got:      [NOT FOUND]")

        if len(results['failed']) > 20:
            print(f"\n... and {len(results['failed']) - 20} more failures")

    print("\n" + "=" * 60)

    # Exit code
    sys.exit(0 if success_rate >= 95 else 1)


if __name__ == '__main__':
    main()
