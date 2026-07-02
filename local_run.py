from __future__ import annotations

#!/usr/bin/env python3
"""
local_run.py — Analizator local oferte constructii.

Folosire:
    python3 local_run.py

Input:  input_AO/di_referinta.json + input_AO/di_oferta_N.json
Output: output_AO/referinta.json, output_AO/holistic_oferta_N.json,
        output_AO/Raport_Oferta_N.docx

Checkpoint: output_AO/checkpoints/di_X_page_classes.json
    Daca exista, sare peste clasificarea LLM (util la re-rulare dupa crash).
    Sterge fisierele din checkpoints/ daca vrei sa re-rulezi clasificarea de la zero.

Configurare: .env cu ANTHROPIC_API_KEY si ANTHROPIC_MODEL
"""
import argparse
import hashlib
import inspect
import json
import logging
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from shared.client_config import ClientConfig
from shared.f3_page_classifier import _resolve_partial_keys_fallback

load_dotenv(override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# ─── Paths ────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent
INPUT_DIR = ROOT / "input_AO"
OUTPUT_DIR = ROOT / "output_AO"
CHECKPOINT_DIR = OUTPUT_DIR / "checkpoints"

OUTPUT_DIR.mkdir(exist_ok=True)
CHECKPOINT_DIR.mkdir(exist_ok=True)


def _build_client():
    """Construieste clientul Anthropic cu adapter OpenAI-compatible."""
    from anthropic_adapter import AnthropicAdapter
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError(
            "ANTHROPIC_API_KEY lipseste. Adauga in fisierul .env:\n"
            "  ANTHROPIC_API_KEY=sk-ant-..."
        )
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    raw = anthropic.Anthropic(base_url=base_url, api_key=api_key) if base_url else anthropic.Anthropic(api_key=api_key)
    logger.info(f"Model: {model} @ {base_url or 'Anthropic direct'}")
    return AnthropicAdapter(raw, model=model), model


def run_pipeline(
    client_config: ClientConfig,
    subcomponent_mode: str = "full",
    no_semantic_cache: bool = False,
) -> None:
    """
    Run complete analysis pipeline for a single client.

    Main entry point for multi-client mode. Accepts ClientConfig with paths.

    Args:
        client_config: ClientConfig instance with paths and file list
        subcomponent_mode: Subcomponent extraction mode ("full", "deviz-only", or "skip")
        no_semantic_cache: If True, disable semantic comparator cache (always call LLM)
    """
    logger.info(f"Starting pipeline for client: {client_config.name}")
    client_config.ensure_output_dirs()

    # Load reference and offers
    logger.info(f"Loading reference: {client_config.reference_file}")
    with open(client_config.reference_file) as f:
        referinta_data = json.load(f)

    oferta_data_list = []
    for offer_file in client_config.list_offer_files():
        logger.info(f"Loading offer: {offer_file}")
        with open(offer_file) as f:
            oferta_data_list.append(json.load(f))

    logger.info(f"Loaded {len(oferta_data_list)} offer(s)")

    # Continue with existing pipeline logic using these loaded files
    # The pipeline functions below are refactored to accept client_config
    _run_analysis_pipeline(client_config, referinta_data, oferta_data_list,
                           subcomponent_mode=subcomponent_mode,
                           no_semantic_cache=no_semantic_cache)


def _normalize_obiectivul_cross_doc(
    ref_articles: list,
    oferta_articles: list,
    client,
    model: str,
) -> tuple[list, dict]:
    """Detecteaza semantic daca obiectivul ofertei == obiectivul referintei (limba romana).
    Daca da, normalizeaza obiectivul din oferta la forma canonica din referinta si
    recompute deviz_key pentru toate articolele ofertei.

    Returns: (oferta_articles_patched, mapping {of_obj1 → ref_obj1})
    """
    from shared.deviz_header_extractor import _make_deviz_key

    ref_obj1s = {
        (a.get("deviz_header") or {}).get("obiectivul", "").strip()
        for a in ref_articles
        if (a.get("deviz_header") or {}).get("obiectivul", "").strip()
    }
    of_obj1s = {
        (a.get("deviz_header") or {}).get("obiectivul", "").strip()
        for a in oferta_articles
        if (a.get("deviz_header") or {}).get("obiectivul", "").strip()
    }

    if not ref_obj1s or not of_obj1s or ref_obj1s == of_obj1s:
        return oferta_articles, {}

    ref_list = "\n".join(f"- {x}" for x in sorted(ref_obj1s))
    of_list = "\n".join(f"- {x}" for x in sorted(of_obj1s))

    prompt = (
        "Esti expert in documente de constructii romanesti.\n"
        "Compara obiectivele de investitii din doua documente (referinta si oferta).\n\n"
        f"Obiectiv(e) REFERINTA:\n{ref_list}\n\n"
        f"Obiectiv(e) OFERTA:\n{of_list}\n\n"
        "Pentru fiecare obiectiv din OFERTA, determina daca se refera la ACELASI proiect de constructie "
        "ca unul din REFERINTA (chiar daca formularea este diferita).\n"
        "Raspunde STRICT JSON, fara text suplimentar:\n"
        '{"mappings": [{"from": "text_din_oferta", "to": "text_din_referinta"}]}\n'
        "Incluzi DOAR perechile unde esti sigur ca e acelasi proiect. Lista goala daca nicio pereche."
    )

    try:
        resp = client.chat.completions.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            import re as _re
            text = _re.sub(r'^```(?:json)?\s*', '', text)
            text = _re.sub(r'\s*```\s*$', '', text)
        data = json.loads(text.strip())
        mappings = data.get("mappings", [])
    except Exception as e:
        logger.warning(f"[OBJ1-NORM] LLM call failed: {e}")
        return oferta_articles, {}

    # Snap "to" to exact ref text (LLM may return slightly different wording)
    from difflib import get_close_matches
    snapped = {}
    for m in mappings:
        from_text = m.get("from", "").strip()
        to_text = m.get("to", "").strip()
        if not from_text or not to_text:
            continue
        if to_text in ref_obj1s:
            snapped[from_text] = to_text
        else:
            matches = get_close_matches(to_text, ref_obj1s, n=1, cutoff=0.7)
            if matches:
                snapped[from_text] = matches[0]
                logger.info(f"[OBJ1-NORM] Snapped '{to_text}' → '{matches[0]}'")

    obj1_map = snapped
    if not obj1_map:
        logger.info("[OBJ1-NORM] LLM: no obiectivul equivalences found")
        return oferta_articles, {}

    logger.info(f"[OBJ1-NORM] Mapped obiectivul: {obj1_map}")

    patched = 0
    for art in oferta_articles:
        hdr = art.get("deviz_header") or {}
        old_obj1 = (hdr.get("obiectivul") or "").strip()
        if old_obj1 not in obj1_map:
            continue
        new_obj1 = obj1_map[old_obj1]
        hdr["obiectivul"] = new_obj1
        art["deviz_header"] = hdr
        new_key, _ = _make_deviz_key(new_obj1, hdr.get("obiectul"), hdr.get("categoria"))
        art["deviz_key"] = new_key
        patched += 1

    logger.info(f"[OBJ1-NORM] Patched {patched}/{len(oferta_articles)} articles")
    return oferta_articles, obj1_map


def _rekey_checkpoint_deviz_headers(checkpoint_data: dict, oferta_articles: list) -> None:
    """Rebuild deviz_headers in checkpoint_data keyed by new deviz_key after obiectivul normalization."""
    if not checkpoint_data:
        return
    new_headers = {}
    for art in oferta_articles:
        dkey = (art.get("deviz_key") or "").strip()
        if not dkey or dkey.startswith("__INCOMPLETE__") or dkey in new_headers:
            continue
        hdr = art.get("deviz_header") or {}
        new_headers[dkey] = {
            "obiectivul": hdr.get("obiectivul"),
            "obiectul": hdr.get("obiectul"),
            "categoria": hdr.get("categoria"),
            "deviz_key": dkey,
            "is_valid": True,
            "deviz_cod": art.get("deviz", ""),
        }
    checkpoint_data["deviz_headers"] = new_headers


def _headers_from_articles(arts: list) -> dict:
    """Reconstruieste deviz_headers din metadatele articolelor, keyed by deviz_key.

    deviz_key = hash(OBIECTIVUL + OBIECTUL + CATEGORIA) — identificator canonic al grupului.
    Acelasi deviz_cod (ex: BLC1) poate genera mai multe deviz_key (BLOC A, BLOC B, etc.).
    """
    from shared.deviz_header_extractor import DevizHeader
    headers: dict = {}
    for a in arts:
        key = (a.get("deviz_key") or "").strip()
        if not key or key in headers:
            continue
        dh = a.get("deviz_header") or {}
        obj1 = dh.get("obiectivul")
        obj2 = dh.get("obiectul")
        cat = dh.get("categoria")
        cod = (a.get("deviz") or "").strip()
        valid = bool(key) and not key.startswith("__INCOMPLETE__")
        headers[key] = DevizHeader(obj1, obj2, cat, key, valid, "metadata", cod)
    return headers


def _run_analysis_pipeline(client_config: ClientConfig, ref_di_json: dict, oferta_di_list: list,
                            subcomponent_mode: str = "full",
                            no_semantic_cache: bool = False) -> None:
    """
    Internal pipeline: extract and compare documents.

    Refactored to use client_config instead of global paths.
    """
    from shared.deviz_namer import populate_deviz_denominations

    client, model = _build_client()

    logger.info("=" * 50)
    logger.info("  Analizator Local Oferte Constructii")
    logger.info("=" * 50)
    logger.info(f"Client: {client_config.name}")
    logger.info(f"Input:  {client_config.input_dir}")
    logger.info(f"Output: {client_config.output_dir}")

    # Verify reference exists
    if not client_config.reference_file.exists():
        logger.error(f"Referinta lipsa: {client_config.reference_file}")
        sys.exit(1)

    oferta_paths = client_config.list_offer_files()
    if not oferta_paths:
        logger.error(f"Nicio oferta gasita in {client_config.input_dir}")
        sys.exit(1)

    logger.info(f"Referinta: {client_config.reference_file.name}")
    logger.info(f"Oferte ({len(oferta_paths)}): {[p.name for p in oferta_paths]}")

    # Step 1: Extract reference
    logger.info("\n--- Extragere REFERINTA ---")
    ref_articles, ref_checkpoint_data = extract_document(
        client_config.reference_file, client, model, client_config=client_config
    )

    # Extract reference deviz groups for LLM partial key resolution
    ref_deviz_groups = []
    ref_checkpoint_path = None

    if ref_checkpoint_data:
        ref_deviz_groups = ref_checkpoint_data.get("deviz_groups", [])
        logger.info(f"   DEBUG: ref_checkpoint_data keys: {list(ref_checkpoint_data.keys())}")
        logger.info(f"   DEBUG: ref_deviz_groups count: {len(ref_deviz_groups)}")
        if ref_deviz_groups:
            logger.info(f"   DEBUG: first deviz_group: {ref_deviz_groups[0].get('deviz_cod', 'UNKNOWN')}")
        ref_checkpoint_path = _save_checkpoint(ref_checkpoint_data, client_config.reference_file, client_config)
        logger.info(f"   Checkpoint: {ref_checkpoint_path}")
    else:
        matching_checkpoints = list(client_config.checkpoint_dir.glob(
            f"{client_config.reference_file.stem}_deviz_mapping_*.json"
        ))
        if matching_checkpoints:
            ref_checkpoint_path = matching_checkpoints[0]
            try:
                ref_checkpoint_data = json.loads(ref_checkpoint_path.read_text(encoding="utf-8"))
                ref_deviz_groups = ref_checkpoint_data.get("deviz_groups", [])
                logger.info(f"   DEBUG: loaded ref_checkpoint_data keys: {list(ref_checkpoint_data.keys())}")
                logger.info(f"   DEBUG: loaded ref_deviz_groups count: {len(ref_deviz_groups)}")
                logger.info(f"   Checkpoint loaded from cache: {ref_checkpoint_path.name}")
            except Exception as e:
                logger.warning(f"   Failed to load checkpoint: {e}")

    if ref_deviz_groups:
        logger.info(f"   {len(ref_deviz_groups)} deviz groups available for LLM resolution")
    else:
        logger.warning(f"   NO deviz groups found — partial key resolution will be skipped")

    # Populate missing deviz denominations
    ref_articles = populate_deviz_denominations(ref_articles)

    # Filter out TRULY INVALID articles
    def is_truly_invalid(a):
        return not a.get("cod", "").strip()

    invalid_count = sum(1 for a in ref_articles if is_truly_invalid(a))
    ref_articles = [a for a in ref_articles if not is_truly_invalid(a)]
    if invalid_count > 0:
        logger.info(f"  Removed {invalid_count} articles with no code (truly unparseable)")

    ref_out = client_config.output_dir / "referinta.json"
    ref_out.write_text(
        json.dumps({"articole": ref_articles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"  Salvat: {ref_out.name}")

    # Load reference DI JSON for validation purposes
    ref_di_raw = json.loads(client_config.reference_file.read_text(encoding="utf-8"))

    # Step 2: Extract + compare each offer
    for oferta_path in oferta_paths:
        try:
            oferta_nr = int(oferta_path.stem.replace("di_oferta_", ""))
        except ValueError:
            logger.warning(f"Nu pot extrage numarul din {oferta_path.name}, skip")
            continue

        logger.info(f"\n--- Extragere OFERTA {oferta_nr} ---")
        ofertant_name = _extract_ofertant_name(oferta_path)
        if ofertant_name:
            logger.info(f"  Ofertant: {ofertant_name}")

        oferta_articles, oferta_checkpoint_data = extract_document(
            oferta_path, client, model, ref_deviz_groups=ref_deviz_groups,
            reference_articles=ref_articles, client_config=client_config
        )

        # Save deviz checkpoint after offer extraction
        if oferta_checkpoint_data:
            oferta_checkpoint_path = _save_checkpoint(oferta_checkpoint_data, oferta_path, client_config)
            logger.info(f"   Checkpoint: {oferta_checkpoint_path}")

        # Populate missing deviz denominations
        oferta_articles = populate_deviz_denominations(oferta_articles)

        # Filter out TRULY INVALID articles
        invalid_count = sum(1 for a in oferta_articles if is_truly_invalid(a))
        oferta_articles = [a for a in oferta_articles if not is_truly_invalid(a)]
        if invalid_count > 0:
            logger.info(f"  Removed {invalid_count} articles with no code (truly unparseable)")

        # Normalize article codes
        articles_with_plus = [a for a in oferta_articles if '+' in a.get('cod', '')]
        if articles_with_plus:
            for art in articles_with_plus:
                art['cod'] = art['cod'].rstrip('+')
            logger.info(f"  [NORMALIZE] Removed '+' suffix from {len(articles_with_plus)} article codes")

        # Filter out malformed articles
        before_filter = len(oferta_articles)
        oferta_articles = [
            a for a in oferta_articles
            if not (a.get('cod', '').startswith('$') and not a.get('denumire', '').strip())
        ]
        filtered_count = before_filter - len(oferta_articles)
        if filtered_count > 0:
            logger.info(f"  [FILTER] Removed {filtered_count} malformed articles ($ prefix + empty denomination)")

        # Normalize obiectivul cross-doc: LLM detecteaza daca ref si oferta au acelasi proiect
        # si normalizeaza la forma canonica din referinta, recomputand deviz_key
        oferta_articles, _obj1_map = _normalize_obiectivul_cross_doc(
            ref_articles, oferta_articles, client, model
        )
        if _obj1_map:
            _rekey_checkpoint_deviz_headers(oferta_checkpoint_data, oferta_articles)

        logger.info(f"\n--- Comparare OFERTA {oferta_nr} ---")
        comp = compare_and_report(
            ref_articles, oferta_articles, oferta_nr, oferta_path, client, model,
            ofertant_name=ofertant_name, ref_di_json=ref_di_raw,
            checkpoint_data=oferta_checkpoint_data, ref_checkpoint_data=ref_checkpoint_data,
            client_config=client_config, subcomponent_mode=subcomponent_mode,
            no_semantic_cache=no_semantic_cache,
        )

    logger.info("\n" + "=" * 50)
    logger.info("  DONE")
    logger.info(f"  Rezultate in: {client_config.output_dir}")
    logger.info("=" * 50)


def _normalize_deviz_for_filter(cod: str) -> str:
    """Normalizeaza cod deviz pentru comparare cu ref_deviz_codes (U→0, OCR fix)."""
    return (cod or "").replace("U", "0")


def _checkpoint_path(di_path: Path, client_config: ClientConfig = None) -> Path:
    """Returnează calea checkpoint-ului pentru un document DI."""
    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    checkpoint_dir = client_config.checkpoint_dir if client_config else CHECKPOINT_DIR
    return checkpoint_dir / f"{di_path.stem}_page_classes_{_clf_hash}.json"


def _save_checkpoint(checkpoint: dict, di_path: Path, client_config: ClientConfig = None) -> Path:
    """Save deviz checkpoint to checkpoint directory."""
    import shared.f3_page_classifier as _clf_module

    # Get classifier hash (same as page classes checkpoint)
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]

    checkpoint_dir = client_config.checkpoint_dir if client_config else CHECKPOINT_DIR
    checkpoint_path = checkpoint_dir / f"{di_path.stem}_deviz_mapping_{_clf_hash}.json"

    with open(checkpoint_path, "w") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)

    return checkpoint_path


def _extract_ofertant_name(di_path: Path) -> str:
    """
    Extrage numele ofertantului/executantului din DI JSON (primele 10 pagini).

    Strategii în ordine de prioritate:
      1) 'Executant:' singur pe linie → linia imediat urmatoare (dacă nu e label)
      2) 'Executant: NUME' inline → extrage după ':'
      3) 'OFERTANT,' singur pe linie → linia imediat urmatoare
      4) 'Ofertant: NUME' inline → extrage după ':'
      5) 'Asociere: NUME' sau 'denumirea Asociere: NUME'
    """
    import re as _re
    try:
        di = json.loads(di_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    pages = di.get("pages", [])[:10]

    # Labels care indica un nou camp — stop colectare dupa acestea
    _STOP_RE = _re.compile(
        r'^(Proiectant|Proiect\b|Beneficiar|Obiectivul|Obiectul|Stadiul\s+fizic|'
        r'Director|Semnatura|Nume|Data\b|Deviz\b|Formular|'
        r'Sistem\s+informatic|e\s*Devize|SECTIUNEA|Nr\.|Lista|'
        r'Raport\s+generat|- lei -)',
        _re.IGNORECASE
    )

    def _clean(s: str) -> str:
        """Trunchiaza la primul marker de junk."""
        for marker in ('Deviz "', 'Formular', 'Sistem informatic',
                       'eDevize', 'Raport generat', '- lei -'):
            idx = s.find(marker)
            if 0 < idx:
                s = s[:idx]
        return _re.sub(r'\s+', ' ', s).strip()

    def _collect_name(lines, i, max_lines=4):
        """Colectează linii consecutive (non-label) de după linia i și le uneste."""
        parts = []
        for j in range(i + 1, min(i + max_lines + 1, len(lines))):
            cand = lines[j].strip()
            if not cand:
                continue
            if _STOP_RE.match(cand):
                break
            name = _clean(cand)
            if name:
                parts.append(name)
        result = ' '.join(parts).strip()
        return result if len(result) > 5 else ""

    for p in pages:
        lines = [l.get("content", "") for l in p.get("lines", [])]
        for i, line in enumerate(lines):
            ls = line.strip()

            # 1. Executant: singur pe linie
            if _re.match(r'^Executant\s*:\s*$', ls, _re.IGNORECASE):
                name = _collect_name(lines, i)
                if name:
                    return name
                continue  # executant gol, cauta mai departe

            # 2. Executant: INLINE
            m = _re.match(r'^Executant\s*:\s*(.+)', ls, _re.IGNORECASE)
            if m:
                name = _clean(m.group(1).strip())
                if name and len(name) > 5:
                    return name

            # 3. OFERTANT, singur pe linie (cu sau fara virgula/punct)
            if _re.match(r'^OFERTANT\s*[,.]?\s*$', ls, _re.IGNORECASE):
                name = _collect_name(lines, i)
                if name:
                    return name

            # 4. Ofertant: INLINE
            m = _re.match(r'^Ofertant\s*:\s*(.+)', ls, _re.IGNORECASE)
            if m:
                name = _clean(m.group(1).strip())
                if name and len(name) > 10:
                    return name

            # 5. Asociere: / denumirea Asociere: INLINE
            m = _re.search(r'(?:denumirea\s+)?Asociere\s*:\s*(.+)', ls, _re.IGNORECASE)
            if m:
                name = _clean(m.group(1).strip())
                if name and len(name) > 8:
                    return name

    return ""


def _reclassify_missed_f3_pages(
    page_classes: list,
    di_pages: list,
    checkpoint_path,
    client,
    model: str,
) -> tuple:
    """
    Re-clasificare LLM tintita pentru pagini is_f3=False cu semnal F3 euristic.

    Fluxul:
    1. Reclassifier euristic identifica candidate (nu apeleaza LLM)
    2. Filtreaza candidatii: pastreaza numai paginile reclasificate de euristica
       (exclude paginile deja corecte — evita re-trimiterea la LLM inutila)
    3. Trimite NUMAI candidatii la LLM in batch
    4. Actualizeaza page_classes cu raspunsul LLM
    5. Salveaza checkpoint actualizat (evita re-clasificare la run-uri viitoare)

    Returns: (page_classes_updated, checkpoint_was_updated)
    """
    from shared.f3_page_reclassifier import reclassify_non_f3_pages
    from shared.f3_page_classifier import _classify_pages_llm

    # Pasul 1: identifica candidate euristic (in-memory, fara LLM)
    page_classes_heuristic = reclassify_non_f3_pages(page_classes)

    # Pasul 2: gaseste paginile schimbate de euristica (is_f3: False → True)
    # Excludem paginile deja verificate de LLM in run-uri anterioare (flag _reclf_checked)
    original_by_pn = {p["page_number"]: p for p in page_classes}
    candidates = []
    for pc_h in page_classes_heuristic:
        pn = pc_h["page_number"]
        orig = original_by_pn.get(pn, {})
        if orig.get("_reclf_checked"):
            continue  # deja verificat de LLM anterior — sarim
        if not orig.get("is_f3") and pc_h.get("is_f3"):
            # Pagina reclasificata de euristica — trimitem la LLM pentru confirmare
            candidates.append(pc_h)

    if not candidates:
        return page_classes, False

    logger.info(
        f"  [RECLF] {len(candidates)} candidate pagini F3 omise → LLM re-clasificare..."
    )

    # Pasul 3: pregateste datele DI brute pentru candidate
    di_pages_by_pn = {p["page_number"]: p for p in di_pages}
    llm_input = []
    for pc_h in candidates:
        pn = pc_h["page_number"]
        di_page = di_pages_by_pn.get(pn)
        if di_page is None:
            continue
        # Reconstituie liniile brute din DI (mai complete decat cele din checkpoint)
        lines_raw = [
            l.get("content", "") if isinstance(l, dict) else str(l)
            for l in di_page.get("lines", [])
        ]
        llm_input.append({
            "page_number": pn,
            "lines": lines_raw,
            "deviz_cod": pc_h.get("deviz_cod", ""),  # hint din euristica
        })

    if not llm_input:
        return page_classes, False

    # Pasul 4: apel LLM batch
    llm_results = _classify_pages_llm(llm_input, client, model)
    logger.info(
        f"  [RECLF] LLM a raspuns pentru {len(llm_results)}/{len(llm_input)} pagini"
    )

    # Pasul 5: actualizeaza page_classes cu rezultatele LLM
    updated_count = 0
    page_classes_updated = [dict(pc) for pc in page_classes]
    for pc in page_classes_updated:
        pn = pc["page_number"]
        if pn in llm_results:
            llm = llm_results[pn]
            if llm.get("is_f3"):
                old_f3 = pc.get("is_f3", False)
                pc["is_f3"] = True
                pc["header_only"] = False
                if llm.get("deviz_cod"):
                    pc["deviz_cod"] = llm["deviz_cod"]
                if not old_f3:
                    updated_count += 1
                    logger.info(
                        f"  [RECLF] pag{pn}: is_f3=True deviz={pc['deviz_cod']!r} (confirmat LLM)"
                    )
            else:
                logger.debug(f"  [RECLF] pag{pn}: LLM confirma NON_F3")

    # Marcam toate paginile candidate ca verificate (indiferent de rezultat)
    # → evitam re-apelul LLM in run-uri viitoare pentru aceleasi pagini
    checkpoint_needs_save = False
    page_classes_updated_map = {p["page_number"]: p for p in page_classes_updated}
    for pc_h in candidates:
        pn = pc_h["page_number"]
        if pn in page_classes_updated_map:
            page_classes_updated_map[pn]["_reclf_checked"] = True
            checkpoint_needs_save = True

    if updated_count == 0:
        logger.info("  [RECLF] LLM a confirmat: nicio pagina suplimentara F3")
        if checkpoint_needs_save:
            checkpoint_path.write_text(
                json.dumps(page_classes_updated, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        return page_classes_updated if checkpoint_needs_save else page_classes, False

    # Pasul 6: salveaza checkpoint actualizat
    checkpoint_path.write_text(
        json.dumps(page_classes_updated, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(
        f"  [RECLF] {updated_count} pagini re-clasificate F3, checkpoint actualizat"
    )
    return page_classes_updated, True


def extract_document(di_path: Path, client, model: str, ref_deviz_groups: list | None = None, reference_articles: list | None = None, client_config: ClientConfig = None) -> tuple[list, dict | None]:
    """
    Extrage articolele F3 dintr-un DI JSON.
    Foloseste checkpoint daca exista — sare peste clasificarea LLM (pasul lent).

    Extrage TOATE devizele fara filtru. Devizele prezente in oferta dar absente
    din referinta sunt surfacate ca alerte in raport, nu ascunse.

    Args:
        di_path: Path to DI JSON file
        client: Anthropic client
        model: Model ID
        ref_deviz_groups: Optional list of reference deviz groups (for LLM partial key resolution)
        reference_articles: Optional list of reference articles (for dynamic deviz text mapping)
        client_config: Optional ClientConfig for path resolution

    Returns: tuple of (articles, checkpoint_data)
        articles: list of extracted articles
        checkpoint_data: dict with deviz mapping and metadata (or None if from cached checkpoint)
    """
    from shared.f3_page_classifier import classify_pages, _resolve_partial_keys_with_llm
    from shared.f3_extractor import extract_articles_v3

    checkpoint = _checkpoint_path(di_path, client_config)
    checkpoint_data = None

    di = json.loads(di_path.read_text(encoding="utf-8"))
    pages = di.get("pages", [])
    logger.info(f"  {di_path.name}: {len(pages)} pagini DI")

    checkpoint_data = {}  # Metadata like subcomponent_format
    if checkpoint.exists():
        logger.info(f"  Checkpoint gasit — sare peste clasificare LLM")
        ckpt = json.loads(checkpoint.read_text(encoding="utf-8"))
        # Support both old format (list) and new format (dict with page_classes + metadata)
        if isinstance(ckpt, list):
            page_classes = ckpt
            # Old format: regenerate checkpoint_data with deviz_groups from page_classes
            from shared.f3_page_classifier import build_deviz_groups
            checkpoint_data = {
                "deviz_groups": build_deviz_groups(page_classes),
                "metadata": {},
                "validation": {}
            }
        else:
            page_classes = ckpt.get("page_classes", ckpt.get("results", []))
            checkpoint_data = ckpt.get("metadata", {})
    else:
        logger.info(f"  Clasificare pagini cu LLM (poate dura 2-5 min)...")
        page_classes, checkpoint_data = classify_pages(pages, client, model, reference_articles=reference_articles)
        checkpoint.write_text(
            json.dumps({
                "page_classes": page_classes,
                "metadata": checkpoint_data
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  Checkpoint salvat: {checkpoint.name}")

    # LLM resolution of partial keys (missing numeric prefixes in Obiectul/Categoria)
    # Uses ref_deviz_groups if available (offer extraction), otherwise fallback text parsing
    has_partial = any(
        p.get("deviz_cod", "").startswith("__partial__")
        for p in page_classes
    )
    if has_partial:
        # Filter out __partial__ codes from ref_deviz_groups (they're not useful for matching)
        valid_ref_groups = [
            g for g in (ref_deviz_groups or [])
            if not g.get("deviz_cod", "").startswith("__partial__")
        ]
        if valid_ref_groups:
            logger.info(f"  Rezolvare chei partiale cu LLM...")
            page_classes = _resolve_partial_keys_with_llm(
                page_classes, valid_ref_groups, client, model
            )
        else:
            logger.info(f"  Rezolvare chei partiale din text patterns (fara referinta valida)...")
            page_classes = _resolve_partial_keys_fallback(page_classes)

        # Overwrite checkpoint with resolved keys, preserve metadata
        checkpoint.write_text(
            json.dumps({
                "page_classes": page_classes,
                "metadata": checkpoint_data
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  Checkpoint actualizat cu chei rezolvate")

    # Re-clasificare LLM tintita: pagini is_f3=False cu semnal F3 detectat euristic.
    # Ruleaza NUMAI cand exista astfel de pagini — LLM e apelat doar pentru candidate.
    page_classes, checkpoint_updated = _reclassify_missed_f3_pages(
        page_classes, pages, checkpoint, client, model
    )

    f3_count = sum(1 for p in page_classes if p.get("is_f3") and not p.get("header_only"))
    no_deviz = sum(1 for p in page_classes if p.get("is_f3") and not p.get("header_only") and not p.get("deviz_cod"))
    logger.info(f"  {f3_count} pagini F3 ({no_deviz} fara deviz_cod)")

    # Apply end-detection in-memory AFTER checkpoint is loaded/saved (never persisted)
    from shared.f3_page_classifier import _apply_end_detection
    from shared.f3_knowledge import F3Knowledge
    page_classes = _apply_end_detection(page_classes, F3Knowledge())

    # Extract 3-layer deviz headers (OBIECTIVUL / Obiectul / Categoria)
    from shared.deviz_header_extractor import extract_deviz_headers
    from shared.document_profiler import profile_document_cached
    from shared.group_extractor import extract_groups_as_headers

    _checkpoints_dir = Path(client_config.output_dir) / "checkpoints"
    _doc_profile = profile_document_cached(di, _checkpoints_dir)
    logger.info(f"  DocumentProfile: mode={_doc_profile.mode}, tables={_doc_profile.table_count}")

    deviz_headers = extract_groups_as_headers(di, page_classes, _doc_profile)
    if not deviz_headers:
        deviz_headers = extract_deviz_headers(page_classes, client, model)
        logger.info("  GroupExtractor v2: gol — fallback la extract_deviz_headers()")
    else:
        logger.info(f"  GroupExtractor v2: {len(deviz_headers)} grupuri (mode={_doc_profile.mode})")

    valid_count = sum(1 for h in deviz_headers.values() if h.is_valid)
    logger.info(f"  {len(deviz_headers)} devize cu header extras ({valid_count} valide, "
                f"{len(deviz_headers) - valid_count} incomplete)")

    # Persist deviz_headers to checkpoint_data for use in compare_by_groups()
    checkpoint_data['deviz_headers'] = {
        k: {
            'obiectivul': v.obiectivul,
            'obiectul': v.obiectul,
            'categoria': v.categoria,
            'is_valid': v.is_valid,
            'deviz_cod': v.deviz_cod,
            'deviz_key': v.deviz_key,
        }
        for k, v in deviz_headers.items()
    }

    articles = extract_articles_v3(page_classes)
    logger.info(f"  {len(articles)} articole extrase din linii")

    # deviz_key si deviz_header sunt acum setate per-pagina de extract_articles_v3().
    # NU suprascriem — fiecare articol are deviz_key corect din sub-grupul sau de pagini.
    # Fallback pt articolele fara deviz_key valid (din devize fara header detectat):
    # deviz_headers este keyed by hash, nu deviz_cod — construim index secundar by cod.
    _dh_by_cod: dict[str, list] = {}
    for _dh_val in deviz_headers.values():
        if _dh_val.is_valid:
            _dh_by_cod.setdefault(_dh_val.deviz_cod, []).append(_dh_val)

    for art in articles:
        existing_key = (art.get("deviz_key") or "").strip()
        if not existing_key or existing_key.startswith("__INCOMPLETE__"):
            art_cod = art.get("deviz", "")
            candidates = _dh_by_cod.get(art_cod, [])
            if len(candidates) == 1:
                dh = candidates[0]
                art["deviz_key"] = dh.deviz_key
                art["deviz_header"] = {
                    "obiectivul": dh.obiectivul,
                    "obiectul": dh.obiectul,
                    "categoria": dh.categoria,
                }

    # Deduplicate by 5-tuple: (deviz_key, nr_ordine, cod, um, cantitate)
    # deviz_key (hash) is the canonical group identifier — same cod/qty in different
    # logical groups (e.g. "3 ORGANIZARE SANTIER|BLC7" vs "4 ORGANIZARE SANTIER|BLC7")
    # must NOT be merged even when deviz_cod string is identical.
    # nr_ordine in cheie: articole distincte pot avea acelasi cod+um+cant in acelasi deviz
    # (CK09A1 GLAFURI LEMN INT. nr=23 vs TABLA EXT. nr=24 — Gura Foii O1).
    seen_4tuple = {}
    deduped = []
    for art in articles:
        key = (art.get("deviz_key") or art.get("deviz"), art.get("nr_ordine"), art.get("cod"), art.get("um"), art.get("cantitate"))
        if key not in seen_4tuple:
            deduped.append(art)
            seen_4tuple[key] = True

    if len(deduped) < len(articles):
        logger.info(f"  {len(articles) - len(deduped)} duplicates removed (same deviz/cod/um/cantitate)")
    articles = deduped

    # Table extraction disabled in v1 (using v2 for table-aware extraction)
    # v1 uses regex-only extraction for compatibility

    # Apply final deduplication for code suffix duplicates (e.g., $0156 vs $3270156)
    # This handles cases where line extraction and table extraction both produce articles
    # with the same deviz/cantitate/um but different (suffix-related) codes
    from shared.f3_regex_parser import _deduplicate_by_code_suffix
    articles_before = len(articles)
    articles = _deduplicate_by_code_suffix(articles)
    if len(articles) < articles_before:
        logger.info(f"  Final deduplication: removed {articles_before - len(articles)} suffix-duplicate articles")

    # Filter out articles with fake/invalid deviz codes (e.g., "DINTRE" from marketing text extraction)
    # Accept most codes that were extracted by the parser, including:
    # - Numeric codes: "226108", "07", "19"
    # - Compound codes: "4.1-01", "4.3-02"
    # - Word codes: "CAMIN", "CAMINE" (Obiectul names from new format documents)
    # - Full denomination keys: "INSTALATII SANITARE INTERIOARE" (Gura Foii ref, deviz fara cod)
    # Reject only: very long codes (>40 chars = likely OCR garbage)
    invalid_deviz = []
    articles_filtered = []
    for art in articles:
        deviz = art.get("deviz", "")
        # Valid deviz: non-empty, 2-40 chars (covers all legitimate formats incl. denumiri complete)
        # The parser already did most filtering, so we're mainly rejecting obvious OCR garbage
        if deviz and len(deviz) >= 2 and len(deviz) <= 40:
            articles_filtered.append(art)
        else:
            invalid_deviz.append(deviz)

    if len(invalid_deviz) > 0:
        invalid_count = len([a for a in articles if a.get("deviz", "") in set(invalid_deviz)])
        logger.info(f"  Filtered out {invalid_count} articles with invalid deviz codes: {set(invalid_deviz)}")
    articles = articles_filtered

    return articles, checkpoint_data


def _track_subcomponent_anomalies(
    oferta_articles: list,
    ref_lookup: dict,
    fmt_info: dict
) -> list:
    """
    Track subcomponent codes in offer that don't match reference.

    Returns list of anomalies:
        {
            'deviz': str,
            'cod': str,
            'subcomp_code': str,
            'type': 'SUBCOMP_EXTRA' (in offer but not in ref)
        }
    """
    anomalies = []

    if not ref_lookup.get("codes"):
        return anomalies

    ref_codes = ref_lookup["codes"]

    for art in oferta_articles:
        art_text = str(art.get("deviz_denumire", "")) + " " + str(art.get("denumire", ""))

        # Use the format info to extract codes
        from shared.subcomponent_extractor import extract_subcomponent_codes_from_text
        codes = extract_subcomponent_codes_from_text(art_text, fmt_info)

        for code in codes:
            if code not in ref_codes:
                anomalies.append({
                    "deviz": art.get("deviz"),
                    "cod": art.get("cod"),
                    "subcomp_code": code,
                    "type": "SUBCOMP_EXTRA"
                })

    return anomalies


def compare_and_report(
    ref_articles: list,
    oferta_articles: list,
    oferta_nr: int,
    oferta_path: Path,
    client,
    model: str,
    include_prices: bool = False,
    ofertant_name: str = "",
    ref_di_json: dict = None,
    checkpoint_data: dict = None,
    ref_checkpoint_data: dict = None,
    client_config: ClientConfig = None,
    subcomponent_mode: str = "full",
    no_semantic_cache: bool = False,
):
    """Compara oferta cu referinta si genereaza raport XLSX + DOCX."""
    from shared.deviz_normalizer import normalize_devize
    from shared.report_excel import generate_excel
    from shared.comparatie_lista_writer import build_comparatie_docx

    # Phase 2: Subcomponent code extraction and matching (optional, based on detected format)
    subcomp_stats = {"detected": False, "format": "unknown", "confidence": 0.0}
    if checkpoint_data and checkpoint_data.get("subcomponent_format"):
        from shared.subcomponent_formats import SubcomponentFormat, SUBCOMPONENT_PATTERNS
        from shared.subcomponent_extractor import (
            build_subcomponent_lookup,
            extract_subcomponent_codes_from_text
        )

        subcomp_fmt = checkpoint_data["subcomponent_format"]
        fmt_str = subcomp_fmt.get("format", "unknown")
        fmt_name = subcomp_fmt.get("name", "unknown")
        confidence = subcomp_fmt.get("confidence", 0.0)

        if fmt_str != "unknown" and confidence >= 0.70:
            subcomp_stats["detected"] = True
            subcomp_stats["format"] = fmt_str
            subcomp_stats["confidence"] = confidence

            logger.info(f"  [SUBCOMP_PHASE2] Format: {fmt_name} (confidence={confidence:.2f})")

            # Build reference lookup from articles
            ref_lookup = build_subcomponent_lookup(
                " ".join(str(a.get("deviz_denumire", "")) for a in ref_articles),
                {
                    "format": SubcomponentFormat(fmt_str),
                    "regex": SUBCOMPONENT_PATTERNS[SubcomponentFormat(fmt_str)]["regex"],
                    "code_group": SUBCOMPONENT_PATTERNS[SubcomponentFormat(fmt_str)]["code_group"]
                }
            )

            if ref_lookup["codes"]:
                logger.info(f"  [SUBCOMP_PHASE2] Reference: {ref_lookup['lines_matched']} subcomponent codes found ({', '.join(sorted(list(ref_lookup['codes'])[:5]))}...)")

                # Build format_info for anomaly tracking
                fmt_info = {
                    "format": SubcomponentFormat(fmt_str),
                    "regex": SUBCOMPONENT_PATTERNS[SubcomponentFormat(fmt_str)]["regex"],
                    "code_group": SUBCOMPONENT_PATTERNS[SubcomponentFormat(fmt_str)]["code_group"]
                }

                # Subcomponent anomaly tracking removed (old pipeline)
                subcomp_stats["anomalies"] = 0
                logger.info(f"  [SUBCOMP_PHASE2] Subcomponent stats collected")

                # Extract from offer articles (for statistics)
                offer_subcomp_codes = {}
                for art in oferta_articles:
                    art_text = str(art.get("deviz_denumire", "")) + " " + str(art.get("denumire", ""))
                    codes = extract_subcomponent_codes_from_text(art_text, fmt_info)
                    if codes:
                        art_key = (art.get("deviz"), art.get("cod"))
                        offer_subcomp_codes[art_key] = codes

                if offer_subcomp_codes:
                    logger.info(f"  [SUBCOMP_PHASE2] Offer: {len(offer_subcomp_codes)} articles with subcomponent codes")
                    subcomp_stats["ref_codes"] = len(ref_lookup["codes"])
                    subcomp_stats["offer_articles"] = len(offer_subcomp_codes)
            else:
                logger.debug(f"  [SUBCOMP_PHASE2] No reference subcomponent codes found")
        else:
            logger.debug(f"  [SUBCOMP_PHASE2] Format confidence too low ({confidence:.2f}) or unknown, skipping")

    # Normalizeaza devizele ofertei sa corespunda cu cele din referinta
    oferta_norm = normalize_devize(ref_articles, oferta_articles, client, model)

    # Holistic group-based comparison
    from shared.group_comparator import compare_by_groups
    from shared.report_builder import build_raport_holistic
    from shared.deviz_header_extractor import DevizHeader

    # Load original page-level headers from checkpoint (persisted in extract_document())
    _ref_dh = {}
    _oferta_dh = {}

    # Reconstruct DevizHeader objects from checkpoint data.
    # New format: keyed by deviz_key (hash). Old format: keyed by deviz_cod.
    # Both handled — store by deviz_key hash for compare_by_groups lookup.
    if isinstance(ref_checkpoint_data, dict) and "deviz_headers" in ref_checkpoint_data:
        for ck, hdr_data in ref_checkpoint_data["deviz_headers"].items():
            hdr = DevizHeader(
                obiectivul=hdr_data.get('obiectivul'),
                obiectul=hdr_data.get('obiectul'),
                categoria=hdr_data.get('categoria'),
                deviz_key=hdr_data.get('deviz_key', ''),
                is_valid=hdr_data.get('is_valid', False),
                source="checkpoint",
                deviz_cod=hdr_data.get('deviz_cod', ck),
            )
            deviz_key = hdr_data.get('deviz_key', '') or ck
            if deviz_key:
                _ref_dh[deviz_key] = hdr
    else:
        logger.warning("  [HEADERS] Ref deviz_headers not found in checkpoint, using fallback")
        _ref_dh = _headers_from_articles(ref_articles)

    if isinstance(checkpoint_data, dict) and "deviz_headers" in checkpoint_data:
        for ck, hdr_data in checkpoint_data["deviz_headers"].items():
            hdr = DevizHeader(
                obiectivul=hdr_data.get('obiectivul'),
                obiectul=hdr_data.get('obiectul'),
                categoria=hdr_data.get('categoria'),
                deviz_key=hdr_data.get('deviz_key', ''),
                is_valid=hdr_data.get('is_valid', False),
                source="checkpoint",
                deviz_cod=hdr_data.get('deviz_cod', ck),
            )
            deviz_key = hdr_data.get('deviz_key', '') or ck
            if deviz_key:
                _oferta_dh[deviz_key] = hdr
    else:
        logger.warning("  [HEADERS] Oferta deviz_headers not found in checkpoint, using fallback")
        _oferta_dh = _headers_from_articles(oferta_norm)

    logger.info(f"  [HEADERS] Ref: {len(_ref_dh)} deviz_keys, Oferta: {len(_oferta_dh)} deviz_keys")

    _sem_cache_path = (
        None if no_semantic_cache
        else (client_config.output_dir if client_config else OUTPUT_DIR) / "semantic_cache.json"
    )
    _holistic = compare_by_groups(
        ref_articles, oferta_norm, _ref_dh, _oferta_dh, client, model,
        client_name=client_config.name if client_config else "",
        semantic_cache_path=_sem_cache_path,
    )
    raport_holistic = build_raport_holistic(_holistic)
    logger.info(
        f"  [HOLISTIC] {raport_holistic['sumar']['total_matched_groups']} grupuri matchate, "
        f"{raport_holistic['sumar']['total_ref_only_groups']} ref-only, "
        f"{raport_holistic['sumar']['total_oferta_only_groups']} oferta-only"
    )

    _h_sumar = raport_holistic.get("sumar", {})
    logger.info(
        f"  [HOLISTIC] Neconformitati: {_h_sumar.get('neconformitati_by_tip', {})} "
        f"(total: {sum(_h_sumar.get('neconformitati_by_tip', {}).values())})"
    )
    logger.info(f"  [HOLISTIC] Matched: {_h_sumar.get('total_matched_articles', 0)} articole")
    _n_unassigned = _h_sumar.get('total_unassigned_ref', 0) + _h_sumar.get('total_unassigned_oferta', 0)
    if _n_unassigned:
        logger.warning(f"  [HOLISTIC] Neasignate: {_n_unassigned} articole fara deviz_key valid")

    output_dir = client_config.output_dir if client_config else OUTPUT_DIR
    session = {"client_name": client_config.name if client_config else "", "obiect_investitii": ""}
    comp = {
        "oferta_nr": oferta_nr,
        "source_file": oferta_path.name,
        "ofertant": ofertant_name or f"Oferta {oferta_nr}",
        "ref_art_count": len(ref_articles),
        "oferta_art_count": len(oferta_norm),
        "ref_articles": ref_articles,
        "oferta_articles": oferta_norm,
        "raport_holistic": raport_holistic,
    }
    comparison_mode = "cu_pret" if include_prices else "fara_pret"

    # Raport XLSX — comentat deocamdata (nu e prioritar)
    # xlsx_path = OUTPUT_DIR / f"Raport_Oferta_{oferta_nr}.xlsx"
    # try:
    #     xlsx_bytes = generate_excel(session, [comp], comparison_mode=comparison_mode)
    #     xlsx_path.write_bytes(xlsx_bytes)
    #     logger.info(f"  XLSX: {xlsx_path.name}")
    # except Exception as e:
    #     logger.warning(f"  XLSX failed: {e}")

    # Raport DOCX — NC-only extract cu layout comparatie
    docx_path = output_dir / f"Raport_Oferta_{oferta_nr}.docx"
    try:
        client_name = client_config.name if client_config else ""
        build_comparatie_docx(raport_holistic, client_name, oferta_nr, str(docx_path), nc_only=True)
        logger.info(f"  DOCX: {docx_path.name}")
    except Exception as e:
        logger.warning(f"  DOCX failed: {e}")

    # Holistic JSON
    try:
        holistic_path = output_dir / f"holistic_oferta_{oferta_nr}.json"
        holistic_path.write_text(
            json.dumps(raport_holistic, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8"
        )
        logger.info(f"  Holistic JSON: {holistic_path.name}")
    except Exception as e:
        logger.warning(f"  Holistic JSON failed: {e}")

    # Matching debug trace
    try:
        debug_path = output_dir / f"matching_debug_oferta_{oferta_nr}.json"
        debug_path.write_text(
            json.dumps(_holistic.match_trace, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  Matching debug: {debug_path.name}")
    except Exception as e:
        logger.warning(f"  Matching debug failed: {e}")

    return comp


def main():
    """Main entry point for backward-compatible local mode (uses root paths)."""
    # Parse CLI arguments
    parser = argparse.ArgumentParser(description="Analizator local oferte constructii")
    args = parser.parse_args()

    # For backward compatibility: create a ClientConfig for root paths
    root_config = ClientConfig(
        name="root",
        input_dir=INPUT_DIR,
        output_dir=OUTPUT_DIR,
        checkpoint_dir=CHECKPOINT_DIR,
        reference_file=INPUT_DIR / "di_referinta.json",
        offer_files=sorted(INPUT_DIR.glob("di_oferta_*.json")),
    )

    # Validate root config
    if not root_config.validate():
        logger.error(f"Referinta lipsa: {root_config.reference_file}")
        logger.error("Adauga di_referinta.json in folderul input_AO/")
        sys.exit(1)

    if not root_config.list_offer_files():
        logger.error(f"Nicio oferta gasita. Adauga di_oferta_1.json, di_oferta_2.json etc. in input_AO/")
        sys.exit(1)

    # Run the pipeline using the refactored internal function
    _run_analysis_pipeline(root_config, {}, [])


if __name__ == "__main__":
    main()
