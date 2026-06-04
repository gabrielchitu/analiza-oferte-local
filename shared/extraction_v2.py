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

        # Build page_idx → (deviz_cod, deviz_den, obiectul_text, categoria_text) map
        # obiectul_text/categoria_text are forward-filled within same deviz_cod so that
        # pages following the first header page inherit the right group assignment.
        page_deviz_map: Dict[int, Tuple[str, str, str, str]] = {}
        if page_classes:
            prev_cod, prev_obj, prev_cat = "", "", ""
            for idx, pc in enumerate(page_classes):
                cod = pc.get("deviz_cod", "") or ""
                den = pc.get("deviz_den", "") or ""
                if cod:
                    obj_raw = pc.get("obiectul") or ""
                    if isinstance(obj_raw, dict):
                        num = obj_raw.get("num", "") or ""
                        txt = obj_raw.get("text", "") or ""
                        obj_text = f"{num} {txt}".strip() if num else txt
                    else:
                        obj_text = str(obj_raw) if obj_raw else ""
                    cat_raw = pc.get("categoria") or ""
                    if isinstance(cat_raw, dict):
                        num = cat_raw.get("num", "") or ""
                        txt = cat_raw.get("text", "") or ""
                        cat_text = f"{num} {txt}".strip() if num else txt
                    else:
                        cat_text = str(cat_raw) if cat_raw else ""
                    # Forward-fill within same deviz_cod only.
                    # Reset when deviz_cod changes to avoid inheriting the previous
                    # group's obiectul on the first page of a new group.
                    if cod == prev_cod:
                        if not obj_text:
                            obj_text = prev_obj
                        if not cat_text:
                            cat_text = prev_cat
                    # else: new deviz_cod group — keep obj_text/cat_text as-is (may be empty)
                    page_deviz_map[idx] = (cod, den, obj_text, cat_text)
                    prev_cod = cod
                    prev_obj = obj_text
                    prev_cat = cat_text

        # Step 3: Extract articles per page, grouped by (deviz_cod, obiectul_text).
        # Using obiectul as secondary key handles clients where multiple logical groups
        # share the same deviz_cod in page_classes but differ by obiectul (e.g. BR BLOCS).
        GroupKey = Tuple[str, str]  # (deviz_cod, obiectul_text)
        articles_by_deviz: Dict[GroupKey, List] = defaultdict(list)
        deviz_den_map: Dict[str, str] = {}
        pages_by_deviz: Dict[GroupKey, List] = defaultdict(list)
        obj_text_by_key: Dict[GroupKey, str] = {}
        cat_text_by_key: Dict[GroupKey, str] = {}

        for page_idx, page in enumerate(pages):
            page_articles_table = []
            page_articles_regex = []

            # Get deviz_cod for this page from page_classes or fallback
            if page_idx in page_deviz_map:
                page_deviz_cod, page_deviz_den, page_obj, page_cat = page_deviz_map[page_idx]
            else:
                page_deviz_cod = page.get("deviz_cod", f"PAGE_{page_idx}")
                page_deviz_den = page.get("deviz_den", "")
                page_obj, page_cat = "", ""

            group_key: GroupKey = (page_deviz_cod, page_obj)

            if page_deviz_cod and page_deviz_cod not in deviz_den_map:
                deviz_den_map[page_deviz_cod] = page_deviz_den
            if group_key not in obj_text_by_key:
                obj_text_by_key[group_key] = page_obj
                cat_text_by_key[group_key] = page_cat

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
                articles_by_deviz[group_key].extend(best_articles)
                pages_by_deviz[group_key].append(page_idx)

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

        # Step 5: Build grupos — one per (deviz_cod, obiectul_text) compound key.
        # When multiple groups share the same deviz_cod (different obiectul), they get
        # unique deviz_cod suffixes (__0, __1, …) so downstream code treats them separately.
        grupos = []

        all_page_keys = set(articles_by_deviz.keys())
        is_page_fallback = all_page_keys and all(
            k[0].startswith("PAGE_") for k in all_page_keys
        )

        if not articles_by_deviz:
            pass  # no articles extracted
        elif is_page_fallback:
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
            # Group compound keys by deviz_cod to assign sequential suffixes
            from collections import defaultdict as _dd
            keys_by_cod: Dict[str, List[GroupKey]] = _dd(list)
            for gk in articles_by_deviz.keys():
                keys_by_cod[gk[0]].append(gk)

            for deviz_cod, gkeys in keys_by_cod.items():
                hdrs_list = (deviz_headers or {}).get(deviz_cod, [])
                n_keys = len(gkeys)

                for i, gkey in enumerate(gkeys):
                    articles = articles_by_deviz[gkey]
                    obj_text = obj_text_by_key.get(gkey, "")
                    cat_text = cat_text_by_key.get(gkey, "")

                    # When only 1 compound-key for this deviz_cod AND >1 deviz_headers:
                    # fallback to _split_articles (e.g. DT's 0017-0169 with no per-page obiectul)
                    if n_keys == 1 and len(hdrs_list) > 1:
                        sub_groups = _split_articles(articles, hdrs_list)
                        for j, sub_arts in enumerate(sub_groups):
                            hdr = hdrs_list[j] if j < len(hdrs_list) else (hdrs_list[0] if hdrs_list else {})
                            corrected, hierarchy_stats = self.hierarchy_corrector.correct(sub_arts)
                            group_cod = deviz_cod if len(sub_groups) == 1 else f"{deviz_cod}__{j}"
                            grupos.append({
                                "deviz_cod": group_cod,
                                "deviz_den": deviz_den_map.get(deviz_cod, ""),
                                "obiectivul": hdr.get("obiectivul", ""),
                                "obiectul": hdr.get("obiectul", ""),
                                "categoria": hdr.get("categoria", ""),
                                "source_pages": pages_by_deviz[gkey],
                                "articole": corrected,
                                "article_count": len(corrected),
                                "hierarchy_stats": hierarchy_stats,
                            })
                        continue

                    # Normal case: each compound key → one grupo.
                    # Use deviz_headers for the canonical obiectul/categoria text —
                    # page_classes values are raw OCR and may contain administrative
                    # garbage that hurts matching scores.  page_classes obj_text is
                    # used only as the split key (above); deviz_headers is the source
                    # of truth for the actual header content.
                    hdr_obiectivul, hdr_obiectul, hdr_categoria = "", obj_text, cat_text
                    if hdrs_list:
                        if len(hdrs_list) == 1:
                            hdr_obiectivul = hdrs_list[0].get("obiectivul", "")
                            hdr_obiectul = hdrs_list[0].get("obiectul", "") or obj_text
                            hdr_categoria = hdrs_list[0].get("categoria", "") or cat_text
                        else:
                            # For compound groups, pick the header entry whose
                            # obiectul best matches the compound key's obj_text
                            best_hdr = hdrs_list[0]
                            best_score = 0.0
                            for hdr in hdrs_list:
                                hdr_obj = hdr.get("obiectul", "") or ""
                                if obj_text and hdr_obj:
                                    from difflib import SequenceMatcher
                                    sc = SequenceMatcher(None, obj_text.lower(), hdr_obj.lower()).ratio()
                                    if sc > best_score:
                                        best_score, best_hdr = sc, hdr
                            hdr_obiectivul = best_hdr.get("obiectivul", "")
                            hdr_obiectul = best_hdr.get("obiectul", "") or obj_text
                            hdr_categoria = best_hdr.get("categoria", "") or cat_text

                    corrected, hierarchy_stats = self.hierarchy_corrector.correct(articles)
                    # Make deviz_cod unique when multiple keys share same cod
                    group_cod = deviz_cod if n_keys == 1 else f"{deviz_cod}__{i}"
                    grupos.append({
                        "deviz_cod": group_cod,
                        "deviz_den": deviz_den_map.get(deviz_cod, ""),
                        "obiectivul": hdr_obiectivul,
                        "obiectul": hdr_obiectul,
                        "categoria": hdr_categoria,
                        "source_pages": pages_by_deviz[gkey],
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
