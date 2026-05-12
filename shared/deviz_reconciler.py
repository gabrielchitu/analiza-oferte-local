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


def _page_opens_deviz(lines: list[str], target_re) -> bool:
    """Verifică dacă pagina conține un header STADIUL FIZIC pentru target_code.

    Caută 'STADIUL FIZIC:' urmat de target_code în fereastra de 8 linii —
    același comportament ca f3_page_classifier. Previne false pozitive din
    pagini FORMULAR C6, footer-uri sau totaluri care menționează codul întâmplător.
    """
    for i, line in enumerate(lines):
        if _STADIUL_FIZIC_RE.search(line):
            window = lines[i: i + 8]
            if any(target_re.search(ln) for ln in window):
                return True
    return False


def _find_deviz_page_range(
    di_pages: list[dict],
    target_code: str,
    pc_by_pn: dict,
) -> list[tuple[int, list[str]]]:
    """
    Caută target_code în toate paginile DI JSON.

    Returnează lista de (page_number, lines_as_strings) pentru paginile
    aparținând devizului target_code, în ordine consecutivă.

    Intrarea în interval necesită un header STADIUL FIZIC explicit cu target_code —
    simpla prezență a codului pe pagină (footer, total, referință) nu este suficientă.

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

        if not in_target:
            # Intrare DOAR dacă pagina are header STADIUL FIZIC cu target_code
            if _page_opens_deviz(lines, _target_re):
                in_target = True
                result.append((pn, lines))
        else:
            full_text = " ".join(lines)
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


def reconcile_missing_devize(
    di_path: Path,
    missing_codes: set[str],
    checkpoint_path: Path,
    existing_articles: list,
) -> tuple[list, set[str]]:
    """
    Pentru fiecare cod din missing_codes, caută devizul în toate paginile di_path.
    Actualizează checkpoint-ul cu paginile nou clasificate F3.

    Returns:
        (updated_articles, still_missing_codes)
        - updated_articles: existing_articles + articolele nou extrase
        - still_missing_codes: coduri negăsite nicăieri (eroare OCR/parsare)
    """
    from shared.f3_extractor import extract_articles_v3

    if not missing_codes:
        return existing_articles, set()

    if not checkpoint_path.exists():
        logger.warning(f"  [RECONCILE] Checkpoint lipsă: {checkpoint_path} — skip reconciliere")
        return existing_articles, set(missing_codes)

    di = json.loads(di_path.read_text(encoding="utf-8"))
    di_pages = di.get("pages", [])
    page_classes: list[dict] = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    pc_by_pn: dict[int, dict] = {pc["page_number"]: pc for pc in page_classes}

    all_articles = list(existing_articles)
    still_missing: set[str] = set()
    checkpoint_dirty = False

    for code in sorted(missing_codes):
        target = code.strip().upper()
        page_range = _find_deviz_page_range(di_pages, target, pc_by_pn)

        if not page_range:
            logger.warning(f"  [RECONCILE] Deviz {target} NEGASIT in {di_path.stem}")
            still_missing.add(code)
            continue

        pages_to_extract: list[dict] = []
        for pn, lines in page_range:
            pc = pc_by_pn.get(pn)
            if pc is None:
                pc = {
                    "page_number": pn, "is_f3": True,
                    "deviz_cod": target, "deviz_den": "",
                    "lines": lines, "needs_llm": False, "header_only": False,
                }
                page_classes.append(pc)
                pc_by_pn[pn] = pc
                checkpoint_dirty = True
                pages_to_extract.append(pc)
            elif pc.get("is_f3") and pc.get("deviz_cod", "").upper() == target:
                pass  # deja clasificat corect — articolele sunt în existing_articles
            else:
                pc["is_f3"] = True
                pc["deviz_cod"] = target
                pc["header_only"] = False
                checkpoint_dirty = True
                pages_to_extract.append(pc)

        if pages_to_extract:
            new_arts = extract_articles_v3(pages_to_extract)
            logger.info(
                f"  [RECONCILE] Deviz {target}: {len(new_arts)} articole gasite"
                f" pe {len(pages_to_extract)} pagini (din {len(page_range)} total)"
            )
            all_articles.extend(new_arts)
        else:
            logger.info(f"  [RECONCILE] Deviz {target}: pagini deja extrase — skip")

    if checkpoint_dirty:
        checkpoint_path.write_text(
            json.dumps(page_classes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  [RECONCILE] Checkpoint actualizat: {checkpoint_path.name}")

    return all_articles, still_missing
