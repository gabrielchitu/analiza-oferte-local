"""
Subcomponent Code Extraction

Uses detected format to properly extract subcomponent codes from reference articles.
Integrates with the article extraction pipeline.
"""
import re
import logging
from shared.subcomponent_formats import (
    extract_subcomponent_code,
    SubcomponentFormat
)

logger = logging.getLogger(__name__)


def extract_subcomponent_codes_from_text(text: str, format_info: dict) -> list:
    """
    Extract all subcomponent codes from a text block.

    Args:
        text: Full text block (may contain multiple subcomponents)
        format_info: Format detection result with 'format' and 'regex' fields

    Returns:
        List of extracted codes, or empty list if format unknown
    """
    if not format_info or format_info.get("format") == SubcomponentFormat.UNKNOWN:
        return []

    codes = []
    pattern = format_info.get("regex")
    code_group = format_info.get("code_group", 1)

    if not pattern:
        return codes

    try:
        for match in re.finditer(pattern, text, re.MULTILINE):
            if code_group <= len(match.groups()):
                code = match.group(code_group).strip().upper()
                if code:
                    codes.append(code)
    except Exception as e:
        logger.warning(f"[SUBEXT] Failed to extract codes: {e}")

    return codes


def parse_subcomponent_line(line: str, format_info: dict) -> dict:
    """
    Parse a single line that may contain subcomponent info.

    Args:
        line: Single line of text
        format_info: Detected format info

    Returns:
        {
            "code": extracted code,
            "raw_line": original line,
            "format_matched": whether format matched
        }
    """
    if not format_info or format_info.get("format") == SubcomponentFormat.UNKNOWN:
        return {"code": None, "raw_line": line, "format_matched": False}

    code = extract_subcomponent_code(line, format_info)
    return {
        "code": code,
        "raw_line": line,
        "format_matched": code is not None
    }


def build_subcomponent_lookup(ref_text: str, format_info: dict) -> dict:
    """
    Build a lookup table of all subcomponent codes in reference.

    Args:
        ref_text: Full reference text
        format_info: Detected format

    Returns:
        {
            "format": format name,
            "codes": set of all extracted codes,
            "lines_matched": count of lines with codes
        }
    """
    codes = extract_subcomponent_codes_from_text(ref_text, format_info)

    return {
        "format": format_info.get("name", "unknown") if format_info else "unknown",
        "codes": set(codes),
        "lines_matched": len(codes),
        "code_samples": codes[:10] if codes else []
    }


def match_subcomponent_in_offer(offer_code: str, ref_lookup: dict) -> bool:
    """
    Check if an offer subcomponent code exists in reference lookup.

    Args:
        offer_code: Code from offer
        ref_lookup: Lookup table from build_subcomponent_lookup()

    Returns:
        True if code found in reference
    """
    if not ref_lookup or not offer_code:
        return False

    return offer_code.upper() in ref_lookup.get("codes", set())


def validate_subcomponent_extraction(
    extracted_codes: list,
    format_info: dict,
    expected_count: int = None
) -> dict:
    """
    Validate quality of subcomponent extraction.

    Args:
        extracted_codes: List of extracted codes
        format_info: Format info used
        expected_count: Expected number of subcomponents (optional)

    Returns:
        {
            "valid": true/false,
            "count": number of codes extracted,
            "format": format name,
            "confidence": confidence score,
            "warnings": list of warnings if any
        }
    """
    warnings = []
    confidence = format_info.get("confidence", 0.0) if format_info else 0.0

    if not extracted_codes and expected_count and expected_count > 0:
        warnings.append(f"Expected {expected_count} subcomponents but extracted 0")
        confidence *= 0.5

    if expected_count and len(extracted_codes) != expected_count:
        warnings.append(
            f"Extracted {len(extracted_codes)} codes but expected ~{expected_count}"
        )

    return {
        "valid": len(warnings) == 0 and len(extracted_codes) > 0,
        "count": len(extracted_codes),
        "format": format_info.get("name", "unknown") if format_info else "unknown",
        "confidence": confidence,
        "warnings": warnings
    }
