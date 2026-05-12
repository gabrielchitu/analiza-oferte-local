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
    logger.info(f"Model Anthropic: {model}")
    return AnthropicAdapter(anthropic.Anthropic(api_key=api_key), model=model), model


def _normalize_deviz_for_filter(cod: str) -> str:
    """Normalizeaza cod deviz pentru comparare cu ref_deviz_codes (U→0, OCR fix)."""
    return (cod or "").replace("U", "0")


def _checkpoint_path(di_path: Path) -> Path:
    """Returnează calea checkpoint-ului pentru un document DI."""
    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    return CHECKPOINT_DIR / f"{di_path.stem}_page_classes_{_clf_hash}.json"


def _extract_ofertant_name(di_path: Path) -> str:
    """
    Extrage numele ofertantului din DI JSON (primele 10 pagini).

    Strategii în ordine de prioritate:
      A) 'OFERTANT,' singur pe linie → linia/liniile imediat urmatoare
      B) 'Ofertant: NUME' inline → extrage după ':'
      C) 'Asociere: NUME' sau 'denumirea Asociere: NUME'
      D) Fallback: 'Oferta N' din numele fișierului
    """
    import re as _re
    try:
        di = json.loads(di_path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    pages = di.get("pages", [])[:10]

    def _is_company_line(s: str) -> bool:
        s = s.strip()
        return bool(s) and (
            _re.search(r'\bS\.?C\.?\b|\bSRL\b|\bSA\b|\bRA\b|\bAsociere\b|Asocierea', s, _re.I)
            or (s.isupper() and len(s) > 8)
            or s.startswith("-")
        )

    for p in pages:
        lines = [l.get("content", "") for l in p.get("lines", [])]
        for i, line in enumerate(lines):
            ls = line.strip()

            # Pattern A: OFERTANT, singur pe linie
            if _re.match(r'^OFERTANT\s*[,.]?\s*$', ls, _re.IGNORECASE):
                parts = []
                for j in range(i + 1, min(i + 5, len(lines))):
                    cand = lines[j].strip()
                    if not cand or _re.match(r'^(Director|Semnatura|Nume|Data\b)', cand, _re.I):
                        break
                    parts.append(cand)
                if parts:
                    name = " ".join(parts)
                    name = _re.sub(r'\s+', ' ', name).strip()
                    return name

            # Pattern B: Ofertant: INLINE_NAME (minim 10 chars)
            m = _re.match(r'^Ofertant\s*:\s*(.+)', ls, _re.IGNORECASE)
            if m and len(m.group(1).strip()) > 10:
                return m.group(1).strip()

            # Pattern C: Asociere: / denumirea Asociere: INLINE_NAME
            m = _re.search(r'(?:denumirea\s+)?Asociere\s*:\s*(.+)', ls, _re.IGNORECASE)
            if m and len(m.group(1).strip()) > 8:
                return m.group(1).strip()

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


def extract_document(di_path: Path, client, model: str) -> list:
    """
    Extrage articolele F3 dintr-un DI JSON.
    Foloseste checkpoint daca exista — sare peste clasificarea LLM (pasul lent).

    Extrage TOATE devizele fara filtru. Devizele prezente in oferta dar absente
    din referinta sunt surfacate ca alerte in raport, nu ascunse.
    """
    from shared.f3_page_classifier import classify_pages
    from shared.f3_extractor import extract_articles_v3

    checkpoint = _checkpoint_path(di_path)

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

    # Re-clasificare LLM tintita: pagini is_f3=False cu semnal F3 detectat euristic.
    # Ruleaza NUMAI cand exista astfel de pagini — LLM e apelat doar pentru candidate.
    page_classes, checkpoint_updated = _reclassify_missed_f3_pages(
        page_classes, pages, checkpoint, client, model
    )

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

        # Merge: tabela are prioritate fata de linii in 3 cazuri:
        # 1. Duplicat exact (deviz, cod, um, cantitate) → skip
        # 2. Acelasi (deviz, cod, cantitate) dar UM diferit → tabela inlocuieste
        # 3. Acelasi (deviz, cod) iar linia are cant=0 (esec parsare) → tabela inlocuieste
        article_3key = {}   # (deviz, cod, cantitate) -> index in articles
        article_2key_zero = {}  # (deviz, cod) -> index, doar pt cant=0 (esec parsare)
        article_4tuple = set()
        for i, art in enumerate(articles):
            k3 = (art.get("deviz"), art.get("cod"), art.get("cantitate"))
            article_3key[k3] = i
            if (art.get("cantitate") or 0) == 0:
                article_2key_zero[(art.get("deviz"), art.get("cod"))] = i
            article_4tuple.add((art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate")))

        for art in articles_from_tables:
            k4 = (art.get("deviz"), art.get("cod"), art.get("um"), art.get("cantitate"))
            k3 = (art.get("deviz"), art.get("cod"), art.get("cantitate"))
            k2 = (art.get("deviz"), art.get("cod"))
            tbl_cant = art.get("cantitate") or 0
            if k4 in article_4tuple:
                continue  # duplicat exact
            if k3 in article_3key:
                # Acelasi articol, UM diferit — tabela castiga
                old_idx = article_3key[k3]
                articles[old_idx] = art
                article_4tuple.add(k4)
            elif k2 in article_2key_zero and tbl_cant != 0:
                # Linia a extras cant=0 (esec) → tabela cu cantitate reala inlocuieste
                old_idx = article_2key_zero[k2]
                old_art = articles[old_idx]
                del article_3key[(old_art.get("deviz"), old_art.get("cod"), 0)]
                article_2key_zero.pop(k2)
                articles[old_idx] = art
                article_3key[k3] = old_idx
                article_4tuple.add(k4)
            else:
                articles.append(art)
                article_3key[k3] = len(articles) - 1
                article_4tuple.add(k4)

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
    ofertant_name: str = "",
):
    """Compara oferta cu referinta si genereaza raport XLSX + DOCX."""
    from shared.deviz_normalizer import normalize_devize
    from shared.deviz_mismatch_detector import detect_deviz_mismatches
    from shared.extraction_validator import mark_suspicious_extras
    from shared.orphan_detector import detect_orphans
    from shared.report_excel import generate_excel
    from shared.report_word import generate_word
    from AgentComparator_local import match_global

    # Normalizeaza devizele ofertei sa corespunda cu cele din referinta
    oferta_norm = normalize_devize(ref_articles, oferta_articles, client, model)

    # Detectare deviz mismatch (devize din oferta cu cod diferit dar articole similare)
    deviz_mismatches = detect_deviz_mismatches(ref_articles, oferta_norm)
    _deviz_remap: dict = {}  # oferta_deviz → ref_deviz pentru mismatch-uri cu overlap inalt
    if deviz_mismatches:
        for m in deviz_mismatches:
            logger.warning(
                f"  [DEVIZ_MISMATCH] Deviz {m['oferta_deviz']} din oferta (~{m['overlap_score']:.0%} overlap) "
                f"pare echivalentul lui {m['ref_deviz']} din referinta "
                f"({m['oferta_art_count']} vs {m['ref_art_count']} articole)"
            )
            # Remap automat cand overlap e foarte inalt (≥90%): redenumeste codul deviz
            # in articolele ofertei astfel incat Layer 1 sa le potriveasca cu referinta.
            # Ofertantul a numerotata devizele diferit (226113 vs 226118) — acelasi continut.
            if m['overlap_score'] >= 0.9:
                _deviz_remap[m['oferta_deviz']] = m['ref_deviz']

    if _deviz_remap:
        for art in oferta_norm:
            old = art.get('deviz', '')
            if old in _deviz_remap:
                art['deviz'] = _deviz_remap[old]
                art['_deviz_original'] = old  # pastram originalul pt raport
        logger.info(f"  Remap devize oferta: {_deviz_remap}")

    # Matching 3 straturi — returneaza si cheile REF match-uite
    neconformitati, matches, matched_ref_keys = match_global(
        ref_articles, oferta_norm, client, model, include_prices=include_prices
    )

    # Detecta orphane DUPA matching: cod din REF neacoperit dar prezent in O2 sub alt deviz
    # matched_ref_keys exclude articolele deja acoperite (fara produs cartezian)
    orphans = detect_orphans(ref_articles, oferta_norm, matched_ref_keys=matched_ref_keys)

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

    # Colecteaza devize_extra si devize_lipsa pentru raport
    from collections import defaultdict as _defaultdict
    ref_devize_set = {a.get('deviz', '') for a in ref_articles if a.get('deviz')}
    oferta_devize_set = {a.get('deviz', '') for a in oferta_norm if a.get('deviz')}

    oferta_devize_art_count = _defaultdict(int)
    for a in oferta_norm:
        oferta_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_art_count = _defaultdict(int)
    for a in ref_articles:
        ref_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_den = {}
    for a in ref_articles:
        d = a.get('deviz', ''); n = a.get('deviz_denumire', '')
        if d and n:
            ref_devize_den[d] = n

    _devize_extra = [
        {
            'deviz': d,
            'denumire': next((a.get('deviz_denumire', '') for a in oferta_norm
                              if a.get('deviz') == d), ''),
            'art_count': oferta_devize_art_count[d],
        }
        for d in sorted(oferta_devize_set - ref_devize_set - {''})
    ]
    _devize_lipsa = [
        {
            'deviz': d,
            'denumire': ref_devize_den.get(d, ''),
            'art_count': ref_devize_art_count[d],
        }
        for d in sorted(ref_devize_set - oferta_devize_set - {''})
    ]

    # Salveaza JSON comparatie
    comparatie_path = OUTPUT_DIR / f"comparatie_oferta_{oferta_nr}.json"
    comparatie_path.write_text(
        json.dumps({
            "oferta_nr": oferta_nr,
            "neconformitati": neconformitati,
            "total_neconformitati": len(neconformitati),
            "matches": len(matches),
            "deviz_mismatches": deviz_mismatches,
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
        "ofertant": ofertant_name or f"Oferta {oferta_nr}",
        "neconformitati": neconformitati,
        "ref_art_count": len(ref_articles),
        "oferta_art_count": len(oferta_norm),
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
        docx_bytes = generate_word(
            session, comp,
            comparison_mode=comparison_mode,
            devize_extra=_devize_extra,
            devize_lipsa=_devize_lipsa,
        )
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

    ref_deviz_codes = set(a.get("deviz", "") for a in ref_articles if a.get("deviz"))
    logger.info(f"  {len(ref_deviz_codes)} devize in referinta")

    # Step 2: Extrage + compara fiecare oferta (fara filtru de devize)
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
        oferta_articles = extract_document(oferta_path, client, model)

        # Populate missing deviz denominations (so reports show work categories)
        oferta_articles = populate_deviz_denominations(oferta_articles)

        # Identificare devize extra (in oferta dar absente din referinta) — alerta calitate
        oferta_deviz_codes = set(a.get("deviz", "") for a in oferta_articles if a.get("deviz"))
        devize_extra = oferta_deviz_codes - ref_deviz_codes - {""}
        devize_lipsa_din_oferta = ref_deviz_codes - oferta_deviz_codes
        if devize_extra:
            logger.warning(f"  ALERTA: {len(devize_extra)} devize in oferta ABSENTE din referinta: {sorted(devize_extra)}")
            logger.warning(f"  → Posibil F3 neextras din referinta SAU lucrari suplimentare propuse de ofertant")
        if devize_lipsa_din_oferta:
            logger.info(f"  {len(devize_lipsa_din_oferta)} devize din referinta NEACOPERITE de oferta: {sorted(devize_lipsa_din_oferta)}")

        oferta_out = OUTPUT_DIR / f"oferta_{oferta_nr}.json"
        oferta_out.write_text(
            json.dumps({"articole": oferta_articles}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        logger.info(f"\n--- Comparare OFERTA {oferta_nr} ---")
        compare_and_report(ref_articles, oferta_articles, oferta_nr, oferta_path, client, model,
                           ofertant_name=ofertant_name)

    logger.info("\n" + "=" * 50)
    logger.info("  DONE")
    logger.info(f"  Rezultate in: {OUTPUT_DIR}")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
