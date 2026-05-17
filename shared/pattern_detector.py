"""Pattern detection for hierarchical component extraction.

Detects document format (MANECIU, DRAGOMIRESTI, SPORTIVA, etc.)
and applies pattern-specific extraction rules.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

PATTERN_LIBRARY_PATH = Path(__file__).parent / "pattern_library.json"


def load_pattern_library() -> Dict:
    """Load known patterns from pattern_library.json."""
    if not PATTERN_LIBRARY_PATH.exists():
        logger.warning(f"Pattern library not found: {PATTERN_LIBRARY_PATH}")
        return {"patterns": []}

    with open(PATTERN_LIBRARY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_pattern_library(library: Dict) -> None:
    """Save pattern library to JSON."""
    with open(PATTERN_LIBRARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(library, f, ensure_ascii=False, indent=2)


def get_pattern_by_name(name: str) -> Optional[Dict]:
    """Retrieve pattern definition by name."""
    library = load_pattern_library()
    for p in library.get("patterns", []):
        if p["name"] == name:
            return p
    return None


def detect_pattern(chapter_text: str, min_confidence: float = 0.70) -> Optional[Dict]:
    """Detect pattern in chapter text by matching indicators.

    Args:
        chapter_text: Full chapter text (STADIUL FIZIC section)
        min_confidence: Minimum confidence threshold

    Returns:
        {pattern_name, confidence, extraction_rules} or None
    """
    library = load_pattern_library()
    lines = chapter_text.split('\n')

    best_match = None
    best_score = 0.0

    for pattern in library.get("patterns", []):
        score = _calculate_pattern_confidence(lines, pattern)
        if score > best_score:
            best_score = score
            best_match = pattern

    if best_match and best_score >= min_confidence:
        return {
            "pattern_name": best_match["name"],
            "confidence": best_score,
            "extraction_rules": best_match.get("extraction_rules", {})
        }

    return None


def _calculate_pattern_confidence(lines: List[str], pattern: Dict) -> float:
    """Calculate confidence score for pattern match.

    Score based on percentage of lines that match parent or component indicators.
    """
    parent_matches = 0
    component_matches = 0
    total_lines = len([l for l in lines if l.strip()])

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Check parent indicators
        for parent_re in pattern.get("parent_indicators", []):
            if re.match(parent_re, line_stripped):
                parent_matches += 1
                break

        # Check component indicators
        for comp_ind in pattern.get("component_indicators", []):
            if re.match(comp_ind["pattern"], line_stripped):
                component_matches += 1
                break

    if total_lines == 0:
        return 0.0

    # Score: percentage of lines that matched any indicator
    # Boost if both parent and component indicators found
    matches = parent_matches + component_matches
    base_score = matches / total_lines

    # If we have both parent and component matches, boost confidence
    if parent_matches > 0 and component_matches > 0:
        base_score = min(1.0, base_score * 1.5)

    return min(1.0, base_score)
