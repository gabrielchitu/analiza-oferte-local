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
    lipsa_by_nr: dict[int, tuple[int, dict]] = {}
    extra_by_nr: dict[int, tuple[int, dict]] = {}
    for i, nc in enumerate(ncs):
        if nc.get("tip") == "ARTICOL_LIPSA" and not nc.get("is_component") and nc.get("nr_ordine_ref") is not None:
            lipsa_by_nr[nc["nr_ordine_ref"]] = (i, nc)
        elif nc.get("tip") == "ARTICOL_EXTRA" and not nc.get("is_component") and nc.get("nr_ordine_oferta") is not None:
            extra_by_nr[nc["nr_ordine_oferta"]] = (i, nc)

    shared_nrs = set(lipsa_by_nr) & set(extra_by_nr)
    if not shared_nrs:
        return ncs

    to_remove: set[int] = set()  # indices into ncs
    new_ncs: list[dict] = []

    for nr in sorted(shared_nrs):
        lipsa_idx, lipsa_nc = lipsa_by_nr[nr]
        extra_idx, extra_nc = extra_by_nr[nr]
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
        to_remove.add(lipsa_idx)
        to_remove.add(extra_idx)
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
    return [nc for i, nc in enumerate(ncs) if i not in to_remove] + new_ncs


def semantic_spec_check(
    matches: list,
    ref_arts: list,
    oferta_arts: list,
    deviz_context: str,
    llm_client,
    llm_model: str,
) -> list:
    """Check already-matched same-code pairs for technically significant denomination differences."""
    ref_by_cod = {a.get("cod", ""): a for a in ref_arts if a.get("cod")}
    oferta_by_cod = {a.get("cod", ""): a for a in oferta_arts if a.get("cod")}
    new_ncs: list[dict] = []

    for m in matches:
        ref_cod = m.get("ref_cod", "")
        oferta_cod = m.get("oferta_cod", "")
        if ref_cod != oferta_cod:
            continue  # COD_SIMILAR or cross-deviz — not in scope for Pass 2
        ref_den = m.get("ref_denumire", "")
        oferta_den = m.get("oferta_denumire", "")

        ref_art = ref_by_cod.get(ref_cod)
        if ref_art and ref_art.get("is_component"):
            continue

        norm_ref = _normalize_den(ref_den)
        norm_off = _normalize_den(oferta_den)
        if norm_ref == norm_off:
            continue
        num_ref = _numeric_tokens(ref_den)
        num_off = _numeric_tokens(oferta_den)
        if num_ref == num_off:
            continue  # no numeric diff → text-only divergence is OCR/formatting noise

        oferta_art = oferta_by_cod.get(oferta_cod)
        user = (
            f"Context deviz: {deviz_context}\n\n"
            f"Articolul cu codul {ref_cod} apare în ambele documente cu descrieri diferite:\n"
            f"REFERINȚĂ: \"{ref_den}\"\n"
            f"OFERTĂ:    \"{oferta_den}\"\n\n"
            "Diferența este semnificativă din punct de vedere tehnic și al costului lucrării?\n\n"
            "Semnificative (exemple): înălțime stalp 8m vs 5m, diametru conductă 110 vs 160mm,\n"
            "  clasă beton C20/25 vs C30/37, număr canale DVR 16 vs 8.\n"
            "Nesemnificative (exemple): majuscule/minuscule, prescurtări, ordine cuvinte,\n"
            "  text OCR incomplet care nu contrazice referința.\n\n"
            "Răspunde STRICT JSON:\n"
            "{\n"
            "  \"diferenta_semnificativa\": true,\n"
            "  \"nota_specialist\": \"...\"\n"
            "}"
        )
        result = _llm_json(llm_client, llm_model, _PASS2_SYSTEM, user)
        if result.get("diferenta_semnificativa") is not True:
            continue

        new_ncs.append({
            "tip": "SPECIFICATIE_DIFERITA",
            "deviz_ref": ref_art.get("deviz", "") if ref_art else "",
            "deviz_denumire": ref_art.get("deviz_denumire", "") if ref_art else "",
            "is_component": False,
            "ref_cod": ref_cod,
            "ref_denumire": ref_den,
            "oferta_cod": oferta_cod,
            "oferta_denumire": oferta_den,
            "ref_um": ref_art.get("um", "") if ref_art else "",
            "ref_cantitate": ref_art.get("cantitate", "") if ref_art else "",
            "oferta_um": oferta_art.get("um", "") if oferta_art else "",
            "oferta_cantitate": oferta_art.get("cantitate", "") if oferta_art else "",
            "nota_specialist": result.get("nota_specialist", ""),
            "nr_ordine_ref": ref_art.get("nr_ordine") if ref_art else None,
            "nr_ordine_oferta": oferta_art.get("nr_ordine") if oferta_art else None,
        })

    return new_ncs
