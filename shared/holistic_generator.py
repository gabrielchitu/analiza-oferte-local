"""Holistic JSON generator from v2 extraction + matching results.

Converts v2 extracted data (reference + offer with groups and articles)
into v1-compatible holistic JSON with matched_groups, ref_only_groups,
oferta_only_groups, and aggregated statistics.

Entry point: generate_holistic_v2(ref_extracted, oferta_extracted)
"""

from typing import Dict, List
from shared.group_set_matcher import match_groups_by_deviz


def generate_holistic_v2(ref_extracted: Dict, oferta_extracted: Dict) -> Dict:
    """Generate v1-compatible holistic JSON from v2 extraction + matching.

    Converts v2 extracted groups (reference + offer) into holistic JSON
    with matched/ref_only/oferta_only groups and aggregated statistics.

    Workflow:
    1. Extract groups from ref_extracted and oferta_extracted
    2. Call match_groups_by_deviz() to perform set-based group matching
    3. Count articles in each category (matched, ref_only, oferta_only)
    4. Build holistic JSON with v1-compatible structure
    5. Add aggregated statistics

    Args:
        ref_extracted: Dict with structure:
            {
                "client": str,
                "di_file": str,
                "extraction_version": "2.0",
                "grupos": [
                    {
                        "deviz_cod": str,
                        "deviz_den": str,
                        "articole": [article_dict],
                        ...
                    }
                ]
            }
        oferta_extracted: Same structure as ref_extracted

    Returns:
        Dict with structure:
        {
            "client": str,
            "di_file": str,
            "extraction_version": "2.0",
            "matched_groups": [matched_group_dict],
            "ref_only_groups": [group_dict],
            "oferta_only_groups": [group_dict],
            "stats": {
                "matched_articles_count": int,
                "ref_only_articles_count": int,
                "oferta_only_articles_count": int,
                "matched_groups_count": int,
                "ref_only_groups_count": int,
                "oferta_only_groups_count": int
            }
        }
    """
    # Extract groups from both extracted documents
    ref_groups = ref_extracted.get("grupos", [])
    oferta_groups = oferta_extracted.get("grupos", [])

    # Perform group matching by deviz_cod
    match_result = match_groups_by_deviz(ref_groups, oferta_groups)

    # Count articles in each category
    # 1. Matched articles within matched groups
    matched_articles = sum(
        len(g.get("articole", [])) for g in match_result["matched_groups"]
    )

    # 2. Ref-only articles: sum from ref_only_groups + ref_only articles within matched groups
    ref_only_from_groups = sum(
        len(g.get("articole", [])) for g in match_result["ref_only_groups"]
    )
    ref_only_within_matched = sum(
        g.get("stats", {}).get("ref_only_count", 0)
        for g in match_result["matched_groups"]
    )
    ref_only_articles = ref_only_from_groups + ref_only_within_matched

    # 3. Oferta-only articles: sum from oferta_only_groups + oferta_only articles within matched groups
    oferta_only_from_groups = sum(
        len(g.get("articole", [])) for g in match_result["oferta_only_groups"]
    )
    oferta_only_within_matched = sum(
        g.get("stats", {}).get("oferta_only_count", 0)
        for g in match_result["matched_groups"]
    )
    oferta_only_articles = oferta_only_from_groups + oferta_only_within_matched

    # Build holistic JSON with v1-compatible structure
    holistic = {
        "client": oferta_extracted.get("client", ""),
        "di_file": oferta_extracted.get("di_file", ""),
        "extraction_version": "2.0",
        "matched_groups": match_result["matched_groups"],
        "ref_only_groups": match_result["ref_only_groups"],
        "oferta_only_groups": match_result["oferta_only_groups"],
        "stats": {
            "matched_articles_count": matched_articles,
            "ref_only_articles_count": ref_only_articles,
            "oferta_only_articles_count": oferta_only_articles,
            "matched_groups_count": len(match_result["matched_groups"]),
            "ref_only_groups_count": len(match_result["ref_only_groups"]),
            "oferta_only_groups_count": len(match_result["oferta_only_groups"]),
        },
    }

    return holistic
