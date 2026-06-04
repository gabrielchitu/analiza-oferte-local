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
    """Fix broken hierarchy using forward fill (ffill) with group awareness.

    For component articles with missing parent_nr, inherit parent from the current
    group's parent context. The context is established by main articles
    (is_component=False) and resets at group boundaries.

    GROUP-AWARE LOGIC:
    - Track `current_parent` based on the most recent main article
    - When a new main article is encountered, update `current_parent` (GROUP BOUNDARY RESET)
    - For components with missing parent_nr, fill from the current group's parent
    - This prevents components from inheriting parents from previous groups

    EXAMPLES:
    ```
    Article 1 (main, nr="1", parent_nr=None)
    Article 1.1 (comp, nr="1.1", parent_nr="1")           ✓ Valid
    Article 1.2 (comp, nr="1.2", parent_nr=None)          → Fixed to "1" (group context)
    Article 2 (main, nr="2", parent_nr=None)              ← GROUP BOUNDARY: reset current_parent to "2"
    Article 2.1 (comp, nr="2.1", parent_nr=None)          → Fixed to "2" (NOT "1")
    ```

    Args:
        articles: List of article dictionaries with keys: nr, parent_nr, is_component

    Returns:
        List of article dictionaries with:
        - Fixed parent_nr values (filled from group's parent context)
        - New field 'hierarchy_corrected' (boolean): True if parent_nr was modified
    """
    if not articles:
        return []

    result = []
    current_parent = None

    for article in articles:
        article_copy = article.copy()
        original_parent = article.get("parent_nr")
        is_component = article.get("is_component", False)
        nr = article.get("nr")

        # GROUP BOUNDARY DETECTION: Update current_parent based on main articles
        if not is_component:
            # Main article found: establish/reset the group context
            if article.get("parent_nr") is None:
                # Main article with no parent_nr: becomes the group parent
                current_parent = nr
            else:
                # Main article with explicit parent_nr: use it as group parent
                current_parent = article.get("parent_nr")

        # FIX MISSING PARENTS: For components without parent_nr, fill from current group
        if is_component and original_parent is None:
            article_copy["parent_nr"] = current_parent
            article_copy["hierarchy_corrected"] = True
        else:
            article_copy["hierarchy_corrected"] = False

        result.append(article_copy)

    return result


def validate_hierarchy(articles: List[Dict]) -> Dict:
    """Validate corrected hierarchies against constraints.

    Checks four constraints:
    1. PARENT_NOT_FOUND: All parent_nr references exist (no dangling references)
    2. NESTING_TOO_DEEP: Max nesting depth ≤ 3 (0=main, 1=sub, 2=subsub, max 2 dots)
    3. COMPONENT_NO_PARENT: Components have valid parent_nr (no None after correction)
    4. CIRCULAR_REFERENCE: No circular references (A→B→C→A is forbidden)

    Args:
        articles: List of article dictionaries with keys: nr, parent_nr, is_component

    Returns:
        Dictionary with structure:
        {
            "is_valid": bool,
            "error_count": int,
            "errors": [
                {"index": idx, "nr": "...", "error": "PARENT_NOT_FOUND"|"NESTING_TOO_DEEP"|"COMPONENT_NO_PARENT"|"CIRCULAR_REFERENCE"}
            ]
        }
    """
    if not articles:
        return {
            "is_valid": True,
            "error_count": 0,
            "errors": [],
        }

    errors = []

    # Build set of all existing article NRs for parent validation
    all_nrs = {art.get("nr") for art in articles if art.get("nr")}

    # Check constraints
    for idx, article in enumerate(articles):
        nr = article.get("nr")
        parent_nr = article.get("parent_nr")
        is_component = article.get("is_component", False)

        # Constraint 1: PARENT_NOT_FOUND - parent_nr must reference existing parent
        if parent_nr is not None and parent_nr not in all_nrs:
            errors.append({
                "index": idx,
                "nr": nr,
                "error": "PARENT_NOT_FOUND",
            })

        # Constraint 2: NESTING_TOO_DEEP - max depth is 2 dots (levels 0, 1, 2)
        if nr:
            dot_count = nr.count(".")
            if dot_count > 2:
                errors.append({
                    "index": idx,
                    "nr": nr,
                    "error": "NESTING_TOO_DEEP",
                })

        # Constraint 3: COMPONENT_NO_PARENT - components must have parent_nr
        if is_component and parent_nr is None:
            errors.append({
                "index": idx,
                "nr": nr,
                "error": "COMPONENT_NO_PARENT",
            })

    # Constraint 4: CIRCULAR_REFERENCE - detect circular parent chains
    for idx, article in enumerate(articles):
        nr = article.get("nr")
        parent_nr = article.get("parent_nr")

        if parent_nr is None:
            continue

        # Trace the parent chain to detect cycles
        visited = set()
        current = parent_nr

        while current is not None:
            if current in visited:
                # Circular reference detected
                errors.append({
                    "index": idx,
                    "nr": nr,
                    "error": "CIRCULAR_REFERENCE",
                })
                break

            visited.add(current)

            # Find the parent of current
            next_parent = None
            for art in articles:
                if art.get("nr") == current:
                    next_parent = art.get("parent_nr")
                    break

            current = next_parent

    return {
        "is_valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors,
    }
