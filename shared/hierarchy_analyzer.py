"""Hierarchy analyzer - detect and fix broken parent-child relationships in articles.

This module provides tools to:
1. Detect broken hierarchy issues (missing parents, nonexistent parent references)
2. Fix hierarchy using forward fill (ffill) to propagate parent context through component sequences
"""

import pandas as pd
from typing import Dict, List, Optional


def detect_broken_hierarchy(articles: List[Dict]) -> List[Dict]:
    """Detect articles with broken parent-child relationships.

    Detects two types of issues:
    1. Component articles (is_component=True) with parent_nr=None
    2. Articles whose parent_nr references a non-existent parent NR

    Args:
        articles: List of article dictionaries with keys: nr, parent_nr, is_component

    Returns:
        List of issue dictionaries with structure:
        {
            "nr": str,
            "issue": "MISSING_PARENT" | "NONEXISTENT_PARENT",
            "parent_nr": str (optional, only for NONEXISTENT_PARENT),
        }
    """
    if not articles:
        return []

    issues = []

    # Build set of all existing article NRs for parent validation
    all_nrs = {art.get("nr") for art in articles if art.get("nr")}

    for article in articles:
        nr = article.get("nr")
        parent_nr = article.get("parent_nr")
        is_component = article.get("is_component", False)

        # Issue 1: Component with no parent_nr
        if is_component and parent_nr is None:
            issues.append({
                "nr": nr,
                "issue": "MISSING_PARENT",
            })

        # Issue 2: parent_nr references non-existent parent
        if parent_nr is not None and parent_nr not in all_nrs:
            issues.append({
                "nr": nr,
                "issue": "NONEXISTENT_PARENT",
                "parent_nr": parent_nr,
            })

    return issues


def fix_hierarchy_ffill(articles: List[Dict]) -> List[Dict]:
    """Fix broken hierarchy using forward fill (ffill) to propagate parent context.

    For component articles with missing parent_nr, inherit parent from the previous
    article's parent_nr value (if that article is a component) or its own nr (if main).
    This assumes articles are ordered correctly by extraction.

    Logic:
    - When parent_nr is None AND is_component is True, fill from last non-None parent_nr
    - Reset context when we hit a new main article (is_component=False with parent_nr=None)

    Args:
        articles: List of article dictionaries with keys: nr, parent_nr, is_component

    Returns:
        List of article dictionaries with:
        - Fixed parent_nr values (filled from previous valid parent)
        - New field 'hierarchy_corrected' (boolean): True if parent_nr was modified
    """
    if not articles:
        return []

    # Make a copy and add tracking field
    result = []
    current_parent = None

    for article in articles:
        article_copy = article.copy()
        original_parent = article.get("parent_nr")
        is_component = article.get("is_component", False)
        nr = article.get("nr")

        # Update current_parent based on current article
        if not is_component and article.get("parent_nr") is None:
            # Main article with no parent_nr: this becomes the context
            current_parent = nr
        elif not is_component and article.get("parent_nr") is not None:
            # Main article with explicit parent_nr: use it as context
            current_parent = article.get("parent_nr")

        # For components with missing parent_nr, fill from current_parent
        if is_component and original_parent is None:
            article_copy["parent_nr"] = current_parent
            article_copy["hierarchy_corrected"] = True
        else:
            article_copy["hierarchy_corrected"] = False

        result.append(article_copy)

    return result
