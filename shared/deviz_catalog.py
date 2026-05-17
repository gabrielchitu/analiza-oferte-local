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


def find_deviz_for_text(text: str, deviz_text_map: dict) -> str | None:
    """
    Find numeric deviz code by matching text against reference denominations.

    Args:
        text: Text from page (e.g., "Arhitectura - eligibili tip I")
        deviz_text_map: Map built from reference data via build_deviz_text_map()

    Returns:
        Numeric deviz code (e.g., "4.1-03") or None if no good match
    """
    if not text or not deviz_text_map:
        return None

    text_lower = text.lower().strip()
    best_deviz = None
    best_score = 0.0

    # Try each deviz's texts
    for deviz, info in deviz_text_map.items():
        for ref_text in info['texts']:
            # Exact substring match (highest priority)
            if ref_text in text_lower or text_lower in ref_text:
                return deviz

            # Fuzzy match
            score = _text_similarity(text_lower, ref_text)
            if score > best_score:
                best_score = score
                best_deviz = deviz

    # Return best match if above threshold
    if best_score >= 0.65:
        return best_deviz

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
