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
