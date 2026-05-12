"""
deviz_reconciler.py — Reconciliere post-extracție pentru devize lipsă.

Detectează devize absente prin cross-verificare referință vs ofertă,
le caută țintit în documentul DI, actualizează checkpoint-ul.
Zero apeluri LLM.
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Detectează header de deviz nou: "STADIUL FIZIC:" / "STADIU FIZIC:"
_STADIUL_FIZIC_RE = re.compile(r'STADIU[L]?\s+FIZIC\s*:', re.IGNORECASE)

# Extrage codul devizului dintr-o linie cu STADIUL FIZIC
# Acceptă: "oferta 226100", "001 226100", "226100" direct
_DEVIZ_COD_RE = re.compile(
    r'(?:oferta\s+)?(?:\d{1,3}\s+)?((?=[A-Z0-9]*\d{3})[A-Z0-9]{5,8})',
    re.IGNORECASE,
)


def _find_deviz_page_range(
    di_pages: list[dict],
    target_code: str,
    pc_by_pn: dict,
) -> list[tuple[int, list[str]]]:
    """
    Caută target_code în toate paginile DI JSON.

    Returnează lista de (page_number, lines_as_strings) pentru paginile
    aparținând devizului target_code, în ordine consecutivă.

    Se oprește când:
    - apare un header "STADIUL FIZIC:" cu un cod diferit
    - pagina e deja clasificată F3 cu un alt deviz_cod

    Args:
        di_pages: paginile brute din DI JSON ({"page_number": N, "lines": [{"content": "..."}]})
        target_code: codul devizului căutat (ex: "226400"), uppercase
        pc_by_pn: page_classes indexate după page_number (pentru verificare clasificare existentă)
    """
    target = target_code.strip().upper()
    _target_re = re.compile(r'\b' + re.escape(target) + r'\b', re.IGNORECASE)

    result: list[tuple[int, list[str]]] = []
    in_target = False

    for page in sorted(di_pages, key=lambda p: p.get("page_number", 0)):
        pn = page.get("page_number", 0)
        lines = [ln.get("content", "") for ln in page.get("lines", [])]
        full_text = " ".join(lines)

        if not in_target:
            if _target_re.search(full_text):
                in_target = True
                result.append((pn, lines))
        else:
            # Verifică dacă această pagină deschide un deviz NOU
            if _STADIUL_FIZIC_RE.search(full_text):
                m = _DEVIZ_COD_RE.search(full_text)
                if m:
                    found_code = m.group(1).upper()
                    if found_code != target:
                        break  # header cu alt deviz — oprim

            # Verifică clasificarea existentă în checkpoint
            existing = pc_by_pn.get(pn, {})
            if existing.get("is_f3") and existing.get("deviz_cod") and existing.get("deviz_cod").upper() != target:
                break  # pagină deja atribuită altui deviz — oprim

            result.append((pn, lines))

    return result
