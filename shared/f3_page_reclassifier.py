"""
f3_page_reclassifier.py — Post-procesor determinist pentru re-clasificarea
paginilor F3 greșit clasificate de LLM.

Problemă: unele pagini cu conținut F3 real sunt clasificate is_f3=False
din cauza formatelor neobișnuite (pagini de tranziție, format eDevize
cu articole numerice pure, pagini fără marker STADIUL FIZIC etc.)

Soluție: scanare deterministă cu reguli de semnal F3, fără LLM.
Se apelează DUPĂ checkpoint și ÎNAINTE de extract_articles_v3.
Checkpoint-ul NU se modifică — reclasificarea e in-memory.

Public API:
    reclassify_non_f3_pages(page_classifications: list) -> list
"""
import re
import logging

logger = logging.getLogger(__name__)

# ── Constante ────────────────────────────────────────────────────────────────

# Coduri normative de articol: TSC35A22, CA02A1, VA02B08 (2-5L + 1-4D + opt)
_COD_NORM_RE = re.compile(r'\b[A-Z]{2,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?\b')

# Coduri numerice cu separator (breviar): "7000763 - BANDA", "3274584 - OTEL"
_COD_NUMERIC_SEP_RE = re.compile(r'\b\d{5,8}\s*[-–]')

# Cod deviz explicit în header: "226108 pag", "226U08 pag"
_DEVIZ_PAG_RE = re.compile(r'\b([A-Z0-9]{5,8})\s+pag\b', re.IGNORECASE)

# Cod deviz numeric direct: 226xxx
_COD_226_RE = re.compile(r'\b(226[A-Z0-9]{3})\b', re.IGNORECASE)

# Semnale F3 certe (indiferent de alte condiții)
_SECTIUNEA_TEHNICA_RE = re.compile(
    r'SECTIUNEA\s+TEHNICA.*SECTIUNEA\s+FINANCIARA|'
    r'Capitol\s+de\s+lucrari.*U\.?M\.?.*Cantitate',
    re.IGNORECASE | re.DOTALL
)
_EDEVIZE_COMPONENT_RE = re.compile(r'>>>\s*componenta', re.IGNORECASE)

# Markeri de sumar/consum financiar (pagini NON-F3 certe)
# Include Lista consumurilor de resurse care are acelasi format ca F3 dar NU e F3
_SUMAR_RE = re.compile(
    r'Total\s+cheltuieli\s+directe|TOTAL\s+GENERAL\s+DEVIZ|'
    r'Cheltuieli\s+indirecte|Centralizatorul\s+cheltuielilor|'
    r'LISTA\s+cuprinzand\s+consumurile|Recapitulatia\s+lucrarilor|'
    r'consum\s+de\s+manopera|consum\s+de\s+materiale|consum\s+de\s+utilaje|'
    r'Lista\s+consumurilor\s+de\s+resurse|CONSUMURI\s+DE\s+RESURSE|'
    r'Detaliere\s+transporturi|Nr\.\s+crt\.\s+Denumirea\s+resurselor',
    re.IGNORECASE
)

# UM valide (subset din f3_regex_parser.UM_KNOWN)
_UM_VALID = {
    'MP', 'MC', 'BUC', 'KG', 'TONA', 'ML', 'M', 'KM', 'L', 'ORE', 'ORA',
    'ZI', 'ZILE', 'BUC.', 'MP.', 'MC.', 'ML.', 'LEI', 'RON',
    '100 MP', '100 MC', '100 M',
}

# Cantitate: decimal cu separator sau întreg cu punct
_CANT_RE = re.compile(
    r'^\d{1,10}[.,]\d{1,6}$|'      # 18.144 sau 1,840.00
    r'^\d{1,10}[.,]\d{3}[.,]\d{1,3}$'  # 1.840,00
)

# Fereastra de căutare deviz în vecini
_WINDOW = 4

# Scor minim articole potențiale (cod + UM sau cantitate in proximity)
_MIN_SCORE = 1


# ── Funcții auxiliare ────────────────────────────────────────────────────────

def _has_f3_signal(lines: list) -> bool:
    """Semnal F3 cert (SECTIUNEA TEHNICA sau >>> componenta + cod)."""
    full = '\n'.join(lines)
    if _SECTIUNEA_TEHNICA_RE.search(full):
        return True
    if _EDEVIZE_COMPONENT_RE.search(full) and _COD_NORM_RE.search(full):
        return True
    return False


def _is_valid_um_line(line: str) -> bool:
    """Linia e un UM standalone valid."""
    t = re.sub(r'[\.\s]+', '', line.strip()).upper()
    if not t or re.search(r'\d', t):
        return False
    return t in {re.sub(r'[\.\s]+', '', u).upper() for u in _UM_VALID}


def _score_f3_content(lines: list) -> int:
    """
    Numără perechile (cod_articol + UM/cantitate) din pagină.
    Fiecare pereche confirmată înseamnă un articol F3 probabil.
    """
    n = len(lines)
    score = 0
    matched_positions = set()

    for i, line in enumerate(lines):
        s = line.strip()
        if not s:
            continue

        # Detectare cod (normativ sau numeric cu separator)
        is_cod = bool(_COD_NORM_RE.search(s)) or bool(_COD_NUMERIC_SEP_RE.search(s))
        if not is_cod:
            continue

        # Verifică fereastra [-2, +4] pentru UM sau cantitate
        window = range(max(0, i - 2), min(n, i + 5))
        for j in window:
            if j == i or j in matched_positions:
                continue
            wl = lines[j].strip()
            if _is_valid_um_line(wl) or _CANT_RE.match(wl):
                score += 1
                matched_positions.add(i)
                break

    return score


def _infer_deviz_cod(idx: int, pages: list, lines: list) -> str:
    """
    Inferă deviz_cod pentru o pagină reclasificată.

    Strategii (prioritate):
    1. Scan primele 10 linii pentru pattern "XXXXXX pag" sau "226xxx"
    2. Pagina F3 precedentă cu deviz_cod setat (stânga)
    3. Pagina F3 următoare cu deviz_cod setat (dreapta)
    4. Scan complet pagină pentru "226xxx"
    """
    # 1. Header explicit
    early = '\n'.join(lines[:10])
    m = _DEVIZ_PAG_RE.search(early)
    if m:
        return m.group(1).upper()
    m = _COD_226_RE.search(early)
    if m:
        return m.group(1).upper()

    # 2 + 3. Vecini F3 cu deviz_cod
    n = len(pages)
    for delta in range(1, _WINDOW + 1):
        for sign in (-1, +1):
            j = idx + sign * delta
            if 0 <= j < n:
                nb = pages[j]
                if nb.get('is_f3') and not nb.get('header_only'):
                    cod = nb.get('deviz_cod', '')
                    if cod:
                        return cod

    # 4. Scan complet
    full = '\n'.join(lines)
    m = _COD_226_RE.search(full)
    return m.group(1).upper() if m else ''


# ── API public ────────────────────────────────────────────────────────────────

def reclassify_non_f3_pages(page_classifications: list) -> list:
    """
    Scanează paginile is_f3=False și reclasifică determinst cele care
    conțin articole F3 reale (coduri + UM/cantitate).

    Se apelează după citirea checkpoint-ului, înainte de extract_articles_v3.
    Checkpoint-ul NU se modifică — reclasificarea e in-memory, idempotentă.

    Args:
        page_classifications: output din classify_pages() sau checkpoint.

    Returns:
        Lista cu is_f3 și deviz_cod actualizate pentru paginile reclasificate.
    """
    result = [dict(pc) for pc in page_classifications]
    n_reclassified = 0
    n_non_f3 = sum(1 for p in result if not p.get('is_f3'))

    for idx, pc in enumerate(result):
        if pc.get('is_f3'):
            continue

        lines = pc.get('lines', [])
        if not lines:
            continue

        pn = pc.get('page_number', idx)

        # Regula 1: semnal F3 cert (SECTIUNEA TEHNICA, >>> componenta)
        if _has_f3_signal(lines):
            deviz = _infer_deviz_cod(idx, result, lines)
            result[idx].update({'is_f3': True, 'deviz_cod': deviz, 'header_only': False})
            logger.info(f"[RECLF] pag{pn}: F3 (semnal cert) → deviz={deviz!r}")
            n_reclassified += 1
            continue

        # Filtrare rapidă: trebuie cel puțin un cod de articol
        full = ' '.join(lines)
        if not _COD_NORM_RE.search(full) and not _COD_NUMERIC_SEP_RE.search(full):
            continue

        # Regula 2: score-based — CONSERVATIVA.
        # Reclasifică NUMAI dacă devizul e explicit în header-ul propriu paginii.
        # Nu folosim vecini — prevenire false-positives pentru Lista consumuri resurse
        # care are acelasi format ca F3 dar apare in blocuri mari de pagini.

        # Verific mai intai markeri negativi (sumar, resurse)
        if _SUMAR_RE.search(full):
            logger.debug(f"[RECLF] pag{pn}: skip (marker sumar/resurse)")
            continue

        # Deviz explicit in header-ul propriu paginii (primele 10 linii)
        early = '\n'.join(lines[:10])
        m_deviz = _DEVIZ_PAG_RE.search(early) or _COD_226_RE.search(early)
        if not m_deviz:
            continue  # fara deviz explicit in header → nu reclasificam

        deviz_explicit = m_deviz.group(1).upper()

        # Scor articole
        score = _score_f3_content(lines)
        if score < _MIN_SCORE:
            continue

        result[idx].update({'is_f3': True, 'deviz_cod': deviz_explicit, 'header_only': False})
        logger.info(f"[RECLF] pag{pn}: F3 (score={score}, deviz explicit) → deviz={deviz_explicit!r}")
        n_reclassified += 1

    if n_reclassified:
        logger.info(
            f"[RECLF] {n_reclassified} pagini reclasificate din {n_non_f3} non-F3"
        )
    return result
