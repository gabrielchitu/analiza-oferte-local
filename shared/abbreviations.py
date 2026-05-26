"""
Dicționar abrevieri F3 + sistem de auto-învățare.

Flux:
  1. ABREVIERI_F3 (statice, curate) — expandate în _clean_den() din comparator.py
  2. Perechi borderline (Jaccard 0.30-0.50) marcate în DESCRIERE_DIFERITA
  3. LLM validare batch → perechi confirmate echivalente salvate în learned_pairs.json
  4. learned_pairs.json încărcat la startup → expandate tot în _clean_den()
"""

from __future__ import annotations

import json
import re
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Dicționar static abrevieri comune în documentele F3 românești
# Chei: forma prescurtată (lowercase), Valori: forma completă (lowercase)
ABREVIERI_F3: dict[str, str] = {
    # Prepoziții / particule
    "pt": "pentru",
    "pt.": "pentru",
    "c/": "cu",

    # Suprafețe / dimensiuni
    "supr": "suprafata",
    "supr.": "suprafata",
    "gr": "grosime",
    "gr.": "grosime",
    "gros": "grosime",
    "gros.": "grosime",
    "dim": "dimensiune",
    "dim.": "dimensiune",
    "diam": "diametru",
    "diam.": "diametru",

    # Materiale / tehnic
    "termoizol": "termoizolatii",
    "termoizol.": "termoizolatii",
    "termoizolat": "termoizolate",
    "termoizolat.": "termoizolate",
    "b.a": "beton armat",
    "b.a.": "beton armat",
    "ba": "beton armat",
    "b.c.a": "beton celular autoclavizat",
    "b.c.a.": "beton celular autoclavizat",

    # Verbe / substantive prescurtate
    "inc": "inclusiv",
    "inc.": "inclusiv",
    "incl": "inclusiv",
    "incl.": "inclusiv",
    "exec": "executare",
    "exec.": "executare",
    "mont": "montare",
    "mont.": "montare",
    "conf": "conform",
    "conf.": "conform",

    # Materiale construcții
    "bca": "beton celular autoclavizat",
    "pvc": "policlorura de vinil",
    "pp": "polipropilena",
    "pe": "polietilena",
}

# Calea fișierului cu perechi învățate de la LLM
_LEARNED_PATH = Path(__file__).parent.parent / "output_AO" / "learned_abbreviations.json"


def load_learned_pairs() -> dict[str, str]:
    """Încarcă perechile echivalente învățate de la LLM (ref_den → oferta_den normalizată)."""
    if not _LEARNED_PATH.exists():
        return {}
    try:
        data = json.loads(_LEARNED_PATH.read_text(encoding="utf-8"))
        return data.get("equivalences", {})
    except Exception as e:
        logger.warning(f"[ABBR] Nu pot citi learned_abbreviations.json: {e}")
        return {}


def save_learned_pairs(equivalences: dict[str, str]) -> None:
    """Salvează perechile echivalente în JSON persistent."""
    _LEARNED_PATH.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if _LEARNED_PATH.exists():
        try:
            existing = json.loads(_LEARNED_PATH.read_text(encoding="utf-8")).get("equivalences", {})
        except Exception:
            pass
    existing.update(equivalences)
    _LEARNED_PATH.write_text(
        json.dumps({"equivalences": existing}, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    logger.info(f"[ABBR] Salvat {len(equivalences)} echivalențe noi → total {len(existing)}")


# Cache în memorie pentru perechi învățate (evită I/O la fiecare comparație)
_learned_cache: dict[str, str] | None = None


def get_learned_pairs() -> dict[str, str]:
    global _learned_cache
    if _learned_cache is None:
        _learned_cache = load_learned_pairs()
    return _learned_cache


def reload_learned_cache() -> None:
    """Forțează reîncărcarea cache-ului după o actualizare LLM."""
    global _learned_cache
    _learned_cache = None


def expand_abbreviations(text: str) -> str:
    """
    Expandează abrevierile din text:
    1. Aplică ABREVIERI_F3 (statice)
    2. Normalizează perechile echivalente învățate de la LLM

    Returnează textul cu abrevierile expandate.
    """
    if not text:
        return text

    result = text.lower().strip()

    # 1. Abrevieri statice — word-boundary replace
    for abbr, expanded in ABREVIERI_F3.items():
        pattern = r'\b' + re.escape(abbr.lower()) + r'\b'
        result = re.sub(pattern, expanded, result, flags=re.IGNORECASE)

    # 2. Collapse spații multiple apărute după înlocuiri
    result = re.sub(r'\s+', ' ', result).strip()

    return result


def are_learned_equivalent(den_a: str, den_b: str) -> bool:
    """
    Verifică dacă perechea (den_a, den_b) a fost marcată ca echivalentă de LLM.
    Verifică ambele direcții.
    """
    pairs = get_learned_pairs()
    key_ab = f"{den_a.lower().strip()}|||{den_b.lower().strip()}"
    key_ba = f"{den_b.lower().strip()}|||{den_a.lower().strip()}"
    return key_ab in pairs or key_ba in pairs
