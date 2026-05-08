#!/usr/bin/env python3
"""
local_run.py — Analizator local oferte constructii.

Folosire:
    python3 local_run.py

Input:  input_AO/di_referinta.json + input_AO/di_oferta_N.json
Output: output_AO/referinta.json, output_AO/oferta_N.json,
        output_AO/comparatie_oferta_N.json,
        output_AO/Raport_Oferta_N.xlsx, output_AO/Raport_Oferta_N.docx

Checkpoint: output_AO/checkpoints/di_X_page_classes.json
    Daca exista, sare peste clasificarea LLM (util la re-rulare dupa crash).
    Sterge fisierele din checkpoints/ daca vrei sa re-rulezi clasificarea de la zero.

Configurare: .env cu ANTHROPIC_API_KEY si ANTHROPIC_MODEL
"""
import hashlib
import inspect
import json
import logging
import os
import sys
from collections import Counter
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

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
    logger.info(f"Model Anthropic: {model}")
    return AnthropicAdapter(anthropic.Anthropic(api_key=api_key), model=model), model


def _normalize_deviz_for_filter(cod: str) -> str:
    """Normalizeaza cod deviz pentru comparare cu ref_deviz_codes (U→0, OCR fix)."""
    return (cod or "").replace("U", "0")


def extract_document(di_path: Path, client, model: str, ref_deviz_codes: set = None) -> list:
    """
    Extrage articolele F3 dintr-un DI JSON.
    Foloseste checkpoint daca exista — sare peste clasificarea LLM (pasul lent).

    Args:
        ref_deviz_codes: Optional set of valid deviz codes from reference.
                        If provided, only extract articles from these deviz codes.
    """
    from shared.f3_page_classifier import classify_pages
    from shared.f3_extractor import extract_articles_v3

    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    checkpoint = CHECKPOINT_DIR / f"{di_path.stem}_page_classes_{_clf_hash}.json"

    di = json.loads(di_path.read_text(encoding="utf-8"))
    pages = di.get("pages", [])
    logger.info(f"  {di_path.name}: {len(pages)} pagini DI")

    if checkpoint.exists():
        logger.info(f"  Checkpoint gasit — sare peste clasificare LLM")
        page_classes = json.loads(checkpoint.read_text(encoding="utf-8"))
    else:
        logger.info(f"  Clasificare pagini cu LLM (poate dura 2-5 min)...")
        page_classes = classify_pages(pages, client, model)
        checkpoint.write_text(
            json.dumps(page_classes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  Checkpoint salvat: {checkpoint.name}")

    # Filtrare: doar devize care exista si in referinta (daca ref_deviz_codes e furnizat)
    if ref_deviz_codes is not None:
        page_classes_before = len([p for p in page_classes if p.get("is_f3") and not p.get("header_only")])
        page_classes = [
            p for p in page_classes
            if not p.get("is_f3") or p.get("header_only") or _normalize_deviz_for_filter(p.get("deviz_cod", "")) in ref_deviz_codes
        ]
        page_classes_after = len([p for p in page_classes if p.get("is_f3") and not p.get("header_only")])
        if page_classes_before != page_classes_after:
            logger.info(f"  Filtrare devize: {page_classes_before} → {page_classes_after} pagini F3 (excluse devize din oferta extra)")

    f3_count = sum(1 for p in page_classes if p.get("is_f3") and not p.get("header_only"))
    no_deviz = sum(1 for p in page_classes if p.get("is_f3") and not p.get("header_only") and not p.get("deviz_cod"))
    logger.info(f"  {f3_count} pagini F3 ({no_deviz} fara deviz_cod)")

    articles = extract_articles_v3(page_classes)
    logger.info(f"  {len(articles)} articole extrase din linii")

    # Deduplicate by 4-tuple: (deviz, cod, um, cantitate)
    # If same article appears multiple times with identical quantity and UM, keep only one
    seen_4tuple = {}
    deduped = []
    for art in articles:
        key = (art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
        if key not in seen_4tuple:
            deduped.append(art)
            seen_4tuple[key] = True

    if len(deduped) < len(articles):
        logger.info(f"  {len(articles) - len(deduped)} duplicates removed (same deviz/cod/um/cantitate)")
    articles = deduped

    # Extract articles from tables (structured F3 data)
    # Tables contain the same articles as pages but in structured format
    # Extract once from identified tables, not for each deviz separately
    from shared.table_extractor import extract_articles_from_tables_smart
    tables = di.get("tables", [])
    if tables:
        # Identify which devizes have tables with article data
        articles_from_tables = extract_articles_from_tables_smart(tables)

        # Merge: avoid duplicates by (deviz, cod, um, cantitate) 4-tuple
        article_4tuple = set()
        for art in articles:
            key = (art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
            article_4tuple.add(key)

        for art in articles_from_tables:
            key = (art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
            if key not in article_4tuple:
                articles.append(art)
                article_4tuple.add(key)

        logger.info(f"  {len(articles_from_tables)} articole din tabele, {len(articles)} total dupa merge")

    return articles


def compare_and_report(
    ref_articles: list,
    oferta_articles: list,
    oferta_nr: int,
    oferta_path: Path,
    client,
    model: str,
    include_prices: bool = False,
):
    """Compara oferta cu referinta si genereaza raport XLSX + DOCX."""
    from shared.deviz_normalizer import normalize_devize
    from shared.extraction_validator import mark_suspicious_extras
    from shared.orphan_detector import detect_orphans
    from shared.report_excel import generate_excel
    from shared.report_word import generate_word
    from AgentComparator_local import match_global

    # Normalizeaza devizele ofertei sa corespunda cu cele din referinta
    oferta_norm = normalize_devize(ref_articles, oferta_articles, client, model)

    # NO deviz reassignment - match strictly by (deviz, cod) pairs
    # If article code appears in different deviz, it's a DIFFERENT work item

    # Detecta coduri orphane (cod identical, deviz diferit)
    orphans = detect_orphans(ref_articles, oferta_norm)

    # Matching 3 straturi
    neconformitati, matches = match_global(
        ref_articles, oferta_norm, client, model, include_prices=include_prices
    )

    # Marcheaza EXTRA suspecte (codul exista in referinta dar cu alta denumire)
    ref_codes_text = " ".join(a.get("cod", "") for a in ref_articles)
    neconformitati = mark_suspicious_extras(neconformitati, ref_codes_text)

    # Adauga orphane-le la neconformitati cu tip special
    for orphan in orphans:
        neconformitati.append({
            'tip': 'ARTICOL_ORPHAN',
            'deviz_ref': orphan['ref_deviz'],
            'deviz_denumire': f'REF:{orphan["ref_deviz"]} vs OFERTA:{orphan["oferta_deviz"]}',
            'ref_cod': orphan['cod'],
            'ref_denumire': orphan['ref_denom'],
            'ref_um': orphan['ref_um'],
            'ref_cantitate': orphan['ref_cant'],
            'oferta_cod': orphan['cod'],
            'oferta_denom': orphan['oferta_denom'],
            'oferta_denumire': f"Deviz {orphan['oferta_deviz']}",
            'oferta_um': orphan['oferta_um'],
            'oferta_cantitate': orphan['oferta_cant'],
            'motiv': f'Cod {orphan["cod"]}: REF categoriei {orphan["ref_deviz"]} => OFERTA categoriei {orphan["oferta_deviz"]}',
        })

    # Salveaza JSON comparatie
    comparatie_path = OUTPUT_DIR / f"comparatie_oferta_{oferta_nr}.json"
    comparatie_path.write_text(
        json.dumps({
            "oferta_nr": oferta_nr,
            "neconformitati": neconformitati,
            "total_neconformitati": len(neconformitati),
            "matches": len(matches),
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    tipuri = Counter(n["tip"] for n in neconformitati)
    logger.info(f"  Neconformitati: {dict(tipuri)} (total: {len(neconformitati)})")
    logger.info(f"  Matched: {len(matches)} articole")

    # Obiecte necesare rapoartelor
    session = {"client_name": "", "obiect_investitii": ""}
    comp = {
        "oferta_nr": oferta_nr,
        "source_file": oferta_path.name,
        "ofertant": "",
        "neconformitati": neconformitati,
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

    # Raport DOCX
    docx_path = OUTPUT_DIR / f"Raport_Oferta_{oferta_nr}.docx"
    try:
        docx_bytes = generate_word(session, comp, comparison_mode=comparison_mode)
        docx_path.write_bytes(docx_bytes)
        logger.info(f"  DOCX: {docx_path.name}")
    except Exception as e:
        logger.warning(f"  DOCX failed: {e}")

    return neconformitati


def main():
    logger.info("=" * 50)
    logger.info("  Analizator Local Oferte Constructii")
    logger.info("=" * 50)
    logger.info(f"Input:  {INPUT_DIR}")
    logger.info(f"Output: {OUTPUT_DIR}")

    # Verifica input
    ref_path = INPUT_DIR / "di_referinta.json"
    if not ref_path.exists():
        logger.error(f"Referinta lipsa: {ref_path}")
        logger.error("Adauga di_referinta.json in folderul input_AO/")
        sys.exit(1)

    oferta_paths = sorted(INPUT_DIR.glob("di_oferta_*.json"))
    if not oferta_paths:
        logger.error(f"Nicio oferta gasita. Adauga di_oferta_1.json, di_oferta_2.json etc. in input_AO/")
        sys.exit(1)

    logger.info(f"Referinta: {ref_path.name}")
    logger.info(f"Oferte ({len(oferta_paths)}): {[p.name for p in oferta_paths]}")

    client, model = _build_client()

    # Step 1: Extrage referinta
    logger.info("\n--- Extragere REFERINTA ---")
    ref_articles = extract_document(ref_path, client, model)

    # Populate missing deviz denominations (so reports show work categories)
    from shared.deviz_namer import populate_deviz_denominations
    ref_articles = populate_deviz_denominations(ref_articles)

    ref_out = OUTPUT_DIR / "referinta.json"
    ref_out.write_text(
        json.dumps({"articole": ref_articles}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    logger.info(f"  Salvat: {ref_out.name}")

    # Extrage deviz codurile valide din referinta (pentru a filtra oferte cu devize extra)
    ref_deviz_codes = set(a.get("deviz", "") for a in ref_articles if a.get("deviz"))
    logger.info(f"  Deviz coduri valide din referinta: {sorted(ref_deviz_codes)}")

    # Step 2: Extrage + compara fiecare oferta
    for oferta_path in oferta_paths:
        try:
            oferta_nr = int(oferta_path.stem.replace("di_oferta_", ""))
        except ValueError:
            logger.warning(f"Nu pot extrage numarul din {oferta_path.name}, skip")
            continue

        logger.info(f"\n--- Extragere OFERTA {oferta_nr} ---")
        oferta_articles = extract_document(oferta_path, client, model, ref_deviz_codes=ref_deviz_codes)

        # Populate missing deviz denominations (so reports show work categories)
        oferta_articles = populate_deviz_denominations(oferta_articles)

        oferta_out = OUTPUT_DIR / f"oferta_{oferta_nr}.json"
        oferta_out.write_text(
            json.dumps({"articole": oferta_articles}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(f"\n--- Comparare OFERTA {oferta_nr} ---")
        compare_and_report(ref_articles, oferta_articles, oferta_nr, oferta_path, client, model)

    logger.info("\n" + "=" * 50)
    logger.info("  DONE")
    logger.info(f"  Rezultate in: {OUTPUT_DIR}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
