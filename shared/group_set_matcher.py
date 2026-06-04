"""Group-level matching using OBIECTUL + CATEGORIA text similarity.

Mirrors V1 Phase 2 logic (SequenceMatcher on header text) — same business
requirement, deterministic implementation without LLM.

Workflow:
1. Normalize OBIECTUL + CATEGORIA text per group (strip leading code prefixes)
2. SequenceMatcher similarity for all (ref_group, oferta_group) pairs
3. Greedy 1:1 assignment by similarity descending
4. Pairs above threshold → matched; remainder → ref_only / oferta_only
5. Within each matched group: set-based article matching (NR → COD → hash)
"""

import re
from difflib import SequenceMatcher
from typing import Dict, List, Tuple

from shared.set_based_matcher import match_articles_by_key
from shared.unique_key_detector import detect_article_key

MATCH_THRESHOLD = 0.55  # primary: categoria similarity; lower than V1 (0.80) to compensate
                        # for SequenceMatcher being stricter than RapidFuzz partial_token
RESIDUAL_THRESHOLD = 0.6  # min fraction of ref articles found in offer group's oferta_only
                          # 0.6 prevents spurious 1/2 matches (e.g. OCR artefact groups)


def _normalize(text: str) -> str:
    """Strip leading code/number prefixes, normalize punctuation, lowercase.

    Only strips tokens that are numeric codes or letter+digit codes.
    Does NOT strip regular words like "Terasamente", "Acostamente".

    Examples:
      "0001 Strada Zoica"           → "strada zoica"
      "0001 1 Strada Zoica"         → "strada zoica"
      "ZO0001 Terasamente 7.70smp"  → "terasamente 7.70smp"
      "BI0006 Acostamente 10cm"     → "acostamente 10cm"
      "0001 Terasamente 7,70smp"    → "terasamente 7.70smp"
      "M0005 BAPC16 - 4CM 4.80SMP" → "4cm 4.80smp"
      "0005 BAPC16-4cm 4,80smp"    → "4cm 4.80smp"
      "0001 45230000"               → "45230000"  (caller checks _has_letters)
    """
    if not text:
        return ""
    t = text.strip()
    # Strip leading tokens that are pure numeric codes (e.g. "0001 ", "8 ")
    # or letter-prefix codes (e.g. "ZO0001 ", "BI0006 ", "AN1 ", "LC001A ")
    # Does NOT strip regular words (they lack embedded digits right after letters)
    t = re.sub(r'^((?:\d+|[A-Z]{1,4}\d+[A-Z]?)\s+)+', '', t)
    # Strip code-dash prefix: "BAPC16-4cm" → "4cm" (code attached to content by dash)
    t = re.sub(r'^[A-Za-z]{1,4}\d+[A-Za-z]?-', '', t)
    # Normalize separators: comma decimal → period, leading dash artifact → strip
    t = t.replace(',', '.')
    t = re.sub(r'^\s*-\s*', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t.lower().strip()


def _has_letters(text: str) -> bool:
    """True if text contains at least one real letter (not pure digits/codes)."""
    return bool(re.search(r'[a-zA-Z]', text))


def _group_score(ref_group: Dict, oferta_group: Dict) -> float:
    """Matching score between two groups using OBIECTUL + CATEGORIA.

    Primary: categoria similarity (most specific, always used).
    Secondary: obiectul similarity, only when both sides have meaningful text
               (i.e., not pure-numeric codes like EU procurement numbers).

    Score ∈ [0, 1]. MATCH_THRESHOLD applies to this score.
    """
    ref_cat = _normalize(ref_group.get("categoria", "") or "")
    oferta_cat = _normalize(oferta_group.get("categoria", "") or "")

    if not ref_cat or not oferta_cat:
        return 0.0

    cat_sim = SequenceMatcher(None, ref_cat, oferta_cat).ratio()

    ref_obj = _normalize(ref_group.get("obiectul", "") or "")
    oferta_obj = _normalize(oferta_group.get("obiectul", "") or "")

    if ref_obj and oferta_obj and _has_letters(ref_obj) and _has_letters(oferta_obj):
        obj_sim = SequenceMatcher(None, ref_obj, oferta_obj).ratio()
        return 0.7 * cat_sim + 0.3 * obj_sim

    return cat_sim


def match_groups_by_deviz(ref_groups: List[Dict], oferta_groups: List[Dict]) -> Dict:
    """
    Match groups by OBIECTUL + CATEGORIA text similarity, then match
    articles within each matched group pair using set_based_matcher.

    Falls back to deviz_cod string equality when header text is unavailable.

    Args:
        ref_groups: List of reference group dicts (must have obiectul, categoria)
        oferta_groups: List of offer group dicts (same structure)

    Returns:
        Dict with keys:
        - matched_groups: matched pairs with article matching results
        - ref_only_groups: groups only in reference
        - oferta_only_groups: groups only in offer
    """
    # Compute all candidate pairs above threshold
    candidates: List[Tuple[float, int, int]] = []
    for ri, ref_group in enumerate(ref_groups):
        for oi, oferta_group in enumerate(oferta_groups):
            score = _group_score(ref_group, oferta_group)
            if score >= MATCH_THRESHOLD:
                candidates.append((score, ri, oi))
            elif score == 0.0:
                # Fallback: exact deviz_cod match when no header text available
                if ref_group.get("deviz_cod") == oferta_group.get("deviz_cod"):
                    candidates.append((1.0, ri, oi))

    # Greedy 1:1 assignment, highest similarity first
    # Sort descending by sim; for ties keep lower indices first (stable)
    candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_ref: set = set()
    used_oferta: set = set()
    assignments: List[Tuple[int, int, float]] = []

    for sim, ri, oi in candidates:
        if ri in used_ref or oi in used_oferta:
            continue
        assignments.append((ri, oi, sim))
        used_ref.add(ri)
        used_oferta.add(oi)

    # Build matched groups with article-level matching
    matched_groups = []
    pair_article_matches: List[Dict] = []

    for ri, oi, sim in assignments:
        ref_group = ref_groups[ri]
        oferta_group = oferta_groups[oi]
        article_match = match_articles_by_key(
            ref_group.get("articole", []),
            oferta_group.get("articole", []),
        )
        pair_article_matches.append(article_match)
        matched_groups.append({
            "deviz_cod": ref_group.get("deviz_cod", ""),
            "deviz_den": ref_group.get("deviz_den", ""),
            "obiectivul": ref_group.get("obiectivul", ""),
            "obiectul": ref_group.get("obiectul", ""),
            "categoria": ref_group.get("categoria", ""),
            "oferta_deviz_cod": oferta_group.get("deviz_cod", ""),
            "match_similarity": round(sim, 3),
            "articole": article_match["matched"],
            "ref_only": article_match["ref_only"],
            "oferta_only": article_match["oferta_only"],
            "stats": article_match["stats"],
        })

    # === RESIDUAL N:1 PASS ===
    # When an offer merges multiple ref categories into one group, the primary
    # greedy 1:1 assigns the offer group to one ref group, leaving others unmatched.
    # Check if unmatched ref articles appear in already-matched offer groups' oferta_only.
    residual_candidates: List[Tuple[float, int, int]] = []  # (coverage, uri, pair_idx)
    for uri in range(len(ref_groups)):
        if uri in used_ref:
            continue
        ref_arts = ref_groups[uri].get("articole", [])
        if not ref_arts:
            continue
        ref_keys = {detect_article_key(a) for a in ref_arts}
        for pair_idx in range(len(assignments)):
            oferta_only_keys = {
                detect_article_key(a) for a in pair_article_matches[pair_idx]["oferta_only"]
            }
            overlap = ref_keys & oferta_only_keys
            coverage = len(overlap) / len(ref_keys)
            if coverage >= RESIDUAL_THRESHOLD:
                residual_candidates.append((coverage, uri, pair_idx))

    # Greedy assignment: highest coverage first; each ref group used at most once
    residual_candidates.sort(key=lambda x: (-x[0], x[1], x[2]))
    used_ref_residual: set = set()

    for coverage, uri, pair_idx in residual_candidates:
        if uri in used_ref_residual:
            continue
        used_ref_residual.add(uri)
        used_ref.add(uri)

        ref_group = ref_groups[uri]
        oi = assignments[pair_idx][1]
        oferta_group = oferta_groups[oi]

        # Match ref articles against the primary pair's current oferta_only only
        article_match = match_articles_by_key(
            ref_group.get("articole", []),
            pair_article_matches[pair_idx]["oferta_only"],
        )

        # Shrink primary pair's oferta_only — remove articles claimed by this residual match
        claimed_keys = {detect_article_key(p["oferta"]) for p in article_match["matched"]}
        pair_article_matches[pair_idx]["oferta_only"] = [
            a for a in pair_article_matches[pair_idx]["oferta_only"]
            if detect_article_key(a) not in claimed_keys
        ]
        matched_groups[pair_idx]["oferta_only"] = pair_article_matches[pair_idx]["oferta_only"]
        matched_groups[pair_idx]["stats"]["oferta_only_count"] = len(
            pair_article_matches[pair_idx]["oferta_only"]
        )

        matched_groups.append({
            "deviz_cod": ref_group.get("deviz_cod", ""),
            "deviz_den": ref_group.get("deviz_den", ""),
            "obiectivul": ref_group.get("obiectivul", ""),
            "obiectul": ref_group.get("obiectul", ""),
            "categoria": ref_group.get("categoria", ""),
            "oferta_deviz_cod": oferta_group.get("deviz_cod", ""),
            "match_similarity": round(coverage, 3),
            "match_type": "residual_n1",
            "articole": article_match["matched"],
            "ref_only": article_match["ref_only"],
            "oferta_only": article_match["oferta_only"],
            "stats": article_match["stats"],
        })

    # Sort by ref deviz_cod for deterministic output
    matched_groups.sort(key=lambda g: g.get("deviz_cod", ""))

    ref_only_groups = [
        ref_groups[i] for i in range(len(ref_groups)) if i not in used_ref
    ]
    oferta_only_groups = [
        oferta_groups[i] for i in range(len(oferta_groups)) if i not in used_oferta
    ]

    return {
        "matched_groups": matched_groups,
        "ref_only_groups": ref_only_groups,
        "oferta_only_groups": oferta_only_groups,
    }
