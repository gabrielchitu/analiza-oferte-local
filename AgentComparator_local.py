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

logger = logging.getLogger(__name__)


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
    return cleaned


def _normalize_cod(cod: str) -> str:
    """
    DEPRECATED: Use clean_code() instead for general code cleaning.

    This function applies aggressive transformations that break valid codes.
    Kept for backward compatibility with Layer 2 fuzzy matching only.
    """
    cod = (cod or "").strip().upper()
    # OCR fix: lowercase 'l' often confused with digit '1'
    cod = cod.replace('l', '1').replace('L', '1')
    # OCR fix: letter 'I' often confused with digit '1' — normalize I to 1
    # SA13I# vs SA131# should be treated as identical
    cod = cod.replace('I', '1')
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
    # Coduri normative utilaj cu sufix pur numeric (AUT6753, CMP1234 etc.):
    # unele oferte omit prefixul si scriu doar numarul (6753 → $6753).
    # Normalizare: AUT6753 → $6753 = identic cu $6753 din oferta.
    m_util = re.match(r'^[A-Z]{2,5}(\d{4,5})$', cod)
    if m_util:
        return '$' + m_util.group(1)
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

    Uses (deviz_code, cleaned_cod) where cleaned_cod removes artifact characters.
    This ensures codes like CK01A01^ and CK01A01 match correctly.
    """
    return (_deviz_key(art), clean_code(art.get("cod") or ""))


def _deduplicate_neconformitati(neconformitati: list) -> list:
    """
    Remove duplicate non-conformities for the same (deviz, ref_cod, oferta_cod) pair.

    When the same article pair appears multiple times with different issue types,
    keep only the primary (most important) one. Priority order:
    1. COD_SIMILAR (code difference detected)
    2. ARTICOL_ORPHAN (article in wrong deviz)
    3. Others (DIFERENTA_CAMP, etc)

    This handles cases like:
    - ref $3274270 ↔ oferta $32742701: reported as both COD_SIMILAR + DIFERENTA_CAMP
    - Should keep only COD_SIMILAR (the root cause), discard DIFERENTA_CAMP
    """
    if not neconformitati:
        return neconformitati

    # Priority map for issue types (higher number = higher priority, kept)
    priority = {
        'COD_SIMILAR': 3,
        'ARTICOL_ORPHAN': 2,
        'DIFERENTA_CAMP': 1,
        'UM_DIFERIT': 1,
        'ARTICOL_LIPSA': 0,
        'ARTICOL_EXTRA': 0,
    }

    # Group by (deviz, ref_cod, oferta_cod)
    seen = {}
    result = []

    for nc in neconformitati:
        deviz = nc.get('deviz', '')
        ref_cod = nc.get('ref_cod', '')
        oferta_cod = nc.get('oferta_cod', '')
        tip = nc.get('tip', '')
        key = (deviz, ref_cod, oferta_cod)

        if key not in seen:
            # First occurrence: add and track
            seen[key] = (tip, nc)
            result.append(nc)
        else:
            # Seen before: keep only if this has higher priority
            prev_tip, prev_nc = seen[key]
            curr_priority = priority.get(tip, 0)
            prev_priority = priority.get(prev_tip, 0)

            if curr_priority > prev_priority:
                # Replace with higher priority
                result.remove(prev_nc)
                seen[key] = (tip, nc)
                result.append(nc)
            # else: keep the previous one (already higher or equal priority)

    return result


def _should_match_cant_um(article: dict, comp_mode: str = 'strict') -> bool:
    """
    Determine if article should be matched on (cod, cant, UM).

    Returns False for subcomponents with missing cant/UM in lenient mode,
    allowing them to match by code only.

    Args:
        article: Article dict to check
        comp_mode: 'strict' (always validate cant+UM) or 'lenient' (code-only for incomplete subcomponents)

    Returns:
        True if cant+UM should be validated, False if code-only match is acceptable
    """
    is_subcomp = article.get('is_component', False)
    has_cant = article.get('cantitate', 0) != 0
    has_um = bool(article.get('um', '').strip())

    # In strict mode, always validate cant+UM
    if comp_mode == 'strict':
        return True

    # In lenient mode: if subcomponent lacks cant or UM, skip cant+UM validation
    if is_subcomp and (not has_cant or not has_um):
        return False

    # Otherwise validate normally
    return True


def match_global(
    ref_articole: list,
    oferta_articole: list,
    openai_client,
    deployment: str,
    include_prices: bool = False,
    comp_mode: str = 'strict',
) -> tuple:
    """
    3-layer matching (Layer 1 exact, Layer 2 normalized, Layer 2.5 cross-deviz, Layer 3 LLM).
    Returns (neconformitati, matches).

    Identic cu _match_global din AgentComparator/core.py dar fara dependente Azure.
    include_prices=False implicit — pentru comparare fara preturi.
    comp_mode: 'strict' (validate cant+UM for all) or 'lenient' (code-only for incomplete subcomponents)
    """
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

    ref_component_cods = {_normalize_cod(a.get("cod", ""))
                          for a in ref_articole if a.get("is_component")}

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

    neconformitati = []
    matches = []
    matched_oferta_keys = set()
    matched_by_llm_ref_keys: set = set()
    unmatched_ref = []
    extra_from_nm: list = []  # instanțe oferta în exces față de ref (N:M)

    # Layer 1: N:M exact match pe (deviz, cod) — sortate după cantitate, perechi în ordine.
    # ref(34.2)↔oferta(34.2), ref(40.0)↔oferta(40.0); excesul → LIPSA/EXTRA.
    # In lenient mode: subcomponents with missing cant/UM can match by code alone.
    for key, ref_list in ref_by_key.items():
        oferta_list = oferta_by_key.get(key, [])
        deviz_cod = ref_list[0].get("deviz", "")
        deviz_den = ref_list[0].get("deviz_denumire", "")

        if not oferta_list:
            unmatched_ref.extend(ref_list)
            continue

        matched_oferta_keys.add(key)

        # Check if we need strict cant+UM matching or can allow code-only match for subcomponents
        # Split into two groups: those needing cant+UM match vs those that can match by code only
        ref_strict = []  # articles requiring cant+UM match
        ref_lenient = []  # subcomponents that can match by code only

        for ref_art in ref_list:
            if _should_match_cant_um(ref_art, comp_mode):
                ref_strict.append(ref_art)
            else:
                ref_lenient.append(ref_art)

        # Process strict-mode references (normal N:M by cant)
        for ref_art, oferta_art in zip(ref_strict, oferta_list[:len(ref_strict)]):
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

        # Process lenient-mode references (subcomponents with incomplete data)
        # These can match by code only, consuming remaining offer articles
        remaining_oferta = oferta_list[len(ref_strict):]
        for ref_art, oferta_art in zip(ref_lenient, remaining_oferta):
            # Code-only match for subcomponents in lenient mode
            # For incomplete subcomponents, skip cant+UM validation (they can differ)
            # Only check price/arithmetic
            diffs = compare_articles(ref_art, oferta_art, include_prices=include_prices)
            # Filter out UM_DIFERIT (tip) and cantitate field differences
            diffs = [d for d in diffs if d.get('tip') != 'UM_DIFERIT' and d.get('camp') != 'cantitate']
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

        # Unmatched references (strict requiring exact match + lenient requiring code match)
        total_matched = min(len(ref_list), len(oferta_list))
        unmatched_ref.extend(ref_list[total_matched:])
        # Exces oferta → ARTICOL_EXTRA
        extra_from_nm.extend(oferta_list[total_matched:])

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
            if ref_cod != original_oferta_cod and (diffs or arith):
                neconf = {
                    "tip": "COD_SIMILAR",
                    "motiv_similaritate": f"Cod similar: referinta '{ref_cod}', ofertat '{original_oferta_cod}'",
                }
                _enrich(neconf, ref_art, oferta_art, deviz_cod, deviz_den)
                neconformitati.append(neconf)
            for d in diffs + arith:
                _enrich(d, ref_art, oferta_art, deviz_cod, deviz_den)
            neconformitati.extend(diffs + arith)
            matches.append({
                "ref_cod": ref_cod,
                "ref_denumire": ref_art.get("denumire", ""),
                "oferta_cod": original_oferta_cod,
                "oferta_denumire": oferta_art.get("denumire", ""),
            })
        # Exces ref → LIPSA, exces oferta → EXTRA
        still_unmatched_ref.extend(ref_list[len(oferta_list):])
        extra_from_nm.extend(oferta_list[len(ref_list):])


    # Layer 3: LLM fuzzy match per grup deviz
    if still_unmatched_ref and unmatched_oferta_keys:
        ref_by_deviz = defaultdict(list)
        for a in still_unmatched_ref:
            ref_by_deviz[_deviz_key(a)].append(a)

        oferta_by_deviz = defaultdict(list)
        for ok in unmatched_oferta_keys:
            oferta_by_deviz[ok[0]].append(oferta_map[ok])

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
                best_art, best_score = None, 0.0
                for of_art in oferta_cands:
                    if id(of_art) in det_matched_oferta_arts:
                        continue
                    cs = _cod_similarity(ref_cod, of_art.get("cod", ""))
                    if cs < _SIM_DET:
                        continue
                    dj = _denom_jaccard(ref_art.get("denumire", ""),
                                        of_art.get("denumire", ""))
                    score = cs * 0.6 + dj * 0.4
                    if score > best_score:
                        best_score, best_art = score, of_art
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
                if diffs:
                    neconf = {
                        "tip": "COD_SIMILAR",
                        "motiv_similaritate": (
                            f"Cod similar (OCR): '{ref_cod}' ↔ '{best_art.get('cod','')}'"
                        ),
                    }
                    _enrich(neconf, ref_art, best_art, deviz_cod, deviz_den)
                    neconformitati.append(neconf)
                for d in diffs:
                    _enrich(d, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.extend(diffs)
                matches.append({
                    "ref_cod": ref_cod,
                    "ref_denumire": ref_art.get("denumire", ""),
                    "oferta_cod": best_art.get("cod", ""),
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
            if diffs:
                neconf = {
                    "tip": "COD_SIMILAR",
                    "motiv_similaritate": (
                        f"Cod diferit (produs echivalent): '{ref_cod}' ↔ '{best_art.get('cod','')}'"
                    ),
                }
                _enrich(neconf, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.append(neconf)
                for d in diffs:
                    _enrich(d, ref_art, best_art, deviz_cod, deviz_den)
                neconformitati.extend(diffs)
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
                        "motiv_similaritate": fp.get("motiv", "Cod similar identificat automat"),
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

    # ARTICOL_EXTRA — instante neacoperite din oferta (chei nemat-uite + exces N:M)
    # But first, try to fuzzy match by denomination
    from difflib import SequenceMatcher

    def _normalize_denom(s):
        return (s or "").lower().strip()

    def _denom_similarity(d1, d2):
        """Fuzzy match denomination strings."""
        n1 = _normalize_denom(d1)
        n2 = _normalize_denom(d2)
        if not n1 or not n2 or len(n1) < 3 or len(n2) < 3:
            return 0.0
        return SequenceMatcher(None, n1, n2).ratio()

    extras_to_report = [a for k in unmatched_oferta_keys for a in oferta_by_key[k]] + extra_from_nm

    # Try fuzzy matching extras to reference by denomination
    fuzzy_matched = set()
    for oferta_art in extras_to_report:
        oferta_cod = oferta_art.get("cod", "")
        oferta_denom = oferta_art.get("denumire", "")

        if not oferta_denom or len(oferta_denom) < 3:
            continue

        # Find best denomination match in reference
        best_match = None
        best_score = 0
        for ref_art in ref_dedup:
            ref_denom = ref_art.get("denumire", "")
            if not ref_denom:
                continue
            score = _denom_similarity(oferta_denom, ref_denom)
            if score > best_score:
                best_score = score
                best_match = ref_art

        # If fuzzy match found with reasonable score, mark as match instead of extra
        if best_match and best_score >= 0.45:  # Threshold: 45% similarity
            fuzzy_matched.add(id(oferta_art))
            match = {
                "ref_cod": best_match.get("cod", ""),
                "ref_denom": best_match.get("denumire", ""),
                "oferta_cod": oferta_cod,
                "oferta_denom": oferta_denom,
                "fuzzy_match_score": best_score,
                "deviz": oferta_art.get("deviz", ""),
            }
            matches.append(match)
            logger.debug(f"[FUZZ] Fuzzy matched by denom: {oferta_cod} → {best_match.get('cod', '')} (score={best_score:.2f})")

    for oferta_art in extras_to_report:
        if id(oferta_art) in fuzzy_matched:
            continue  # Skip, already fuzzy matched

        norm_cod = _normalize_cod(oferta_art.get("cod", ""))
        if norm_cod in ref_component_cods:
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
        })

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
    return neconformitati, matches, matched_ref_keys
