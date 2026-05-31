"""Set-based article matching using unique keys.

Performs set operations (intersection, difference) on article keys to produce
matched/ref_only/oferta_only results. Uses get_unique_articles() for deduplication.
"""

from typing import Dict, List
from shared.unique_key_detector import get_unique_articles


def match_articles_by_key(
    ref_articles: List[Dict], oferta_articles: List[Dict]
) -> Dict:
    """
    Set-based matching of reference and offer articles using unique keys.

    Workflow:
    1. Deduplicate ref and oferta by unique key (using get_unique_articles)
    2. Extract key sets
    3. Compute set operations:
       - matched_keys = ref_keys & oferta_keys (intersection)
       - ref_only_keys = ref_keys - oferta_keys (difference)
       - oferta_only_keys = oferta_keys - ref_keys (difference)
    4. Build result with matched pairs, singles, and statistics

    Args:
        ref_articles: List of reference article dicts (nr, cod, descriere, um, cant, etc.)
        oferta_articles: List of offer article dicts (same structure)

    Returns:
        Dict with keys:
        - matched: List of {"ref": article, "oferta": article} pairs
        - ref_only: List of articles only in reference
        - oferta_only: List of articles only in offer
        - stats: Dict with counts and statistics
            - matched_count: Number of matched pairs
            - ref_only_count: Number of ref-only articles
            - oferta_only_count: Number of offer-only articles
            - ref_total: Total unique articles in reference (after dedup)
            - oferta_total: Total unique articles in offer (after dedup)
            - ref_articles_count: Original count of reference articles (before dedup)
            - oferta_articles_count: Original count of offer articles (before dedup)
    """
    # Store original counts before deduplication
    ref_articles_count = len(ref_articles)
    oferta_articles_count = len(oferta_articles)

    # Get unique articles (deduped by key)
    ref_unique = get_unique_articles(ref_articles)
    oferta_unique = get_unique_articles(oferta_articles)

    # Extract key sets
    ref_keys = set(ref_unique.keys())
    oferta_keys = set(oferta_unique.keys())

    # Set operations: intersection and differences
    matched_keys = ref_keys & oferta_keys
    ref_only_keys = ref_keys - oferta_keys
    oferta_only_keys = oferta_keys - ref_keys

    # Build matched pairs (sorted by key for consistency)
    matched = [
        {"ref": ref_unique[k], "oferta": oferta_unique[k]}
        for k in sorted(matched_keys)
    ]

    # Build ref_only list (sorted by key)
    ref_only = [ref_unique[k] for k in sorted(ref_only_keys)]

    # Build oferta_only list (sorted by key)
    oferta_only = [oferta_unique[k] for k in sorted(oferta_only_keys)]

    return {
        "matched": matched,
        "ref_only": ref_only,
        "oferta_only": oferta_only,
        "stats": {
            "matched_count": len(matched),
            "ref_only_count": len(ref_only),
            "oferta_only_count": len(oferta_only),
            "ref_total": len(ref_unique),
            "oferta_total": len(oferta_unique),
            "ref_articles_count": ref_articles_count,
            "oferta_articles_count": oferta_articles_count,
        },
    }
