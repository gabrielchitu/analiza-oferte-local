"""
Deviz Denomination Matcher — Match offer devizes to reference devizes using denomination.

When deviz code extraction fails (partial/none), this module matches devizes by their
denomination text (obiectul + categoria descriptions).

Two strategies:
1. Exact denomination matching: Find reference deviz with identical denomination
2. Fuzzy matching: Find best-match reference deviz using SequenceMatcher
"""
import logging
from collections import defaultdict
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip whitespace."""
    return (text or "").lower().strip()


def _denomination_similarity(denom_a: str, denom_b: str) -> float:
    """Calculate similarity ratio between two denomination strings (0.0 to 1.0).

    Handles corrupted denominations where article data is appended.
    Extracts first meaningful words and compares.
    """
    norm_a = _normalize_text(denom_a)
    norm_b = _normalize_text(denom_b)

    if not norm_a or not norm_b:
        return 0.0

    # Extract first few meaningful words (before numbers or special patterns)
    # This handles corrupted denominations like "Arhitectura - eligibile tip I 0 1 2 3..."
    def extract_main_text(text: str) -> str:
        # Split on numbers/special patterns, keep first meaningful part
        import re
        match = re.match(r'^([a-z\s\-]+?)(?:\s+[0-9]|\s*[=×]|$)', text)
        if match:
            return match.group(1).strip()
        return text.split()[0] if text.split() else text

    main_a = extract_main_text(norm_a)
    main_b = extract_main_text(norm_b)

    # Compare main parts
    similarity = SequenceMatcher(None, main_a, main_b).ratio()

    # Also try full comparison as fallback
    full_similarity = SequenceMatcher(None, norm_a, norm_b).ratio()

    return max(similarity, full_similarity * 0.8)  # Prefer main text match


def build_deviz_reference_map(ref_articles: list) -> dict:
    """
    Build a map of reference devizes and their canonical denominations.

    Returns:
        {
            'deviz_code': {
                'canonical_denom': str,
                'count': int,
                'sample_article': dict
            }
        }
    """
    ref_by_deviz = defaultdict(list)

    for art in ref_articles:
        deviz = (art.get('deviz') or '').strip()
        if not deviz:
            continue
        ref_by_deviz[deviz].append(art)

    result = {}
    for deviz, arts in ref_by_deviz.items():
        # Use first non-empty denomination as canonical
        canonical_denom = ""
        for art in arts:
            denom = (art.get('deviz_denumire') or '').strip()
            if denom:
                canonical_denom = denom
                break

        result[deviz] = {
            'canonical_denom': canonical_denom,
            'count': len(arts),
            'sample_article': arts[0]
        }

    logger.debug(f"[DM] Built reference map: {len(result)} devizes")
    return result


def _extract_deviz_prefix(deviz_code: str) -> str:
    """Extract prefix from deviz code for matching.

    Examples:
        "4.1-01" → "4.1"
        "4.2-1" → "4.2"
        "Arhitectura" → "arhitectura"
        "Structura conexe..." → "structura"
    """
    if not deviz_code:
        return ""

    # Numeric code like "4.1-01"
    if "-" in deviz_code:
        return deviz_code.split("-")[0].strip()

    # Text code like "Arhitectura" - return first word normalized
    first_word = deviz_code.split()[0].lower()
    return first_word


def match_devize_by_denomination(ref_articles: list, oferta_articles: list,
                                 min_similarity: float = 0.70) -> dict:
    """
    Match offer devizes to reference devizes using denomination as fallback.

    Strategy:
    1. Build reference map (deviz → denomination)
    2. For each offer deviz:
       a. Try exact match on code
       b. If not found, try exact match on denomination
       c. If not found, use fuzzy match (best similarity score)
    3. Return mapping: {oferta_deviz: ref_deviz, ...}

    Args:
        ref_articles: Reference articles (source of truth)
        oferta_articles: Offer articles to match
        min_similarity: Minimum similarity threshold for fuzzy matching (0.0-1.0)

    Returns:
        Mapping dict: {oferta_deviz: ref_deviz, ...}
        Empty dict if no matches possible
    """
    if not ref_articles or not oferta_articles:
        logger.warning("[DM] Empty ref or offer articles")
        return {}

    ref_map = build_deviz_reference_map(ref_articles)
    if not ref_map:
        logger.warning("[DM] No reference devizes to match against")
        return {}

    # Group offer articles by deviz
    oferta_by_deviz = defaultdict(list)
    for art in oferta_articles:
        deviz = (art.get('deviz') or '').strip()
        if deviz:  # Only process non-empty deviz codes
            oferta_by_deviz[deviz].append(art)

    mapping = {}

    for oferta_deviz, oferta_arts in oferta_by_deviz.items():
        # Strategy 1: Exact code match
        if oferta_deviz in ref_map:
            mapping[oferta_deviz] = oferta_deviz
            logger.debug(f"[DM] {oferta_deviz}: exact code match")
            continue

        # Get offer denomination
        oferta_denom = ""
        for art in oferta_arts:
            denom = (art.get('deviz_denumire') or '').strip()
            if denom:
                oferta_denom = denom
                break

        if not oferta_denom:
            logger.warning(f"[DM] {oferta_deviz}: no denomination found, skipping")
            continue

        # Strategy 2: Try exact denomination match
        best_match = None
        best_score = 0.0

        for ref_deviz, ref_info in ref_map.items():
            ref_denom = ref_info['canonical_denom']

            # Exact denomination match (after normalization)
            if _normalize_text(oferta_denom) == _normalize_text(ref_denom):
                best_match = ref_deviz
                best_score = 1.0
                logger.debug(f"[DM] {oferta_deviz} → {ref_deviz}: exact denomination match")
                break

            # Fuzzy match for similarity
            similarity = _denomination_similarity(oferta_denom, ref_denom)
            if similarity > best_score:
                best_score = similarity
                best_match = ref_deviz

        # Strategy 3: If still no match and offer_deviz looks like text (no hyphen),
        # try matching by first word (handles truncated codes like "Arhitectura" → "Arhitectura - eligibile")
        if (not best_match or best_score < 0.65) and "-" not in oferta_deviz:
            oferta_prefix = _extract_deviz_prefix(oferta_deviz).lower()
            for ref_deviz, ref_info in ref_map.items():
                ref_denom = ref_info['canonical_denom'].lower()
                if oferta_prefix in ref_denom or ref_denom.startswith(oferta_prefix):
                    best_match = ref_deviz
                    best_score = 0.85  # High confidence for prefix match
                    logger.info(
                        f"[DM] {oferta_deviz} → {ref_deviz}: "
                        f"text-code prefix match ('{oferta_prefix}' in '{ref_denom[:40]}')"
                    )
                    break

        if best_match and best_score >= min_similarity:
            mapping[oferta_deviz] = best_match
            if best_score < 1.0 and best_score < 0.85:
                logger.info(
                    f"[DM] {oferta_deviz} → {best_match}: "
                    f"denomination fuzzy match (score={best_score:.2f})"
                )
        else:
            logger.warning(
                f"[DM] {oferta_deviz}: no match found "
                f"(best_score={best_score:.2f}, min={min_similarity})"
            )

    logger.info(f"[DM] Matched {len(mapping)}/{len(oferta_by_deviz)} offer devizes")
    return mapping


def remap_devize_in_articles(articles: list, mapping: dict) -> list:
    """
    Apply deviz mapping to articles.

    Args:
        articles: Articles to remap
        mapping: Mapping dict {oferta_deviz: ref_deviz, ...}

    Returns:
        Updated articles with remapped devizes (preserves original in _deviz_original)
    """
    if not mapping:
        return articles

    result = []
    remapped_count = 0

    for art in articles:
        deviz = (art.get('deviz') or '').strip()

        if deviz in mapping and mapping[deviz] != deviz:
            # Remap and preserve original
            new_art = {**art, 'deviz': mapping[deviz]}
            if '_deviz_original' not in new_art:
                new_art['_deviz_original'] = deviz
            result.append(new_art)
            remapped_count += 1
        else:
            result.append(art)

    if remapped_count > 0:
        logger.info(f"[DM] Remapped {remapped_count} articles to new devizes")

    return result
