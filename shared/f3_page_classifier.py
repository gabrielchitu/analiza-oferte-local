# func-analiza-oferte/shared/f3_page_classifier.py
"""
Page-aware F3 classifier for DI JSON pages.

Public API:
    classify_page_local(page: dict) -> dict  — clasificare fără LLM
    classify_pages(pages, openai_client, deployment) -> list[dict]  — full pipeline (Task 4)
"""
import re
import json
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Semnale F3 ────────────────────────────────────────────────────────────────

# "STADIUL FIZIC: oferta 226108 STRUCTURA..." sau "STADIU FIZIC: ..."
_STADIUL_FIZIC_RE = re.compile(
    r'STADIU[L]?\s+FIZIC\s*:\s*(.+)',
    re.IGNORECASE
)

# "Formularul F3" sau "Formular F3"
_FORMULAR_F3_RE = re.compile(
    r'Formular(?:ul)?\s+F3',
    re.IGNORECASE
)

# eDevize data pages: "SECTIUNEA TEHNICA SECTIUNEA FINANCIARA Nr. Capitol de lucrari"
_SECTIUNEA_TEHNICA_RE = re.compile(
    r'SECTIUNEA\s+TEHNICA\s+SECTIUNEA\s+FINANCIARA.*Capitol\s+de\s+lucrari',
    re.IGNORECASE
)

# eDevize cover page: "Stadiul fizic: NNN XXXXXX NAME"  (lowercase 's')
# NNN = 1-3 digit chapter, XXXXXX = 6-char code with optional letters
_STADIUL_FIZIC_EDEVIZE_RE = re.compile(
    r'Stadiul\s+fizic\s*:\s*(?:\d{1,3}\s+)?([A-Z0-9]{5,8})\s+(.*)',
    re.IGNORECASE
)

# eDevize continuation pages: ">>> componenta NNN" format with article data
# Example: "226228 pag >>> componenta 010 035 SD05A1 BUC. 2.000 ROBINET..."
_EDEVIZE_CONTINUATION_RE = re.compile(r'>>>\s*componenta')

# ── Semnale non-F3 ────────────────────────────────────────────────────────────

_NON_F3_PATTERNS = [
    re.compile(r'FORMULAR\s+(?!F3\b)[CF][0-9]', re.IGNORECASE),      # FORMULAR C6, F1, F2, F4 — excludes F3
    re.compile(r'CENTRALIZATORUL\s+cheltuielilor', re.IGNORECASE),
    re.compile(r'LISTA\s+cuprinzand\s+consumurile', re.IGNORECASE),
    re.compile(r'Formularul\s+nr\.', re.IGNORECASE),         # formular de oferta
]

# Recapitulatie = pagina de sumar la finalul unui deviz, NU date F3
_RECAPITULATIE_RE = re.compile(r'\bRecapitulati[ae]?\b', re.IGNORECASE)

# Article code pattern: matches various normative code formats
# Examples: VA02B08, CA01J1, ACA10B1, TSC02D11, CD05B1, CE05E1, etc.
# Matches: 2-5 letters + 1-4 digits + optional letter + 0-2 digits
_ARTICLE_CODE_RE = re.compile(r'\b[A-Z]{2,5}\d{1,4}[A-Z]?\d{0,2}\b')

# NOTĂ: nu defini _DEVIZ_COD_RE — neutilizat, dead code


def _extract_lines(page: dict) -> list[str]:
    return [l.get("content", "") for l in page.get("lines", [])]


def _has_article_codes(full_content: str) -> bool:
    """Check if page contains article codes (e.g. VA02B08, VA03K02).
    Used to distinguish between pure header pages and pages with data."""
    return bool(_ARTICLE_CODE_RE.search(full_content))


def _extract_deviz_from_stadiul_fizic(text: str) -> tuple[str, str]:
    """Din 'STADIUL FIZIC: oferta 226108 STRUCTURA CUPOLA' or 'Stadiul fizic: 001 226108 STRUCTURA CUPOLA' (eDevize)."""
    # Elimina 'oferta' prefix dacă există (ISDP format)
    text = re.sub(r'^(?:oferta\s+)?', '', text.strip(), flags=re.IGNORECASE)
    # Pentru eDevize, elimina prefixul numeric NNN (ex: "001 226108 STRUCTURA" → "226108 STRUCTURA")
    text = re.sub(r'^\d{1,3}\s+', '', text.strip())
    # Cauta codul (primul token de 5-8 alfanumerice)
    m = re.match(r'([A-Z0-9]{5,8})\s*(.*)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).strip()
    return "", text.strip()


def classify_page_local(page: dict) -> dict:
    """
    Clasifică o pagină DI JSON fără LLM.

    Returns:
        {
            "label": "F3" | "NON_F3" | "AMBIGUOUS",
            "deviz_cod": str,   # ex: "226108" (doar pentru F3)
            "deviz_den": str,   # ex: "STRUCTURA DE REZISTENTA CUPOLA"
            "is_header": bool,  # True dacă pagina e cover/header pentru devizul următor
        }
    """
    lines = _extract_lines(page)
    if not lines:
        return {"label": "AMBIGUOUS", "deviz_cod": "", "deviz_den": "", "is_header": False}

    full_content = " ".join(lines)

    # ── Verifică semnale non-F3 ──
    for pat in _NON_F3_PATTERNS:
        if pat.search(full_content):
            return {"label": "NON_F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică Recapitulatia în tot conținutul paginii (override după STADIUL FIZIC) ──
    # O pagină care conține "Recapitulatia:" este o pagina de sumar, NU de date F3,
    # chiar dacă are STADIUL FIZIC în header (ex: ultima pagina a unui deviz ISDP).
    if _RECAPITULATIE_RE.search(full_content):
        return {"label": "NON_F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică STADIUL FIZIC (ISDP format) — în primele 3 linii ──
    for line in lines[:3]:
        m = _STADIUL_FIZIC_RE.match(line.strip())
        if m:
            cod, den = _extract_deviz_from_stadiul_fizic(m.group(1))
            return {"label": "F3", "deviz_cod": cod, "deviz_den": den, "is_header": False}

    # ── Verifică Stadiul fizic eDevize (cover page) — ÎNAINTE de Formular F3 ──
    # OCR poate împărți "Stadiul fizic: 226108 STRUCTURA" pe două linii separate →
    # folosim search în full_content (linii joined) nu match per linie.
    m = _STADIUL_FIZIC_EDEVIZE_RE.search(full_content)
    if m:
        cod = m.group(1).upper()
        den = m.group(2).strip()
        # Only mark as header if page has NO article codes.
        # If page contains article codes (VA02B08, etc.), it's data not pure header.
        is_header_only = not _has_article_codes(full_content)
        return {"label": "F3", "deviz_cod": cod, "deviz_den": den, "is_header": is_header_only}

    # ── Verifică Formularul F3 (standard format) ──
    if _FORMULAR_F3_RE.search(full_content):
        # Extrage codul deviz din context (număr înainte de "Formularul F3")
        m = re.search(r'(\d{5,8})\s+pag\s+\d+\s+Formular', full_content, re.IGNORECASE)
        if not m:
            # Fallback: 'Deviz "226208" - Formular F3' sau 'Deviz "008"' (eDevize last-page format)
            m = re.search(r'Deviz\s+"(\w+)"', full_content, re.IGNORECASE)
        if not m:
            # Fallback: "Deviz oferta 226108 STRUCTURA..." (Design Studio / format standard)
            m = re.search(r'Deviz\s+oferta\s+([A-Z0-9]{5,8})', full_content, re.IGNORECASE)
        cod = m.group(1) if m else ""
        den = ""  # va fi completat de deviz_normalizer
        return {"label": "F3", "deviz_cod": cod, "deviz_den": den, "is_header": False}

    # ── Verifică SECTIUNEA TEHNICA (eDevize data pages) ──
    if _SECTIUNEA_TEHNICA_RE.search(full_content):
        return {"label": "F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică eDevize continuation pages (>>> componenta NNN format) ──
    # These are data continuation pages from eDevize documents that contain articles
    # but lack standard F3 headers. Example: "226228 pag >>> componenta 010 035 SD05A1 BUC..."
    if _EDEVIZE_CONTINUATION_RE.search(full_content) and _has_article_codes(full_content):
        # Extract deviz code from page (format: "226228 pag" or similar)
        m = re.search(r'\b(\d{6})\s+pag', full_content, re.IGNORECASE)
        cod = m.group(1) if m else ""
        return {"label": "F3", "deviz_cod": cod, "deviz_den": "", "is_header": False}

    return {"label": "AMBIGUOUS", "deviz_cod": "", "deviz_den": "", "is_header": False}


def build_page_classifications(pages: list[dict]) -> list[dict]:
    """
    Clasifică toate paginile unui document și propagă devizul (eDevize format).

    Returns: list[dict] cu câmpuri:
        page_number, is_f3, deviz_cod, deviz_den, lines, needs_llm
    """
    results = []
    current_deviz_cod = ""
    current_deviz_den = ""

    for page in pages:
        lines = _extract_lines(page)
        page_number = page.get("page_number", 0)
        local = classify_page_local(page)

        if local["label"] == "NON_F3":
            # Reset propagare la orice pagină non-F3
            current_deviz_cod = ""
            current_deviz_den = ""
            results.append({
                "page_number": page_number, "is_f3": False,
                "deviz_cod": "", "deviz_den": "",
                "lines": lines, "needs_llm": False,
            })

        elif local["label"] == "F3":
            if local["deviz_cod"]:
                # Pagina are deviz propriu (STADIUL FIZIC explicit, Formularul F3 cu cod, header eDevize)
                current_deviz_cod = local["deviz_cod"]
                current_deviz_den = local["deviz_den"]
            # else: SECTIUNEA TEHNICA fără cod → folosește devizul propagat

            if local.get("is_header"):
                # Pagina de header nu conține articole — nu o transmitem extractor-ului
                results.append({
                    "page_number": page_number, "is_f3": True,
                    "deviz_cod": current_deviz_cod, "deviz_den": current_deviz_den,
                    "lines": lines, "needs_llm": False,
                    "header_only": True,
                })
            else:
                # Pagina F3 data: dacă nu are deviz (orfană), trimite la LLM
                needs_llm = not current_deviz_cod
                results.append({
                    "page_number": page_number, "is_f3": True,
                    "deviz_cod": current_deviz_cod, "deviz_den": current_deviz_den,
                    "lines": lines, "needs_llm": needs_llm,
                    "header_only": False,
                })

        else:  # AMBIGUOUS
            # Pagina ambiguă → trimitem la LLM
            # Reset propagare — nu știm ce urmează
            results.append({
                "page_number": page_number, "is_f3": False,  # default, LLM poate schimba
                "deviz_cod": current_deviz_cod, "deviz_den": current_deviz_den,
                "lines": lines, "needs_llm": True,
            })
            current_deviz_cod = ""
            current_deviz_den = ""

    return results


# ─── LLM batch ──────────────────────────────────────────────────────

_LLM_SYSTEM_PROMPT = """\
You are classifying pages from a Romanian public procurement document.
For each page below, determine:
1. Is it a Formular F3 bill of quantities page (lista de cantitati de lucrari)?
   A F3 page contains work items with codes, units, and quantities.
2. If yes, what is the deviz (bill) code? Look in any line containing words like
   "deviz", "stadiul fizic", "formular F3", or any standalone alphanumeric code
   (e.g. "226108", "008", "A1"). Return empty string if not found.
Return ONLY valid JSON in this exact format:
{"page_classifications": [{"page_number": <int>, "is_f3": <bool>, "deviz_cod": "<string>"}, ...]}
No other text, no markdown, no explanation."""

_LLM_MAX_LINES = 20   # linii trimise per pagina la LLM (codul poate aparea la finalul paginii)


def _classify_pages_llm(
    ambiguous: list[dict],
    openai_client,
    deployment: str,
) -> dict[int, dict]:
    """
    Trimite paginile la LLM într-un singur batch.
    Returns: {page_number: {"is_f3": bool, "deviz_cod": str}}
    """
    user_payload = {
        "pages": [
            {
                "page_number": r["page_number"],
                "lines": r["lines"][:_LLM_MAX_LINES],
            }
            for r in ambiguous
        ]
    }
    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            max_tokens=2000,
        )
        raw = json.loads(resp.choices[0].message.content)
        classifications = raw.get("page_classifications", [])
        if not classifications:
            logger.warning(f"[PC] LLM returned empty page_classifications for {len(ambiguous)} pages — treating all as NON_F3")
        return {
            item["page_number"]: {
                "is_f3": bool(item.get("is_f3", False)),
                "deviz_cod": str(item.get("deviz_cod", "") or "").strip(),
            }
            for item in classifications
            if "page_number" in item
        }
    except Exception as e:
        logger.warning(f"[PC] LLM batch classification failed: {e} — tratam ca non-F3")
        return {}


def classify_pages(
    pages: list[dict],
    openai_client,
    deployment: str,
) -> list[dict]:
    """
    Pipeline complet de clasificare pagini.

    1. Clasificare locală + propagare deviz (build_page_classifications)
       Paginile F3 fără deviz_cod (regex nu a găsit) sunt marcate needs_llm=True.
    2. LLM batch pentru toate paginile cu needs_llm=True:
       — clasifică (AMBIGUOUS → F3/NON_F3)
       — extrage deviz_cod pentru orice format, indiferent de soft
    3. Gardă zero-F3 (warning dacă niciuna nu e F3)

    Returns: list[dict] cu is_f3, deviz_cod, deviz_den, lines, page_number
    """
    results = build_page_classifications(pages)

    # Marcăm și paginile F3 fără deviz_cod ca needs_llm (LLM extrage codul)
    for r in results:
        if r["is_f3"] and not r.get("header_only") and not r.get("deviz_cod"):
            r["needs_llm"] = True

    # LLM batch pentru pagini cu needs_llm=True
    needs_llm_pages = [r for r in results if r.get("needs_llm")]
    if needs_llm_pages:
        logger.info(f"[PC] {len(needs_llm_pages)} pagini → LLM batch (clasificare + deviz_cod)")
        llm_results = _classify_pages_llm(needs_llm_pages, openai_client, deployment)
        for r in results:
            if r.get("needs_llm") and r["page_number"] in llm_results:
                llm = llm_results[r["page_number"]]
                r["is_f3"] = llm["is_f3"]
                r["needs_llm"] = False
                if r["is_f3"] and llm["deviz_cod"]:
                    r["deviz_cod"] = llm["deviz_cod"]
                    r["deviz_den"] = ""  # LLM nu returnează denumirea

    # Clear remaining needs_llm flags (pagini fără răspuns LLM → fallback nemodificat)
    for r in results:
        if r.get("needs_llm"):
            r["needs_llm"] = False

    # Gardă zero-F3
    f3_count = sum(1 for r in results if r["is_f3"])
    if f3_count == 0:
        logger.warning("[PC] zero F3 pages found in document — extracție va returna []")

    logger.info(f"[PC] Clasificare completă: {f3_count}/{len(results)} pagini F3")
    return results
