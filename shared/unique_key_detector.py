"""Unique key detection for set-based matching.

Extracts unique keys per article for deduplication and matching.
Priority: NR (article number) → COD (catalog code) → hash(descriere+um+cant)
"""

import hashlib
from typing import Dict, List
import pandas as pd


def detect_article_key(article: Dict) -> str:
    """
    Detect unique key for a single article.

    Priority:
    1. NR (article number) - if present and non-empty
    2. COD (catalog code) - if present and non-empty
    3. Hash of (descriere+um+cant) - fallback for articles without codes

    Args:
        article: Article dict with fields nr, cod, descriere, um, cant

    Returns:
        Unique key as string (NR/COD or 8-char hex hash)
    """
    # Try NR first
    if pd.notna(article.get("nr")):
        nr = article["nr"]
        if isinstance(nr, (int, float)):
            nr = str(int(nr)) if isinstance(nr, float) and nr.is_integer() else str(nr)
        nr_str = str(nr).strip()
        if nr_str:
            return nr_str

    # Try COD second
    if pd.notna(article.get("cod")):
        cod = article["cod"]
        if isinstance(cod, (int, float)):
            cod = str(int(cod)) if isinstance(cod, float) and cod.is_integer() else str(cod)
        cod_str = str(cod).strip()
        if cod_str:
            return cod_str

    # Fallback: hash of descriere + um + cant
    descriere = str(article.get("descriere", "")).lower().strip()
    um = str(article.get("um", "")).lower().strip()
    cant = str(article.get("cant", "")).strip()
    combined = f"{descriere}|{um}|{cant}"
    return hashlib.md5(combined.encode()).hexdigest()[:8]


def detect_article_keys(articles: List[Dict]) -> List[str]:
    """
    Extract unique keys for list of articles.

    Args:
        articles: List of article dicts

    Returns:
        List of keys in same order as articles
    """
    return [detect_article_key(art) for art in articles]


def get_unique_articles(articles: List[Dict]) -> Dict[str, Dict]:
    """
    Build dict: key -> article, preserving all occurrences via occurrence-indexed keys.

    Same catalog code can legitimately appear multiple times in a deviz (e.g. IZF16A01
    used in two sub-sections: fence foundation + concrete platform). Each occurrence gets
    a distinct key: first → base_key, second → base_key__1, third → base_key__2, etc.
    Matching between ref and offer is then done occurrence-by-occurrence in document order.

    Args:
        articles: List of article dicts

    Returns:
        Dict mapping occurrence-disambiguated keys to article dicts
    """
    unique: dict = {}
    occurrence_count: dict = {}
    for art in articles:
        base_key = detect_article_key(art)
        count = occurrence_count.get(base_key, 0)
        key = base_key if count == 0 else f"{base_key}__{count}"
        occurrence_count[base_key] = count + 1
        unique[key] = art
    return unique
