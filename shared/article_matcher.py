import json
import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

_MIN_COD_SIMILARITY = 0.75  # Below this, codes are too different for OCR confusion


def _cod_similarity(cod_a: str, cod_b: str) -> float:
    """Normalized similarity ratio between two codes (after stripping OCR noise chars)."""
    na = re.sub(r'[#$@\s]', '', (cod_a or "").upper().strip())
    nb = re.sub(r'[#$@\s]', '', (cod_b or "").upper().strip())
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()

SYSTEM_PROMPT = """Esti expert in norme de deviz constructii romanesti.
Ti se dau doua liste de articole: REFERINTA si OFERTA.
Fiecare articol are: cod, denumire, um, cantitate.
Sarcina: gaseste corespondenta intre articolele din referinta si cele din oferta.
Reguli:
- Foloseste codul articolului ca cheie primara de matching.
- Daca codul difera putin (eroare OCR), foloseste denumirea pentru confirmare.
- Daca un articol din referinta nu are corespondent in oferta, pune oferta_cod=null.
- Articolele din oferta fara corespondent in referinta se pun in oferta_extra.
Returneaza DOAR JSON valid, fara text suplimentar."""


def _build_match_prompt(ref_arts: list, oferta_arts: list) -> str:
    def fmt(arts):
        return "\n".join(
            f"  cod={a.get('cod','')} | den={a.get('denumire','')[:50]} | um={a.get('um','')} | cant={a.get('cantitate','')}"
            for a in arts
        )
    return (
        f"REFERINTA ({len(ref_arts)} articole):\n{fmt(ref_arts)}\n\n"
        f"OFERTA ({len(oferta_arts)} articole):\n{fmt(oferta_arts)}\n\n"
        'Returneaza JSON: {"matches": [{"ref_cod":"...","oferta_cod":"...","confidence":"high|medium|low","motiv":"optional"}], "oferta_extra": [{"oferta_cod":"...","oferta_denumire":"..."}]}'
    )


def match_category(ref_arts: list, oferta_arts: list,
                   openai_client, deployment: str) -> dict:
    prompt = _build_match_prompt(ref_arts, oferta_arts)
    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt}
            ],
            max_tokens=4000
        )
        return json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.error(f"[Matcher] LLM failed: {e}")
        return {"matches": [], "oferta_extra": []}


FUZZY_SYSTEM_PROMPT = """Esti expert in coduri de articole de constructii romanesti.
Ti se dau doua liste: articole din REFERINTA fara corespondent in oferta, si articole din OFERTA fara corespondent in referinta.
Sarcina: identifica DOAR perechile care reprezinta ACELASI articol fizic, unde codul difera dintr-o eroare minora de transcriere/OCR.

REGULI STRICTE — respecta toate:
1. Codurile trebuie sa fie foarte asemanatoare: difera prin cel mult 1-2 caractere (ex: '0' vs 'O', '1' vs 'I', '1' vs 'l', spatiu sau sufix '#' '$').
2. Denumirile articolelor trebuie sa descrie aceeasi lucrare — cel putin jumatate din cuvintele principale trebuie sa se regaseasca in ambele denumiri.
3. Daca denumirile sunt complet diferite (ex: 'BOILER' vs 'ARMATURI', 'SENZOR' vs 'PARCARE'), NU potrivi chiar daca codurile seamana.
4. Daca codurile difera in mai mult de 2 pozitii, NU potrivi.

Returneaza DOAR JSON valid:
{"matches": [{"ref_cod": "...", "oferta_cod": "...", "motiv": "descriere eroare OCR"}]}"""


def match_unmatched_global(
    unmatched_ref: list,
    unmatched_oferta: list,
    openai_client,
    deployment: str,
    batch_size: int = 50
) -> list:
    """
    LLM fuzzy matching for globally unmatched articles.
    Handles large lists by batching.
    Returns list of {"ref_cod": ..., "oferta_cod": ..., "motiv": ...}
    """
    if not unmatched_ref or not unmatched_oferta:
        return []

    def fmt(arts):
        return "\n".join(
            f"  cod={a.get('cod','')} | den={a.get('denumire','')[:40]}"
            for a in arts
        )

    # Pre-filter: keep only oferta articles that are code-similar to at least one ref article.
    # Eliminates completely different codes before they reach the LLM.
    oferta_candidates = [
        o for o in unmatched_oferta
        if any(_cod_similarity(r.get("cod", ""), o.get("cod", "")) >= _MIN_COD_SIMILARITY
               for r in unmatched_ref)
    ]
    if not oferta_candidates:
        logger.info("[Matcher] No candidate pairs above similarity threshold — skipping LLM fuzzy")
        return []

    all_matches = []
    # Process in batches if needed
    for i in range(0, len(unmatched_ref), batch_size):
        ref_batch = unmatched_ref[i:i + batch_size]
        # Further filter ref batch to only articles with at least one similar oferta code
        ref_batch_filtered = [
            r for r in ref_batch
            if any(_cod_similarity(r.get("cod", ""), o.get("cod", "")) >= _MIN_COD_SIMILARITY
                   for o in oferta_candidates)
        ]
        if not ref_batch_filtered:
            continue
        prompt = (
            f"REFERINTA nemat-uita ({len(ref_batch_filtered)} articole):\n{fmt(ref_batch_filtered)}\n\n"
            f"OFERTA nemat-uita ({len(oferta_candidates)} articole):\n{fmt(oferta_candidates)}"
        )
        try:
            resp = openai_client.chat.completions.create(
                model=deployment,
                temperature=0.0,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": FUZZY_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000
            )
            result = json.loads(resp.choices[0].message.content)
            all_matches.extend(result.get("matches", []))
        except Exception as e:
            logger.error(f"[Matcher] match_unmatched_global LLM error: {e}")
            return []

    return all_matches
