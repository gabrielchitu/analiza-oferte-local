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
from datetime import datetime
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── Semnale F3 ────────────────────────────────────────────────────────────────

# "STADIUL FIZIC: oferta 226108 STRUCTURA..." sau "STADIU FIZIC: ..."
_STADIUL_FIZIC_RE = re.compile(
    r'STADIU[L]?\s+FIZIC\s*:\s*(.+)',
    re.IGNORECASE
)
# Marker pentru STADIUL FIZIC singur pe linie (continutul devizului e pe linia urmatoare)
_STADIUL_FIZIC_MARKER_RE = re.compile(r'STADIU[L]?\s+FIZIC\s*:\s*$', re.IGNORECASE)

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

# eDevize/ISDP cover page: "Stadiul fizic: [NNN] [oferta] XXXXXX NAME"
# Suporta formate:
#   eDevize: "Stadiul fizic: 001 226108 STRUCTURA"  (NNN = numar capitol)
#   ISDP:    "STADIUL FIZIC:\noferta 226108 STRUCTURA"  (oferta keyword)
#   ISDP:    "STADIUL FIZIC: oferta 226108 STRUCTURA"   (pe aceeasi linie)
# Lookahead (?=...\d{4}) garanteaza ca deviz_cod contine >= 4 cifre,
# eliminand capturarea gresita a cuvantului 'oferta' (0 cifre) ca cod.
_STADIUL_FIZIC_EDEVIZE_RE = re.compile(
    r'Stadiul\s+fizic\s*:\s*(?:oferta\s+)?(?:\d{1,3}\s+)?'
    r'((?=[A-Z0-9]*\d{3})[A-Z0-9]{5,8})\s+(.*)',
    re.IGNORECASE
)
# Nota: \d{3} in loc de \d{4} — coduri ca 226U08 au '226' (3 cifre) + 'U' + '08',
# deci nu satisfac \d{4}. Codurile scurte (001, 008) sunt excluse prin {5,8} chars.

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
# Examples: VA02B08, CA01J1, ACA10B1, TSC02D11, CD05B1, CE05E1, L1C25A1, W2F05C01, etc.
# Matches: 2-5 letters + 1-4 digits + optional letter + 0-2 digits
# Also matches single-letter codes: L + digit + letters + digits (e.g., L1C25A1, W2F05C01)
_ARTICLE_CODE_RE = re.compile(r'\b(?:[A-Z]{2,5}\d{1,4}[A-Z]?\d{0,2}|[A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2})\b')

# Tier 1: Explicit "Deviz Oferta XXXX" — highest priority
# Patterns: "Deviz oferta 226238", "Deviz Oferta 226238", "Deviz oferta 226U38"
_DEVIZ_OFERTA_RE = re.compile(
    r'Deviz\s+[Oo]ferta\s+([A-Z0-9]{5,8})',
    re.IGNORECASE
)

# Tier 2a: Extract Obiectul (Object/Section number)
# Patterns: "Obiectul: 4.1 Cladire camin", "Obiectul: 0002 VESTIAR TEREN"
# Captures: (number, description)
_OBIECTUL_RE = re.compile(
    r'Obiectul\s*:\s*([0-9.]+)\s*(.+?)(?=\n|Categoria|Stadiul|$)',
    re.IGNORECASE
)

# Tier 2b: Extract Categoria de lucrari / Stadiul fizic
# Patterns: "Categoria de lucrari: 03 Arhitectura", "Stadiul fizic: 1 Lucrari", "Stadiul fizic: 0120 VESTIAR"
# Captures: (category_number, description)
# Note: Accepts 1-4 digit codes (01, 1, 03, 0120, etc.)
_CATEGORIA_RE = re.compile(
    r'(?:Categoria\s+de\s+lucrari|Stadiul\s+fizic)\s*:\s*([0-9]{1,4})\s*(.+?)(?=\n|Lista|OBSE|$)',
    re.IGNORECASE
)

# Text-optional variants — numeric prefix is optional (0 or more digits)
# Used in Phase 1 grouping key extraction for documents without numeric codes (e.g., offers)
_OBIECTUL_OPT_RE = re.compile(
    r'Obiectul\s*:\s*([0-9.]*)\s*(.+?)(?=Categoria|Stadiul|Beneficiar|Nr\.|Lista|\n|$)',
    re.IGNORECASE
)
_CATEGORIA_OPT_RE = re.compile(
    r'(?:Categoria\s+de\s+lucrari|Stadiul\s+fizic)\s*:\s*([0-9]{0,4})\s*(.+?)'
    r'(?=Beneficiar|Nr\.|Lista|OBSE|Executant|Proiectant|Formular|e\s+Devize|\n|$)',
    re.IGNORECASE
)

# NOTĂ: nu defini _DEVIZ_COD_RE — neutilizat, dead code


def _extract_lines(page: dict) -> list[str]:
    return [l.get("content", "") for l in page.get("lines", [])]


def _has_article_codes(full_content: str) -> bool:
    """Check if page contains article codes (e.g. VA02B08, VA03K02, L1C25A1, $2911).
    Used to distinguish between pure header pages and pages with data."""
    # Check for normative/single-letter codes
    if _ARTICLE_CODE_RE.search(full_content):
        return True
    # Check for breviar codes ($XXXX format)
    if re.search(r'\$[A-Z0-9]{4,8}', full_content):
        return True
    return False


def _extract_deviz_from_stadiul_fizic(text: str) -> tuple[str, str]:
    """Din 'STADIUL FIZIC: oferta 226108 STRUCTURA CUPOLA' or 'Stadiul fizic: 001 1.1 ARHITECTURA' (eDevize with sub-codes)."""
    text = text.strip()

    # Pattern 1: Extract short sub-codes like "1.1", "1.2", "2.3" that appear after main code
    # Format: "001 1.1 ARHITECTURA" or "002 1.2 INSTALATII" → extract "1.1" or "1.2"
    m = re.search(r'^\d{1,3}\s+([0-9]\.[0-9])\s+', text, re.IGNORECASE)
    if m:
        deviz_cod = m.group(1)  # Extract "1.1", "1.2", etc.
        # Get description after the sub-code
        rest = re.sub(r'^\d{1,3}\s+[0-9]\.[0-9]\s+', '', text).strip()
        return deviz_cod, rest

    # Pattern 2: Direct format (no main code) — "1.1 ARHITECTURA"
    m = re.match(r'([0-9]\.[0-9])\s+(.*)', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2).strip()

    # Pattern 3: Fallback to original logic for other formats (eDevize with 6-digit codes)
    # Elimina 'oferta' prefix dacă există (ISDP format)
    text = re.sub(r'^(?:oferta\s+)?', '', text.strip(), flags=re.IGNORECASE)
    # Pentru eDevize, elimina prefixul numeric NNN (ex: "001 226108 STRUCTURA" → "226108 STRUCTURA")
    text = re.sub(r'^\d{1,3}\s+', '', text.strip())
    # Cauta codul (primul token de 5-8 alfanumerice care contine cel putin o cifra)
    # Evita matching de cuvinte pure (ex: "DINTRE") prin cerinta de cel putin una cifra
    m = re.match(r'((?=.*\d)[A-Z0-9]{5,8})\s*(.*)', text, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).strip()

    return "", text.strip()


def _extract_compound_deviz(lines: list[str]) -> tuple[str, dict]:
    """
    Extract deviz code using three-tier priority:
    1. Explicit "Deviz Oferta XXXX" (highest priority)
    2. Compound: "Obiectul" + "Categoria de lucrari" → "X.X-YY"
    3. Empty fallback (use inheritance or existing logic)

    Args:
        lines: List of page line content strings

    Returns:
        Tuple of (deviz_cod, extraction_metadata)
        Where deviz_cod is "" if no code found
        And extraction_metadata contains:
            - extraction_method: "explicit" | "compound" | "none"
            - obiectul: {"number": str, "description": str} or None
            - categoria: {"number": str, "description": str} or None
    """
    full_content = " ".join(lines)

    # Tier 1: Check for explicit "Deviz Oferta" (highest priority)
    m = _DEVIZ_OFERTA_RE.search(full_content)
    if m:
        cod = m.group(1).upper()
        return cod, {
            "extraction_method": "explicit",
            "source": "Deviz Oferta",
            "obiectul": None,
            "categoria": None
        }

    # Tier 2: Try compound extraction from Obiectul + Categoria
    m_obj = _OBIECTUL_RE.search(full_content)
    m_cat = _CATEGORIA_RE.search(full_content)

    if m_obj and m_cat:
        obj_num = m_obj.group(1).strip()
        obj_desc = m_obj.group(2).strip() if m_obj.group(2) else ""
        cat_num = m_cat.group(1).strip()
        cat_desc = m_cat.group(2).strip() if m_cat.group(2) else ""

        # Construct compound code
        deviz_cod = f"{obj_num}-{cat_num}"

        return deviz_cod, {
            "extraction_method": "compound",
            "source": "Obiectul-Categoria",
            "obiectul": {
                "number": obj_num,
                "description": obj_desc
            },
            "categoria": {
                "number": cat_num,
                "description": cat_desc
            }
        }

    # Tier 3: Fallback — no compound code found
    return "", {
        "extraction_method": "none",
        "source": None,
        "obiectul": None,
        "categoria": None
    }


def _extract_deviz_name_from_formular_f3(full_content: str) -> str:
    """Extrage denumirea devizului din pagina Formular F3.

    Cautare patterns:
    1. "Deviz oferta 226208 STRUCTURA DE..." → extrage STRUCTURA DE...
    2. "Obiectul : NNNN STRUCTURA DE..." → extrage STRUCTURA DE...

    Fallback: gol dacă nu gasit
    """
    # Pattern 1: "Deviz oferta NNNNNN STRUCTURED_NAME" (up to "Categoria" or "Lista")
    # Uses greedy match (.+?) with positive lookahead
    m = re.search(r'Deviz\s+oferta\s+\d{5,8}\s+(.+?)(?=\s+(?:Categ|Lista))', full_content, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    # Pattern 2: "Obiectul : NNNN STRUCTURED_NAME"
    m = re.search(r'Obiectul\s*:\s*\d+\s+(.+?)(?=\s+(?:Categ|Lista))', full_content, re.IGNORECASE)
    if m:
        return m.group(1).strip()

    return ""


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

    # ── Verifică Recapitulatia în tot conținutul paginii ──
    # O pagina de sumar (fara coduri articol) → NON_F3.
    # O pagina cu articole SI Recapitulatia la final (ultima pagina deviz) → tratata ca F3.
    if _RECAPITULATIE_RE.search(full_content) and not _has_article_codes(full_content):
        return {"label": "NON_F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică pagini sumar cu TOTAL GENERAL (fara articole) → NON_F3 ──
    # Pagini ca "TOTAL GENERAL (fara TVA) / 569,207.79 / TVA..." sunt sumare de deviz,
    # nu pagini de date F3. Detectam prezenta in primele ~200 chars.
    if 'TOTAL GENERAL' in full_content[:200] and not _has_article_codes(full_content):
        return {"label": "NON_F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică STADIUL FIZIC — fereastra de 8 linii ──
    # OCR poate intercala linii extra (ex: 'Beneficiar:') intre 'STADIUL FIZIC:'
    # si codul deviz. Cautam codul in urmatoarele 8 linii dupa marker.
    # Suporta atat coduri lungi (226108) cat si sub-coduri (1.1, 2.1, etc.)
    _DEVIZ_COD_IN_LINE_RE = re.compile(
        r'(?:oferta\s+)?(?:\d{1,3}\s+)?((?=[A-Z0-9]*\d{3})[A-Z0-9]{5,8})',
        re.IGNORECASE
    )
    # Sub-code pattern for eDevize: "001 1.1 ARHITECTURA" or "1.1 ARHITECTURA"
    _SUB_CODE_RE = re.compile(r'^\d{1,3}\s+([0-9]\.[0-9])\s+|^([0-9]\.[0-9])\s+')
    for i, line in enumerate(lines):
        m_sf = _STADIUL_FIZIC_RE.match(line.strip())
        m_sf_marker = _STADIUL_FIZIC_MARKER_RE.match(line.strip())
        if m_sf or m_sf_marker:
            # Incearca pe aceeasi linie (continut direct dupa ":")
            cod, den = ("", "")
            if m_sf:
                cod, den = _extract_deviz_from_stadiul_fizic(m_sf.group(1))
            if not cod:
                # Cauta codul in fereastra de 8 linii urmatoare (OCR poate intercala junk)
                for j in range(i + 1, min(i + 8, len(lines))):
                    # First try sub-code pattern (for eDevize with main+sub codes)
                    m_sub = _SUB_CODE_RE.search(lines[j].strip())
                    if m_sub:
                        # Extract sub-code (group 1 or 2 depending on which alternative matched)
                        cod = m_sub.group(1) or m_sub.group(2)
                        # Extract description after the sub-code
                        rest = re.sub(r'^\d{1,3}\s+[0-9]\.[0-9]\s+|^[0-9]\.[0-9]\s+', '', lines[j].strip())
                        den = rest if rest else ""
                        break
                    # Then try long alphanumeric codes (for standard eDevize 226XXX)
                    m2 = _DEVIZ_COD_IN_LINE_RE.search(lines[j])
                    if m2:
                        cod = m2.group(1).upper()
                        den = ""
                        break
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

    # ── Verifică SECTIUNEA TEHNICA (eDevize data pages) ──
    # TREBUIE sa fie INAINTE de FORMULAR_F3: footer-ul eDevize contine
    # 'Deviz "001" - Formular F3' care ar extrage gresit "001" ca deviz_cod.
    # BUT: Pages with "SECTIUNEA TEHNICA" AND article codes should NOT match here
    # (those are data pages, not just headers). Continue to extract deviz from footer.
    if _SECTIUNEA_TEHNICA_RE.search(full_content) and not _has_article_codes(full_content):
        return {"label": "F3", "deviz_cod": "", "deviz_den": "", "is_header": False}

    # ── Verifică Formularul F3 (standard format) ──
    if _FORMULAR_F3_RE.search(full_content):
        # Try compound extraction first (if not already extracted)
        compound_cod, compound_meta = _extract_compound_deviz(lines)
        if compound_cod and compound_meta["extraction_method"] == "compound":
            # Use compound code and store metadata
            den = ""
            if compound_meta.get("categoria"):
                den = compound_meta["categoria"].get("description", "")
            return {
                "label": "F3",
                "deviz_cod": compound_cod,
                "deviz_den": den,
                "is_header": False,
                "extraction_method": "compound",
                "metadata": compound_meta
            }

        # Extrage codul deviz din context (număr înainte de "Formularul F3")
        m = re.search(r'(\d{5,8})\s+pag\s+\d+\s+Formular', full_content, re.IGNORECASE)
        if not m:
            # Fallback: 'Deviz "226208" - Formular F3' or 'Deviz "1.1"' (eDevize format)
            # Accepta coduri de 1-8 caractere (cifre, litere, puncte): "001", "1.1", "226108" etc.
            # BUT: Only extract if this is an eDevize cover page with STADIUL FIZIC/article codes
            # Pages without STADIUL FIZIC should return empty deviz to inherit from predecessor.
            m = re.search(r'Deviz\s+"([A-Z0-9.]{1,8})"', full_content, re.IGNORECASE)
            # If we found "Deviz "XXX"" but this page lacks STADIUL FIZIC, don't use it
            # (let propagation inherit from cover page)
            if m:
                has_stadiul = any("STADIUL" in line.upper() for line in lines)
                if not has_stadiul and _has_article_codes(full_content):
                    # This is an eDevize data page without its own STADIUL FIZIC
                    # Return empty deviz so propagation can inherit from cover page
                    m = None
        if not m:
            # Fallback: "Deviz oferta 226108 STRUCTURA..." (Design Studio / format standard)
            m = re.search(r'Deviz\s+oferta\s+([A-Z0-9]{5,8})', full_content, re.IGNORECASE)
        cod = m.group(1) if m else ""
        den = _extract_deviz_name_from_formular_f3(full_content)
        # Daca nu s-a putut extrage codul deviz SI pagina nu are articole
        # → e o pagina de semnatura/footer eDevize (ex: "Deviz '008' - Formular F3"),
        # nu o pagina de date F3. O clasificam NON_F3 pentru a evita extragerea
        # de articole cu deviz="" care devin false EXTRA.
        if not cod and not _has_article_codes(full_content):
            return {"label": "NON_F3", "deviz_cod": "", "deviz_den": "", "is_header": False}
        return {"label": "F3", "deviz_cod": cod, "deviz_den": den, "is_header": False, "extraction_method": "explicit"}

    # ── Verifică eDevize continuation pages (>>> componenta NNN format) ──
    # These are data continuation pages from eDevize documents that contain articles
    # but lack standard F3 headers. Example: "226228 pag >>> componenta 010 035 SD05A1 BUC..."
    if _EDEVIZE_CONTINUATION_RE.search(full_content) and _has_article_codes(full_content):
        # Extract deviz code from page (format: "226228 pag" or similar)
        m = re.search(r'\b(\d{6})\s+pag', full_content, re.IGNORECASE)
        cod = m.group(1) if m else ""
        return {"label": "F3", "deviz_cod": cod, "deviz_den": "", "is_header": False}

    # ── Verifică continuation pages cu pattern "NNNN pag" (zonder >>> marker) ──
    # Pages like "226U08 pag 170 011 TSD04D1..." sau "226358 pag 079..."
    # These have deviz code marker at start of page (first ~150 chars).
    # NOTA: garda _has_article_codes() e ELIMINATA intentionat — paginile cu
    # articole numerice pure ($6716997 etc.) nu contin coduri alfanumerice, deci
    # _has_article_codes() returna False si pagina era clasificata gresit AMBIGUOUS.
    # Prezenta "NNNNNN pag" in primele 150 chars e suficient de specifica.
    m = re.search(r'\b([A-Z0-9]{6})\s+pag\b', full_content, re.IGNORECASE)
    if m:
        pos = m.start()
        content_before = full_content[:pos]
        # Pattern should appear early (within ~150 chars = ~3-4 lines)
        if len(content_before) < 150:
            cod = m.group(1)
            return {"label": "F3", "deviz_cod": cod, "deviz_den": "", "is_header": False}

    return {"label": "AMBIGUOUS", "deviz_cod": "", "deviz_den": "", "is_header": False}


def _build_deviz_checkpoint(results: list[dict], document_type: str, source_path: str) -> dict:
    """
    Build deviz checkpoint mapping from page classification results.

    Args:
        results: List of page classification results from build_page_classifications()
        document_type: "reference" or "offer"
        source_path: Original DI JSON path (for logging)

    Returns:
        Checkpoint dict with metadata and deviz_groups
    """
    deviz_groups = {}

    # Aggregate all deviz codes encountered
    for pc in results:
        if not pc.get("is_f3"):
            continue

        deviz_cod = pc.get("deviz_cod", "")
        if not deviz_cod:
            continue

        if deviz_cod not in deviz_groups:
            deviz_groups[deviz_cod] = {
                "deviz_cod": deviz_cod,
                "extraction_method": pc.get("extraction_method", "unknown"),
                "metadata": pc.get("metadata", {}),
                "article_count": 0,
                "pages": []
            }

        page_num = pc.get("page_number", 0)
        if page_num not in deviz_groups[deviz_cod]["pages"]:
            deviz_groups[deviz_cod]["pages"].append(page_num)

    # Count articles per deviz (will be updated after extraction)
    # For now, just track that the deviz exists

    checkpoint = {
        "metadata": {
            "source": source_path,
            "document_type": document_type,
            "extracted_at": datetime.utcnow().isoformat() + "Z",
            "classifier_version": "local"
        },
        "deviz_groups": list(deviz_groups.values()),
        "validation": {
            "total_articles": 0,
            "total_pages_with_deviz": len([p for p in results if p.get("deviz_cod")]),
            "coverage": "100%"
        }
    }

    return checkpoint


def build_page_classifications(pages: list[dict]) -> tuple[list[dict], dict]:
    """
    Clasifică toate paginile unui document și propagă devizul (eDevize format).

    Returns: tuple of (results, checkpoint)
        results: list[dict] cu câmpuri:
            page_number, is_f3, deviz_cod, deviz_den, lines, needs_llm
        checkpoint: dict with deviz mapping and metadata
    """
    results = []
    current_deviz_cod = ""
    current_deviz_den = ""

    for page in pages:
        lines = _extract_lines(page)
        page_number = page.get("page_number", 0)
        local = classify_page_local(page)

        if local["label"] == "NON_F3":
            # Keep current deviz — non-F3 pages (cover, summary, etc.) don't reset deviz context.
            # Following F3 pages in same deviz can inherit the deviz code.
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

    # Build and return checkpoint data alongside results
    # (checkpoint will be saved by caller)
    checkpoint = _build_deviz_checkpoint(results, "reference", "")
    return results, checkpoint


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
) -> tuple[list[dict], dict]:
    """
    Pipeline complet de clasificare pagini.

    1. Clasificare locală + propagare deviz (build_page_classifications)
       Paginile F3 fără deviz_cod (regex nu a găsit) sunt marcate needs_llm=True.
    2. LLM batch pentru toate paginile cu needs_llm=True:
       — clasifică (AMBIGUOUS → F3/NON_F3)
       — extrage deviz_cod pentru orice format, indiferent de soft
    3. Gardă zero-F3 (warning dacă niciuna nu e F3)

    Returns: tuple of (results, checkpoint)
        results: list[dict] cu is_f3, deviz_cod, deviz_den, lines, page_number
        checkpoint: dict with deviz mapping and metadata
    """
    results, checkpoint = build_page_classifications(pages)

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
    return results, checkpoint
