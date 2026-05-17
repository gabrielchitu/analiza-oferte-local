"""
Deviz Catalog — Maps deviz denominations to numeric codes.

This is the source of truth for all deviz mappings extracted from referinta.
Used to resolve ambiguous page-level text to precise numeric deviz codes.
"""

# Mapping: deviz_denomination (from page text) → numeric_code
# These come from analyzing referinta deviz structure
# NOTE: Longer keys are matched first (substring matching), so order specificity: longer first
DEVIZ_BY_DENOMINATION = {
    # Terasamente
    "terasam desf conexe": "4.1-01",
    "terasam canal": "4.1-01",
    "structura conexe": "4.1-02",
    "structura": "4.1-02",

    # Arhitectura (eligibili is more common, so it's default for ambiguous "Arhitectura")
    "arhitectura - eligibili": "4.1-03",
    "arhitectura eligibili": "4.1-03",
    "arhitectura conexe": "4.1-04",
    "arhitectura": "4.1-03",

    # Instalații electrice
    "inst electrice tip": "4.1-05",
    "inst electrice ilum": "4.1-06",

    # Instalații speciale
    "instal el paratrás": "4.1-07",
    "inst detectie incendiu": "4.1-08",

    # Instalații termice și sanitare
    "inst sanit hidranti": "4.1-13",
    "instalatii termice": "4.1-09",
    "instalatii hvac": "4.1-10",
    "inst apa calda": "4.1-11",
    "instalatii ventilatii": "4.1-12",
    "inst sanitare gosp": "4.1-13",
    "instalatii sanitare gosp": "4.1-13",
    "instalatii sanitare": "4.1-13",

    # Echipamente
    "echipam el tablouri": "4.1-15",
    "echipamente hvac": "4.1-16",
    "echipam apa calda": "4.1-17",
    "echipam panouri solare": "4.1-18",
    "echipam detect inc": "4.1-20",
    "echipam el paratras": "4.1-21",

    # Utilitari și speciale - incinta
    "instalatii incinta": "4.3-01",

    # Utilitari - camine
    "camine canal": "4.3-03",
    "camin": "4.3-04",

    # Utilitari - conducte
    "conducte apa": "4.3-07",
    "conducte canal": "4.3-08",

    # Parcare
    "parcare": "4.4-2",

    # Lucrari
    "lucrari": "5.1-1",
}


def find_deviz_for_text(text: str) -> str | None:
    """
    Find numeric deviz code for a given text denomination.

    Args:
        text: Text from "STADIUL FIZIC" or similar page header

    Returns:
        Numeric deviz code (e.g., "4.1-01") or None if not found
    """
    if not text:
        return None

    text_lower = text.lower().strip()

    # Exact substring match (longer matches first, better specificity)
    for denom_key in sorted(DEVIZ_BY_DENOMINATION.keys(), key=len, reverse=True):
        if denom_key in text_lower:
            return DEVIZ_BY_DENOMINATION[denom_key]

    return None


def extract_stadiul_fizic(page_text: str) -> str | None:
    """
    Extract "STADIUL FIZIC:" value from page text.

    Format: "STADIUL FIZIC: [value]"
    Sometimes followed by "0 1 2 3 4 5" (table headers)

    Args:
        page_text: Full page extracted text

    Returns:
        Extracted value or None if not found
    """
    import re

    # Pattern: "STADIUL FIZIC:" followed by text up to newline or numbers
    match = re.search(
        r'STADIUL\s+FIZIC:\s*([^\n0-9]+?)(?:\s+[0-9]|\s*$)',
        page_text,
        re.IGNORECASE | re.MULTILINE
    )

    if match:
        return match.group(1).strip()

    return None
