"""Group-level matching using deviz_cod with article-level matching.

Performs set operations on deviz_cod keys to match groups, then uses
set-based article matching within each matched group.
"""

from typing import Dict, List
from shared.set_based_matcher import match_articles_by_key


def match_groups_by_deviz(ref_groups: List[Dict], oferta_groups: List[Dict]) -> Dict:
    """
    Match groups by deviz_cod, then articles within each matched group.

    Workflow:
    1. Build deviz_cod maps for ref and oferta groups
    2. Extract deviz_cod sets
    3. Compute set operations:
       - matched_devizes = ref_devizes & oferta_devizes (intersection)
       - ref_only_devizes = ref_devizes - oferta_devizes (difference)
       - oferta_only_devizes = oferta_devizes - ref_devizes (difference)
    4. For each matched group: run match_articles_by_key() on articles
    5. Return structure: {matched_groups, ref_only_groups, oferta_only_groups}

    Args:
        ref_groups: List of reference group dicts with deviz_cod and articole
        oferta_groups: List of offer group dicts with deviz_cod and articole

    Returns:
        Dict with keys:
        - matched_groups: List of matched groups with article matching results
        - ref_only_groups: List of groups only in reference (full structure preserved)
        - oferta_only_groups: List of groups only in offer (full structure preserved)
    """
    # Build deviz_cod maps
    ref_deviz_map = {g.get("deviz_cod"): g for g in ref_groups}
    oferta_deviz_map = {g.get("deviz_cod"): g for g in oferta_groups}

    # Extract deviz_cod sets
    ref_devizes = set(ref_deviz_map.keys())
    oferta_devizes = set(oferta_deviz_map.keys())

    # Set operations
    matched_devizes = ref_devizes & oferta_devizes
    ref_only_devizes = ref_devizes - oferta_devizes
    oferta_only_devizes = oferta_devizes - ref_devizes

    # Match articles within each matched group
    matched_groups = []
    for deviz in sorted(matched_devizes):
        ref_group = ref_deviz_map[deviz]
        oferta_group = oferta_deviz_map[deviz]

        # Match articles within group
        article_match = match_articles_by_key(
            ref_group.get("articole", []), oferta_group.get("articole", [])
        )

        matched_groups.append(
            {
                "deviz_cod": deviz,
                "deviz_den": ref_group.get("deviz_den", ""),
                "articole": article_match["matched"],
                "stats": article_match["stats"],
            }
        )

    # Ref-only groups (keep full structure)
    ref_only_groups = [ref_deviz_map[d] for d in sorted(ref_only_devizes)]

    # Oferta-only groups (keep full structure)
    oferta_only_groups = [oferta_deviz_map[d] for d in sorted(oferta_only_devizes)]

    return {
        "matched_groups": matched_groups,
        "ref_only_groups": ref_only_groups,
        "oferta_only_groups": oferta_only_groups,
    }
