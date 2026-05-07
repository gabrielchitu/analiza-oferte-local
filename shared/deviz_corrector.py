"""
Deviz Code Assignment Corrector

After extraction, articles are assigned to deviz sections based on OCR-extracted
denomination text. When the same work category appears with OCR variations
in reference vs oferta, they may be assigned different deviz codes.

This module corrects these assignments by:
1. Finding articles with the same code in both documents
2. Determining which deviz code in reference is the "correct" one for each code
3. Updating oferta articles to use the reference's deviz codes when applicable

Public API:
    correct_oferta_deviz_assignments(ref_articole, oferta_articole) -> list
        Returns oferta articles with corrected deviz codes.
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def correct_oferta_deviz_assignments(ref_articole: list, oferta_articole: list) -> list:
    """
    Correct oferta articles' deviz assignments based on reference data.

    Strategy:
    1. For codes appearing in BOTH documents: use reference's deviz assignments
    2. For codes only in oferta: keep as-is
    3. For codes only in reference: nothing to correct in oferta

    This handles cases where the same code appears in different devizes due to
    OCR variations or legitimate multi-section assignments.

    Args:
        ref_articole: list of reference articles with 'cod' and 'deviz' fields
        oferta_articole: list of offer articles with 'cod' and 'deviz' fields

    Returns:
        Shallow copy of oferta_articole with corrected 'deviz' field values
    """
    if not ref_articole or not oferta_articole:
        return oferta_articole

    # Build ref mapping: code -> set of deviz codes where it appears
    ref_code_to_devizes: dict[str, set[str]] = defaultdict(set)
    for art in ref_articole:
        cod = (art.get("cod") or "").strip().upper()
        deviz = (art.get("deviz") or "").strip()
        if cod and deviz:
            ref_code_to_devizes[cod].add(deviz)

    # Build oferta mapping by (cod, deviz) -> list of articles
    # This allows us to track all instances of each code in each deviz
    oferta_code_deviz_to_articles: dict = defaultdict(list)
    for art in oferta_articole:
        cod = (art.get("cod") or "").strip().upper()
        deviz = (art.get("deviz") or "").strip()
        if cod and deviz:
            key = (cod, deviz)
            oferta_code_deviz_to_articles[key].append(art)

    # Identify codes that appear in both documents
    codes_in_both = set(ref_code_to_devizes.keys()) & {
        cod for cod, _ in oferta_code_deviz_to_articles.keys()
    }

    logger.info(f"[DC] Codes in both documents: {len(codes_in_both)}")

    # Build correction mapping: for each code in both docs,
    # remap oferta's extra devizes to reference's devizes
    corrections_count = 0
    result = []

    for art in oferta_articole:
        cod = (art.get("cod") or "").strip().upper()
        deviz = (art.get("deviz") or "").strip()

        if cod not in codes_in_both or not deviz:
            result.append(art)
            continue

        ref_devizes = ref_code_to_devizes[cod]

        # If this article's deviz is already in reference, keep it
        if deviz in ref_devizes:
            result.append(art)
        else:
            # Article code is in reference but this deviz assignment isn't
            # Correct it to use the first deviz from reference
            corrected_deviz = min(ref_devizes)  # Use min for deterministic ordering
            corrected_art = {**art, "deviz": corrected_deviz}
            result.append(corrected_art)
            corrections_count += 1
            logger.debug(
                f"[DC] Code {cod}: corrected deviz {deviz} → {corrected_deviz}"
            )

    if corrections_count > 0:
        logger.info(f"[DC] Applied {corrections_count} deviz corrections to oferta articles")
    else:
        logger.info("[DC] No deviz assignment corrections needed")

    return result
