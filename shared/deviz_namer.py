"""
Deviz Denomination Populator

For each deviz code, find its denomination name from articles that have it,
then populate it for all other articles in the same deviz section.

This ensures every article can be tracked to its work category in reports.
"""
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


def populate_deviz_denominations(articole: list) -> list:
    """
    For each deviz code, populate deviz_denumire for all articles.

    Strategy:
    1. Find deviz code → {list of denominations} mapping
    2. For each deviz code, pick the most common non-empty denomination
    3. Update all articles in that deviz to use this name

    Args:
        articole: List of articles with 'deviz' and optionally 'deviz_denumire'

    Returns:
        List of articles with deviz_denumire populated for all entries
    """
    if not articole:
        return articole

    # Build deviz -> names mapping
    deviz_to_names = defaultdict(list)
    for art in articole:
        deviz = (art.get("deviz") or "").strip()
        name = (art.get("deviz_denumire") or "").strip()

        if deviz and name:  # Only count non-empty pairs
            deviz_to_names[deviz].append(name)

    # Find canonical name for each deviz
    # Prefer SHORTEST name to avoid bloated table content from DI JSON
    deviz_to_canonical_name = {}
    for deviz, names in deviz_to_names.items():
        if names:
            # Pick shortest name (avoids table structure bloat)
            # Tiebreaker: most common among shortest ones
            from collections import Counter
            min_len = min(len(n) for n in names)
            shortest_names = [n for n in names if len(n) == min_len]

            if len(shortest_names) == 1:
                canonical = shortest_names[0]
            else:
                # Multiple names with same shortest length - pick most common
                name_counts = Counter(shortest_names)
                canonical = max(name_counts.items(), key=lambda x: x[1])[0]

            deviz_to_canonical_name[deviz] = canonical
            logger.debug(f"[DN] Deviz {deviz}: canonical name = '{canonical}' (len={len(canonical)})")

    if not deviz_to_canonical_name:
        logger.info("[DN] No deviz denominations to populate")
        return articole

    # Populate missing names
    result = []
    populated = 0

    for art in articole:
        deviz = (art.get("deviz") or "").strip()
        current_name = (art.get("deviz_denumire") or "").strip()

        if deviz and not current_name and deviz in deviz_to_canonical_name:
            # Populate missing name
            new_art = {**art, "deviz_denumire": deviz_to_canonical_name[deviz]}
            result.append(new_art)
            populated += 1
        else:
            result.append(art)

    logger.info(f"[DN] Populated {populated} missing deviz denominations")
    return result
