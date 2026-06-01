"""Group-level matching using article content (COD-based keys).

Instead of matching groups by deviz_cod string equality (which fails when
ref and offer use different deviz_cod formats), this module matches groups
by the content of their articles using Jaccard similarity on COD key sets.

Workflow:
1. For each group, build a set of COD-based article keys (skip NR — repeats 1,2,3 across all groups)
2. Compute Jaccard similarity for all (ref_group, oferta_group) pairs
3. Greedy 1:1 assignment by similarity descending
4. Pairs above threshold → matched; remainder → ref_only / oferta_only
5. Within each matched group pair, run set-based article matching
"""

import hashlib
from typing import Dict, List, Tuple

from shared.set_based_matcher import match_articles_by_key

MATCH_THRESHOLD = 0.15  # minimum Jaccard similarity to consider a group match


def _group_cod_keys(group: Dict) -> set:
    """Build COD-based key set for a group's articles.

    Uses COD (catalog code) as primary key — NOT NR, because NR repeats
    1, 2, 3... across every group and produces useless intersections.
    Falls back to hash(descriere+um+cant) when COD absent.
    """
    keys = set()
    for art in group.get("articole", []):
        cod = str(art.get("cod", "")).strip()
        if cod:
            keys.add(cod)
            continue
        descriere = str(art.get("descriere", "")).lower().strip()
        um = str(art.get("um", "")).lower().strip()
        cant = str(art.get("cant", "")).strip()
        combined = f"{descriere}|{um}|{cant}"
        keys.add(hashlib.md5(combined.encode()).hexdigest()[:8])
    return keys


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def match_groups_by_deviz(ref_groups: List[Dict], oferta_groups: List[Dict]) -> Dict:
    """
    Match groups by article content (Jaccard on COD keys), then match
    articles within each matched group pair using set_based_matcher.

    Args:
        ref_groups: List of reference group dicts with deviz_cod and articole
        oferta_groups: List of offer group dicts with deviz_cod and articole

    Returns:
        Dict with keys:
        - matched_groups: matched pairs with article matching results
        - ref_only_groups: groups only in reference
        - oferta_only_groups: groups only in offer
    """
    # Build COD key sets per group
    ref_key_sets = [_group_cod_keys(g) for g in ref_groups]
    oferta_key_sets = [_group_cod_keys(g) for g in oferta_groups]

    # Compute all (similarity, ref_idx, oferta_idx) pairs above threshold
    candidates: List[Tuple[float, int, int]] = []
    for ref_idx, ref_keys in enumerate(ref_key_sets):
        for oferta_idx, oferta_keys in enumerate(oferta_key_sets):
            sim = _jaccard(ref_keys, oferta_keys)
            if sim >= MATCH_THRESHOLD:
                candidates.append((sim, ref_idx, oferta_idx))

    # Greedy 1:1 assignment, highest similarity first
    candidates.sort(reverse=True)
    used_ref: set = set()
    used_oferta: set = set()
    assignments: List[Tuple[int, int, float]] = []

    for sim, ref_idx, oferta_idx in candidates:
        if ref_idx in used_ref or oferta_idx in used_oferta:
            continue
        assignments.append((ref_idx, oferta_idx, sim))
        used_ref.add(ref_idx)
        used_oferta.add(oferta_idx)

    # Build matched groups with article-level matching
    matched_groups = []
    for ref_idx, oferta_idx, sim in assignments:
        ref_group = ref_groups[ref_idx]
        oferta_group = oferta_groups[oferta_idx]

        article_match = match_articles_by_key(
            ref_group.get("articole", []),
            oferta_group.get("articole", []),
        )

        matched_groups.append({
            "deviz_cod": ref_group.get("deviz_cod", ""),
            "deviz_den": ref_group.get("deviz_den", ""),
            "oferta_deviz_cod": oferta_group.get("deviz_cod", ""),
            "match_similarity": round(sim, 3),
            "articole": article_match["matched"],
            "ref_only": article_match["ref_only"],
            "oferta_only": article_match["oferta_only"],
            "stats": article_match["stats"],
        })

    ref_only_groups = [
        ref_groups[i] for i in range(len(ref_groups)) if i not in used_ref
    ]
    oferta_only_groups = [
        oferta_groups[i] for i in range(len(oferta_groups)) if i not in used_oferta
    ]

    # Sort by ref deviz_cod for deterministic output
    matched_groups.sort(key=lambda g: g.get("deviz_cod", ""))

    return {
        "matched_groups": matched_groups,
        "ref_only_groups": ref_only_groups,
        "oferta_only_groups": oferta_only_groups,
    }
