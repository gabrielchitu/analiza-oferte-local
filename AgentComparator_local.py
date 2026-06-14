"""
AgentComparator_local.py — Logica de matching extrasa din AgentComparator/core.py.

Fara dependente Azure (fara BlobServiceClient, TableServiceClient, Queue, HTTP).
Folosit de local_run.py.

Sursa: func-analiza-oferte/AgentComparator/core.py (functiile de matching)
"""
import logging
import re
from collections import defaultdict

from shared.comparator import compare_articles, check_arithmetic, _normalize_um
from shared.article_matcher import match_unmatched_global
import json as _json
from pathlib import Path as _Path

logger = logging.getLogger(__name__)

_OCR_PATTERNS_FILE = _Path(__file__).parent / "shared" / "ocr_patterns_knowledge.json"
_HARDCODED_FROM = {'L', 'I', 'O'}  # chars handled by hardcoded rules in _normalize_cod


def _load_ocr_learned() -> dict:
    try:
        data = _json.loads(_OCR_PATTERNS_FILE.read_text())
        return {
            r["from"].upper(): r["to"]
            for r in data.get("char_substitutions", [])
            if r["from"].upper() not in _HARDCODED_FROM
        }
    except Exception:
        return {}


def _load_code_aliases() -> dict:
    def _norm_alias_key(v: str) -> str:
        v = re.sub(r'[^A-Z0-9$]', '', v.strip().upper())
        if v.startswith('$') and len(v) > 1:
            stripped = re.sub(r'^0+', '', v[1:])
            return '$' + stripped if stripped else v
        # Match clean_code() behavior: strip leading zeros from numeric suffix after letters
        return re.sub(r'(?<=[A-Z])0+(\d+)$', r'\1', v)
    try:
        data = _json.loads(_OCR_PATTERNS_FILE.read_text())
        return {_norm_alias_key(r["from"]): _norm_alias_key(r["to"])
                for r in data.get("code_aliases", [])}
    except Exception:
        return {}


_OCR_LEARNED: dict = _load_ocr_learned()
_CODE_ALIASES: dict = _load_code_aliases()


def clean_code(cod: str) -> str:
    """
    GENERAL SOLUTION: Clean code by removing artifact characters.

    Removes: ^, #, @, -, etc. (formatting artifacts)
    Preserves: $prefix, A-Z, 0-9

    Examples:
      CK01A01^     → CK01A01
      SA14B#       → SA14B
      CO01A01      → CO01A01 (unchanged, valid code)
      $2911        → $2911 (unchanged)
      ID03A01-     → ID03A01

    Use this function CONSISTENTLY when comparing codes across reference and offer.
    """
    if not cod:
        return cod

    cod = str(cod).strip().upper()
    # Remove artifact characters: ^, #, @, -, [, ], (, ), etc.
    # Keep only: letters (A-Z), digits (0-9), and $ prefix
    cleaned = re.sub(r'[^A-Z0-9$]', '', cod)
    # Strip leading zeros from trailing numeric suffix (formatare OCR)
    # RPCE07A01 → RPCE07A1, IZF03A01 → IZF03A1
    cleaned = re.sub(r'(?<=[A-Z])0+(\d+)$', r'\1', cleaned)
    # Dollar codes: $0003831 → $3831
    if cleaned.startswith('$') and len(cleaned) > 1:
        cleaned = '$' + re.sub(r'^0+', '', cleaned[1:]) or cleaned
    return cleaned


def _normalize_cod(cod: str) -> str:
    """
    DEPRECATED: Use clean_code() instead for general code cleaning.

    This function applies aggressive transformations that break valid codes.
    Kept for backward compatibility with Layer 2 fuzzy matching only.
    """
    cod = (cod or "").strip().upper()
    # Strip special characters FIRST (before OCR replacements)
    # Caractere speciale (#, @, -, etc.) sunt artefacte software/OCR — stripuim.
    cod = re.sub(r'[^A-Z0-9$]', '', cod)

    # Whole-code aliases (different code systems for same article, e.g. C20/25 ↔ $2110955)
    if cod in _CODE_ALIASES:
        result = _CODE_ALIASES[cod]
        # Strip leading zeros from $-prefix targets to match clean_code() behavior
        if result.startswith('$') and len(result) > 1:
            stripped = re.sub(r'^0+', '', result[1:])
            return '$' + stripped if stripped else result
        return result

    # Handle $ prefixed codes early (numeric only)
    if cod.startswith('$'):
        num = re.sub(r'[^0-9]', '', cod[1:])  # extrage doar cifrele
        if len(num) >= 8:
            # Codurile de breviar au max 7 cifre; 8+ cifre = cifra OCR in plus → trunchiaza
            num = num[:7]
        return '$' + num if num else cod

    # Coduri normative utilaj cu sufix pur numeric (AUT6753, CMP1234 etc.):
    # unele oferte omit prefixul si scriu doar numarul (6753 → $6753).
    # Normalizare: AUT6753 → $6753 = identic cu $6753 din oferta.
    m_util = re.match(r'^[A-Z]{2,5}(\d{4,5})$', cod)
    if m_util:
        return '$' + m_util.group(1)

    # Pure numeric codes (no letters) → $prefix
    if re.match(r'^\d+$', cod):
        return '$' + cod

    # For valid code patterns, strip artifacts and return as-is
    # Valid pattern: prefix (2-5 letters) + number (2-4 digits) + optional letter + optional 1-2 digits
    m = re.match(r'^([A-Z]{2,5}\d{2,4}[A-Z]?\d{0,2})$', cod)
    if m:
        # Code already matches valid pattern — no aggressive OCR replacements
        return m.group(1)

    # For codes that don't match valid pattern, apply aggressive OCR fixes
    # OCR fix: lowercase 'l' often confused with digit '1'
    cod = cod.replace('l', '1').replace('L', '1')
    # OCR fix: letter 'I' often confused with digit '1' — normalize I to 1
    # SA13I → SA131 (I becomes 1 in OCR)
    cod = cod.replace('I', '1')
    # OCR fix: letter 'O' often confused with digit '0' — normalize to '0'
    # IZDO4D1 → IZD04D1 (O becomes 0 in PDF)
    cod = cod.replace('O', '0')
    # Apply learned OCR patterns (additive — never override hardcoded above)
    for src, dst in _OCR_LEARNED.items():
        cod = cod.replace(src, dst)

    # Extract valid code structure from the OCR-corrected version
    m = re.match(r'^([A-Z]{2,5}\d{2,4}[A-Z]?\d{0,2})', cod)
    return m.group(1) if m else cod


def _enrich(neconf: dict, ref_art: dict, oferta_art: dict,
            deviz_cod_ref: str, deviz_den: str) -> dict:
    """Adauga campuri de context la o neconformitate."""
    neconf.update({
        "deviz_ref": deviz_cod_ref,
        "deviz_denumire": deviz_den,
        "is_component": ref_art.get("is_component", False),
        "ref_cod": ref_art.get("cod", ""),
        "ref_denumire": ref_art.get("denumire", ""),
        "ref_um": ref_art.get("um", ""),
        "ref_cantitate": ref_art.get("cantitate", ""),
        "ref_pret_material": ref_art.get("pret_material", 0),
        "ref_pret_manopera": ref_art.get("pret_manopera", 0),
        "ref_pret_utilaj": ref_art.get("pret_utilaj", 0),
        "ref_pret_transport": ref_art.get("pret_transport", 0),
        "ref_val_material": ref_art.get("val_material", 0),
        "ref_val_manopera": ref_art.get("val_manopera", 0),
        "ref_val_utilaj": ref_art.get("val_utilaj", 0),
        "ref_val_transport": ref_art.get("val_transport", 0),
        # v7.0: hierarchy context fields
        "nr_ordine_ref": ref_art.get("nr_ordine"),
        "parent_cod_ref": ref_art.get("parent_cod"),
        "parent_nr_ordine_ref": ref_art.get("parent_nr_ordine"),
        "display_parent_cod": ref_art.get("display_parent_cod"),
        "cant_mostenita": ref_art.get("cant_mostenita", False),
        "ref_source_pages": ref_art.get("source_pages", []),
    })
    if oferta_art:
        neconf.update({
            "oferta_cod": oferta_art.get("cod", ""),
            "oferta_denumire": oferta_art.get("denumire", ""),
            "oferta_um": oferta_art.get("um", ""),
            "oferta_cantitate": oferta_art.get("cantitate", ""),
            "oferta_pret_material": oferta_art.get("pret_material", 0),
            "oferta_pret_manopera": oferta_art.get("pret_manopera", 0),
            "oferta_pret_utilaj": oferta_art.get("pret_utilaj", 0),
            "oferta_pret_transport": oferta_art.get("pret_transport", 0),
            "oferta_val_material": oferta_art.get("val_material", 0),
            "oferta_val_manopera": oferta_art.get("val_manopera", 0),
            "oferta_val_utilaj": oferta_art.get("val_utilaj", 0),
            "oferta_val_transport": oferta_art.get("val_transport", 0),
            "nr_ordine_oferta": oferta_art.get("nr_ordine"),
            "oferta_display_parent_cod": oferta_art.get("display_parent_cod"),
            "oferta_source_pages": oferta_art.get("source_pages", []),
        })
    return neconf


def _normalize_deviz_code(deviz_cod: str) -> str:
    """
    Normalizeaza codurile deviz pentru a gestiona variatiile OCR.
    226U18 → 226018 (U = 0)
    226U38 → 226038 (U = 0)
    226U28 → 226028 (U = 0)
    226U08 → 226008 (U = 0)
    """
    if not deviz_cod:
        return deviz_cod

    # Replace U with 0 (OCR confusion: U looks like 0)
    normalized = deviz_cod.replace('U', '0')
    return normalized


def _deviz_key(art: dict) -> str:
    """Returneaza cheia de deviz normalizata pentru un articol.

    Uses deviz code as primary key — 3-layer canonical is applied via art["deviz"]
    remap in local_run.py before matching, not here.
    """
    deviz_cod = (art.get("deviz") or "").strip()
    if deviz_cod:
        return _normalize_deviz_code(deviz_cod)

    # Last fallback: use normalized denomination if no code
    raw = (art.get("deviz_denumire") or "").strip().upper()
    raw = re.sub(r'^(\d+\s+)+', '', raw).strip()
    raw = re.sub(r'\b(OB|NR|CAP|ART)[\s.]*(\d+)', r'\1\2', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw


def _art_key(art: dict) -> tuple:
    """Cheia compusa (deviz, cod) pentru un articol.

    Uses (deviz_code, cleaned_cod) where cleaned_cod removes artifact characters.
    This ensures codes like CK01A01^ and CK01A01 match correctly.
    """
    return (_deviz_key(art), clean_code(art.get("cod") or ""))


# ── DIFERENTA_PARAMETRU detection ────────────────────────────────────────────
# Matches correct business-wise (same article) but with different numeric
# parameters in the denomination (distance, height, capacity, etc.).
_PARAM_RE = re.compile(
    r'\b(\d+(?:[.,]\d+)?)\s*'
    r'(km|mc|mp|ml|m[23]?|cm|mm|kw[ah]?|kva|kn|bar|mpa|tone?|tona|t|l)\b',
    re.IGNORECASE,
)


def _extract_param_pairs(text: str) -> frozenset:
    result = set()
    for m in _PARAM_RE.finditer(text or ''):
        val = float(m.group(1).replace(',', '.'))
        unit = m.group(2).lower()
        if unit in ('tona', 'tone'):
            unit = 't'
        result.add((val, unit))
    return frozenset(result)


def _nc_parametru_diferit(
    ref_art: dict, off_art: dict, deviz_cod: str, deviz_den: str
) -> "dict | None":
    ref_params = _extract_param_pairs(ref_art.get('denumire') or '')
    off_params = _extract_param_pairs(off_art.get('denumire') or '')
    if ref_params == off_params:
        return None
    ref_only = ref_params - off_params
    off_only = off_params - ref_params
    nc: dict = {
        'tip': 'DIFERENTA_PARAMETRU',
        'ref_parametri': sorted(f"{v:g} {u}" for v, u in ref_only),
        'oferta_parametri': sorted(f"{v:g} {u}" for v, u in off_only),
    }
    _enrich(nc, ref_art, off_art, deviz_cod, deviz_den)
    return nc


def _deduplicate_neconformitati(neconformitati: list) -> list:
    """Remove duplicate non-conformities.

    Per article pair (deviz, ref_cod, oferta_cod):
    - COD_SIMILAR suppresses all DIFERENTA_CAMP/UM_DIFERIT (COD already explains the mismatch)
    - Multiple DIFERENTA_CAMP with different `camp` fields ALL survive (e.g. tip_articol + cantitate)
    - Exact-same (tip, camp) duplicates are collapsed to one
    """
    if not neconformitati:
        return neconformitati

    from collections import defaultdict
    pair_ncs: dict = defaultdict(list)
    for nc in neconformitati:
        pair_key = (nc.get('deviz', ''), nc.get('ref_cod', ''), nc.get('oferta_cod', ''))
        pair_ncs[pair_key].append(nc)

    result = []
    for ncs in pair_ncs.values():
        cod_similar = [nc for nc in ncs if nc.get('tip') == 'COD_SIMILAR']
        if cod_similar:
            result.append(cod_similar[0])
            # DIFERENTA_PARAMETRU survives alongside COD_SIMILAR (real business difference)
            for nc in ncs:
                if nc.get('tip') == 'DIFERENTA_PARAMETRU':
                    result.append(nc)
            continue
        seen_tip_camp: set = set()
        for nc in ncs:
            tip_camp = (nc.get('tip', ''), nc.get('camp', ''))
            if tip_camp not in seen_tip_camp:
                seen_tip_camp.add(tip_camp)
                result.append(nc)

    return result


def build_ref_catalog(ref_articole: list) -> dict:
    """Catalog canonical: $cod → normative_cod, extras exclusiv din referință.

    Sursa de adevăr pentru parent mapping în Layer 0.
    """
    catalog = {}
    for art in ref_articole:
        cod = art.get('cod', '')
        parent = art.get('display_parent_cod')
        if cod.startswith('$') and parent:
            catalog[cod] = parent
    return catalog


def match_global(
    ref_articole: list,
    oferta_articole: list,
    openai_client,
    deployment: str,
    include_prices: bool = False,
) -> tuple:
    """
    3-layer matching (Layer 1 exact, Layer 2 normalized, Layer 2.5 cross-deviz, Layer 3 LLM).
    Returns (neconformitati, matches).

    Identic cu _match_global din AgentComparator/core.py dar fara dependente Azure.
    include_prices=False implicit — pentru comparare fara preturi.
    """
    # Caz B: orice articol fără deviz → exclus matching, returnat separat
    articole_fara_deviz: list = []
    ref_articole_valid = []
    for a in ref_articole:
        if not a.get('deviz'):
            articole_fara_deviz.append(('ref', a))
        else:
            ref_articole_valid.append(a)
    ref_articole = ref_articole_valid

    oferta_articole_valid = []
    for a in oferta_articole:
        if not a.get('deviz'):
            articole_fara_deviz.append(('oferta', a))
        else:
            oferta_articole_valid.append(a)
    oferta_articole = oferta_articole_valid

    # Deduplicate by 4-tuple (deviz, cod, um, cantitate) before matching
    # If same article appears multiple times with identical values, keep first occurrence
    # Filtreaza artefactele breviar: cantitate=0 cu UM gol sau majuscule (template/header)
    def _is_breviar_artifact(a: dict) -> bool:
        cant = a.get("cantitate") or 0
        um = (a.get("um") or "").strip()
        return cant == 0 and (not um or um == um.upper())

    ref_seen = {}
    ref_dedup = []
    for a in ref_articole:
        if a.get("cod") and not a.get("is_component") and not _is_breviar_artifact(a):
            key = (a.get("deviz"), a.get("cod"), a.get("um"), a.get("cantitate"))
            if key not in ref_seen:
                ref_dedup.append(a)
                ref_seen[key] = True

    oferta_seen = {}
    oferta_dedup = []
    for a in oferta_articole:
        if a.get("cod") and not _is_breviar_artifact(a):
            key = (a.get("deviz"), a.get("cod"), a.get("um"), a.get("cantitate"))
            if key not in oferta_seen:
                oferta_dedup.append(a)
                oferta_seen[key] = True

    # Build canonical parent catalog from reference (after dedup)
    ref_catalog = build_ref_catalog(ref_articole)

    ref_component_cods = {_normalize_cod(a.get("cod", ""))
                          for a in ref_articole if a.get("is_component")}
    # Also include explicit subcomponent codes stored in parent articles' 'subcomponents' field.
    # Ofertants often list these as standalone articles (detailed resource breakdown) while the
    # reference stores them as components of normative work items — they must not be EXTRA.
    for _a in ref_articole:
        for _sub in _a.get("subcomponents", []):
            _sub_cod = _sub if isinstance(_sub, str) else _sub.get("cod", "")
            if _sub_cod:
                ref_component_cods.add(_normalize_cod(_sub_cod))

    neconformitati = []
    matches = []
    matched_oferta_keys = set()
    matched_by_llm_ref_keys: set = set()
    unmatched_ref = []
    extra_from_nm: list = []

    # Multimaps: (deviz, cod) → [art, ...] sortat după cantitate.
    # Același cod poate apărea de N ori în același deviz cu cantități diferite (poziții diferite).
    ref_by_key: dict = defaultdict(list)
    for a in ref_dedup:
        ref_by_key[_art_key(a)].append(a)
    for lst in ref_by_key.values():
        lst.sort(key=lambda a: a.get("cantitate", 0) or 0)

    oferta_by_key: dict = defaultdict(list)
    for a in oferta_dedup:
        oferta_by_key[_art_key(a)].append(a)
    for lst in oferta_by_key.values():
        lst.sort(key=lambda a: a.get("cantitate", 0) or 0)

    # View 1:1 pentru Layer 2/3 (coduri OCR-eronate apar o singură dată în practică)
    ref_map = {k: v[0] for k, v in ref_by_key.items()}
    oferta_map = {k: v[0] for k, v in oferta_by_key.items()}

    # Layer 1: N:M exact match pe (deviz, cod) — sortate după cantitate, perechi în ordine.
    # ref(34.2)↔oferta(34.2), ref(40.0)↔oferta(40.0); excesul → LIPSA/EXTRA.
    for key, ref_list in ref_by_key.items():
        oferta_list = oferta_by_key.get(key, [])
        deviz_cod = ref_list[0].get("deviz", "")
        deviz_den = ref_list[0].get("deviz_denumire", "")

        if not oferta_list:
            unmatched_ref.extend(ref_list)
            continue

        matched_oferta_keys.add(key)

        ref_strict = ref_list

        # Process strict-mode references using best-first global matching.
        # At each step pick the (ref, offer) pair with minimum score across ALL remaining pairs.
        # Prevents greedy-order errors: e.g. ref=[101.2,683.0] offer=[683.0] → without global
        # search, ref_101.2 is processed first and consumes offer_683.0 (score=581.8), leaving
        # ref_683.0 as LIPSA. Best-first correctly pairs ref_683.0↔offer_683.0 (score=0) first.
        ref_ums = {(r.get('um') or '').lower() for r in ref_strict}
        oferta_pool = sorted(
            oferta_list,
            key=lambda a: (0 if (a.get('um') or '').lower() in ref_ums else 1,
                           a.get('cantitate', 0) or 0)
        )
        ref_remaining = list(ref_strict)
        unmatched_strict_ref: list = []
        paired_strict: list = []  # (ref_art, oferta_art) pairs in best-first order
        while ref_remaining and oferta_pool:
            best_score = float('inf')
            best_ri = 0
            best_oi = 0
            for ri, ra in enumerate(ref_remaining):
                ra_cant = ra.get('cantitate', 0) or 0
                ra_um = (ra.get('um') or '').lower()
                for oi, oa in enumerate(oferta_pool):
                    oa_cant = oa.get('cantitate', 0) or 0
                    oa_um = (oa.get('um') or '').lower()
                    um_penalty = 0.0 if oa_um == ra_um else 1e9
                    score = um_penalty + abs(oa_cant - ra_cant)
                    if score < best_score:
                        best_score = score
                        best_ri = ri
                        best_oi = oi
            paired_strict.append((ref_remaining.pop(best_ri), oferta_pool.pop(best_oi)))
        unmatched_strict_ref.extend(ref_remaining)
        for ra, oferta_art in paired_strict:
            diffs = compare_articles(ra, oferta_art, include_prices=include_prices)
            arith = check_arithmetic(oferta_art) if include_prices else []
            if ra.get("is_component") and not oferta_art.get("is_component"):
                # ref=subcomponent but offer=principal: genuine reclassification
                # Reverse (ref=principal, offer=subcomponent) is document format noise
                # (offer uses chapter headers 1 → 1.1, 1.2...; ref uses flat NR list)
                nc_comp = {
                    "tip": "DIFERENTA_CAMP",
                    "camp": "tip_articol",
                    "ref": "subcomponenta",
                    "oferta": "articol_principal",
                }
                _enrich(nc_comp, ra, oferta_art, deviz_cod, deviz_den)
                neconformitati.append(nc_comp)
            for d in diffs + arith:
                _enrich(d, ra, oferta_art, deviz_cod, deviz_den)
            neconformitati.extend(diffs + arith)
            nc_param = _nc_parametru_diferit(ra, oferta_art, deviz_cod, deviz_den)
            if nc_param:
                neconformitati.append(nc_param)
            matches.append({
                "ref_cod": ra.get("cod", ""),
                "ref_denumire": ra.get("denumire", ""),
                "oferta_cod": oferta_art.get("cod", ""),
                "oferta_denumire": oferta_art.get("denumire", ""),
            })
        # oferta_pool holds excess (not consumed by strict refs); unmatched_strict_ref has ref overflow
        unmatched_ref.extend(unmatched_strict_ref)
        extra_from_nm.extend(oferta_pool)

    # Layer 2: Normalized N:M match pe (deviz, normalize(cod))
    # Upgrade față de 1:1: grupează toate ref nemat-uite cu același norm_key
    # și le potrivește N:M cu lista completă din ofertă (ca Layer 1).
    # Prinde: AUT6752 (ref) ↔ $6752 (oferta), cod normativ cu sufix numeric omis de ofertant.
    unmatched_oferta_keys = set(oferta_by_key.keys()) - matched_oferta_keys
    norm_to_oferta_key = {}
    for ok in unmatched_oferta_keys:
        deviz, cod = ok
        # Use clean_code which handles artifact character removal
        norm = (deviz, _normalize_cod(clean_code(cod)))
        if norm not in norm_to_oferta_key:
            norm_to_oferta_key[norm] = ok

    # Grupează ref nemat-uite după norm_key pentru N:M
    ref_by_norm: dict = defaultdict(list)
    still_unmatched_ref = []
    for ref_art in unmatched_ref:
        norm_key = (_deviz_key(ref_art), _normalize_cod(clean_code(ref_art.get("cod", ""))))
        if norm_key in norm_to_oferta_key:
            ref_by_norm[norm_key].append(ref_art)
        else:
            still_unmatched_ref.append(ref_art)

    for norm_key, ref_list in ref_by_norm.items():
        original_oferta_key = norm_to_oferta_key[norm_key]
        oferta_list = oferta_by_key[original_oferta_key]
        matched_oferta_keys.add(original_oferta_key)
        unmatched_oferta_keys.discard(original_oferta_key)
        del norm_to_oferta_key[norm_key]

        ref_list.sort(key=lambda a: a.get("cantitate", 0) or 0)
        deviz_cod = ref_list[0].get("deviz", "")
        deviz_den = ref_list[0].get("deviz_denumire", "")
        original_oferta_cod = oferta_list[0].get("cod", "") if oferta_list else ""

        for ref_art, oferta_art in zip(ref_list, oferta_list):
            ref_cod = ref_art.get("cod", "")
            diffs = compare_articles(ref_art, oferta_art, include_prices=include_prices)
            arith = check_arithmetic(oferta_art) if include_prices else []
            if ref_cod != original_oferta_cod:
                neconf = {
                    "tip": "COD_SIMILAR",
                    "motiv_similaritate": f"Caracteristici similare, cod diferit: referință '{ref_cod}' ↔ ofertat '{original_oferta_cod}'",
                }
                _enrich(neconf, ref_art, oferta_art, deviz_cod, deviz_den)
                neconformitati.append(neconf)
            for d in diffs + arith:
                _enrich(d, ref_art, oferta_art, deviz_cod, deviz_den)
            neconformitati.extend(diffs + arith)
            nc_param = _nc_parametru_diferit(ref_art, oferta_art, deviz_cod, deviz_den)
            if nc_param:
                neconformitati.append(nc_param)
            matches.append({
                "ref_cod": ref_cod,
                "ref_denumire": ref_art.get("denumire", ""),
                "oferta_cod": original_oferta_cod,
                "oferta_denumire": oferta_art.get("denumire", ""),
            })
        # Exces ref → LIPSA, exces oferta → EXTRA
        still_unmatched_ref.extend(ref_list[len(oferta_list):])
        extra_from_nm.extend(oferta_list[len(ref_list):])


    # Layer 2.1: Trailing-digit variant matching — IC35D↔IC35D1, IC41C↔IC41C1, SB09E↔SB09E1
    # Oferta uses variant suffix digit while ref uses base code without trailing digit.
    # N:M grouped match (same logic as Layer 2) to handle multiple occurrences correctly.
    if still_unmatched_ref and unmatched_oferta_keys:
        # Build (deviz, stripped_code) → oferta_key for unmatched oferta codes ending in digit.
        variant_to_oferta_key: dict = {}
        for ok in unmatched_oferta_keys:
            deviz_ok, cod_ok = ok
            cod_clean_ok = clean_code(cod_ok)
            if cod_clean_ok and cod_clean_ok[-1].isdigit():
                vkey = (deviz_ok, cod_clean_ok[:-1])
                if vkey not in variant_to_oferta_key:
                    variant_to_oferta_key[vkey] = ok

        # Group unmatched ref by (deviz, ref_code) that has a variant in oferta.
        ref_by_variant: dict = defaultdict(list)
        still_unmatched_ref_21 = []
        for ref_art in still_unmatched_ref:
            vkey_ref = (_deviz_key(ref_art), clean_code(ref_art.get("cod", "")))
            if vkey_ref in variant_to_oferta_key:
                ref_by_variant[vkey_ref].append(ref_art)
            else:
                still_unmatched_ref_21.append(ref_art)

        for vkey, ref_list in ref_by_variant.items():
            oferta_key = variant_to_oferta_key[vkey]
            oferta_list = oferta_by_key[oferta_key]
            matched_oferta_keys.add(oferta_key)
            unmatched_oferta_keys.discard(oferta_key)

            ref_list.sort(key=lambda a: a.get("cantitate", 0) or 0)
            deviz_cod = ref_list[0].get("deviz", "")
            deviz_den = ref_list[0].get("deviz_denumire", "")
            original_oferta_cod = oferta_list[0].get("cod", "") if oferta_list else ""

            for r_art, o_art in zip(ref_list, oferta_list):
                diffs = compare_articles(r_art, o_art, include_prices=include_prices)
                arith = check_arithmetic(o_art) if include_prices else []
                if r_art.get("cod", "") != original_oferta_cod:
                    neconf = {
                        "tip": "COD_SIMILAR",
                        "motiv_similaritate": f"Caracteristici similare, cod diferit: referință '{r_art.get('cod')}' ↔ ofertat '{original_oferta_cod}'",
                    }
                    _enrich(neconf, r_art, o_art, deviz_cod, deviz_den)
                    neconformitati.append(neconf)
                for d in diffs + arith:
                    _enrich(d, r_art, o_art, deviz_cod, deviz_den)
                neconformitati.extend(diffs + arith)
                nc_param = _nc_parametru_diferit(r_art, o_art, deviz_cod, deviz_den)
                if nc_param:
                    neconformitati.append(nc_param)
                matches.append({
                    "ref_cod": r_art.get("cod", ""),
                    "ref_denumire": r_art.get("denumire", ""),
                    "oferta_cod": o_art.get("cod", ""),
                    "oferta_denumire": o_art.get("denumire", ""),
                })
            still_unmatched_ref_21.extend(ref_list[len(oferta_list):])
            extra_from_nm.extend(oferta_list[len(ref_list):])
        still_unmatched_ref = still_unmatched_ref_21

    # Layer 2.1b: Check extra_from_nm for variant matches.
    # Handles: IC35D(ref) not matched because IC35D1(oferta) key was consumed by Layer 1
    # N:M excess, but the excess IC35D1 is actually the variant match for IC35D.
    if still_unmatched_ref and extra_from_nm:
        extra_matched_ids: set = set()
        still_unmatched_ref_21b: list = []
        for ref_art in still_unmatched_ref:
            ref_deviz = _deviz_key(ref_art)
            ref_cod_clean = clean_code(ref_art.get("cod", ""))
            if not ref_cod_clean:
                still_unmatched_ref_21b.append(ref_art)
                continue
            match_ea = None
            ref_norm = _normalize_cod(ref_art.get("cod", ""))
            ref_cant = ref_art.get("cantitate") or 0
            for ea in extra_from_nm:
                if id(ea) in extra_matched_ids:
                    continue
                if _deviz_key(ea) != ref_deviz:
                    continue
                ea_cod_clean = clean_code(ea.get("cod", ""))
                # Check 1: trailing-digit variant (IC35D1 → IC35D)
                if (ea_cod_clean and ea_cod_clean[-1].isdigit()
                        and ea_cod_clean[:-1] == ref_cod_clean):
                    match_ea = ea
                    break
                # Check 2: normalized code match with same cantitate (CNO1A → CN01A via O→0)
                ea_norm = _normalize_cod(ea.get("cod", ""))
                ea_cant = ea.get("cantitate") or 0
                if (ea_norm == ref_norm and ea_norm != ref_cod_clean
                        and abs(ea_cant - ref_cant) < 0.01):
                    match_ea = ea
                    break
            if match_ea:
                extra_matched_ids.add(id(match_ea))
                deviz_cod = ref_art.get("deviz", "")
                deviz_den = ref_art.get("deviz_denumire", "")
                original_oferta_cod = match_ea.get("cod", "")
                diffs = compare_articles(ref_art, match_ea, include_prices=include_prices)
                arith = check_arithmetic(match_ea) if include_prices else []
                if ref_art.get("cod", "") != original_oferta_cod:
                    neconf = {
                        "tip": "COD_SIMILAR",
                        "motiv_similaritate": f"Caracteristici similare, cod diferit: referință '{ref_art.get('cod')}' ↔ ofertat '{original_oferta_cod}'",
                    }
                    _enrich(neconf, ref_art, match_ea, deviz_cod, deviz_den)
                    neconformitati.append(neconf)
                for d in diffs + arith:
                    _enrich(d, ref_art, match_ea, deviz_cod, deviz_den)
                neconformitati.extend(diffs + arith)
                nc_param = _nc_parametru_diferit(ref_art, match_ea, deviz_cod, deviz_den)
                if nc_param:
                    neconformitati.append(nc_param)
                matches.append({
                    "ref_cod": ref_art.get("cod", ""),
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": match_ea.get("cod", ""),
                    "oferta_denumire": match_ea.get("denumire", ""),
                })
            else:
                still_unmatched_ref_21b.append(ref_art)
        extra_from_nm = [ea for ea in extra_from_nm if id(ea) not in extra_matched_ids]
        still_unmatched_ref = still_unmatched_ref_21b

    # Layer 2.2: Cross-deviz matching — GENERAL SOLUTION for deviz mismatches
    # Prinde articole cu (cod, cantitate, UM) identice dar in devize diferite
    # Exemple: ref(4.2-1, TRA05A05, 10.34) ↔ oferta(4.3-01, TRA05A05, 10.34)
    # Once matched here, removes from still_unmatched_ref and unmatched_oferta_keys
    # so Layer 3 doesn't try to re-match them
    if still_unmatched_ref and unmatched_oferta_keys:
        # Build a map of (code, quantity, UM) → (oferta_art, oferta_key) — ignore deviz
        oferta_by_code_qty = {}
        for ok in unmatched_oferta_keys:
            oferta_art = oferta_map.get(ok)
            if oferta_art:
                key = (
                    clean_code(oferta_art.get("cod", "")),
                    oferta_art.get("cantitate"),
                    _normalize_um(oferta_art.get("um", ""))
                )
                if key not in oferta_by_code_qty:
                    oferta_by_code_qty[key] = (oferta_art, ok)

        # Process still_unmatched_ref: keep only those NOT matched cross-deviz
        remaining_unmatched_ref = []
        matched_oferta_keys_cross = set()

        for ref_art in still_unmatched_ref:
            ref_key = (
                clean_code(ref_art.get("cod", "")),
                ref_art.get("cantitate"),
                _normalize_um(ref_art.get("um", ""))
            )

            if ref_key in oferta_by_code_qty:
                # Found match across devizes — remove from both pools
                oferta_art, oferta_key = oferta_by_code_qty[ref_key]
                matched_oferta_keys_cross.add(oferta_key)

                # Record as DEVIZ_MISMATCH (not LIPSA, not matched)
                neconf = {
                    "tip": "DEVIZ_MISMATCH",
                    "motiv": f"Cod+Qty identic in deviz diferit: ref {ref_art.get('deviz')}, oferta {oferta_art.get('deviz')}",
                }
                _enrich(neconf, ref_art, oferta_art, ref_art.get("deviz", ""), ref_art.get("deviz_denumire", ""))
                neconformitati.append(neconf)

                matches.append({
                    "ref_cod": ref_art.get("cod", ""),
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": oferta_art.get("cod", ""),
                    "oferta_denumire": oferta_art.get("denumire", ""),
                })

                logger.debug(f"[CROSS-DEVIZ] {ref_art.get('cod')}: ref deviz={ref_art.get('deviz')}, oferta deviz={oferta_art.get('deviz')}")
            else:
                # No match — stays in still_unmatched_ref for Layer 3
                remaining_unmatched_ref.append(ref_art)

        still_unmatched_ref = remaining_unmatched_ref
        unmatched_oferta_keys -= matched_oferta_keys_cross

        if matched_oferta_keys_cross:
            logger.info(f"[CROSS-DEVIZ] Detectate {len(matched_oferta_keys_cross)} articole in devize diferite")


    # Layer 3: LLM fuzzy match per grup deviz
    if still_unmatched_ref and unmatched_oferta_keys:
        ref_by_deviz = defaultdict(list)
        for a in still_unmatched_ref:
            ref_by_deviz[_deviz_key(a)].append(a)

        oferta_by_deviz = defaultdict(list)
        for ok in unmatched_oferta_keys:
            oferta_by_deviz[ok[0]].extend(oferta_by_key[ok])

        # Layer 2.5: potrivire deterministă pe similaritate înaltă de cod + denumire.
        # Prinde perechi precum $3275680/$3275630 (1 caracter diferit, OCR)
        # fără a depinde de LLM. Threshold 0.80 (cu Jaccard ≥0.4 ca ancora).
        _SIM_DET = 0.80

        def _denom_jaccard(a: str, b: str) -> float:
            def _tok(s: str) -> set:
                # Normalizeaza separatori intre cifre: 110,45 → 11045, 110x45 → 11045
                s = re.sub(r'(\d)[,x.\-](\d)', r'\1\2', (s or '').lower())
                return set(re.sub(r'[^a-z0-9]', ' ', s).split())
            wa, wb = _tok(a), _tok(b)
            if not wa or not wb:
                return 0.0
            inter = len(wa & wb)
            # Jaccard pur penalizeaza cand oferta e mai detaliata decat referinta.
            # Folosim max(Jaccard, recall) — daca ref e "continuta" in oferta, e match.
            jaccard = inter / len(wa | wb)
            recall  = inter / len(wa)  # proportia cuvintelor ref gasite in oferta
            return max(jaccard, recall)

        from shared.article_matcher import _cod_similarity
        matched_by_llm_ref_keys: set = set()
        det_matched_oferta_arts: set = set()

        for deviz, ref_list in ref_by_deviz.items():
            oferta_cands = oferta_by_deviz.get(deviz, [])
            for ref_art in list(ref_list):
                ref_cod = ref_art.get("cod", "")
                ref_cant = ref_art.get("cantitate") or 0
                best_art, best_score, best_cant_match = None, 0.0, False
                for of_art in oferta_cands:
                    if id(of_art) in det_matched_oferta_arts:
                        continue
                    cs = _cod_similarity(ref_cod, of_art.get("cod", ""))
                    if cs < _SIM_DET:
                        continue
                    dj = _denom_jaccard(ref_art.get("denumire", ""),
                                        of_art.get("denumire", ""))
                    score = cs * 0.6 + dj * 0.4
                    of_cant = of_art.get("cantitate") or 0
                    cant_match = bool(ref_cant and abs(of_cant - ref_cant) / max(abs(ref_cant), 1e-9) < 0.001)
                    # Prefer cantitate-matching candidate as tiebreaker (avoids cross-match:
                    # TRA01A05[94.86] wrongly consuming TRA01A50[72.25] instead of [94.86])
                    if score > best_score or (score == best_score and cant_match and not best_cant_match):
                        best_score, best_art, best_cant_match = score, of_art, cant_match
                if best_art is None or _denom_jaccard(
                        ref_art.get("denumire", ""), best_art.get("denumire", "")) < 0.4:
                    continue
                # Potrivire confirmată
                oferta_key = _art_key(best_art)
                matched_oferta_keys.add(oferta_key)
                unmatched_oferta_keys.discard(oferta_key)
                det_matched_oferta_arts.add(id(best_art))
                matched_by_llm_ref_keys.add(_art_key(ref_art))
                deviz_cod = ref_art.get("deviz", "")
                deviz_den = ref_art.get("deviz_denumire", "")
                diffs = compare_articles(ref_art, best_art, include_prices=include_prices)
                oferta_cod_val = best_art.get("cod", "")
                if ref_cod != oferta_cod_val:
                    neconf = {
                        "tip": "COD_SIMILAR",
                        "motiv_similaritate": (
                            f"Caracteristici similare, cod diferit: referință '{ref_cod}' ↔ ofertat '{oferta_cod_val}'"
                        ),
                    }
                    _enrich(neconf, ref_art, best_art, deviz_cod, deviz_den)
                    neconformitati.append(neconf)
                for d in diffs:
                    _enrich(d, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.extend(diffs)
                nc_param = _nc_parametru_diferit(ref_art, best_art, deviz_cod, deviz_den)
                if nc_param:
                    neconformitati.append(nc_param)
                matches.append({
                    "ref_cod": ref_cod,
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": oferta_cod_val,
                    "oferta_denumire": best_art.get("denumire", ""),
                })

        still_unmatched_ref = [a for a in still_unmatched_ref
                               if _art_key(a) not in matched_by_llm_ref_keys]

        # Layer 2.6: matching pe UM + cantitate + denumire Jaccard in acelasi deviz.
        # Prinde perechi cu cod complet diferit (furnizor diferit, variante de produs):
        #   $7002380 ↔ $7800774 (folie anticondens, acelasi cant+UM)
        #   AUT3000  ↔ $30001   (aparat de sudura, acelasi cant+UM)
        #   $3271881 ↔ $327101  (teava pn20, acelasi cant+UM)
        _DENOM_THRESH_26 = 0.4  # prag mai relaxat — cantitate+UM anchoreaza deja potrivirea
        det_matched_of_26: set = set()
        for ref_art in list(still_unmatched_ref):
            deviz = _deviz_key(ref_art)
            ref_um = _normalize_um(ref_art.get("um", ""))
            ref_cant = ref_art.get("cantitate", 0) or 0
            if ref_cant == 0 and not ref_um:
                continue  # articole fara cantitate/UM → risc false positive

            best_art, best_score = None, 0.0
            for ok in list(unmatched_oferta_keys):
                if ok[0] != deviz:
                    continue
                of_art = oferta_map[ok]
                if id(of_art) in det_matched_of_26:
                    continue
                if _normalize_um(of_art.get("um", "")) != ref_um:
                    continue
                of_cant = of_art.get("cantitate", 0) or 0
                # Cantitate trebuie sa fie identica sau apropiata (<1%)
                if abs(ref_cant - of_cant) > max(abs(ref_cant), abs(of_cant)) * 0.01 + 0.01:
                    continue
                dj = _denom_jaccard(ref_art.get("denumire", ""), of_art.get("denumire", ""))
                if dj > best_score:
                    best_score, best_art = dj, of_art

            if best_art is None or best_score < _DENOM_THRESH_26:
                continue

            ref_cod = ref_art.get("cod", "")
            oferta_key = _art_key(best_art)
            matched_oferta_keys.add(oferta_key)
            unmatched_oferta_keys.discard(oferta_key)
            det_matched_of_26.add(id(best_art))
            matched_by_llm_ref_keys.add(_art_key(ref_art))
            deviz_cod = ref_art.get("deviz", "")
            deviz_den = ref_art.get("deviz_denumire", "")
            diffs = compare_articles(ref_art, best_art, include_prices=include_prices)
            if ref_cod != best_art.get("cod", ""):
                neconf = {
                    "tip": "COD_SIMILAR",
                    "motiv_similaritate": (
                        f"Cod diferit (produs echivalent): '{ref_cod}' ↔ '{best_art.get('cod','')}'"
                    ),
                }
                _enrich(neconf, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.append(neconf)
            if diffs:
                for d in diffs:
                    _enrich(d, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.extend(diffs)
            nc_param = _nc_parametru_diferit(ref_art, best_art, deviz_cod, deviz_den)
            if nc_param:
                neconformitati.append(nc_param)
            matches.append({
                "ref_cod": ref_cod,
                "ref_denumire": ref_art.get("denumire", ""),
                "oferta_cod": best_art.get("cod", ""),
                "oferta_denumire": best_art.get("denumire", ""),
            })

        still_unmatched_ref = [a for a in still_unmatched_ref
                               if _art_key(a) not in matched_by_llm_ref_keys]

        # Rebuild oferta_by_deviz fara articolele deja potrivite
        oferta_by_deviz = defaultdict(list)
        for ok in unmatched_oferta_keys:
            oferta_by_deviz[ok[0]].append(oferta_map[ok])

        deviz_groups = sorted(ref_by_deviz.keys(), key=lambda d: ("" if d else "\xff"))

        for deviz in deviz_groups:
            ref_batch = [a for a in ref_by_deviz[deviz]
                         if _art_key(a) not in matched_by_llm_ref_keys]
            oferta_candidates = oferta_by_deviz.get(deviz, [])
            if not ref_batch or not oferta_candidates:
                continue
            try:
                fuzzy_pairs = match_unmatched_global(
                    ref_batch, oferta_candidates, openai_client, deployment
                )
            except Exception as e:
                logger.warning(f"[COMP] LLM fuzzy match failed deviz '{deviz}': {e}")
                fuzzy_pairs = []

            for fp in fuzzy_pairs:
                fp_ref_cod = fp.get("ref_cod", "")
                fp_oferta_cod = fp.get("oferta_cod", "")
                ref_art = next((a for a in ref_batch if a.get("cod") == fp_ref_cod), None)
                oferta_art = next((a for a in oferta_candidates if a.get("cod") == fp_oferta_cod), None)
                if not ref_art or not oferta_art:
                    continue
                oferta_key = _art_key(oferta_art)
                matched_oferta_keys.add(oferta_key)
                unmatched_oferta_keys.discard(oferta_key)
                matched_by_llm_ref_keys.add(_art_key(ref_art))
                deviz_val = ref_art.get("deviz", "")
                deviz_den = ref_art.get("deviz_denumire", "")
                diffs_llm = compare_articles(ref_art, oferta_art, include_prices=include_prices)
                if diffs_llm:
                    neconf = {
                        "tip": "COD_SIMILAR",
                        "motiv_similaritate": fp.get("motiv", "Caracteristici similare, cod diferit — identificat automat"),
                    }
                    _enrich(neconf, ref_art, oferta_art, deviz_val, deviz_den)
                    neconformitati.append(neconf)
                    for d in diffs_llm:
                        _enrich(d, ref_art, oferta_art, deviz_val, deviz_den)
                    neconformitati.extend(diffs_llm)
                matches.append({
                    "ref_cod": fp_ref_cod,
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": fp_oferta_cod,
                    "oferta_denumire": oferta_art.get("denumire", ""),
                })

        still_unmatched_ref = [a for a in still_unmatched_ref
                               if _art_key(a) not in matched_by_llm_ref_keys]

    # ARTICOL_LIPSA / DEVIZ_MISMATCH
    # If code exists anywhere in offer (any deviz), prefer DEVIZ_MISMATCH over LIPSA.
    _all_offer_codes = {clean_code(k[1]) for k in oferta_by_key.keys() if k[1]}

    for ref_art in still_unmatched_ref:
        # skip articole fara cantitate (capitole/anteturi, nu articole reale)
        if not ref_art.get("cantitate"):
            continue
        deviz_cod = ref_art.get("deviz", "")
        deviz_den = ref_art.get("deviz_denumire", "")
        ref_code = clean_code(ref_art.get("cod", ""))

        if ref_code and ref_code in _all_offer_codes:
            neconf = {
                "tip": "DEVIZ_MISMATCH",
                "motiv": "Cod gasit in alt deviz din oferta",
            }
        else:
            neconf = {
                "tip": "ARTICOL_LIPSA",
                "oferta_cod": "", "oferta_denumire": "", "oferta_um": "", "oferta_cantitate": "",
            }
        _enrich(neconf, ref_art, {}, deviz_cod, deviz_den)
        neconformitati.append(neconf)

    # ARTICOL_EXTRA — instante neacoperite din oferta (chei nemat-uite + exces N:M)
    extras_to_report = [a for k in unmatched_oferta_keys for a in oferta_by_key[k]] + extra_from_nm

    for oferta_art in extras_to_report:
        norm_cod = _normalize_cod(oferta_art.get("cod", ""))
        if norm_cod in ref_component_cods:
            if oferta_art.get("is_component"):
                # Both ref and offer classify as subcomponent — compare cantitate/UM
                ref_comps = [a for a in ref_articole if a.get("is_component") and
                             _normalize_cod(a.get("cod", "")) == norm_cod]
                if ref_comps:
                    ref_sub = ref_comps[0]
                    sub_diffs = compare_articles(ref_sub, oferta_art, include_prices=False)
                    for d in sub_diffs:
                        if d.get("camp") in ("cantitate", "um"):
                            _enrich(d, ref_sub, oferta_art,
                                    oferta_art.get("deviz", ""),
                                    oferta_art.get("deviz_denumire", ""))
                            neconformitati.append(d)
                continue
            # ref=component, offer=main article — structural reclassification, report it
            deviz_cod_e = oferta_art.get("deviz", "")
            deviz_den_e = oferta_art.get("deviz_denumire", "")
            nc_comp = {
                "tip": "DIFERENTA_CAMP",
                "camp": "tip_articol",
                "ref": "subcomponenta",
                "oferta": "articol_principal",
                "deviz_ref": deviz_cod_e,
                "deviz_denumire": deviz_den_e,
                "is_component": False,
                "ref_cod": oferta_art.get("cod", ""),
                "ref_denumire": "",
                "oferta_cod": oferta_art.get("cod", ""),
                "oferta_denumire": oferta_art.get("denumire", ""),
                "oferta_um": oferta_art.get("um", ""),
                "oferta_cantitate": oferta_art.get("cantitate", ""),
            }
            neconformitati.append(nc_comp)
            continue
        deviz_den = oferta_art.get("deviz_denumire", "")
        if "e Devize" in deviz_den:
            deviz_den = deviz_den.split("e Devize")[0].strip()
        elif len(deviz_den) > 100:
            deviz_den = deviz_den[:100]
        neconformitati.append({
            "tip": "ARTICOL_EXTRA",
            "deviz_ref": oferta_art.get("deviz", ""),
            "deviz_denumire": deviz_den,
            "is_component": oferta_art.get("is_component", False),
            "ref_cod": "", "ref_denumire": "",
            "oferta_cod": oferta_art.get("cod", ""),
            "oferta_denumire": oferta_art.get("denumire", ""),
            "oferta_um": oferta_art.get("um", ""),
            "oferta_cantitate": oferta_art.get("cantitate", ""),
            "oferta_display_parent_cod": oferta_art.get("display_parent_cod"),
            "nr_ordine_oferta": oferta_art.get("nr_ordine"),
        })

    # Post-processing: collapse ARTICOL_LIPSA + ARTICOL_EXTRA pairs where:
    # - cod similarity >= 0.80 (same article family, e.g. TRA01A35 ↔ TRA01A50)
    # - same cantitate (within 0.1%)
    # - same UM (normalized)
    # These are parametric substitutions (distance, height, etc.) missed by Layer 2.5
    # due to deviz_key mismatch or 1:1 oferta_map limitation.
    _lipsa_ncs = [nc for nc in neconformitati if nc.get('tip') == 'ARTICOL_LIPSA' and nc.get('ref_cod')]
    _extra_ncs = [nc for nc in neconformitati if nc.get('tip') == 'ARTICOL_EXTRA' and nc.get('oferta_cod')]
    _paired_ids: set = set()
    _pair_new_ncs: list = []
    _pair_new_matches: list = []

    for lipsa_nc in _lipsa_ncs:
        if id(lipsa_nc) in _paired_ids:
            continue
        lip_cod = lipsa_nc.get('ref_cod', '')
        lip_cant = lipsa_nc.get('ref_cantitate') or 0
        lip_um = _normalize_um(lipsa_nc.get('ref_um', ''))
        if not lip_cant:
            continue
        best_extra, best_cs = None, 0.0
        for extra_nc in _extra_ncs:
            if id(extra_nc) in _paired_ids:
                continue
            ex_cant = extra_nc.get('oferta_cantitate') or 0
            ex_um = _normalize_um(extra_nc.get('oferta_um', ''))
            if lip_um != ex_um:
                continue
            if abs(ex_cant - lip_cant) / max(abs(lip_cant), 1e-9) >= 0.001:
                continue
            cs = _cod_similarity(lip_cod, extra_nc.get('oferta_cod', ''))
            if cs >= 0.80 and cs > best_cs:
                best_cs, best_extra = cs, extra_nc
        if best_extra is None:
            continue
        _paired_ids.add(id(lipsa_nc))
        _paired_ids.add(id(best_extra))
        deviz_cod = lipsa_nc.get('deviz_ref', '')
        deviz_den = lipsa_nc.get('deviz_denumire', '')
        ex_cod = best_extra.get('oferta_cod', '')
        # Reconstruct article-like dicts for _enrich / _nc_parametru_diferit
        ref_art_proxy = {
            'cod': lip_cod, 'denumire': lipsa_nc.get('ref_denumire', ''),
            'um': lipsa_nc.get('ref_um', ''), 'cantitate': lip_cant,
            'deviz': deviz_cod, 'deviz_denumire': deviz_den,
            'is_component': lipsa_nc.get('is_component', False),
            'source_pages': lipsa_nc.get('ref_source_pages', []),
            'nr_ordine': lipsa_nc.get('nr_ordine_ref'),
            'parent_cod': lipsa_nc.get('parent_cod_ref'),
            'parent_nr_ordine': lipsa_nc.get('parent_nr_ordine_ref'),
            'display_parent_cod': lipsa_nc.get('display_parent_cod'),
            'cant_mostenita': lipsa_nc.get('cant_mostenita', False),
        }
        off_art_proxy = {
            'cod': ex_cod, 'denumire': best_extra.get('oferta_denumire', ''),
            'um': best_extra.get('oferta_um', ''), 'cantitate': ex_cant,
            'is_component': best_extra.get('is_component', False),
            'source_pages': best_extra.get('oferta_source_pages', []),
            'nr_ordine': best_extra.get('nr_ordine_oferta'),
            'display_parent_cod': best_extra.get('oferta_display_parent_cod'),
        }
        cod_sim_nc = {
            "tip": "COD_SIMILAR",
            "motiv_similaritate": f"Cod similar, cantitate identica: '{lip_cod}' ↔ '{ex_cod}'",
        }
        _enrich(cod_sim_nc, ref_art_proxy, off_art_proxy, deviz_cod, deviz_den)
        _pair_new_ncs.append(cod_sim_nc)
        nc_param = _nc_parametru_diferit(ref_art_proxy, off_art_proxy, deviz_cod, deviz_den)
        if nc_param:
            _pair_new_ncs.append(nc_param)
        _pair_new_matches.append({
            "ref_cod": lip_cod, "ref_denumire": lipsa_nc.get('ref_denumire', ''),
            "oferta_cod": ex_cod, "oferta_denumire": best_extra.get('oferta_denumire', ''),
        })

    if _paired_ids:
        neconformitati = [nc for nc in neconformitati if id(nc) not in _paired_ids]
        neconformitati.extend(_pair_new_ncs)
        matches.extend(_pair_new_matches)
        logger.info(f"[COMP] LIPSA+EXTRA collapse: {len(_pair_new_matches)} perechi → COD_SIMILAR")

    # Post-processing: Lenient UM matching for $ codes
    # If EXTRA code is a $ code and exists in reference with same deviz but empty UM,
    # convert from EXTRA to MATCHED with UM_DIFERIT nonconformity
    extra_dollar_count = len([n for n in neconformitati if n['tip']=='ARTICOL_EXTRA' and n.get('oferta_cod','').startswith('$')])
    logger.debug(f"[COMP] Post-processing: {extra_dollar_count} EXTRA $ codes to check")

    extra_to_remove = []
    for i, nc in enumerate(neconformitati):
        if nc['tip'] != 'ARTICOL_EXTRA':
            continue
        oferta_cod = nc.get('oferta_cod', '')
        if not oferta_cod.startswith('$'):
            continue

        deviz_ref = nc.get('deviz_ref', '')
        # Look for code in reference with same deviz but any UM (especially empty)
        # Use ref_articole (not ref_dedup) because dedup might have filtered articles
        found_in_ref = False
        ref_art = None
        for ref_article in ref_articole:
            if ref_article.get('cod') == oferta_cod and ref_article.get('deviz') == deviz_ref:
                # Found it in reference
                found_in_ref = True
                ref_art = ref_article
                break

        if found_in_ref and ref_art:
            # This $ code exists in reference with same deviz
            # If ref UM is empty, add UM_DIFERIT and mark as matched (remove EXTRA)
            ref_um = (ref_art.get('um') or '').strip()
            oferta_um = nc.get('oferta_um', '').strip()

            if oferta_um and ref_um != oferta_um:
                logger.debug(f"[COMP] UM mismatch on $ cod: {oferta_cod} (ref UM={ref_um!r}, oferta UM={oferta_um})")
                # Add UM_DIFERIT nonconformity
                neconformitati.append({
                    'tip': 'UM_DIFERIT',
                    'camp': 'um',
                    'deviz_ref': deviz_ref,
                    'deviz_denumire': nc.get('deviz_denumire', ''),
                    'ref_cod': oferta_cod,
                    'ref_denumire': ref_art.get('denumire', ''),
                    'ref_um': ref_um,
                    'oferta_cod': oferta_cod,
                    'oferta_denumire': nc.get('oferta_denumire', ''),
                    'oferta_um': oferta_um,
                })
                # Mark EXTRA for removal (will be matched)
                extra_to_remove.append(i)
                # Add to matches
                matches.append({
                    "ref_cod": oferta_cod,
                    "ref_denumire": nc.get('ref_denumire', ''),
                    "oferta_cod": oferta_cod,
                    "oferta_denumire": nc.get('oferta_denumire', ''),
                })

    logger.info(f"[COMP] Lenient UM matching: converted {len(extra_to_remove)} EXTRA to matched")
    # Remove EXTRAs that were converted to matches
    neconformitati = [nc for i, nc in enumerate(neconformitati) if i not in extra_to_remove]

    # Deduplicate non-conformities for the same (deviz, ref_cod, oferta_cod) pair
    # When same pair appears multiple times with different tips, keep only the primary one
    neconformitati = _deduplicate_neconformitati(neconformitati)

    logger.info(
        f"[COMP] matched={len(matches)}, "
        f"lipsa={len([n for n in neconformitati if n['tip']=='ARTICOL_LIPSA'])}, "
        f"extra={len([n for n in neconformitati if n['tip']=='ARTICOL_EXTRA'])}, "
        f"similar={len([n for n in neconformitati if n['tip']=='COD_SIMILAR'])}"
    )
    # Construieste setul cheilor REF match-uite pentru orphan detection
    matched_ref_keys = matched_oferta_keys | matched_by_llm_ref_keys
    return neconformitati, matches, matched_ref_keys, articole_fara_deviz
