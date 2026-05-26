"""
Holistic group-based comparison.

Every article belongs to a deviz group (OBIECTIVUL + Obiectul + Categoria).
Groups matched 3-layer ref↔oferta. Unmatched ref → LIPSA. Unmatched oferta → EXTRA.
"""
import logging
import json
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


def _den_string(hdr) -> str:
    """Canonical denomination for a DevizHeader: 'obj1 | obj2 | cat'."""
    if not hdr:
        return ""
    parts = [
        getattr(hdr, "obiectivul", None),
        getattr(hdr, "obiectul", None),
        getattr(hdr, "categoria", None),
    ]
    return " | ".join(p for p in parts if p)


_KNOWLEDGE_PATH = Path(__file__).parent / "group_match_knowledge.json"


def _apply_knowledge(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    client_name: str,
) -> list[tuple[str, str]]:
    """Return (ref_key, oferta_key) pairs from persisted knowledge for this client."""
    if not client_name or not remaining_ref or not remaining_oferta:
        return []
    try:
        knowledge = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    pairs = knowledge.get(client_name, [])
    if not pairs:
        return []
    ref_den_to_key = {
        _den_string(ref_deviz_headers.get(k)): k
        for k in remaining_ref
        if _den_string(ref_deviz_headers.get(k))
    }
    oferta_den_to_key = {
        _den_string(oferta_deviz_headers.get(k)): k
        for k in remaining_oferta
        if _den_string(oferta_deviz_headers.get(k))
    }
    result = []
    for p in pairs:
        rk = ref_den_to_key.get(p.get("ref_den", ""))
        ok = oferta_den_to_key.get(p.get("oferta_den", ""))
        if rk and ok:
            result.append((rk, ok))
    return result


def _save_knowledge(client_name: str, new_pairs: list[dict]) -> None:
    """Append new (ref_den, oferta_den) pairs to knowledge file, deduplicating."""
    if not client_name or not new_pairs:
        return
    try:
        knowledge = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        knowledge = {}
    existing = knowledge.get(client_name, [])
    seen = {(p.get("ref_den", ""), p.get("oferta_den", "")) for p in existing}
    for p in new_pairs:
        key = (p.get("ref_den", ""), p.get("oferta_den", ""))
        if key[0] and key[1] and key not in seen:
            existing.append({"ref_den": key[0], "oferta_den": key[1]})
            seen.add(key)
    knowledge[client_name] = existing
    _KNOWLEDGE_PATH.write_text(
        json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8"
    )


_LLM_GROUP_SYSTEM_PROMPT = (
    "Ești expert în devize de construcții românești.\n"
    "Mai jos sunt grupuri din REFERINȚĂ și OFERTĂ care nu s-au potrivit automat.\n"
    "Textele pot fi abreviate diferit pentru aceeași categorie. "
    "Pot fi de lungimi diferite, în schimb înseamnă același obiectiv sau obiect "
    "sau categorie de lucrări / stadiu fizic.\n\n"
    'Returnează JSON cu cheia "matches":\n'
    '{"matches": [{"ref": "<ref_den_exact>", "oferta": "<oferta_den_exact>"}]}\n\n'
    "Omite perechile nesigure. Dacă nu există nicio potrivire clară, returnează "
    '{"matches": []}.'
)


def _llm_match_groups(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client,
    llm_model: str,
) -> list[tuple[str, str, str, str]]:
    """LLM-assisted group matching. Returns [(ref_key, oferta_key, ref_den, oferta_den)]."""
    if not llm_client or not remaining_ref or not remaining_oferta:
        return []
    ref_den_to_key = {
        _den_string(ref_deviz_headers.get(k)): k
        for k in remaining_ref
        if _den_string(ref_deviz_headers.get(k))
    }
    oferta_den_to_key = {
        _den_string(oferta_deviz_headers.get(k)): k
        for k in remaining_oferta
        if _den_string(oferta_deviz_headers.get(k))
    }
    if not ref_den_to_key or not oferta_den_to_key:
        return []
    ref_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(ref_den_to_key))
    oferta_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(oferta_den_to_key))
    user_prompt = (
        f"REFERINȚĂ (grupuri nematched):\n{ref_list}\n\n"
        f"OFERTĂ (grupuri nematched):\n{oferta_list}"
    )
    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_GROUP_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1000,
        )
        if not resp.choices:
            logger.warning("[GC] LLM group match: empty choices in response")
            return []
        parsed = json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"[GC] LLM group match failed: {e}")
        return []
    _raw = parsed.get("matches", []) if isinstance(parsed, dict) else []
    pairs_raw = _raw if isinstance(_raw, list) else []
    result = []
    for item in pairs_raw:
        ref_den = item.get("ref", "")
        oferta_den = item.get("oferta", "")
        rk = ref_den_to_key.get(ref_den)
        ok = oferta_den_to_key.get(oferta_den)
        if not rk:
            logger.warning(f"[GC] LLM suggested unknown ref_den: {ref_den!r}")
            continue
        if not ok:
            logger.warning(f"[GC] LLM suggested unknown oferta_den: {oferta_den!r}")
            continue
        result.append((rk, ok, ref_den, oferta_den))
    logger.info(f"[GC] LLM matched {len(result)} additional groups")
    return result


@dataclass
class HolisticComparison:
    matched_groups: list = field(default_factory=list)
    ref_only_groups: list = field(default_factory=list)
    oferta_only_groups: list = field(default_factory=list)
    ungrouped: list = field(default_factory=list)
    unassigned_articles: list = field(default_factory=list)
    match_trace: dict = field(default_factory=dict)


def _articles_by_deviz(articles: list, unassigned_out: list | None = None) -> dict:
    """Grupeaza articolele dupa deviz_key (hash OBIECTIVUL+OBIECTUL+CATEGORIA).

    deviz_key e identificatorul canonic al grupului.
    Articles with __INCOMPLETE__ deviz_key sunt colectate in unassigned_out.
    """
    result = defaultdict(list)
    for a in articles:
        key = (a.get("deviz_key") or "").strip()
        if key and not key.startswith("__INCOMPLETE__"):
            result[key].append(a)
        else:
            cod = (a.get("deviz") or "").strip()
            if cod:
                if unassigned_out is not None:
                    unassigned_out.append(a)
                # NU adăugat în result → nu apare ca ref-only/oferta-only cu cheie ciudată
    return dict(result)


def _lipsa_neconf(art: dict, deviz_cod: str, deviz_den: str = "") -> dict:
    return {
        "tip": "ARTICOL_LIPSA",
        "deviz_ref": deviz_cod,
        "deviz_denumire": deviz_den,
        "ref_cod": art.get("cod", ""),
        "ref_denumire": art.get("denumire", ""),
        "ref_um": art.get("um", ""),
        "ref_cantitate": art.get("cantitate", 0),
        "nr_ordine_ref": art.get("nr_ordine", 0),
        "oferta_cod": "", "oferta_denumire": "", "oferta_um": "", "oferta_cantitate": "",
        # Metadata ierarhie — necesara pt afisarea parintelui in raport
        "is_component": art.get("is_component", False),
        "parent_cod_ref": art.get("parent_cod") or art.get("parent_code"),
        "display_parent_cod": art.get("display_parent_cod"),
        "ref_source_pages": art.get("source_pages", []),
        "oferta_source_pages": [],
        "nr_ordine_oferta": None,
    }


def _extra_neconf(art: dict, ref_deviz_cod: str = "", deviz_den: str = "") -> dict:
    return {
        "tip": "ARTICOL_EXTRA",
        "deviz_ref": ref_deviz_cod,
        "deviz_denumire": deviz_den,
        "oferta_cod": art.get("cod", ""),
        "oferta_denumire": art.get("denumire", ""),
        "oferta_um": art.get("um", ""),
        "oferta_cantitate": art.get("cantitate", 0),
        "ref_cod": "", "ref_denumire": "", "ref_um": "", "ref_cantitate": "",
        # Metadata ierarhie
        "is_component": art.get("is_component", False),
        "parent_cod_ref": art.get("parent_cod") or art.get("parent_code"),
        "display_parent_cod": art.get("display_parent_cod"),
        "ref_source_pages": [],
        "oferta_source_pages": art.get("source_pages", []),
        "nr_ordine_ref": None,
        "nr_ordine_oferta": art.get("nr_ordine", 0),
    }


def _compare_articles_in_group(
    ref_arts: list,
    oferta_arts: list,
    group_key: str,
    llm_client,
    llm_model: str,
) -> tuple[list, list]:
    if not ref_arts and not oferta_arts:
        return [], []
    if not ref_arts:
        ncs = [_extra_neconf(a, group_key) for a in oferta_arts if a.get("cantitate")]
        return ncs, []
    if not oferta_arts:
        ncs = [_lipsa_neconf(a, group_key) for a in ref_arts if a.get("cantitate")]
        return ncs, []
    from AgentComparator_local import match_global

    # match_global uses _art_key = (art["deviz"], cod_articol) for Stage-1 matching.
    # Architecture requires key = (deviz_key_hash, cod_articol) — not deviz_cod string.
    # Set art["deviz"] = art["deviz_key"] (hash) on all articles so _art_key
    # becomes (deviz_key_hash, cod_articol) = the canonical per-group identifier.
    # Oferta gets ref's deviz_key so both sides share the same hash → Stage-1 matches.
    ref_dkey = (ref_arts[0].get("deviz_key") or "").strip() if ref_arts else ""
    if ref_dkey:
        ref_arts   = [{**a, "deviz": ref_dkey} for a in ref_arts]
        oferta_arts = [{**a, "deviz": ref_dkey} for a in oferta_arts]

    ncs, matches, _, _ = match_global(
        ref_arts, oferta_arts, llm_client, llm_model or "", include_prices=False
    )

    # DEVIZ_MISMATCH is impossible within a single group — reclassify as ARTICOL_LIPSA.
    for nc in ncs:
        if nc.get("tip") == "DEVIZ_MISMATCH":
            nc["tip"] = "ARTICOL_LIPSA"
            nc.setdefault("oferta_cod", "")
            nc.setdefault("oferta_denumire", "")
            nc.setdefault("oferta_um", "")
            nc.setdefault("oferta_cantitate", "")

    return ncs, matches


def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
) -> HolisticComparison:
    """
    Holistic group-based comparison.

    Returns HolisticComparison with matched_groups, ref_only_groups,
    oferta_only_groups, ungrouped.
    """
    from shared.deviz_matcher import match_devize_by_3layer

    result = HolisticComparison()

    # Collect ungrouped articles
    ungrouped_ref = [a for a in ref_articles if not (a.get("deviz") or "").strip()]
    ungrouped_oferta = [a for a in oferta_articles if not (a.get("deviz") or "").strip()]
    result.ungrouped = (
        [{"source": "ref", **a} for a in ungrouped_ref] +
        [{"source": "oferta", **a} for a in ungrouped_oferta]
    )

    ref_valid = [a for a in ref_articles if (a.get("deviz") or "").strip()]
    oferta_valid = [a for a in oferta_articles if (a.get("deviz") or "").strip()]

    unassigned_ref: list = []
    unassigned_oferta: list = []
    ref_by_deviz = _articles_by_deviz(ref_valid, unassigned_out=unassigned_ref)
    oferta_by_deviz = _articles_by_deviz(oferta_valid, unassigned_out=unassigned_oferta)
    result.unassigned_articles = (
        [{"source": "ref", **a} for a in unassigned_ref] +
        [{"source": "oferta", **a} for a in unassigned_oferta]
    )

    ref_cods = set(ref_by_deviz.keys())
    oferta_cods = set(oferta_by_deviz.keys())

    # 3-layer group matching (cross-code: oferta_cod != ref_cod)
    group_mapping = match_devize_by_3layer(ref_deviz_headers, oferta_deviz_headers)

    # Build complete mapping: oferta_cod → ref_cod
    # Same-code devizes (oferta_cod == ref_cod) sunt verificate prin similitudine 3-layer
    # Daca similitudinea e slaba, NU sunt perechi (vor fi ref-only/oferta-only)
    from difflib import SequenceMatcher

    def _quick_3layer_sim(rh, oh) -> float:
        """Similitudine rapida intre doua DevizHeader-uri (0.0-1.0)."""
        import re as _re
        from shared.deviz_header_extractor import _normalize as _n

        def _norm(text: str) -> str:
            t = _n(text)
            # Strip ONLY zero-padded page prefix (ex: "001 ", "01 ", "003 ")
            # NOT chapter numbers ("3 ", "4 ") which are semantically significant
            t = _re.sub(r'^0\d{1,2}\s+', '', t)
            return t.strip()

        scores = []
        _MIN_OBJ2 = 0.80  # obj2 trebuie sa fie cel putin 80% similar
        _MIN_CAT  = 0.80  # categoria trebuie sa fie cel putin 80% similar
        pairs = [
            (rh.obiectivul, oh.obiectivul, 0.0),
            (rh.obiectul,   oh.obiectul,   _MIN_OBJ2),
            (rh.categoria,  oh.categoria,  _MIN_CAT),
        ]
        for a, b, min_s in pairs:
            if a and b:
                na, nb = _norm(a), _norm(b)
                if na and nb:
                    s = SequenceMatcher(None, na, nb).ratio()
                    if min_s > 0 and s < min_s:
                        return 0.0
                    scores.append(s)
        return sum(scores) / len(scores) if scores else 0.0

    _SAME_CODE_THRESHOLD = 0.75

    full_mapping: dict[str, str] = {}
    for oferta_cod in oferta_cods:
        if oferta_cod in group_mapping:
            # Cross-code match (3-layer)
            full_mapping[oferta_cod] = group_mapping[oferta_cod]
        elif oferta_cod in ref_cods:
            # Same code — verifica similitudinea continutului 3-layer
            rh = ref_deviz_headers.get(oferta_cod)
            oh = oferta_deviz_headers.get(oferta_cod)
            if rh and oh and rh.is_valid and oh.is_valid:
                sim = _quick_3layer_sim(rh, oh)
                if sim >= _SAME_CODE_THRESHOLD:
                    full_mapping[oferta_cod] = oferta_cod  # verificat OK
                else:
                    logger.info(
                        f"[GC] Acelasi cod {oferta_cod} dar continut DIFERIT "
                        f"(sim={sim:.2f} < {_SAME_CODE_THRESHOLD}) → oferta-only"
                    )
                    # Nu se adauga in full_mapping → va fi oferta-only
            else:
                # Nu putem verifica (header incomplet) → presupunem OK
                full_mapping[oferta_cod] = oferta_cod

    matched_ref_cods: set[str] = set()
    matched_oferta_cods: set[str] = set()

    for oferta_cod, ref_cod in sorted(full_mapping.items()):
        if ref_cod in matched_ref_cods:
            continue
        ref_arts = ref_by_deviz.get(ref_cod, [])
        of_arts = oferta_by_deviz.get(oferta_cod, [])
        ncs, matches = _compare_articles_in_group(
            ref_arts, of_arts, ref_cod, llm_client, llm_model
        )
        # Build deviz_denumire from header (3 elements, not hash)
        ref_hdr = ref_deviz_headers.get(ref_cod)
        oferta_hdr = oferta_deviz_headers.get(oferta_cod)

        deviz_den = _den_string(ref_hdr) or _den_string(oferta_hdr)
        # Fallback: use article's embedded deviz_header metadata
        if not deviz_den and ref_arts and ref_arts[0].get("deviz_header"):
            hdr_dict = ref_arts[0].get("deviz_header", {})
            parts = [hdr_dict.get("obiectivul", ""), hdr_dict.get("obiectul", ""), hdr_dict.get("categoria", "")]
            deviz_den = " | ".join(p for p in parts if p)
        if not deviz_den and of_arts and of_arts[0].get("deviz_header"):
            hdr_dict = of_arts[0].get("deviz_header", {})
            parts = [hdr_dict.get("obiectivul", ""), hdr_dict.get("obiectul", ""), hdr_dict.get("categoria", "")]
            deviz_den = " | ".join(p for p in parts if p)

        for nc in ncs:
            nc["deviz_denumire"] = deviz_den

        result.matched_groups.append({
            "ref_deviz_cod": ref_cod,
            "oferta_deviz_cod": oferta_cod,
            "ref_header": ref_hdr,
            "oferta_header": oferta_hdr,
            "deviz_denumire": deviz_den,
            "ref_articles": ref_arts,
            "oferta_articles": of_arts,
            "neconformitati": ncs,
            "matches": matches,
        })
        matched_ref_cods.add(ref_cod)
        matched_oferta_cods.add(oferta_cod)
        logger.info(f"[GC] Matched: ref {ref_cod} ↔ oferta {oferta_cod}")

    # Ref-only → LIPSA
    for ref_cod in sorted(ref_cods - matched_ref_cods):
        arts = ref_by_deviz.get(ref_cod, [])
        ref_hdr = ref_deviz_headers.get(ref_cod)
        deviz_den = ""
        if ref_hdr:
            parts = [ref_hdr.obiectivul, ref_hdr.obiectul, ref_hdr.categoria]
            deviz_den = " | ".join(p for p in parts if p)
        if not deviz_den and arts and arts[0].get("deviz_header"):
            hdr_dict = arts[0].get("deviz_header", {})
            parts = [hdr_dict.get("obiectivul", ""), hdr_dict.get("obiectul", ""), hdr_dict.get("categoria", "")]
            deviz_den = " | ".join(p for p in parts if p)
        ncs = [_lipsa_neconf(a, ref_cod, deviz_den) for a in arts if a.get("cantitate")]
        result.ref_only_groups.append({
            "ref_deviz_cod": ref_cod,
            "ref_header": ref_hdr,
            "deviz_denumire": deviz_den,
            "articles": arts,
            "neconformitati": ncs,
        })
        logger.info(f"[GC] Ref-only: {ref_cod} ({len(ncs)} LIPSA)")

    # Oferta-only → EXTRA
    for oferta_cod in sorted(oferta_cods - matched_oferta_cods):
        arts = oferta_by_deviz.get(oferta_cod, [])
        oferta_hdr = oferta_deviz_headers.get(oferta_cod)
        deviz_den = ""
        if oferta_hdr:
            parts = [oferta_hdr.obiectivul, oferta_hdr.obiectul, oferta_hdr.categoria]
            deviz_den = " | ".join(p for p in parts if p)
        if not deviz_den and arts and arts[0].get("deviz_header"):
            hdr_dict = arts[0].get("deviz_header", {})
            parts = [hdr_dict.get("obiectivul", ""), hdr_dict.get("obiectul", ""), hdr_dict.get("categoria", "")]
            deviz_den = " | ".join(p for p in parts if p)
        ncs = [_extra_neconf(a, "", deviz_den) for a in arts if a.get("cantitate")]
        result.oferta_only_groups.append({
            "oferta_deviz_cod": oferta_cod,
            "oferta_header": oferta_hdr,
            "deviz_denumire": deviz_den,
            "articles": arts,
            "neconformitati": ncs,
        })
        logger.info(f"[GC] Oferta-only: {oferta_cod} ({len(ncs)} EXTRA)")

    logger.info(
        f"[GC] Groups: {len(result.matched_groups)} matched, "
        f"{len(result.ref_only_groups)} ref-only, "
        f"{len(result.oferta_only_groups)} oferta-only, "
        f"{len(result.ungrouped)} ungrouped"
    )
    return result
