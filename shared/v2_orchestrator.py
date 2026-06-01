"""V2EndToEndOrchestrator - Full v2 pipeline orchestration.

Coordinates extraction (S1-S2), matching (S3), and report generation (S4)
into a single end-to-end workflow that produces Raport_Oferta_N_v2.docx.

Entry point: orchestrator.run(client_config, oferta_num)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from shared.client_config import ClientConfig
from shared.extraction_v2 import ExtractionOrchestrator
from shared.matching_orchestrator_v2 import MatchingOrchestratorV2

logger = logging.getLogger(__name__)


# ── Neconformitate builders ────────────────────────────────────────────────


def _make_base_nc(ref_art: Dict, oferta_art: Dict, deviz_cod: str, deviz_den: str) -> Dict:
    """Build base neconformitate dict from a matched ref/oferta pair."""
    return {
        "deviz_ref": deviz_cod,
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
        "nr_ordine_ref": ref_art.get("nr_ordine"),
        "parent_cod_ref": ref_art.get("parent_code"),
        "parent_nr_ordine_ref": ref_art.get("parent_nr_ordine"),
        "display_parent_cod": ref_art.get("parent_code"),
        "cant_mostenita": False,
        "ref_source_pages": ref_art.get("source_pages", []),
        "oferta_cod": oferta_art.get("cod", ""),
        "oferta_denumire": oferta_art.get("denumire", ""),
        "oferta_um": oferta_art.get("um", ""),
        "oferta_cantitate": oferta_art.get("cantitate", ""),
        "nr_ordine_oferta": oferta_art.get("nr_ordine"),
        "oferta_display_parent_cod": oferta_art.get("parent_code"),
        "oferta_source_pages": oferta_art.get("source_pages", []),
    }


def _make_articol_lipsa(art: Dict, deviz_cod: str, deviz_den: str) -> Dict:
    """Build ARTICOL_LIPSA neconformitate for a ref-only article."""
    return {
        "tip": "ARTICOL_LIPSA",
        "oferta_cod": "",
        "oferta_denumire": "",
        "oferta_um": "",
        "oferta_cantitate": "",
        "deviz_ref": deviz_cod,
        "deviz_denumire": deviz_den,
        "is_component": art.get("is_component", False),
        "ref_cod": art.get("cod", ""),
        "ref_denumire": art.get("denumire", ""),
        "ref_um": art.get("um", ""),
        "ref_cantitate": art.get("cantitate", ""),
        "ref_pret_material": art.get("pret_material", 0),
        "ref_pret_manopera": art.get("pret_manopera", 0),
        "ref_pret_utilaj": art.get("pret_utilaj", 0),
        "ref_pret_transport": art.get("pret_transport", 0),
        "ref_val_material": art.get("val_material", 0),
        "ref_val_manopera": art.get("val_manopera", 0),
        "ref_val_uitaj": art.get("val_utilaj", 0),
        "ref_val_transport": art.get("val_transport", 0),
        "nr_ordine_ref": art.get("nr_ordine"),
        "parent_cod_ref": art.get("parent_code"),
        "parent_nr_ordine_ref": art.get("parent_nr_ordine"),
        "display_parent_cod": art.get("parent_code"),
        "cant_mostenita": False,
        "ref_source_pages": art.get("source_pages", []),
    }


def _make_articol_extra(art: Dict, deviz_cod: str, deviz_den: str) -> Dict:
    """Build ARTICOL_EXTRA neconformitate for an oferta-only article."""
    return {
        "tip": "ARTICOL_EXTRA",
        "deviz_ref": deviz_cod,
        "deviz_denumire": deviz_den,
        "is_component": art.get("is_component", False),
        "ref_cod": "",
        "ref_denumire": "",
        "oferta_cod": art.get("cod", ""),
        "oferta_denumire": art.get("denumire", ""),
        "oferta_um": art.get("um", ""),
        "oferta_cantitate": art.get("cantitate", ""),
        "oferta_display_parent_cod": art.get("parent_code"),
        "nr_ordine_oferta": art.get("nr_ordine"),
        "oferta_source_pages": art.get("source_pages", []),
    }


def _build_v1_holistic(v2_holistic: Dict) -> Dict:
    """Convert V2 holistic JSON to V1-compatible holistic for report_word.py.

    V2 matched_group has: deviz_cod, deviz_den, articole (pairs), ref_only, oferta_only
    V1 matched_group needs: ref_deviz_cod, oferta_deviz_cod, ref_header, oferta_header,
                            deviz_denumire, ref_articles, oferta_articles,
                            neconformitati, matches

    Builds neconformitati by:
    - Running compare_articles() on each matched pair → field-level diffs
    - Adding ARTICOL_LIPSA for ref_only articles within the group
    - Adding ARTICOL_EXTRA for oferta_only articles within the group
    - Adding ARTICOL_LIPSA for all articles in ref_only_groups
    - Adding ARTICOL_EXTRA for all articles in oferta_only_groups
    """
    from shared.comparator import compare_articles

    neconf_by_tip: Dict[str, int] = {}
    total_matched = 0
    v1_matched_groups: List[Dict] = []

    for mg in v2_holistic.get("matched_groups", []):
        deviz_cod = mg.get("deviz_cod", "")
        deviz_den = mg.get("deviz_den", "")
        pair_articles = mg.get("articole", [])
        ref_only_arts = mg.get("ref_only", [])
        oferta_only_arts = mg.get("oferta_only", [])

        ref_articles = [p["ref"] for p in pair_articles] + ref_only_arts
        oferta_articles = [p["oferta"] for p in pair_articles] + oferta_only_arts

        neconformitati: List[Dict] = []
        matches: List[Dict] = []

        for pair in pair_articles:
            ref_art = pair["ref"]
            oferta_art = pair["oferta"]
            diffs = compare_articles(ref_art, oferta_art)
            if diffs:
                base = _make_base_nc(ref_art, oferta_art, deviz_cod, deviz_den)
                for diff in diffs:
                    nc = {**base, **diff}
                    neconformitati.append(nc)
                    tip = diff.get("tip", "DIFERENTA_CAMP")
                    neconf_by_tip[tip] = neconf_by_tip.get(tip, 0) + 1
            matches.append({
                "ref_cod": ref_art.get("cod", ""),
                "oferta_cod": oferta_art.get("cod", ""),
            })

        total_matched += len(matches)

        for art in ref_only_arts:
            nc = _make_articol_lipsa(art, deviz_cod, deviz_den)
            neconformitati.append(nc)
            neconf_by_tip["ARTICOL_LIPSA"] = neconf_by_tip.get("ARTICOL_LIPSA", 0) + 1

        for art in oferta_only_arts:
            nc = _make_articol_extra(art, deviz_cod, deviz_den)
            neconformitati.append(nc)
            neconf_by_tip["ARTICOL_EXTRA"] = neconf_by_tip.get("ARTICOL_EXTRA", 0) + 1

        header = f"{deviz_cod} {deviz_den}".strip()
        v1_matched_groups.append({
            "ref_deviz_cod": deviz_cod,
            "oferta_deviz_cod": deviz_cod,
            "ref_header": header,
            "oferta_header": header,
            "deviz_denumire": deviz_den,
            "ref_articles": ref_articles,
            "oferta_articles": oferta_articles,
            "neconformitati": neconformitati,
            "matches": matches,
        })

    v1_ref_only_groups: List[Dict] = []
    for rg in v2_holistic.get("ref_only_groups", []):
        deviz_cod = rg.get("deviz_cod", "")
        deviz_den = rg.get("deviz_den", "")
        articles = rg.get("articole", [])
        neconformitati = []
        for art in articles:
            nc = _make_articol_lipsa(art, deviz_cod, deviz_den)
            neconformitati.append(nc)
            neconf_by_tip["ARTICOL_LIPSA"] = neconf_by_tip.get("ARTICOL_LIPSA", 0) + 1
        header = f"{deviz_cod} {deviz_den}".strip()
        v1_ref_only_groups.append({
            "ref_deviz_cod": deviz_cod,
            "ref_header": header,
            "deviz_denumire": deviz_den,
            "articles": articles,
            "neconformitati": neconformitati,
        })

    v1_oferta_only_groups: List[Dict] = []
    for og in v2_holistic.get("oferta_only_groups", []):
        deviz_cod = og.get("deviz_cod", "")
        deviz_den = og.get("deviz_den", "")
        articles = og.get("articole", [])
        neconformitati = []
        for art in articles:
            nc = _make_articol_extra(art, deviz_cod, deviz_den)
            neconformitati.append(nc)
            neconf_by_tip["ARTICOL_EXTRA"] = neconf_by_tip.get("ARTICOL_EXTRA", 0) + 1
        header = f"{deviz_cod} {deviz_den}".strip()
        v1_oferta_only_groups.append({
            "oferta_deviz_cod": deviz_cod,
            "oferta_header": header,
            "deviz_denumire": deviz_den,
            "articles": articles,
            "neconformitati": neconformitati,
        })

    return {
        "matched_groups": v1_matched_groups,
        "ref_only_groups": v1_ref_only_groups,
        "oferta_only_groups": v1_oferta_only_groups,
        "ungrouped": [],
        "unassigned_articles": [],
        "sumar": {
            "total_matched_articles": total_matched,
            "neconformitati_by_tip": neconf_by_tip,
        },
    }


# ── Orchestrator ───────────────────────────────────────────────────────────


class V2EndToEndOrchestrator:
    """Orchestrate full v2 pipeline: extract → match → report.

    Workflow:
    1. Load reference and offer DI JSON files from input_AO/
    2. Extract articles from reference (ExtractionOrchestrator)
    3. Extract articles from each offer
    4. Match reference with offer (MatchingOrchestratorV2)
    5. Convert V2 holistic → V1-compatible holistic with neconformitati
    6. Generate Word report using shared/report_word.py (identical format to V1)
    7. Save holistic JSON and report to output_AO/
    8. Return all artifacts and paths

    Intermediate results are cached to avoid re-extraction on re-runs.
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        self.extraction_orch = ExtractionOrchestrator()
        self.matching_orch = MatchingOrchestratorV2()

        if cache_dir is None:
            cache_dir = Path.home() / ".claude" / "cache" / "v2_orchestrator"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def run(self, client_config: ClientConfig, oferta_num: int) -> Dict:
        """Execute full v2 pipeline for one offer.

        Returns:
            Dict with keys:
            {
                "client": str,
                "oferta_num": int,
                "extracted_ref": Dict,
                "extracted_offer": Dict,
                "holistic_json": Dict,       # V2 holistic (set-based stats)
                "holistic_json_path": Path,  # Where holistic JSON saved
                "report_path": Optional[Path],
                "stats": Dict,
                "cache_hit": bool,
            }
        """
        logger.info(
            f"Starting v2 pipeline for {client_config.name} oferta {oferta_num}"
        )

        di_ref = self._load_di_json(client_config.reference_file)

        offer_file = None
        for f in client_config.offer_files:
            if f"oferta_{oferta_num}" in f.name or f"oferta{oferta_num}" in f.name:
                offer_file = f
                break
        if not offer_file:
            raise FileNotFoundError(
                f"Offer {oferta_num} not found for {client_config.name}"
            )
        di_offer = self._load_di_json(offer_file)

        ref_stem = client_config.reference_file.stem
        cache_key_ref = f"{client_config.name}_referinta"
        extracted_ref = self._cached_extraction(
            cache_key_ref, di_ref, client_config.name,
            client_config=client_config, di_file_stem=ref_stem, is_offer=False,
        )
        logger.info(f"Extracted reference: {len(extracted_ref.get('grupos', []))} grupos")

        offer_stem = offer_file.stem
        cache_key_offer = f"{client_config.name}_oferta_{oferta_num}"
        extracted_offer = self._cached_extraction(
            cache_key_offer, di_offer, client_config.name,
            client_config=client_config, di_file_stem=offer_stem, is_offer=True,
        )
        logger.info(f"Extracted offer: {len(extracted_offer.get('grupos', []))} grupos")

        logger.info("Matching reference with offer...")
        holistic = self.matching_orch.match(extracted_ref, extracted_offer)
        stats = holistic.get("stats", {})
        logger.info(f"Matched: {stats.get('matched_articles_count', 0)} articles")

        holistic_path = self._save_holistic_json(holistic, client_config, oferta_num)
        logger.info(f"Saved holistic JSON to {holistic_path}")

        report_path = self._generate_report(
            holistic, client_config, oferta_num, extracted_ref, extracted_offer
        )
        if report_path:
            logger.info(f"Generated report to {report_path}")
        else:
            logger.warning("Report generation skipped")

        return {
            "client": client_config.name,
            "oferta_num": oferta_num,
            "extracted_ref": extracted_ref,
            "extracted_offer": extracted_offer,
            "holistic_json": holistic,
            "holistic_json_path": holistic_path,
            "report_path": report_path,
            "stats": stats,
            "cache_hit": False,
        }

    def _load_di_json(self, file_path: Path) -> Dict:
        if not file_path.exists():
            raise FileNotFoundError(f"DI JSON not found: {file_path}")
        with open(file_path, "r") as f:
            return json.load(f)

    def _load_page_classes(
        self, client_config: ClientConfig, di_file_stem: str
    ) -> Optional[List[Dict]]:
        """Load V1 page_classes checkpoint for a DI file.

        Checkpoints are saved by local_run.py as:
        output_AO/{Client}/checkpoints/di_{stem}_page_classes_{hash}.json

        Returns page_classes list or None if not found.
        """
        checkpoint_dir = client_config.output_dir / "checkpoints"
        if not checkpoint_dir.exists():
            return None
        pattern = f"{di_file_stem}_page_classes_*.json"
        matches = list(checkpoint_dir.glob(pattern))
        if not matches:
            return None
        with open(matches[0]) as f:
            data = json.load(f)
        if isinstance(data, list):
            pcs = data
        else:
            pcs = data.get("page_classes", [])
        logger.debug(f"Loaded {len(pcs)} page_classes from {matches[0].name}")
        return pcs

    def _cached_extraction(
        self,
        cache_key: str,
        di_json: Dict,
        client_name: str,
        client_config: Optional[ClientConfig] = None,
        di_file_stem: Optional[str] = None,
        is_offer: bool = False,
    ) -> Dict:
        cache_file = self.cache_dir / f"{cache_key}_extracted.json"
        if cache_file.exists():
            cached = json.load(open(cache_file))
            # Re-extract if cached result is CONSOLIDATED (stale)
            grupos = cached.get("grupos", [])
            if len(grupos) == 1 and grupos[0].get("deviz_cod") == "CONSOLIDATED":
                logger.debug(f"Stale CONSOLIDATED cache for {cache_key} — re-extracting")
            else:
                logger.debug(f"Loading cached extraction for {cache_key}")
                return cached

        doc_type = "oferta" if is_offer else "referinta"
        logger.debug(f"Extracting {doc_type} {client_name}...")

        # Try to load page_classes for proper deviz grouping
        page_classes = None
        if client_config and di_file_stem:
            page_classes = self._load_page_classes(client_config, di_file_stem)
            if page_classes:
                logger.info(f"Using {len(page_classes)} page_classes for {di_file_stem}")

        extracted = self.extraction_orch.extract_from_di(
            di_json, client_name, page_classes=page_classes
        )

        with open(cache_file, "w") as f:
            json.dump(extracted, f, indent=2)

        return extracted

    def _save_holistic_json(
        self, holistic: Dict, client_config: ClientConfig, oferta_num: int
    ) -> Path:
        output_dir = client_config.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"holistic_oferta_{oferta_num}_v2.json"
        with open(output_file, "w") as f:
            json.dump(holistic, f, indent=2)
        return output_file

    def _load_v1_holistic(
        self, client_config: ClientConfig, oferta_num: int
    ) -> Optional[Dict]:
        """Load V1 holistic JSON if available (produced by main V1 pipeline)."""
        v1_path = client_config.output_dir / f"holistic_oferta_{oferta_num}.json"
        if not v1_path.exists():
            return None
        with open(v1_path) as f:
            return json.load(f)

    def _generate_report(
        self,
        holistic: Dict,
        client_config: ClientConfig,
        oferta_num: int,
        extracted_ref: Optional[Dict] = None,
        extracted_offer: Optional[Dict] = None,
    ) -> Optional[Path]:
        """Generate Word report identical in format to V1.

        Strategy:
        1. If V1 holistic JSON exists → use it directly (already has neconformitati)
        2. Else → convert V2 holistic → V1 format via _build_v1_holistic()

        Both paths call shared/report_word.py generate_word() for identical format.
        """
        try:
            from shared.report_word import generate_word

            # Prefer V1 holistic (has proper neconformitati from full V1 pipeline)
            v1_holistic = self._load_v1_holistic(client_config, oferta_num)
            if v1_holistic:
                logger.info("Using V1 holistic JSON for report generation")
            else:
                logger.info("V1 holistic not found, building from V2 holistic")
                v1_holistic = _build_v1_holistic(holistic)

            sumar = v1_holistic.get("sumar", {})
            total_matched = sumar.get("total_matched_articles", 0)
            total_neconf = sum(sumar.get("neconformitati_by_tip", {}).values())

            # Count articles from holistic
            ref_arts = sum(
                len(mg.get("ref_articles", [])) for mg in v1_holistic.get("matched_groups", [])
            ) + sum(
                len(rg.get("articles", [])) for rg in v1_holistic.get("ref_only_groups", [])
            )
            oferta_arts = sum(
                len(mg.get("oferta_articles", [])) for mg in v1_holistic.get("matched_groups", [])
            ) + sum(
                len(og.get("articles", [])) for og in v1_holistic.get("oferta_only_groups", [])
            )

            session = {
                "client_name": client_config.name,
                "obiect_investitii": "",
            }
            comp = {
                "oferta_nr": oferta_num,
                "source_file": f"di_oferta_{oferta_num}.json",
                "ofertant": client_config.name,
                "ref_art_count": ref_arts or "?",
                "oferta_art_count": oferta_arts or "?",
                "matches": total_matched,
                "total_neconformitati": total_neconf,
                "neconformitati": [],
                "deviz_mismatches": [],
                "raport_holistic": v1_holistic,
            }

            doc_bytes = generate_word(session, comp)

            output_dir = client_config.output_dir
            output_dir.mkdir(parents=True, exist_ok=True)
            report_path = output_dir / f"Raport_Oferta_{oferta_num}_v2.docx"
            with open(report_path, "wb") as f:
                f.write(doc_bytes)

            return report_path

        except Exception as e:
            logger.error(f"Report generation failed: {e}", exc_info=True)
            return None
