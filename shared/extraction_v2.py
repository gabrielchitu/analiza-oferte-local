"""ExtractionOrchestrator - unified extraction pipeline v2.

Coordinates all extraction components (TemplateDetector, TableExtractor,
RegexExtractor, ExtractionComparator, DevizHeaderExtractor) into a single
entry point for article extraction from DI JSON files.
"""

import json
import logging
from collections import defaultdict
from typing import Dict, List, Tuple, Optional
from pathlib import Path

from shared.template_detector import TemplateDetector
from shared.table_extractor import TableExtractor
from shared.extraction_comparator import ExtractionComparator
from shared.f3_regex_parser import extract_articles_regex
from shared.deviz_header_extractor import extract_deviz_headers
from shared.hierarchy_corrector import HierarchyCorrector

logger = logging.getLogger(__name__)


def _split_articles(articles: List, hdrs_list: List[Dict]) -> List[List]:
    """Split articles into len(hdrs_list) sub-groups.

    Strategy 1 (primary): COD header detection.
      Each sub-group starts with a marker article where:
        - cod == first token of the sub-group's categoria (e.g. "AN1", "BI0006")
        - cantitate == 0  AND  nr_ordine is None
      Consecutive same-code markers are deduplicated (OCR end-of-form artifacts).
      Marker articles themselves are excluded from output groups.

    Strategy 2 (fallback): NR reset detection.
      When NR goes from >2 back to ≤2 between consecutive articles.

    Returns [articles] (no split) if neither strategy yields exactly n groups.
    """
    n = len(hdrs_list)
    if n <= 1 or not articles:
        return [articles]

    # --- Strategy 1: COD header markers ---
    header_codes = set()
    for hdr in hdrs_list:
        cat = hdr.get("categoria", "")
        if cat:
            header_codes.add(cat.split()[0])

    if header_codes:
        groups: List[List] = []
        current: List = []
        current_header: Optional[str] = None

        for art in articles:
            cod = art.get("cod", "")
            nr_ordine = art.get("nr_ordine")
            cant = float(art.get("cantitate") or 0)

            if cod in header_codes and nr_ordine is None and cant == 0:
                if cod == current_header:
                    continue  # duplicate end-of-form marker — skip
                if current:
                    groups.append(current)
                    current = []
                current_header = cod
                continue  # skip header marker article

            current.append(art)

        if current:
            groups.append(current)

        if len(groups) == n:
            return groups

    # --- Strategy 2: NR reset (fallback) ---
    groups2: List[List] = [[]]
    prev_nr: Optional[int] = None

    for art in articles:
        nr_str = art.get("nr")
        nr_int = None
        if nr_str is not None:
            try:
                nr_int = int(str(nr_str).split(".")[0])
            except (ValueError, TypeError):
                pass

        if nr_int is not None and prev_nr is not None and nr_int <= 2 and prev_nr > 2:
            groups2.append([])

        groups2[-1].append(art)
        if nr_int is not None:
            prev_nr = nr_int

    if len(groups2) == n:
        return groups2

    # Both strategies failed — return single group (safe fallback, no regression)
    return [articles]


class ExtractionOrchestrator:
    """Orchestrate full extraction pipeline (v2).

    Workflow:
    1. Detect template (document type fingerprinting)
    2. Extract headers (deviz_cod, categoria)
    3. Per-page extraction (table + regex)
    4. Compare and pick best source
    5. Consolidate by group
    6. Return unified result
    """

    def __init__(self):
        """Initialize all sub-components."""
        self.template_detector = TemplateDetector()
        self.table_extractor = TableExtractor()
        self.extraction_comparator = ExtractionComparator()
        self.hierarchy_corrector = HierarchyCorrector()
        self.extraction_log = {"client": "", "pages": []}

    def extract_from_di(
        self,
        di_json: Dict,
        client_name: str,
        page_classes: Optional[List[Dict]] = None,
        deviz_headers: Optional[Dict[str, List[Dict]]] = None,
    ) -> Dict:
        """Extract articles from DI JSON file.

        Args:
            di_json: Document info dict with 'pages' and optional 'tables'
            client_name: Name of client (for logging and result metadata)

        Returns:
            Dict with structure:
            {
                "client": str,
                "di_file": str,
                "extraction_version": "2.0",
                "template_id": str,
                "grupos": [
                    {
                        "deviz_cod": str,
                        "deviz_den": str,
                        "source_pages": [int],
                        "articole": [article_dict],
                        ...
                    }
                ]
            }
        """
        self.extraction_log = {"client": client_name, "pages": []}

        # Step 1: Detect template
        template_id, fingerprint, certainty = self.template_detector.detect_template(
            di_json
        )
        logger.info(
            f"Template detection: {template_id} (certainty={certainty:.2f})"
        )

        # Step 2: Extract headers (deviz_cod, categoria)
        # extract_deviz_headers expects page_classifications list
        pages = di_json.get("pages", [])

        # Build page_idx → (deviz_cod, deviz_den) map from page_classes if available
        page_deviz_map: Dict[int, tuple] = {}
        if page_classes:
            for idx, pc in enumerate(page_classes):
                cod = pc.get("deviz_cod", "")
                den = pc.get("deviz_den", "")
                if cod:
                    page_deviz_map[idx] = (cod, den)

        # Step 3: Extract articles per page, grouped by deviz_cod
        articles_by_deviz: Dict[str, List] = defaultdict(list)
        deviz_den_map: Dict[str, str] = {}
        pages_by_deviz: Dict[str, List] = defaultdict(list)

        for page_idx, page in enumerate(pages):
            page_articles_table = []
            page_articles_regex = []

            # Get deviz_cod for this page from page_classes or fallback
            if page_idx in page_deviz_map:
                page_deviz_cod, page_deviz_den = page_deviz_map[page_idx]
            else:
                page_deviz_cod = page.get("deviz_cod", f"PAGE_{page_idx}")
                page_deviz_den = page.get("deviz_den", "")

            if page_deviz_cod and page_deviz_cod not in deviz_den_map:
                deviz_den_map[page_deviz_cod] = page_deviz_den

            # Try table extraction
            if "tables" in page and page.get("tables"):
                for table in page["tables"]:
                    table_articles, _, _ = self.table_extractor.extract(table)
                    page_articles_table.extend(table_articles)

            # Try regex extraction
            page_text = page.get("content", "")
            page_lines = page.get("lines", [])

            lines_to_parse = []
            if page_lines:
                for line_item in page_lines:
                    if isinstance(line_item, dict):
                        content = line_item.get("content", "")
                        if content:
                            lines_to_parse.append(content)
                    elif isinstance(line_item, str):
                        if line_item.strip():
                            lines_to_parse.append(line_item)

            if not lines_to_parse and page_text:
                lines_to_parse = page_text.split("\n")

            if lines_to_parse:
                page_articles_regex = extract_articles_regex(
                    lines_to_parse, page_deviz_cod, page_deviz_den
                )

            # Step 4: Compare and pick best
            best_articles, source, confidence = self.extraction_comparator.compare(
                page_articles_table, page_articles_regex
            )

            if best_articles:
                articles_by_deviz[page_deviz_cod].extend(best_articles)
                pages_by_deviz[page_deviz_cod].append(page_idx)

            self.extraction_log["pages"].append(
                {
                    "page_idx": page_idx,
                    "template_id": template_id,
                    "source_won": source,
                    "table_article_count": len(page_articles_table),
                    "regex_article_count": len(page_articles_regex),
                    "best_article_count": len(best_articles),
                    "confidence": confidence,
                }
            )

        # Step 5: Build grupos — one per deviz_cod with hierarchy correction
        grupos = []

        if not articles_by_deviz:
            pass  # no articles extracted
        elif len(articles_by_deviz) == 1 and "PAGE_0" in articles_by_deviz or all(
            k.startswith("PAGE_") for k in articles_by_deviz
        ):
            # Fallback: no page_classes available → single CONSOLIDATED group
            all_articles = []
            for arts in articles_by_deviz.values():
                all_articles.extend(arts)
            corrected, hierarchy_stats = self.hierarchy_corrector.correct(all_articles)
            grupos.append({
                "deviz_cod": "CONSOLIDATED",
                "deviz_den": "",
                "source_pages": list(range(len(pages))),
                "articole": corrected,
                "article_count": len(corrected),
                "hierarchy_stats": hierarchy_stats,
            })
        else:
            for deviz_cod, articles in articles_by_deviz.items():
                hdrs_list = (deviz_headers or {}).get(deviz_cod, [])

                if len(hdrs_list) > 1:
                    # Multiple logical groups share this deviz_cod — split into sub-groups
                    sub_groups = _split_articles(articles, hdrs_list)
                else:
                    sub_groups = [articles]

                for i, sub_arts in enumerate(sub_groups):
                    hdr = hdrs_list[i] if i < len(hdrs_list) else (hdrs_list[0] if hdrs_list else {})
                    corrected, hierarchy_stats = self.hierarchy_corrector.correct(sub_arts)
                    # Append sub-index to keep deviz_cod unique when split
                    group_cod = deviz_cod if len(sub_groups) == 1 else f"{deviz_cod}__{i}"
                    grupos.append({
                        "deviz_cod": group_cod,
                        "deviz_den": deviz_den_map.get(deviz_cod, ""),
                        "obiectivul": hdr.get("obiectivul", ""),
                        "obiectul": hdr.get("obiectul", ""),
                        "categoria": hdr.get("categoria", ""),
                        "source_pages": pages_by_deviz[deviz_cod],
                        "articole": corrected,
                        "article_count": len(corrected),
                        "hierarchy_stats": hierarchy_stats,
                    })

        # Filter out PAGE_N fallback groups (unclassified pages → garbage articles)
        grupos = [g for g in grupos if not str(g.get("deviz_cod", "")).startswith("PAGE_")]

        # Step 6: Return unified result
        return {
            "client": client_name,
            "di_file": "unknown",
            "extraction_version": "2.0",
            "template_id": template_id,
            "template_certainty": certainty,
            "grupos": grupos,
        }

    def match_reference_with_offer(
        self, ref_extracted: Dict, oferta_extracted: Dict
    ) -> Dict:
        """
        Match extracted reference with offer using v2 set-based matching.

        Performs group-level matching by deviz_cod, then article-level
        matching within each matched group. Returns v1-compatible holistic JSON.

        Args:
            ref_extracted: Extracted reference groups (output from extract_from_di).
                          Must have structure:
                          {
                              "client": str,
                              "di_file": str,
                              "extraction_version": "2.0",
                              "grupos": [group_dict, ...]
                          }
            oferta_extracted: Extracted offer grupos (same structure as ref_extracted)

        Returns:
            Dict with v1-compatible holistic structure:
            {
                "client": str,
                "di_file": str,
                "extraction_version": "2.0",
                "matched_groups": [matched_group_dict, ...],
                "ref_only_groups": [group_dict, ...],
                "oferta_only_groups": [group_dict, ...],
                "stats": {
                    "matched_articles_count": int,
                    "ref_only_articles_count": int,
                    "oferta_only_articles_count": int,
                    "matched_groups_count": int,
                    "ref_only_groups_count": int,
                    "oferta_only_groups_count": int
                }
            }

        Example:
            ref_data = orchestrator.extract_from_di(ref_json, "ClientName")
            offer_data = orchestrator.extract_from_di(offer_json, "ClientName")
            holistic = orchestrator.match_reference_with_offer(ref_data, offer_data)
        """
        from shared.matching_orchestrator_v2 import MatchingOrchestratorV2

        matcher = MatchingOrchestratorV2()
        holistic = matcher.match(ref_extracted, oferta_extracted)

        logger.info(
            f"Matching complete: {matcher.stats['matched_groups']} matched groups, "
            f"{matcher.stats['ref_only_groups']} ref-only, "
            f"{matcher.stats['oferta_only_groups']} oferta-only"
        )

        return holistic

    def get_extraction_log(self) -> Dict:
        """Return extraction metadata log."""
        return self.extraction_log

    def save_extraction_log(self, filepath: str) -> None:
        """Save extraction log to JSON file."""
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.extraction_log, f, indent=2, ensure_ascii=False)
        logger.info(f"Extraction log saved to {filepath}")
