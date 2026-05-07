"""
Extraction validator — verifică acoperirea extracției F3 față de textul brut DI.

Opțiunea 1: numără coduri de articole valide în textul brut vs. extrase în JSON.
Dacă rata < COVERAGE_THRESHOLD → warning în sesiune.

Opțiunea 3: marchează ARTICOL_EXTRA suspecte — coduri prezente în DI-ul referinței
dar lipsă din articolele extrase ale referinței (posibil omise de LLM).

Public API:
    check_extraction_coverage(full_text, articole, out_key) -> dict
    mark_suspicious_extras(neconformitati, ref_di_text) -> list
"""
import re
import logging

logger = logging.getLogger(__name__)

# Prag minim de acoperire: articole extrase / coduri detectate in text brut
COVERAGE_THRESHOLD = 0.70

# Pattern cod articol valid: 2-5 litere + 2-4 cifre + optional litere/cifre
# Ex: TSC35A22, CA07A1, RPCT09H1, ACD01L1, EA02A1
_COD_PATTERN = re.compile(r'\b[A-Z]{2,5}\d{2,4}[A-Z0-9]{0,4}\b')

# Coduri false pozitive frecvente (anteturi, unitati de masura, etc.)
_EXCLUDED_CODES = {
    'MC', 'MP', 'KG', 'BUC', 'ML', 'KM', 'HA', 'TF', 'MJ',
    'TV', 'TVA', 'NR', 'PU', 'UM', 'ID', 'SP'
}


def _extract_codes_from_text(text: str) -> set:
    """Extrage toate codurile de articole candidate din textul brut DI."""
    candidates = _COD_PATTERN.findall(text.upper())
    return {c for c in candidates if c not in _EXCLUDED_CODES}


def check_extraction_coverage(full_text: str, articole: list, out_key: str) -> dict:
    """
    Compară codurile detectate în textul brut cu cele extrase de F3.

    Returns dict cu:
        - detected_in_text: nr coduri unice detectate in DI
        - extracted: nr articole extrase
        - coverage: rata acoperire (0.0 - 1.0+)
        - warning: True dacă coverage < COVERAGE_THRESHOLD
    """
    detected = _extract_codes_from_text(full_text)
    extracted_codes = {a.get("cod", "").upper() for a in articole if a.get("cod")}

    n_detected = len(detected)
    n_extracted = len(extracted_codes)
    coverage = n_extracted / n_detected if n_detected > 0 else 1.0

    result = {
        "detected_in_text": n_detected,
        "extracted": n_extracted,
        "coverage": round(coverage, 3),
        "warning": coverage < COVERAGE_THRESHOLD
    }

    if result["warning"]:
        logger.warning(
            f"[VALID] {out_key}: acoperire scazuta {n_extracted}/{n_detected} "
            f"({coverage:.1%}) < {COVERAGE_THRESHOLD:.0%} — reindexare recomandata"
        )
    else:
        logger.info(
            f"[VALID] {out_key}: acoperire OK {n_extracted}/{n_detected} ({coverage:.1%})"
        )

    return result


def mark_suspicious_extras(neconformitati: list, ref_di_text: str) -> list:
    """
    Opțiunea 3: pentru fiecare ARTICOL_EXTRA, verifică dacă codul apare
    în textul brut DI al referinței. Dacă da → marchează posibil_omis_din_extractie=True.

    Returns lista neconformitati cu câmpul adăugat unde e cazul.
    """
    if not ref_di_text:
        return neconformitati

    ref_text_upper = ref_di_text.upper()
    result = []
    marked = 0

    for n in neconformitati:
        if n.get("tip") == "ARTICOL_EXTRA":
            cod = (n.get("oferta_cod") or "").upper().strip()
            if cod and cod in ref_text_upper:
                n = {**n, "posibil_omis_din_extractie": True}
                marked += 1
        result.append(n)

    if marked:
        logger.warning(
            f"[VALID] {marked} ARTICOL_EXTRA marcate ca posibil_omis_din_extractie "
            f"(codul apare in DI referinta dar lipseste din articolele extrase)"
        )

    return result
