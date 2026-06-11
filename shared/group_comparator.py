"""
Holistic group-based comparison.

Every article belongs to a deviz group (OBIECTIVUL + Obiectul + Categoria).
Groups matched 3-layer ref↔oferta. Unmatched ref → LIPSA. Unmatched oferta → EXTRA.
"""
from __future__ import annotations

import logging
import json
from pathlib import Path
from dataclasses import dataclass, field
from collections import defaultdict

try:
    from rapidfuzz import fuzz as _rfuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False

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


def _extract_obj_nr(hdr) -> str | None:
    """Extract 4-digit leading object code from obiectul (e.g. '0001' from '0001 Strada Zoica').

    Returns None if obiectul doesn't start with a 4-digit code — constraint not applied.
    """
    import re
    obiectul = (getattr(hdr, "obiectul", None) or "").strip()
    m = re.match(r"^(\d{4}\w?)\b", obiectul)
    return m.group(1) if m else None


def _match_by_rapidfuzz(
    remaining_ref: dict,
    remaining_oferta: dict,
    threshold: int = 85,
) -> list[tuple[str, str, str, str]]:
    """Phase 2a: RapidFuzz partial_token_set_ratio pe 'obiectul + categoria'.

    remaining_ref, remaining_oferta: dict[deviz_key, DevizHeader]
    Returnează [(ref_key, oferta_key, ref_den, oferta_den)] cu score >= threshold.
    """
    if not _RAPIDFUZZ_AVAILABLE or not remaining_ref or not remaining_oferta:
        return []

    matches = []
    used_oferta: set[str] = set()

    for rk, rh in sorted(remaining_ref.items()):
        ref_text = f"{rh.obiectul or ''} {rh.categoria or ''}".strip()
        if not ref_text:
            continue
        ref_obj_nr = _extract_obj_nr(rh)
        best_score, best_ok, best_oh = 0, "", None
        for ok, oh in sorted(remaining_oferta.items()):
            if ok in used_oferta:
                continue
            off_text = f"{oh.obiectul or ''} {oh.categoria or ''}".strip()
            if not off_text:
                continue
            # Skip cross-object matches when both sides have 4-digit object codes
            off_obj_nr = _extract_obj_nr(oh)
            if ref_obj_nr and off_obj_nr and ref_obj_nr != off_obj_nr:
                continue
            score = _rfuzz.partial_token_set_ratio(ref_text, off_text)
            if score > best_score:
                best_score, best_ok, best_oh = score, ok, oh
        if best_score >= threshold and best_ok:
            ref_den = _den_string(rh)
            oferta_den = _den_string(best_oh)
            matches.append((rk, best_ok, ref_den, oferta_den))
            used_oferta.add(best_ok)
            logger.info(
                f"[GC] RapidFuzz match (score={best_score}): "
                f"ref {rk[:8]} ↔ oferta {best_ok[:8]}"
            )
    return matches


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


_LLM_CHUNK_SIZE = 15  # max groups per LLM call — keeps response well under 2000 tokens


def _llm_match_groups(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client,
    llm_model: str,
) -> list[tuple[str, str, str, str]]:
    """LLM-assisted group matching. Returns [(ref_key, oferta_key, ref_den, oferta_den)].

    Splits into chunks of _LLM_CHUNK_SIZE when there are many unmatched groups,
    preventing token limit truncation on large offer documents.
    """
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

    ref_dens = list(ref_den_to_key)
    oferta_dens = list(oferta_den_to_key)
    result: list[tuple[str, str, str, str]] = []
    matched_ref: set[str] = set()
    matched_oferta: set[str] = set()

    # Chunk ref groups; send all oferta groups each time (match is N:M per chunk)
    for chunk_start in range(0, len(ref_dens), _LLM_CHUNK_SIZE):
        ref_chunk = [d for d in ref_dens[chunk_start:chunk_start + _LLM_CHUNK_SIZE]
                     if d not in matched_ref]
        oferta_remaining = [d for d in oferta_dens if d not in matched_oferta]
        if not ref_chunk or not oferta_remaining:
            break

        ref_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(ref_chunk))
        oferta_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(oferta_remaining))
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
                max_tokens=2000,
            )
            if not resp.choices:
                logger.warning("[GC] LLM group match: empty choices in response")
                continue
            parsed = json.loads(resp.choices[0].message.content)
        except Exception as e:
            logger.warning(f"[GC] LLM group match failed: {e}")
            continue

        _raw = parsed.get("matches", []) if isinstance(parsed, dict) else []
        for item in (_raw if isinstance(_raw, list) else []):
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
            if rk in matched_ref or ok in matched_oferta:
                continue
            result.append((rk, ok, ref_den, oferta_den))
            matched_ref.add(ref_den)
            matched_oferta.add(oferta_den)

    logger.info(f"[GC] LLM matched {len(result)} additional groups")
    return result


def _deviz_cod_prefix_match(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
) -> list[tuple[str, str]]:
    """Match ref group to offer group when ref.deviz_cod is a prefix of offer.categoria.

    Handles ISDP-style ref docs where the F3 header has 'Deviz oferta 226108 STRUCTURA...'
    and the offer has 'Stadiul fizic: 226108 STRUCTURA...' extracted as CATEGORIA.
    Example: ref deviz_cod='226108' matches offer categoria='226108 STRUCTURA DE REZISTENTA...'.
    """
    _MIN_COD_LEN = 4
    result: list[tuple[str, str]] = []
    matched_ref: set[str] = set()
    matched_oferta: set[str] = set()

    for ref_key in sorted(remaining_ref):
        rh = ref_deviz_headers.get(ref_key)
        if not rh or not rh.deviz_cod or len(rh.deviz_cod.strip()) < _MIN_COD_LEN:
            continue
        cod = rh.deviz_cod.strip()
        for oferta_key in sorted(remaining_oferta):
            if oferta_key in matched_oferta:
                continue
            oh = oferta_deviz_headers.get(oferta_key)
            if not oh or not oh.categoria:
                continue
            # Normalize offer CATEGORIA before prefix check:
            # - Strip "oferta " (ISDP format: "Deviz oferta 226108...")
            # - Strip leading page-number prefix like "001 " (eDevize multi-doc format)
            import re as _re
            cat = oh.categoria.strip()
            if cat.lower().startswith("oferta "):
                cat = cat[7:].strip()
            cat = _re.sub(r'^\d{1,3}\s+', '', cat)
            if cat.startswith(cod):
                result.append((ref_key, oferta_key))
                matched_ref.add(ref_key)
                matched_oferta.add(oferta_key)
                break
    if result:
        logger.info(f"[GC] deviz_cod prefix matched {len(result)} groups")
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


def _dedup_articles(arts: list) -> list:
    """Remove duplicate articles with identical (cod, um, cantitate) within a group."""
    seen = {}
    result = []
    for a in arts:
        key = (a.get("cod", ""), a.get("um", ""), a.get("cantitate", 0))
        if key not in seen:
            seen[key] = True
            result.append(a)
    return result


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


def _deviz_context(ref_arts: list, oferta_arts: list) -> str:
    """Build a human-readable context string for LLM prompts (group label)."""
    for arts in (ref_arts, oferta_arts):
        if not arts:
            continue
        hdr = arts[0].get("deviz_header", {})
        if hdr:
            parts = [hdr.get("obiectivul", ""), hdr.get("obiectul", ""), hdr.get("categoria", "")]
            ctx = " | ".join(p for p in parts if p)
            if ctx:
                return ctx
        den = arts[0].get("deviz_denumire", "")
        if den:
            return den
    return ""


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

    if llm_client and llm_model:
        from shared.semantic_comparator import semantic_nr_match, semantic_spec_check
        ctx = _deviz_context(ref_arts, oferta_arts)
        ncs = semantic_nr_match(ncs, ctx, llm_client, llm_model)
        spec_ncs = semantic_spec_check(matches, ref_arts, oferta_arts, ctx, llm_client, llm_model)
        ncs.extend(spec_ncs)

    return ncs, matches


def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
    client_name: str = "",
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

    match_type_for: dict[str, str] = {}
    full_mapping: dict[str, str] = {}
    for oferta_cod in oferta_cods:
        if oferta_cod in group_mapping:
            full_mapping[oferta_cod] = group_mapping[oferta_cod]
            match_type_for[oferta_cod] = "cross_3layer"
        elif oferta_cod in ref_cods:
            rh = ref_deviz_headers.get(oferta_cod)
            oh = oferta_deviz_headers.get(oferta_cod)
            if rh and oh and rh.is_valid and oh.is_valid:
                sim = _quick_3layer_sim(rh, oh)
                if sim >= _SAME_CODE_THRESHOLD:
                    full_mapping[oferta_cod] = oferta_cod
                    match_type_for[oferta_cod] = "same_code"
                else:
                    logger.info(
                        f"[GC] Acelasi cod {oferta_cod} dar continut DIFERIT "
                        f"(sim={sim:.2f} < {_SAME_CODE_THRESHOLD}) → oferta-only"
                    )
            else:
                full_mapping[oferta_cod] = oferta_cod
                match_type_for[oferta_cod] = "same_code"

    matched_ref_cods: set[str] = set()
    matched_oferta_cods: set[str] = set()
    _trace_matched: list = []

    for oferta_cod, ref_cod in sorted(full_mapping.items()):
        if ref_cod in matched_ref_cods:
            continue
        ref_arts = _dedup_articles(ref_by_deviz.get(ref_cod, []))
        of_arts = _dedup_articles(oferta_by_deviz.get(oferta_cod, []))
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
        _trace_matched.append({
            "ref_key": ref_cod,
            "oferta_key": oferta_cod,
            "match_type": match_type_for.get(oferta_cod, "same_code"),
            "ref_den": _den_string(ref_deviz_headers.get(ref_cod)),
            "oferta_den": _den_string(oferta_deviz_headers.get(oferta_cod)),
        })

    # Phase 2: knowledge + LLM for remaining unmatched groups.
    # Runs BEFORE ref_only/oferta_only population so those loops see final matched state.
    remaining_ref_keys = ref_cods - matched_ref_cods
    remaining_oferta_keys = oferta_cods - matched_oferta_cods

    def _run_secondary_match(pairs_with_type):
        """pairs_with_type: [(ref_key, oferta_key, match_type, ref_den, oferta_den)]"""
        for ref_key, oferta_key, mtype, ref_den, oferta_den in pairs_with_type:
            if ref_key in matched_ref_cods or oferta_key in matched_oferta_cods:
                continue
            r_arts = _dedup_articles(ref_by_deviz.get(ref_key, []))
            o_arts = _dedup_articles(oferta_by_deviz.get(oferta_key, []))
            ncs2, matches2 = _compare_articles_in_group(
                r_arts, o_arts, ref_key, llm_client, llm_model
            )
            r_hdr2 = ref_deviz_headers.get(ref_key)
            o_hdr2 = oferta_deviz_headers.get(oferta_key)
            den2 = _den_string(r_hdr2) or _den_string(o_hdr2)
            for nc in ncs2:
                nc["deviz_denumire"] = den2
            result.matched_groups.append({
                "ref_deviz_cod": ref_key,
                "oferta_deviz_cod": oferta_key,
                "ref_header": r_hdr2,
                "oferta_header": o_hdr2,
                "deviz_denumire": den2,
                "ref_articles": r_arts,
                "oferta_articles": o_arts,
                "neconformitati": ncs2,
                "matches": matches2,
            })
            matched_ref_cods.add(ref_key)
            matched_oferta_cods.add(oferta_key)
            _trace_matched.append({
                "ref_key": ref_key, "oferta_key": oferta_key,
                "match_type": mtype,
                "ref_den": ref_den,
                "oferta_den": oferta_den,
            })
            logger.info(f"[GC] {mtype.capitalize()} match: ref {ref_key} ↔ oferta {oferta_key}")

    if remaining_ref_keys and remaining_oferta_keys:
        # Phase 1.5: deviz_cod prefix match (deterministic, no LLM)
        cod_pairs = _deviz_cod_prefix_match(
            remaining_ref_keys, remaining_oferta_keys,
            ref_deviz_headers, oferta_deviz_headers,
        )
        _run_secondary_match([
            (rk, ok, "deviz_cod_prefix",
             _den_string(ref_deviz_headers.get(rk)),
             _den_string(oferta_deviz_headers.get(ok)))
            for rk, ok in cod_pairs
        ])
        remaining_ref_keys -= matched_ref_cods
        remaining_oferta_keys -= matched_oferta_cods

        # Knowledge phase (BEFORE RapidFuzz — knowledge is more reliable)
        knowledge_pairs = _apply_knowledge(
            remaining_ref_keys, remaining_oferta_keys,
            ref_deviz_headers, oferta_deviz_headers, client_name,
        )
        _run_secondary_match([
            (rk, ok, "knowledge", _den_string(ref_deviz_headers.get(rk)), _den_string(oferta_deviz_headers.get(ok)))
            for rk, ok in knowledge_pairs
        ])

        # Update remaining after Knowledge
        remaining_ref_keys -= matched_ref_cods
        remaining_oferta_keys -= matched_oferta_cods

        # Phase 2a: RapidFuzz (AFTER Knowledge — heuristic fallback before LLM)
        if remaining_ref_keys and remaining_oferta_keys:
            _remaining_ref_hdrs = {k: ref_deviz_headers[k] for k in remaining_ref_keys if k in ref_deviz_headers}
            _remaining_oferta_hdrs = {k: oferta_deviz_headers[k] for k in remaining_oferta_keys if k in oferta_deviz_headers}
            rf_pairs = _match_by_rapidfuzz(_remaining_ref_hdrs, _remaining_oferta_hdrs)
            _run_secondary_match([
                (rk, ok, "rapidfuzz", rd, od) for rk, ok, rd, od in rf_pairs
            ])
            # NOTE: Do NOT save RapidFuzz matches to knowledge — only LLM/human-verified pairs go there
            remaining_ref_keys -= matched_ref_cods
            remaining_oferta_keys -= matched_oferta_cods

        # Update remaining before LLM
        remaining_ref_keys -= matched_ref_cods
        remaining_oferta_keys -= matched_oferta_cods

        # LLM phase — skip when both sides use 4-digit numeric object codes.
        # In that case groups match deterministically by object number; LLM
        # cannot improve on knowledge + rapidfuzz and only wastes tokens.
        _skip_llm_numeric = False
        if remaining_ref_keys and remaining_oferta_keys:
            import re as _re2
            sample_ref = next(iter(remaining_ref_keys))
            rh_sample = ref_deviz_headers.get(sample_ref)
            obj_sample = (getattr(rh_sample, "obiectul", None) or "").strip()
            if _re2.match(r"^\d{4}", obj_sample):
                _skip_llm_numeric = True
                logger.info("[GC] Skipping LLM phase — numeric object codes detected (DT-style format)")
        _new_llm_pairs: list[dict] = []
        if remaining_ref_keys and remaining_oferta_keys and llm_client and not _skip_llm_numeric:
            llm_results = _llm_match_groups(
                remaining_ref_keys, remaining_oferta_keys,
                ref_deviz_headers, oferta_deviz_headers,
                llm_client, llm_model,
            )
            _run_secondary_match([
                (rk, ok, "llm", rd, od) for rk, ok, rd, od in llm_results
            ])
            _new_llm_pairs = [
                {"ref_den": rd, "oferta_den": od}
                for rk, ok, rd, od in llm_results
                if rk in matched_ref_cods  # only actually matched
            ]
        _save_knowledge(client_name, _new_llm_pairs)

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
    result.match_trace = {
        "ref_groups": [
            {"deviz_key": k, "den": _den_string(ref_deviz_headers.get(k)), "n_articles": len(ref_by_deviz.get(k, []))}
            for k in sorted(ref_cods)
        ],
        "oferta_groups": [
            {"deviz_key": k, "den": _den_string(oferta_deviz_headers.get(k)), "n_articles": len(oferta_by_deviz.get(k, []))}
            for k in sorted(oferta_cods)
        ],
        "matched": _trace_matched,
        "ref_only": [
            {"deviz_key": k, "den": _den_string(ref_deviz_headers.get(k)), "n_articles": len(ref_by_deviz.get(k, []))}
            for k in sorted(ref_cods - matched_ref_cods)
        ],
        "oferta_only": [
            {"deviz_key": k, "den": _den_string(oferta_deviz_headers.get(k)), "n_articles": len(oferta_by_deviz.get(k, []))}
            for k in sorted(oferta_cods - matched_oferta_cods)
        ],
    }
    return result
