"""
Dynamic deviz pattern analyzer — detects how deviz codes should be matched
between referinta and oferta for each client/document pair.

Instead of hardcoding transformation rules, this analyzer:
1. Extracts all deviz codes from both documents
2. Compares patterns to detect the matching rule
3. Returns a normalized deviz code function for this client

Supports patterns:
- IDENTICAL: referinta="1.1", oferta="1.1" → no transformation needed
- PREFIXED: referinta="1.1", oferta="001 1.1" → strip prefix
- MAPPED: referinta="226108", oferta="001" → use deviz_map
"""
import re
import logging
from collections import Counter
from typing import Callable, Dict, Tuple

logger = logging.getLogger(__name__)


def analyze_deviz_pattern(
    ref_devizes: set[str],
    oferta_devizes: set[str]
) -> Tuple[str, Callable[[str], str]]:
    """
    Analyze deviz codes in both documents and return (pattern_name, normalizer_function).

    Args:
        ref_devizes: Set of deviz codes from referinta
        oferta_devizes: Set of deviz codes from oferta

    Returns:
        Tuple of (pattern_detected, normalizer_function)
        - pattern_detected: str describing the pattern ("IDENTICAL", "PREFIXED", "MAIN_PLUS_SUB", etc.)
        - normalizer_function: Callable that transforms an oferta deviz to match referinta pattern
    """

    # Pattern 1: IDENTICAL — no transformation needed
    if ref_devizes == oferta_devizes:
        logger.info("[DEVIZ_ANALYZER] Pattern: IDENTICAL (ref devizes == oferta devizes)")
        return "IDENTICAL", lambda x: x

    # Pattern 2: PREFIXED — oferta has "NNN X.Y Z..." format, referinta has "X.Y Z..." format
    # Example: oferta="001 1.1", referinta="1.1"
    # Strategy: Extract sub-code from oferta by removing leading "NNN " pattern
    prefixed_matches = _check_prefixed_pattern(ref_devizes, oferta_devizes)
    if prefixed_matches:
        logger.info(f"[DEVIZ_ANALYZER] Pattern: PREFIXED ({len(prefixed_matches)} matching pairs found)")
        examples = list(prefixed_matches.items())[:5]
        for oferta_code, ref_code in examples:
            logger.info(f"    {oferta_code} → {ref_code}")

        def normalize_prefixed(oferta_deviz: str) -> str:
            # Try to extract sub-code after main code
            # Format: "001 1.1 ..." → "1.1"
            m = re.match(r'^\d{1,3}\s+([0-9]\.[0-9])', oferta_deviz)
            if m:
                return m.group(1)
            # If no match, return as-is (might be a pure numeric code)
            return oferta_deviz

        return "PREFIXED", normalize_prefixed

    # Pattern 3: MAIN_PLUS_SUB — oferta has main codes (001-008) PLUS sub-codes (1.1-9.1)
    # while referinta has section codes (1.0-9.0) PLUS same sub-codes (1.1-9.1)
    # Strategy: Keep articles as-is (main codes stay), let comparison handle mismatch
    # (Main code articles will be unmatched, which is expected for section headers)
    main_plus_sub = _check_main_plus_sub_pattern(ref_devizes, oferta_devizes)
    if main_plus_sub is not None:
        logger.info("[DEVIZ_ANALYZER] Pattern: MAIN_PLUS_SUB (oferta has main codes + sub-codes)")
        logger.info(f"    Main codes in oferta (kept as-is): {main_plus_sub['main_codes']}")
        logger.info(f"    Matching sub-codes: {len(main_plus_sub['matching_subcodes'])} codes found")
        logger.info(f"    Note: Articles with main codes will not match (expected for section headers)")
        # No transformation needed - keep articles as-is
        return "MAIN_PLUS_SUB", lambda x: x

    # Pattern 4: SUBSET — all oferta devizes are in referinta
    # This means oferta is a subset of referinta (no new devizes in oferta)
    if oferta_devizes.issubset(ref_devizes):
        logger.info("[DEVIZ_ANALYZER] Pattern: SUBSET (oferta ⊆ referinta, no new devizes)")
        return "SUBSET", lambda x: x

    # Pattern 5: SUPERSET — all referinta devizes are in oferta
    if ref_devizes.issubset(oferta_devizes):
        logger.info("[DEVIZ_ANALYZER] Pattern: SUPERSET (referinta ⊆ oferta, oferta has extras)")
        return "SUPERSET", lambda x: x

    # Pattern 6: UNKNOWN — couldn't detect a clear pattern
    logger.warning(
        f"[DEVIZ_ANALYZER] Pattern: UNKNOWN (couldn't auto-detect matching rule)\n"
        f"  Referinta devizes: {sorted(ref_devizes)}\n"
        f"  Oferta devizes: {sorted(oferta_devizes)}"
    )
    return "UNKNOWN", lambda x: x


def _check_main_plus_sub_pattern(ref_devizes: set[str], oferta_devizes: set[str]) -> Dict or None:
    """
    Check if oferta has MAIN codes (001-008) + SUB codes (1.1-9.1) while referinta has SECTION codes (1.0-9.0) + SUB codes.

    Handles pattern where:
    - Oferta: main codes like '001', '002', '003', ... AND sub-codes like '1.1', '1.2', '2.1', etc.
    - Referinta: section codes like '1.0', '2.0', '3.0', ... AND same sub-codes like '1.1', '1.2', '2.1', etc.

    The main codes in oferta are containers (they don't appear in referinta), and should be ignored.

    Returns:
        Dict with keys 'main_codes' (set of oferta main codes) and 'matching_subcodes' (set of matching sub-codes)
        or None if pattern doesn't apply
    """
    # Detect main codes in oferta (pure digits, 001-008 or 001-999)
    oferta_main = {code for code in oferta_devizes if re.match(r'^\d{1,3}$', code)}

    # Detect sub-codes in oferta (format: X.Y)
    oferta_sub = {code for code in oferta_devizes if re.match(r'^[0-9]\.[0-9]', code)}

    # Detect section codes in referinta (format: X.0)
    ref_section = {code for code in ref_devizes if re.match(r'^[0-9]\.0$', code)}

    # Detect sub-codes in referinta (format: X.Y where Y != 0)
    ref_sub = {code for code in ref_devizes if re.match(r'^[0-9]\.[0-9]', code) and not code.endswith('.0')}

    # Pattern matches if:
    # 1. Oferta has main codes (001-008) that DON'T appear in referinta
    # 2. Oferta has sub-codes that DO appear in referinta
    # 3. Referinta has section codes (1.0, 2.0, ...) that DON'T appear in oferta

    main_in_both = oferta_main & ref_devizes
    if main_in_both:
        # Main codes also appear in referinta, so not a MAIN+SUB pattern
        return None

    if not oferta_main or not oferta_sub:
        # No main codes or no sub-codes in oferta
        return None

    matching_subcodes = oferta_sub & ref_devizes
    if len(matching_subcodes) < len(oferta_sub) * 0.7:
        # Less than 70% of oferta sub-codes match referinta sub-codes
        # Probably not a MAIN+SUB pattern
        return None

    logger.info(f"    Detected {len(oferta_main)} main codes + {len(oferta_sub)} sub-codes in oferta")
    logger.info(f"    Detected {len(ref_section)} section codes + {len(ref_sub)} sub-codes in referinta")
    logger.info(f"    Matching sub-codes: {len(matching_subcodes)} out of {len(oferta_sub)}")

    return {
        'main_codes': oferta_main,
        'matching_subcodes': matching_subcodes
    }


def _check_prefixed_pattern(ref_devizes: set[str], oferta_devizes: set[str]) -> Dict[str, str]:
    """
    Check if oferta devizes follow 'NNN X.Y' pattern with referinta having 'X.Y'.

    Handles both:
    - Pure prefixed: oferta ALL have "NNN X.Y" format
    - Mixed prefixed: oferta has "NNN X.Y" codes + some pure numeric codes (001-008)

    Returns:
        Dict of oferta_deviz → ref_deviz matches, or {} if pattern doesn't apply
    """
    # Extract sub-codes from oferta (format: "NNN X.Y" → "X.Y")
    oferta_subcodes = {}
    pure_numeric = {}

    for od in oferta_devizes:
        # Try to match "NNN X.Y" pattern
        m = re.match(r'^\d{1,3}\s+([0-9]\.[0-9])', od)
        if m:
            oferta_subcodes[od] = m.group(1)
        # Also track pure numeric codes (001, 002, 003, etc.) separately
        elif re.match(r'^\d{1,3}$', od):
            pure_numeric[od] = True

    if not oferta_subcodes:
        # No devizes in oferta match the "NNN X.Y" pattern
        return {}

    # Check if these extracted sub-codes match referinta devizes
    matches = {}
    for oferta_deviz, subcode in oferta_subcodes.items():
        if subcode in ref_devizes:
            matches[oferta_deviz] = subcode

    # Consider it a valid pattern if:
    # 1. We found enough matches (3+ or 80%+ of extracted sub-codes)
    # 2. OR: We have BOTH prefixed codes AND pure numeric codes (mixed pattern)
    #        with significant sub-code matches (suggests "001 1.1" + orphan codes)

    min_matches = max(3, len(oferta_subcodes) // 2)

    if len(matches) >= min_matches:
        logger.info(f"    Detected {len(matches)} sub-code matches out of {len(oferta_subcodes)} prefixed codes")
        return matches

    if len(matches) > 0 and pure_numeric and len(matches) >= len(oferta_subcodes) * 0.7:
        logger.info(f"    Detected {len(matches)} sub-code matches + {len(pure_numeric)} orphan numeric codes")
        return matches

    return {}


def apply_deviz_normalization(
    articles: list[dict],
    pattern: str,
    normalizer: Callable[[str], str],
    ref_articles: list[dict] = None
) -> list[dict]:
    """
    Apply deviz normalization to articles based on detected pattern.

    Args:
        articles: List of article dicts with 'deviz' field
        pattern: Pattern name (for logging)
        normalizer: Function to transform deviz codes
        ref_articles: Reference articles for MAIN_PLUS_SUB pattern to find correct deviz codes

    Returns:
        Modified articles with normalized deviz codes
    """
    if pattern == "IDENTICAL" or pattern == "SUBSET":
        # No normalization needed - articles kept as-is
        return articles

    if pattern == "MAIN_PLUS_SUB" and ref_articles:
        # For MAIN_PLUS_SUB, try to match main-code articles to reference sub-codes
        return _normalize_main_plus_sub_articles(articles, ref_articles)

    updated_count = 0

    for article in articles:
        old_deviz = article.get("deviz", "")
        if old_deviz:
            new_deviz = normalizer(old_deviz)
            if new_deviz != old_deviz:
                article["deviz"] = new_deviz
                updated_count += 1

    if updated_count > 0:
        logger.info(f"[DEVIZ_ANALYZER] Applied normalization: {updated_count} articles updated")

    return articles


def _normalize_main_plus_sub_articles(oferta_articles: list[dict], ref_articles: list[dict]) -> list[dict]:
    """
    For MAIN_PLUS_SUB pattern: match oferta articles with main codes to reference sub-codes.

    If an oferta article has a main code (001-008) and the same article code appears in reference
    with sub-codes, reassign the oferta article to one of those sub-codes.
    """
    # Build a map of article codes to their deviz codes in reference
    ref_code_to_devizes = {}
    for art in ref_articles:
        cod = art.get('cod', '')
        deviz = art.get('deviz', '')
        if cod and deviz:
            if cod not in ref_code_to_devizes:
                ref_code_to_devizes[cod] = set()
            ref_code_to_devizes[cod].add(deviz)

    updated_count = 0
    main_code_articles = 0

    # For each oferta article with a main code, find matching reference devizes
    for article in oferta_articles:
        old_deviz = article.get('deviz', '')
        cod = article.get('cod', '')

        # Check if this is a main code (001-008)
        if old_deviz and re.match(r'^\d{1,3}$', old_deviz) and cod in ref_code_to_devizes:
            main_code_articles += 1
            ref_devizes = ref_code_to_devizes[cod]
            # Pick the first sub-code (X.1, X.2, etc.) from reference
            sub_codes = [d for d in ref_devizes if re.match(r'^[0-9]\.[0-9]', d)]
            if sub_codes:
                # Prefer lower numeric sub-codes (1.1 before 2.1 before 3.1)
                new_deviz = sorted(sub_codes)[0]
                article['deviz'] = new_deviz
                updated_count += 1
                if updated_count <= 5:  # Log first 5 changes
                    logger.info(f"    {cod}: {old_deviz} → {new_deviz} (matched to reference)")

    if main_code_articles > 0:
        logger.info(f"[DEVIZ_ANALYZER] MAIN_PLUS_SUB: {main_code_articles} articles with main codes, {updated_count} remapped to sub-codes")

    return oferta_articles
