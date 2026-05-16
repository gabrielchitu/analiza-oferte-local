"""
Subcomponent Format Detection & Extraction

Supports multiple reference formats for subcomponent codes:
1. Prefixed (MANECIU): L:LC52A -0067:6110532
2. Simple (DRAGOMIRESTI): 31.1 2100995 -
3. Marker (SPORTIVA RACARI): >>> componenta 002 010 3271283

Uses hardcoded patterns for speed + LLM fallback for unknowns.
"""
import re
import logging
from enum import Enum

logger = logging.getLogger(__name__)


class SubcomponentFormat(Enum):
    """Known subcomponent format types."""
    PREFIXED = "prefixed"      # L:PREFIX -NUMBER:CODE
    SIMPLE = "simple"           # ID CODE - DESC
    MARKER = "marker"           # >>> componenta ID ?? CODE
    UNKNOWN = "unknown"


# Pattern Registry (hardcoded for speed)
SUBCOMPONENT_PATTERNS = {
    SubcomponentFormat.PREFIXED: {
        "name": "Prefixed (MANECIU format)",
        "regex": r"L\s*:\s*([A-Z0-9]+)\s*-\s*([A-Z0-9]*)\s*:\s*([0-9A-Z]+)",
        "code_group": 3,
        "confidence": 0.95,
        "example": "L:LC52A -0067:6110532"
    },
    SubcomponentFormat.SIMPLE: {
        "name": "Simple (DRAGOMIRESTI format)",
        "regex": r"(\d+\.\d+)\s+([A-Z0-9]+)\s*-",
        "code_group": 2,
        "confidence": 0.95,
        "example": "31.1 2100995 -"
    },
    SubcomponentFormat.MARKER: {
        "name": "Marker (SPORTIVA RACARI format)",
        "regex": r">>>\s*componenta\s+(\d+)\s+(\d+)\s+([A-Z0-9]+)",
        "code_group": 3,
        "confidence": 0.95,
        "example": ">>> componenta 002 010 3271283"
    }
}


def detect_subcomponent_format(text_sample: str) -> dict:
    """
    Detect subcomponent format from text sample.

    Fast path: Try hardcoded patterns first.

    Args:
        text_sample: Sample text containing subcomponents (10-50 lines)

    Returns:
        {
            "format": SubcomponentFormat.XXXX,
            "confidence": 0.0-1.0,
            "name": "Human-readable format name",
            "regex": compiled regex pattern,
            "code_group": which group contains the code
        }
    """
    if not text_sample:
        return _unknown_format()

    # Try each pattern
    for fmt, pattern_def in SUBCOMPONENT_PATTERNS.items():
        if fmt == SubcomponentFormat.MARKER:
            # Marker format is very specific - check for >>> componenta
            if ">>> componenta" in text_sample or ">>>" in text_sample:
                if re.search(pattern_def["regex"], text_sample, re.MULTILINE):
                    return _format_result(fmt, pattern_def)
        else:
            # Other formats - check for key indicators
            if re.search(pattern_def["regex"], text_sample, re.MULTILINE):
                return _format_result(fmt, pattern_def)

    # No hardcoded pattern matched
    logger.warning("[SUBCF] No hardcoded pattern matched, format unknown")
    return _unknown_format()


def extract_subcomponent_code(text: str, format_info: dict) -> str:
    """
    Extract subcomponent code using detected format.

    Args:
        text: Text line containing subcomponent
        format_info: Format detection result from detect_subcomponent_format()

    Returns:
        Extracted code, or None if not found
    """
    if format_info["format"] == SubcomponentFormat.UNKNOWN:
        return None

    pattern_def = SUBCOMPONENT_PATTERNS.get(format_info["format"])
    if not pattern_def:
        return None

    regex = pattern_def["regex"]
    code_group = pattern_def["code_group"]

    try:
        match = re.search(regex, text, re.MULTILINE)
        if match and code_group <= len(match.groups()):
            code = match.group(code_group).strip().upper()
            return code if code else None
    except Exception as e:
        logger.error(f"[SUBCF] Extraction failed for '{text[:50]}': {e}")

    return None


def extract_subcomponent_code_batch(texts: list, format_info: dict) -> list:
    """
    Extract codes from multiple text lines.

    Args:
        texts: List of text lines
        format_info: Format detection result

    Returns:
        List of (text, extracted_code) tuples
    """
    results = []
    for text in texts:
        code = extract_subcomponent_code(text, format_info)
        if code:
            results.append((text, code))
    return results


def analyze_format_with_llm(text_sample: str, openai_client, deployment: str) -> dict:
    """
    Use LLM to detect format when hardcoded patterns fail.

    Args:
        text_sample: Sample text with subcomponents
        openai_client: OpenAI-compatible client
        deployment: Model deployment name

    Returns:
        {
            "format": detected format description,
            "pattern": regex pattern for extraction,
            "code_group": which group contains code,
            "confidence": confidence score
        }
    """
    prompt = f"""Analyze these subcomponent code samples and identify the format pattern.

Samples:
{text_sample[:500]}

Return a JSON with:
{{
  "format_description": "Human description of the format",
  "pattern": "Regex pattern to extract codes (use groups)",
  "code_group": <number of group containing code>,
  "confidence": <0.0-1.0>,
  "example_code": "Example extracted code"
}}

Only respond with JSON, no extra text."""

    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500
        )
        result = resp.choices[0].message.content
        import json
        return json.loads(result)
    except Exception as e:
        logger.error(f"[SUBCF] LLM format detection failed: {e}")
        return _unknown_format()


def _format_result(fmt: SubcomponentFormat, pattern_def: dict) -> dict:
    """Helper: Format detection result."""
    return {
        "format": fmt,
        "confidence": pattern_def["confidence"],
        "name": pattern_def["name"],
        "regex": pattern_def["regex"],
        "code_group": pattern_def["code_group"]
    }


def _unknown_format() -> dict:
    """Helper: Unknown format result."""
    return {
        "format": SubcomponentFormat.UNKNOWN,
        "confidence": 0.0,
        "name": "Unknown format",
        "regex": None,
        "code_group": None
    }
