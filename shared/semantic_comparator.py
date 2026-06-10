# shared/semantic_comparator.py
"""
Semantic article comparator — two LLM passes for NC types invisible to code matching.

Pass 1 (semantic_nr_match): LIPSA+EXTRA pairs at same nr_ordine with different codes.
Pass 2 (semantic_spec_check): Already-matched same-code pairs where denominations
  differ significantly from a construction domain specialist perspective.
"""
import json
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

_PASS1_SYSTEM = (
    "Ești specialist în proiectare și execuție lucrări de construcții"
    " (clădiri, drumuri, instalații electrice, sanitare, HVAC)."
    " Răspunde STRICT JSON, fără text în afara JSON."
)

_PASS2_SYSTEM = (
    "Ești specialist în proiectare și execuție lucrări de construcții"
    " (clădiri, drumuri, instalații electrice, sanitare, HVAC)."
    " Răspunde STRICT JSON, fără text în afara JSON."
)


def _normalize_den(s: str) -> str:
    s = unicodedata.normalize("NFD", (s or "").lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s).strip()


def _jaccard(a: str, b: str) -> float:
    wa = set(re.sub(r"[^a-z0-9]", " ", _normalize_den(a)).split())
    wb = set(re.sub(r"[^a-z0-9]", " ", _normalize_den(b)).split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _numeric_tokens(s: str) -> set:
    return set(re.findall(r"\d+(?:[.,]\d+)?", (s or "")))


def _llm_json(llm_client, llm_model: str, system: str, user: str) -> dict:
    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=500,
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"[SEM] LLM call failed: {e}")
        return {}


def semantic_nr_match(ncs: list, deviz_context: str, llm_client, llm_model: str) -> list:
    """Replace LIPSA+EXTRA pairs at same nr_ordine with COD_NORMATIV_DIFERIT where LLM confirms."""
    main_lipsa = [
        nc for nc in ncs
        if nc.get("tip") == "ARTICOL_LIPSA"
        and not nc.get("is_component")
        and nc.get("nr_ordine_ref") is not None
    ]
    main_extra = [
        nc for nc in ncs
        if nc.get("tip") == "ARTICOL_EXTRA"
        and not nc.get("is_component")
        and nc.get("nr_ordine_oferta") is not None
    ]
    lipsa_by_nr = {nc["nr_ordine_ref"]: nc for nc in main_lipsa}
    extra_by_nr = {nc["nr_ordine_oferta"]: nc for nc in main_extra}
    shared_nrs = set(lipsa_by_nr) & set(extra_by_nr)

    if not shared_nrs:
        return ncs

    to_remove: set[int] = set()
    new_ncs: list[dict] = []

    for nr in sorted(shared_nrs):
        lipsa_nc = lipsa_by_nr[nr]
        extra_nc = extra_by_nr[nr]
        user = (
            f"Context deviz: {deviz_context}\n\n"
            f"REFERINȚĂ: NR={nr} | Cod={lipsa_nc.get('ref_cod','')} | "
            f"\"{lipsa_nc.get('ref_denumire','')}\" | {lipsa_nc.get('ref_um','')} | "
            f"cant={lipsa_nc.get('ref_cantitate','')}\n"
            f"OFERTĂ:    NR={nr} | Cod={extra_nc.get('oferta_cod','')} | "
            f"\"{extra_nc.get('oferta_denumire','')}\" | {extra_nc.get('oferta_um','')} | "
            f"cant={extra_nc.get('oferta_cantitate','')}\n\n"
            "Reprezintă aceleași lucrări fizice? Dacă da, listează toate diferențele.\n"
            "Răspunde STRICT JSON:\n"
            "{\n"
            "  \"match\": true,\n"
            "  \"motiv\": \"...\",\n"
            "  \"diferente\": [{\"camp\": \"cod_normativ\", \"ref\": \"...\", \"oferta\": \"...\"}]\n"
            "}"
        )
        result = _llm_json(llm_client, llm_model, _PASS1_SYSTEM, user)
        if not isinstance(result.get("match"), bool):
            logger.warning(f"[SEM] Pass1 NR={nr}: invalid LLM response, skipping")
            continue
        if not result["match"]:
            continue
        to_remove.add(id(lipsa_nc))
        to_remove.add(id(extra_nc))
        new_ncs.append({
            "tip": "COD_NORMATIV_DIFERIT",
            "deviz_ref": lipsa_nc.get("deviz_ref", ""),
            "deviz_denumire": lipsa_nc.get("deviz_denumire", ""),
            "is_component": False,
            "ref_cod": lipsa_nc.get("ref_cod", ""),
            "ref_denumire": lipsa_nc.get("ref_denumire", ""),
            "ref_um": lipsa_nc.get("ref_um", ""),
            "ref_cantitate": lipsa_nc.get("ref_cantitate", ""),
            "oferta_cod": extra_nc.get("oferta_cod", ""),
            "oferta_denumire": extra_nc.get("oferta_denumire", ""),
            "oferta_um": extra_nc.get("oferta_um", ""),
            "oferta_cantitate": extra_nc.get("oferta_cantitate", ""),
            "nr_ordine": nr,
            "nr_ordine_ref": nr,
            "nr_ordine_oferta": nr,
            "diferente": result.get("diferente", []),
            "motiv_llm": result.get("motiv", ""),
        })

    if not to_remove:
        return ncs
    return [nc for nc in ncs if id(nc) not in to_remove] + new_ncs
