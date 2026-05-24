"""
Holistic group-based comparison.

Every article belongs to a deviz group (OBIECTIVUL + Obiectul + Categoria).
Groups matched 3-layer ref↔oferta. Unmatched ref → LIPSA. Unmatched oferta → EXTRA.
"""
import logging
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class HolisticComparison:
    matched_groups: list = field(default_factory=list)
    ref_only_groups: list = field(default_factory=list)
    oferta_only_groups: list = field(default_factory=list)
    ungrouped: list = field(default_factory=list)


def _articles_by_deviz(articles: list) -> dict:
    """Grupeaza articolele dupa deviz_key (hash OBIECTIVUL+OBIECTUL+CATEGORIA).

    deviz_key e identificatorul canonic al grupului.
    Fallback la deviz_cod pt articolele fara deviz_key valid.
    """
    result = defaultdict(list)
    for a in articles:
        key = (a.get("deviz_key") or "").strip()
        if key and not key.startswith("__INCOMPLETE__"):
            result[key].append(a)
        else:
            cod = (a.get("deviz") or "").strip()
            if cod:
                result[f"__cod__{cod}"].append(a)
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
    }


def _compare_articles_in_group(
    ref_arts: list,
    oferta_arts: list,
    deviz_cod: str,
    llm_client,
    llm_model: str,
) -> tuple[list, list]:
    if not ref_arts and not oferta_arts:
        return [], []
    if not ref_arts:
        ncs = [_extra_neconf(a, deviz_cod) for a in oferta_arts if a.get("cantitate")]
        return ncs, []
    if not oferta_arts:
        ncs = [_lipsa_neconf(a, deviz_cod) for a in ref_arts if a.get("cantitate")]
        return ncs, []
    from AgentComparator_local import match_global
    ncs, matches, _, _ = match_global(
        ref_arts, oferta_arts, llm_client, llm_model or "", include_prices=False
    )
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

    ref_by_deviz = _articles_by_deviz(ref_valid)
    oferta_by_deviz = _articles_by_deviz(oferta_valid)

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
            # Strip prefix numeric (ex: "001 ", "01 ", "003 ") pt robustete OCR
            t = _re.sub(r'^\d{1,3}\s+', '', t)
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
        result.matched_groups.append({
            "ref_deviz_cod": ref_cod,
            "oferta_deviz_cod": oferta_cod,
            "ref_header": ref_deviz_headers.get(ref_cod),
            "oferta_header": oferta_deviz_headers.get(oferta_cod),
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
        deviz_den = arts[0].get("deviz_denumire", "") if arts else ""
        ncs = [_lipsa_neconf(a, ref_cod, deviz_den) for a in arts if a.get("cantitate")]
        result.ref_only_groups.append({
            "ref_deviz_cod": ref_cod,
            "ref_header": ref_deviz_headers.get(ref_cod),
            "articles": arts,
            "neconformitati": ncs,
        })
        logger.info(f"[GC] Ref-only: {ref_cod} ({len(ncs)} LIPSA)")

    # Oferta-only → EXTRA
    for oferta_cod in sorted(oferta_cods - matched_oferta_cods):
        arts = oferta_by_deviz.get(oferta_cod, [])
        deviz_den = arts[0].get("deviz_denumire", "") if arts else ""
        ncs = [_extra_neconf(a, "", deviz_den) for a in arts if a.get("cantitate")]
        result.oferta_only_groups.append({
            "oferta_deviz_cod": oferta_cod,
            "oferta_header": oferta_deviz_headers.get(oferta_cod),
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
