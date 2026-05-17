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
    """
    Extract deviz code from STADIUL FIZIC line.

    Supports multiple formats:
    - eDevize with sub-codes: "001 1.1 ARHITECTURA"
    - Text denomination: "Terasam desf conexe tip II"
    - Simple text: "Arhitectura", "Instalatii termice"

    Uses deviz_catalog to map text denominations to numeric codes.
    """
    from shared.deviz_catalog import find_deviz_for_text, extract_stadiul_fizic

    text = text.strip()
    if not text:
        return "", ""

    # Pattern 1: eDevize format with sub-codes like "1.1", "1.2"
    # Format: "001 1.1 ARHITECTURA" or "002 1.2 INSTALATII"
    m = re.search(r'^\d{1,3}\s+([0-9]\.[0-9])\s+', text, re.IGNORECASE)
    if m:
        deviz_cod = m.group(1)  # Extract "1.1", "1.2", etc.
        rest = re.sub(r'^\d{1,3}\s+[0-9]\.[0-9]\s+', '', text).strip()
        return deviz_cod, rest

    # Pattern 2: Direct eDevize format (no main code) — "1.1 ARHITECTURA"
    m = re.match(r'([0-9]\.[0-9])\s+(.*)', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2).strip()

    # Pattern 3: TRY DEVIZ CATALOG FIRST
    # Extract numeric deviz code from text using catalog (handles "Ins electrice", "Instalatii termice", etc.)
    numeric_code = find_deviz_for_text(text)
    if numeric_code:
        return numeric_code, text  # Return the numeric code and original text as denomination

    # Pattern 4: Fallback to original logic for other formats (eDevize with 6-digit codes)
    text_normalized = re.sub(r'^(?:oferta\s+)?', '', text.strip(), flags=re.IGNORECASE)
    text_normalized = re.sub(r'^\d{1,3}\s+', '', text_normalized.strip())

    m = re.match(r'((?=.*\d)[A-Z0-9]{5,8})\s*(.*)', text_normalized, re.IGNORECASE)
    if m:
        return m.group(1).upper(), m.group(2).strip()

    # If nothing matches but text exists, still return it (might be useful for denomination)
    return "", text.strip()


def _non_f3() -> dict:
    """Helper: return a canonical NON_F3 result."""
    return {
        "label": "NON_F3",
        "deviz_cod": "",
        "deviz_den": "",
        "is_header": False,
        "extraction_method": "none",
        "obiectul": None,
        "categoria": None,
    }


def _extract_grouping_key(lines: list[str]) -> dict:
    """
    Extract the grouping key for a page's deviz section.

    Priority:
    1. Explicit 'Deviz Oferta XXXXX' (5-8 chars) → 'explicit'
    2. Obiectul (numeric) + Categoria/Stadiul (numeric) → 'compound', deviz_cod='X.Y-NN'
    3. Obiectul (text) + Categoria/Stadiul (text), both present → 'partial'
       deviz_cod = provisional sentinel '__partial__:{obj_text[:40]}:{cat_text[:40]}'
    4. Nothing extractable → 'none', deviz_cod=''

    Returns:
        {
          'method': 'explicit'|'compound'|'partial'|'none',
          'deviz_cod': str,       # compound/explicit: real key; partial: sentinel; none: ''
          'obiectul':  {'num': str, 'text': str} | None,
          'categoria': {'num': str, 'text': str} | None,
        }
    """
    full = " ".join(lines)

    # Priority 1: Explicit 'Deviz Oferta XXXXX' (5-8 alphanum chars)
    m = _DEVIZ_OFERTA_RE.search(full)
    if m:
        return {
            "method": "explicit",
            "deviz_cod": m.group(1).upper(),
            "obiectul": None,
            "categoria": None,
        }

    # Priority 2 + 3: Try Obiectul + Categoria with optional numeric prefix
    m_obj = _OBIECTUL_OPT_RE.search(full)
    m_cat = _CATEGORIA_OPT_RE.search(full)

    obj_num = m_obj.group(1).strip() if m_obj else ""
    obj_text = m_obj.group(2).strip() if m_obj else ""
    cat_num = m_cat.group(1).strip() if m_cat else ""
    cat_text = m_cat.group(2).strip() if m_cat else ""

    # Both numeric parts present → compound key
    if obj_num and cat_num:
        deviz_cod = f"{obj_num}-{cat_num}"
        return {
            "method": "compound",
            "deviz_cod": deviz_cod,
            "obiectul": {"num": obj_num, "text": obj_text},
            "categoria": {"num": cat_num, "text": cat_text},
        }

    # Both text parts present (at least) but numeric missing → partial
    if obj_text or cat_text:
        sentinel = f"__partial__{obj_text[:40]}:{cat_text[:40]}"
        return {
            "method": "partial",
            "deviz_cod": sentinel,
            "obiectul": {"num": obj_num, "text": obj_text},
            "categoria": {"num": cat_num, "text": cat_text},
        }

    # Nothing useful
    return {
        "method": "none",
        "deviz_cod": "",
        "obiectul": None,
        "categoria": None,
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
    Classify a DI JSON page without LLM. Two-phase algorithm:
    Phase A: Fast non-F3 detection
    Phase B: F3 detection and grouping key extraction

    Returns:
        {
          "label": "F3" | "NON_F3" | "AMBIGUOUS",
          "deviz_cod": str,        # compound, explicit, partial sentinel, or ''
          "deviz_den": str,
          "is_header": bool,
          "extraction_method": str,  # 'compound'|'explicit'|'partial'|'none'
          "obiectul": dict | None,   # {'num': str, 'text': str}
          "categoria": dict | None,
        }
    """
    lines = _extract_lines(page)
    if not lines:
        return {
            "label": "AMBIGUOUS",
            "deviz_cod": "",
            "deviz_den": "",
            "is_header": False,
            "extraction_method": "none",
            "obiectul": None,
            "categoria": None,
        }

    full = " ".join(lines)

    # ── Phase A: NON_F3 detection (fast early exits) ──────────────────────────

    for pat in _NON_F3_PATTERNS:
        if pat.search(full):
            return _non_f3()

    # Summary pages without article codes
    if _RECAPITULATIE_RE.search(full) and not _has_article_codes(full):
        return _non_f3()

    if "TOTAL GENERAL" in full[:200] and not _has_article_codes(full):
        return _non_f3()

    # ── Phase B: F3 detection ─────────────────────────────────────────────────

    is_f3 = False
    is_header = False

    # B1: explicit F3 markers
    if _FORMULAR_F3_RE.search(full) or _SECTIUNEA_TEHNICA_RE.search(full):
        is_f3 = True

    # B2: STADIUL FIZIC (any form) — detection only, not code extraction
    if not is_f3:
        if _STADIUL_FIZIC_RE.search(full) or _STADIUL_FIZIC_MARKER_RE.search("\n".join(lines)):
            is_f3 = True

    # B3: eDevize continuation pages (>>> componenta + article codes)
    if not is_f3:
        if _EDEVIZE_CONTINUATION_RE.search(full) and _has_article_codes(full):
            is_f3 = True

    # B4: eDevize paged format ('XXXXXX pag' in first 150 chars)
    if not is_f3:
        m = re.search(r"\b([A-Z0-9]{6})\s+pag\b", full, re.IGNORECASE)
        if m and m.start() < 150:
            is_f3 = True

    # B5: eDevize cover page (Stadiul fizic: [optional prefix] CODE DESCRIPTION)
    if not is_f3:
        m = _STADIUL_FIZIC_EDEVIZE_RE.search(full)
        if m:
            is_f3 = True
            is_header = not _has_article_codes(full)

    if not is_f3:
        return {
            "label": "AMBIGUOUS",
            "deviz_cod": "",
            "deviz_den": "",
            "is_header": False,
            "extraction_method": "none",
            "obiectul": None,
            "categoria": None,
        }

    # ── Phase C: Grouping key extraction (same logic for ALL F3 pages) ────────

    key = _extract_grouping_key(lines)

    # Special guard: Formular F3 with no key AND no article codes
    # = eDevize signature/footer page (e.g., 'Deviz "07" - Formular F3')
    if key["method"] == "none" and not _has_article_codes(full):
        return _non_f3()

    deviz_den = ""
    if key.get("categoria"):
        deviz_den = key["categoria"].get("text", "")
    elif key.get("obiectul"):
        deviz_den = key["obiectul"].get("text", "")

    return {
        "label": "F3",
        "deviz_cod": key["deviz_cod"],
        "deviz_den": deviz_den,
        "is_header": is_header,
        "extraction_method": key["method"],
        "obiectul": key.get("obiectul"),
        "categoria": key.get("categoria"),
    }


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
                # Enrich with obiectul/categoria if available (first page in group sets it)
                "obiectul": pc.get("obiectul"),
                "categoria": pc.get("categoria"),
                "article_count": 0,
                "pages": [],
            }
        else:
            # Later pages in same group: fill in missing obiectul/categoria if available
            grp = deviz_groups[deviz_cod]
            if not grp.get("obiectul") and pc.get("obiectul"):
                grp["obiectul"] = pc["obiectul"]
            if not grp.get("categoria") and pc.get("categoria"):
                grp["categoria"] = pc["categoria"]

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


def build_page_classifications(
    pages: list[dict],
    document_type: str = "unknown",
    source_path: str = "",
) -> tuple[list[dict], dict]:
    """
    Classify all pages and propagate deviz codes.
    Partial sentinel keys are propagated during this phase;
    LLM resolution (Phase 2) replaces them with compound keys.

    Returns: tuple of (results, checkpoint)
        results: list[dict] cu câmpuri:
            page_number, is_f3, deviz_cod, deviz_den, lines, needs_llm,
            extraction_method, obiectul, categoria
        checkpoint: dict with deviz mapping and metadata
    """
    results = []
    current_deviz_cod = ""
    current_deviz_den = ""

    for page in pages:
        lines = _extract_lines(page)
        page_number = page.get("page_number", 0)
        local = classify_page_local(page)

        base = {
            "page_number": page_number,
            "lines": lines,
            "needs_llm": False,
            "header_only": False,
            # Propagate metadata for checkpoint enrichment
            "extraction_method": local.get("extraction_method", "none"),
            "obiectul": local.get("obiectul"),
            "categoria": local.get("categoria"),
        }

        if local["label"] == "NON_F3":
            # Keep current deviz — non-F3 pages (cover, summary, etc.) don't reset deviz context.
            # Following F3 pages in same deviz can inherit the deviz code.
            results.append({**base, "is_f3": False, "deviz_cod": "", "deviz_den": ""})

        elif local["label"] == "F3":
            if local["deviz_cod"]:
                # Pagina are deviz propriu (STADIUL FIZIC explicit, Formularul F3 cu cod, header eDevize)
                current_deviz_cod = local["deviz_cod"]
                current_deviz_den = local["deviz_den"]
            # else: SECTIUNEA TEHNICA fără cod → folosește devizul propagat

            if local.get("is_header"):
                # Pagina de header nu conține articole — nu o transmitem extractor-ului
                results.append({
                    **base,
                    "is_f3": True,
                    "deviz_cod": current_deviz_cod,
                    "deviz_den": current_deviz_den,
                    "header_only": True,
                })
            else:
                # Pagina F3 data: dacă nu are deviz (orfană), trimite la LLM
                needs_llm = not current_deviz_cod
                results.append({
                    **base,
                    "is_f3": True,
                    "deviz_cod": current_deviz_cod,
                    "deviz_den": current_deviz_den,
                    "needs_llm": needs_llm,
                })

        else:  # AMBIGUOUS
            # Pagina ambiguă → trimitem la LLM
            # Reset propagare — nu știm ce urmează
            results.append({
                **base,
                "is_f3": False,  # default, LLM poate schimba
                "deviz_cod": current_deviz_cod,
                "deviz_den": current_deviz_den,
                "needs_llm": True,
            })
            current_deviz_cod = ""
            current_deviz_den = ""

    # Build and return checkpoint data alongside results
    # (checkpoint will be saved by caller)
    checkpoint = _build_deviz_checkpoint(results, document_type, source_path)
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


def _resolve_partial_keys_with_llm(
    page_classes: list[dict],
    ref_deviz_groups: list[dict],
    openai_client,
    deployment: str,
) -> list[dict]:
    """
    Rezolvă "__partial__" sentinele prin potrivire LLM.

    Pentru fiecare pagină cu deviz_cod = "__partial__:{obj_text}:{cat_text}":
    - Colectează perechile unice (obj_text, cat_text)
    - Trimite la LLM cu lista devizurilor de referință
    - LLM încearcă să potrivească textele cu devizurile existente
    - Înlocuiește sentinelele cu codurile rezolvate

    Args:
        page_classes: list[dict] cu paginile clasificate
        ref_deviz_groups: list[dict] cu deviz_groups din checkpoint-ul referinței
        openai_client: Anthropic client
        deployment: Model ID

    Returns:
        list[dict] cu page_classes actualizate (sentinele înlocuite cu coduri rezolvate)
    """
    # Colectează pagini cu partial keys
    partial_pages = [
        p for p in page_classes
        if p.get("deviz_cod", "").startswith("__partial__")
    ]

    if not partial_pages:
        return page_classes

    # Colectează perechile unice (obj_text, cat_text) din partial keys
    unique_pairs = {}
    for p in partial_pages:
        obj = p.get("obiectul", {}) or {}
        cat = p.get("categoria", {}) or {}
        obj_text = obj.get("text", "")
        cat_text = cat.get("text", "")

        # Create key for deduplication
        pair_key = (obj_text, cat_text)
        if pair_key not in unique_pairs:
            unique_pairs[pair_key] = {"obiectul": obj_text, "categoria": cat_text}

    logger.info(
        f"[LLM-PARTIAL] {len(unique_pairs)} unique (obiectul, categoria) pairs → LLM resolution"
    )

    # Build reference deviz groups for LLM context
    ref_groups_for_llm = []
    for grp in ref_deviz_groups:
        obj_dict = grp.get("obiectul") or {}
        cat_dict = grp.get("categoria") or {}
        ref_groups_for_llm.append({
            "deviz_cod": grp.get("deviz_cod", ""),
            "extraction_method": grp.get("extraction_method", ""),
            "obiectul": obj_dict.get("text", ""),
            "categoria": cat_dict.get("text", ""),
        })

    # LLM system prompt for partial resolution
    system_prompt = """\
You are matching construction work section descriptions from an offer document to reference section codes.
The reference uses compound codes like "4.1-03" or explicit codes like "226348".
The offer uses plain text without numeric prefixes.

For each offer (obiectul, categoria) pair, find the best matching reference deviz_cod by semantic similarity.
Match on key terms (architect work, electrical work, plumbing, etc.) and context clues.
If multiple references match, prefer the most specific.
If no reasonable match exists, return "NONE".

Return ONLY valid JSON with no other text:
{"matches": [{"obiectul": "...", "categoria": "...", "deviz_cod": "4.1-03"}, ...]}

Each input pair must appear exactly once in the output."""

    # Build LLM payload
    user_payload = {
        "reference_deviz_groups": ref_groups_for_llm,
        "offer_pairs_to_match": list(unique_pairs.values()),
    }

    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
            ],
            max_tokens=2000,
        )
        raw = json.loads(resp.choices[0].message.content)
        matches = raw.get("matches", [])

        # Build mapping: (obj_text, cat_text) → deviz_cod
        match_map = {}
        for m in matches:
            key = (m.get("obiectul", ""), m.get("categoria", ""))
            deviz_cod = m.get("deviz_cod", "NONE")
            match_map[key] = deviz_cod if deviz_cod != "NONE" else None

        logger.info(f"[LLM-PARTIAL] LLM resolved {len([x for x in match_map.values() if x])} / {len(unique_pairs)} pairs")

    except Exception as e:
        logger.warning(f"[LLM-PARTIAL] LLM resolution failed: {e} — using fallback")
        match_map = {}

    # Update page_classes: replace partial sentinels with resolved codes
    resolved_count = 0
    fallback_count = 0

    for p in page_classes:
        if not p.get("deviz_cod", "").startswith("__partial__"):
            continue

        obj = p.get("obiectul", {}) or {}
        cat = p.get("categoria", {}) or {}
        obj_text = obj.get("text", "")
        cat_text = cat.get("text", "")

        pair_key = (obj_text, cat_text)
        resolved_cod = match_map.get(pair_key)

        if resolved_cod:
            p["deviz_cod"] = resolved_cod
            p["extraction_method"] = "partial_resolved"
            resolved_count += 1
        else:
            # Fallback: use first word of categoria text, max 20 chars
            fallback = (cat_text.split()[0] if cat_text else obj_text.split()[0] if obj_text else "UNKNOWN")[:20]
            p["deviz_cod"] = fallback
            p["extraction_method"] = "partial_fallback"
            fallback_count += 1

    logger.info(
        f"[LLM-PARTIAL] Resolution complete: {resolved_count} LLM-matched, {fallback_count} fallback"
    )

    return page_classes


def _get_subcomponent_sample(results: list, pages: list) -> str:
    """
    Extract a sample of text containing subcomponents for format detection.

    Returns first 3 F3 pages' text concatenated.
    """
    f3_pages = [r for r in results if r.get("is_f3")][:3]
    if not f3_pages:
        return ""

    samples = []
    for page_info in f3_pages:
        page_num = page_info.get("page_number")
        for page in pages:
            if page.get("page_number") == page_num:
                lines = [l.get("content", "") for l in page.get("lines", [])]
                samples.append(" ".join(lines))
                break

    return " ".join(samples[:3])


def classify_pages(
    pages: list[dict],
    openai_client,
    deployment: str,
    document_type: str = "unknown",
    source_path: str = "",
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
    results, checkpoint = build_page_classifications(pages, document_type, source_path)

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

    # Detect subcomponent format (added to checkpoint for extraction phase)
    from shared.subcomponent_formats import detect_subcomponent_format
    subcomp_sample = _get_subcomponent_sample(results, pages)
    if subcomp_sample:
        subcomp_format = detect_subcomponent_format(subcomp_sample)
        checkpoint["subcomponent_format"] = {
            "format": subcomp_format["format"].value if subcomp_format["format"] else "unknown",
            "confidence": subcomp_format["confidence"],
            "name": subcomp_format.get("name", "unknown")
        }
        logger.info(f"[PC] Detected subcomponent format: {subcomp_format.get('name')} (confidence={subcomp_format['confidence']:.2f})")

    logger.info(f"[PC] Clasificare completă: {f3_count}/{len(results)} pagini F3")
    return results, checkpoint
