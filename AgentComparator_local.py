"""
AgentComparator_local.py — Logica de matching extrasa din AgentComparator/core.py.

Fara dependente Azure (fara BlobServiceClient, TableServiceClient, Queue, HTTP).
Folosit de local_run.py.

Sursa: func-analiza-oferte/AgentComparator/core.py (functiile de matching)
"""
import logging
import re
from collections import defaultdict

from shared.comparator import compare_articles, check_arithmetic
from shared.article_matcher import match_unmatched_global

logger = logging.getLogger(__name__)


def _normalize_cod(cod: str) -> str:
    """
    Extrage codul de baza, ignorand sufixele OCR/variante (#, -, @, ASIM etc.).
    Breviar propriu ($01063) — pastreaza prefixul $ + digits.
    Cod normativ (SA14B#, RPCR21A#-) — extrage doar baza standard.
    Handles OCR confusion: lowercase 'l' (letter L) → '1' (digit one).
    OCR confusion: letter 'O' → '0' (digit zero) and vice versa.
    """
    cod = (cod or "").strip().upper()
    # OCR fix: lowercase 'l' often confused with digit '1'
    cod = cod.replace('l', '1').replace('L', '1')
    # OCR fix: letter 'O' often confused with digit '0' — normalize to '0'
    # IZDO4D1 → IZD04D1 (O becomes 0 in PDF)
    cod = cod.replace('O', '0')
    if cod.startswith('$'):
        num = re.sub(r'[^0-9]', '', cod[1:])  # extrage doar cifrele
        if len(num) >= 8:
            # Codurile de breviar au max 7 cifre; 8+ cifre = cifra OCR in plus → trunchiaza
            num = num[:7]
        return '$' + num if num else cod
    if re.match(r'^\d+$', cod):
        return '$' + cod
    # Caracterele speciale (#, @, -, etc.) sunt artefacte software/OCR — stripuim.
    # Codurile valide contin NUMAI [A-Z0-9]. Nu inlocuim # cu 1 (da cod gresit).
    m = re.match(r'^([A-Z]{2,5}\d{2,4}[A-Z]?\d{0,2})', cod)
    return m.group(1) if m else re.sub(r'[^A-Z0-9]', '', cod)


def _enrich(neconf: dict, ref_art: dict, oferta_art: dict,
            deviz_cod_ref: str, deviz_den: str) -> dict:
    """Adauga campuri de context la o neconformitate."""
    neconf.update({
        "deviz_ref": deviz_cod_ref,
        "deviz_denumire": deviz_den,
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

    Uses deviz code (numeric ID like '226108') as primary key.
    deviz_denumire (name) varies due to OCR differences and formatting.
    Using denomination as key causes matching to fail when same article
    appears in same deviz section with slightly different OCR text.
    """
    # Primary: use deviz code (reliable, numeric) - normalized for OCR variations
    deviz_cod = (art.get("deviz") or "").strip()
    if deviz_cod:
        return _normalize_deviz_code(deviz_cod)

    # Fallback: use normalized denomination if no code
    raw = (art.get("deviz_denumire") or "").strip().upper()
    raw = re.sub(r'^(\d+\s+)+', '', raw).strip()
    raw = re.sub(r'\b(OB|NR|CAP|ART)[\s.]*(\d+)', r'\1\2', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw


def _art_key(art: dict) -> tuple:
    """Cheia compusa (deviz, cod) pentru un articol.

    Now uses (deviz_code, cod) which is reliable and matches across
    reference and oferta without OCR variation issues.
    """
    return (_deviz_key(art), (art.get("cod") or "").strip())


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
    # Deduplicate by 4-tuple (deviz, cod, um, cantitate) before matching
    # If same article appears multiple times with identical values, keep first occurrence
    ref_seen = {}
    ref_dedup = []
    for a in ref_articole:
        if a.get("cod") and not a.get("is_component"):
            key = (a.get("deviz"), a.get("cod"), a.get("um"), a.get("cantitate"))
            if key not in ref_seen:
                ref_dedup.append(a)
                ref_seen[key] = True

    oferta_seen = {}
    oferta_dedup = []
    for a in oferta_articole:
        if a.get("cod"):
            key = (a.get("deviz"), a.get("cod"), a.get("um"), a.get("cantitate"))
            if key not in oferta_seen:
                oferta_dedup.append(a)
                oferta_seen[key] = True

    ref_map = {_art_key(a): a for a in ref_dedup}
    ref_component_cods = {_normalize_cod(a.get("cod", ""))
                          for a in ref_articole if a.get("is_component")}
    oferta_map = {_art_key(a): a for a in oferta_dedup}

    neconformitati = []
    matches = []
    matched_oferta_keys = set()
    matched_by_llm_ref_keys: set = set()
    unmatched_ref = []

    # Layer 1: Exact match pe (deviz, cod)
    for ref_key, ref_art in ref_map.items():
        deviz_cod = ref_art.get("deviz", "")
        deviz_den = ref_art.get("deviz_denumire", "")
        if ref_key in oferta_map:
            oferta_art = oferta_map[ref_key]
            matched_oferta_keys.add(ref_key)
            diffs = compare_articles(ref_art, oferta_art, include_prices=include_prices)
            arith = check_arithmetic(oferta_art) if include_prices else []
            for d in diffs + arith:
                _enrich(d, ref_art, oferta_art, deviz_cod, deviz_den)
            neconformitati.extend(diffs + arith)
            matches.append({
                "ref_cod": ref_art.get("cod", ""),
                "ref_denumire": ref_art.get("denumire", ""),
                "oferta_cod": oferta_art.get("cod", ""),
                "oferta_denumire": oferta_art.get("denumire", ""),
            })
        else:
            unmatched_ref.append(ref_art)

    # Layer 2: Normalized match pe (deviz, normalize(cod))
    unmatched_oferta_keys = set(oferta_map.keys()) - matched_oferta_keys
    norm_to_oferta_key = {}
    for ok in unmatched_oferta_keys:
        deviz, cod = ok
        norm = (deviz, _normalize_cod(cod))
        if norm not in norm_to_oferta_key:
            norm_to_oferta_key[norm] = ok

    still_unmatched_ref = []
    for ref_art in unmatched_ref:
        ref_cod = ref_art.get("cod", "")
        deviz_cod = ref_art.get("deviz", "")
        deviz_den = ref_art.get("deviz_denumire", "")
        norm_key = (deviz_cod, _normalize_cod(ref_cod))
        if norm_key in norm_to_oferta_key:
            original_oferta_key = norm_to_oferta_key[norm_key]
            oferta_art = oferta_map[original_oferta_key]
            original_oferta_cod = oferta_art.get("cod", "")
            matched_oferta_keys.add(original_oferta_key)
            unmatched_oferta_keys.discard(original_oferta_key)
            del norm_to_oferta_key[norm_key]
            neconf = {
                "tip": "COD_SIMILAR",
                "motiv_similaritate": f"Cod similar: referinta '{ref_cod}', ofertat '{original_oferta_cod}'",
            }
            _enrich(neconf, ref_art, oferta_art, deviz_cod, deviz_den)
            neconformitati.append(neconf)
            diffs = compare_articles(ref_art, oferta_art, include_prices=include_prices)
            arith = check_arithmetic(oferta_art) if include_prices else []
            for d in diffs + arith:
                _enrich(d, ref_art, oferta_art, deviz_cod, deviz_den)
            neconformitati.extend(diffs + arith)
            matches.append({
                "ref_cod": ref_cod,
                "ref_denumire": ref_art.get("denumire", ""),
                "oferta_cod": original_oferta_cod,
                "oferta_denumire": oferta_art.get("denumire", ""),
            })
        else:
            still_unmatched_ref.append(ref_art)


    # Layer 3: LLM fuzzy match per grup deviz
    if still_unmatched_ref and unmatched_oferta_keys:
        ref_by_deviz = defaultdict(list)
        for a in still_unmatched_ref:
            ref_by_deviz[_deviz_key(a)].append(a)

        oferta_by_deviz = defaultdict(list)
        for ok in unmatched_oferta_keys:
            oferta_by_deviz[ok[0]].append(oferta_map[ok])

        deviz_groups = sorted(ref_by_deviz.keys(), key=lambda d: ("" if d else "\xff"))

        matched_by_llm_ref_keys = set()
        for deviz in deviz_groups:
            ref_batch = ref_by_deviz[deviz]
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
                neconf = {
                    "tip": "COD_SIMILAR",
                    "motiv_similaritate": fp.get("motiv", "Cod similar identificat automat"),
                }
                _enrich(neconf, ref_art, oferta_art, deviz_val, deviz_den)
                neconformitati.append(neconf)
                matches.append({
                    "ref_cod": fp_ref_cod,
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": fp_oferta_cod,
                    "oferta_denumire": oferta_art.get("denumire", ""),
                })

        still_unmatched_ref = [a for a in still_unmatched_ref
                               if _art_key(a) not in matched_by_llm_ref_keys]

    # ARTICOL_LIPSA
    for ref_art in still_unmatched_ref:
        deviz_cod = ref_art.get("deviz", "")
        deviz_den = ref_art.get("deviz_denumire", "")
        neconf = {
            "tip": "ARTICOL_LIPSA",
            "oferta_cod": "", "oferta_denumire": "", "oferta_um": "", "oferta_cantitate": "",
        }
        _enrich(neconf, ref_art, {}, deviz_cod, deviz_den)
        neconformitati.append(neconf)

    # ARTICOL_EXTRA
    for oferta_key in unmatched_oferta_keys:
        oferta_art = oferta_map[oferta_key]
        norm_cod = _normalize_cod(oferta_art.get("cod", ""))
        if norm_cod in ref_component_cods:
            continue
        # Extract deviz_denumire, truncate if OCR garbage (usually starts with "ARHITECTURA..." but may be followed by "e Devize Formular...")
        deviz_den = oferta_art.get("deviz_denumire", "")
        # Truncate at "e Devize" boundary (OCR garbage starts there)
        if "e Devize" in deviz_den:
            deviz_den = deviz_den.split("e Devize")[0].strip()
        elif len(deviz_den) > 100:
            # Fallback: truncate long strings
            deviz_den = deviz_den[:100]
        neconformitati.append({
            "tip": "ARTICOL_EXTRA",
            "deviz_ref": oferta_art.get("deviz", ""),
            "deviz_denumire": deviz_den,
            "ref_cod": "", "ref_denumire": "",
            "oferta_cod": oferta_art.get("cod", ""),
            "oferta_denumire": oferta_art.get("denumire", ""),
            "oferta_um": oferta_art.get("um", ""),
            "oferta_cantitate": oferta_art.get("cantitate", ""),
        })

    logger.info(
        f"[COMP] matched={len(matches)}, "
        f"lipsa={len([n for n in neconformitati if n['tip']=='ARTICOL_LIPSA'])}, "
        f"extra={len([n for n in neconformitati if n['tip']=='ARTICOL_EXTRA'])}, "
        f"similar={len([n for n in neconformitati if n['tip']=='COD_SIMILAR'])}"
    )
    # Construieste setul cheilor REF match-uite pentru orphan detection
    matched_ref_keys = matched_oferta_keys | matched_by_llm_ref_keys
    return neconformitati, matches, matched_ref_keys
