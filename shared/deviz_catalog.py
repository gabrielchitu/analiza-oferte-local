"""
Deviz Matcher — Dynamically matches deviz denominations from reference data.

Instead of using a hardcoded catalog, extracts actual denomination texts
from reference articles and uses them to classify pages in offers.
"""

from difflib import SequenceMatcher
import logging

logger = logging.getLogger(__name__)


def build_deviz_text_map(reference_articles: list) -> dict:
    """
    Build a map of deviz codes to their denomination texts from reference data.

    Returns:
        {
            'deviz_code': {
                'texts': [list of unique denomination texts],
                'count': total articles
            }
        }
    """
    deviz_map = {}

    for art in reference_articles:
        deviz = (art.get('deviz') or '').strip()
        denom = (art.get('deviz_denumire') or '').strip()

        if not deviz:
            continue

        if deviz not in deviz_map:
            deviz_map[deviz] = {'texts': set(), 'count': 0}

        deviz_map[deviz]['count'] += 1
        if denom:
            deviz_map[deviz]['texts'].add(denom.lower())

    # Convert sets to sorted lists for consistent matching
    for deviz in deviz_map:
        deviz_map[deviz]['texts'] = sorted(list(deviz_map[deviz]['texts']))

    logger.info(f"[DEVIZ-MAP] Built dynamic map from {len(reference_articles)} reference articles")
    logger.info(f"[DEVIZ-MAP] Devizes: {sorted(deviz_map.keys())}")

    return deviz_map


def _text_similarity(text_a: str, text_b: str) -> float:
    """Calculate similarity between two texts (0.0 to 1.0)."""
    if not text_a or not text_b:
        return 0.0
    return SequenceMatcher(None, text_a.lower(), text_b.lower()).ratio()


def find_all_devizes_for_text(text: str, deviz_text_map: dict) -> list[tuple[str, str, float]]:
    """
    GENERAL SOLUTION: Find ALL possible deviz codes matching text, sorted by confidence.
    Returns list of (deviz_code, match_type, score) tuples for disambiguation.

    Example: "Terasamente" returns:
      [(4.2-1, 'exact', 1.0), (4.4-1, 'exact', 1.0), (4.3-01, 'fuzzy', 0.72)]

    Page classifier can then use context (obiectul, articole) to pick the right one.

    Args:
        text: Text from page (e.g., "Terasamente")
        deviz_text_map: Map built from reference data

    Returns:
        List of (deviz_code, match_type, similarity_score) sorted by score descending
    """
    if not text or not deviz_text_map:
        return []

    text_lower = text.lower().strip()
    matches = []  # (deviz, match_type, score)

    for deviz, info in deviz_text_map.items():
        for ref_text in info['texts']:
            # EXACT MATCH: text_lower == ref_text (best match)
            if text_lower == ref_text:
                matches.append((deviz, 'exact', 1.0))
                continue

            # SUBSTRING MATCH: only if text CONTAINS ref_text AND text is longer
            # Avoids "terasamente" incorrectly matching "terasamente apa"
            if len(text_lower) > len(ref_text) and ref_text in text_lower:
                matches.append((deviz, 'substring', 0.85))
                continue

            # FUZZY MATCH: similarity above threshold
            score = _text_similarity(text_lower, ref_text)
            if score >= 0.65:
                matches.append((deviz, 'fuzzy', score))

    # Sort by score descending (exact=1.0 first, then substring, then fuzzy)
    matches.sort(key=lambda x: (-x[2], x[0]))

    return matches


def find_deviz_for_text(text: str, deviz_text_map: dict) -> str | None:
    """
    LEGACY: Find single best deviz code.
    For backward compatibility. Uses find_all_devizes_for_text internally.
    """
    matches = find_all_devizes_for_text(text, deviz_text_map)
    if matches:
        return matches[0][0]
    return None


def extract_stadiul_fizic(page_text: str) -> str | None:
    """
    Extract "STADIUL FIZIC:" value from page text.

    Format: "STADIUL FIZIC: [value]"
    Sometimes followed by "0 1 2 3 4 5" (table headers)

    Args:
        page_text: Full page extracted text

    Returns:
        Extracted value or None if not found
    """
    import re

    # Pattern: "STADIUL FIZIC:" followed by text up to newline or numbers
    match = re.search(
        r'STADIUL\s+FIZIC:\s*([^\n0-9]+?)(?:\s+[0-9]|\s*$)',
        page_text,
        re.IGNORECASE | re.MULTILINE
    )

    if match:
        return match.group(1).strip()

    return None
