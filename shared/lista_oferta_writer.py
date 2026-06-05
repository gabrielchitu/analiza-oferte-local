"""F3-format DOCX list generator for referinta and offer articles."""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Generator


def extract_entity_name(di_json_path: str, is_referinta: bool) -> str:
    """Extract proiectant/ofertant name from raw DI JSON (first 5 pages)."""
    marker = "PROIECTANT" if is_referinta else "CONTRACTANT (OFERTANT)"
    try:
        with open(di_json_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return "Necunoscut"

    pages = data.get("pages", [])
    for page in pages[:5]:
        lines = [ln.get("content", "").strip() for ln in page.get("lines", [])]
        for i, line in enumerate(lines):
            if marker in line:
                for candidate in lines[i + 1 :]:
                    if candidate and candidate.upper() != "SRL":
                        return candidate
    return "Necunoscut"


def _get_header_from_articles(articles: List[Dict]) -> Dict:
    """Extract group header from first article's deviz_header dict."""
    for art in articles:
        dh = art.get("deviz_header")
        if isinstance(dh, dict):
            return dh
    return {"obiectivul": "", "obiectul": "", "categoria": ""}


def _iter_source_groups(holistic: Dict, source: str) -> Generator[Tuple[Dict, List[Dict]], None, None]:
    """Yield (header_dict, articles_list) for each non-empty group.

    Args:
        holistic: holistic JSON structure with matched_groups, ref_only_groups, oferta_only_groups
        source: "oferta" or "referinta"

    Yields:
        (header: Dict, articles: List[Dict]) tuples
    """
    art_key = "oferta_articles" if source == "oferta" else "ref_articles"
    only_key = "oferta_only_groups" if source == "oferta" else "ref_only_groups"

    for group in holistic.get("matched_groups", []):
        articles = group.get(art_key, [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles

    for group in holistic.get(only_key, []):
        articles = group.get("articles", [])
        if not articles:
            continue
        header = _get_header_from_articles(articles)
        yield header, articles
