"""
Deviz section name normalizer.

Maps offer deviz_denumire values to reference deviz_denumire values,
so that _deviz_key() in core.py produces the same key for both documents.

Strategy (no LLM needed for common patterns):
  1. Exact key match via _deviz_key_local() — handles "001 226108 NAME" format
  2. Strip known prefixes, then exact key match — handles "oferta 226008 NAME",
     "STADIUL FIZIC: oferta 226108 NAME", "001 226U08 NAME" (alphanumeric codes)
  3. Word-overlap similarity (threshold > 0.6) — catches remaining variants
  4. LLM fallback only for what still can't be matched

Public API:
    normalize_devize(ref_articole, oferta_articole, openai_client, deployment) -> list
"""
import json
import logging
import re

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are matching construction project section names between two documents.
Given a list of reference section names and a list of offer section names,
map each offer section name to the best matching reference section name.
If no good match exists, use "NONE".
You MUST include every offer section name as a key in your JSON response.
Return ONLY valid JSON: {"offer_section_name": "ref_section_name_or_NONE", ...}"""

# Pattern to strip standard prefixes from oferta deviz_denumire.
# Handles:
#   "oferta 226008 NAME"                     → NAME
#   "STADIUL FIZIC: oferta 226108 NAME"      → NAME
#   "001 226108 NAME"  (already handled by _deviz_key_local, but strip anyway)
#   "001 226U08 NAME"  (alphanumeric code, _deviz_key_local stops at U)
#   "226108 NAME"      (pure numeric, already handled)
_DEVIZ_PREFIX_RE = re.compile(
    r'^(?:STADIUL\s+FIZIC\s*:\s*)?'   # optional "STADIUL FIZIC:"
    r'(?:oferta\s+)?'                  # optional "oferta " keyword
    r'(?:\d{1,3}\s+)?'                # optional 1-3 digit chapter number + space
    r'(?:[A-Z0-9]{4,8}\s+)?',         # optional alphanumeric code (4-8 chars)
    re.IGNORECASE
)

# Minimum word-overlap score (strict >) for similarity mapping
_OVERLAP_THRESHOLD = 0.6


def _deviz_key_local(denumire: str) -> str:
    """Same normalization as _deviz_key() in core.py."""
    raw = (denumire or "").strip().upper()
    raw = re.sub(r'^(\d+\s+)+', '', raw).strip()
    raw = re.sub(r'\b(OB|NR|CAP|ART)[\s.]*(\d+)', r'\1\2', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw


def _strip_deviz_prefix(den: str) -> str:
    """Strip known prefixes from deviz_denumire to get the human-readable name."""
    m = _DEVIZ_PREFIX_RE.match(den)
    stripped = den[m.end():].strip() if m else den.strip()
    return stripped or den.strip()


def _word_overlap(a: str, b: str) -> float:
    """Returnează fracția de cuvinte comune (≥3 litere) din min(len(a_words), len(b_words))."""
    wa = set(w for w in re.sub(r'[^A-Z0-9]', ' ', a.upper()).split() if len(w) >= 3)
    wb = set(w for w in re.sub(r'[^A-Z0-9]', ' ', b.upper()).split() if len(w) >= 3)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def _local_mapping(ref_articole: list, oferta_articole: list) -> dict:
    """
    Fast, LLM-free deviz name mapping using three tiers:
      1. Exact key match (via _deviz_key_local) — e.g. "001 226108 NAME" → "NAME"
      2. Strip prefix + exact key match — e.g. "oferta 226U08 ALIMENTARE CU APA"
      3. Word-overlap similarity (> 0.6) — catches remaining variants

    Returns {oferta_deviz_denumire: ref_deviz_denumire} for names that need renaming.
    Only adds an entry if the mapping actually changes the value (avoids identity entries).
    """
    ref_denums = list({a.get("deviz_denumire", "") for a in ref_articole
                       if a.get("deviz_denumire")})
    if not ref_denums:
        return {}

    # Build lookup: normalized_key → original ref denumire
    ref_key_to_den: dict[str, str] = {}
    for d in ref_denums:
        key = _deviz_key_local(d)
        if key and key not in ref_key_to_den:
            ref_key_to_den[key] = d

    mapping: dict[str, str] = {}
    seen: set[str] = set()

    for a in oferta_articole:
        den = (a.get("deviz_denumire") or "").strip()
        if not den or den in seen:
            continue
        seen.add(den)

        # Tier 1: exact key match (handles pure-numeric prefixes already stripped by _deviz_key_local)
        key1 = _deviz_key_local(den)
        if key1 in ref_key_to_den:
            ref_den = ref_key_to_den[key1]
            if ref_den != den:
                mapping[den] = ref_den
            continue  # already aligned or explicitly mapped

        # Tier 2: strip extended prefix, then exact key match
        stripped = _strip_deviz_prefix(den)
        if stripped and stripped != den:
            key2 = _deviz_key_local(stripped)
            if key2 in ref_key_to_den:
                ref_den = ref_key_to_den[key2]
                if ref_den != den:
                    mapping[den] = ref_den
                continue

        # Tier 3: word-overlap similarity on stripped name
        target = stripped if stripped and stripped != den else den
        best_ref: str | None = None
        best_score = 0.0
        best_len = 0
        for ref_den in ref_denums:
            score = _word_overlap(target, ref_den)
            if score > _OVERLAP_THRESHOLD and (
                score > best_score or (score == best_score and len(ref_den) > best_len)
            ):
                best_ref = ref_den
                best_score = score
                best_len = len(ref_den)
        if best_ref and best_ref != den:
            mapping[den] = best_ref
            logger.debug(f"[DN] Overlap {best_score:.2f}: {den!r} → {best_ref!r}")

    if mapping:
        logger.info(f"[DN] Local mapping (no LLM): {len(mapping)} renames")
    return mapping


def _build_mapping(ref_articole: list, oferta_articole: list,
                   openai_client, deployment: str) -> dict:
    """
    Returns {offer_deviz_denumire: ref_deviz_denumire} for sections that need renaming.
    1. Local 3-tier matching (no LLM) — handles most real-world oferta formats.
    2. LLM fallback for any remaining unmapped + unaligned names.
    Returns {} if no renaming needed or if everything fails (safe fallback).
    """
    ref_denums = list({a.get("deviz_denumire", "") for a in ref_articole if a.get("deviz_denumire")})
    oferta_denums = list({a.get("deviz_denumire", "") for a in oferta_articole if a.get("deviz_denumire")})

    if not ref_denums or not oferta_denums:
        return {}

    # Early exit: all oferta keys already align with ref keys
    ref_keys = {_deviz_key_local(d) for d in ref_denums}
    oferta_keys = {_deviz_key_local(d) for d in oferta_denums}
    if ref_keys == oferta_keys:
        logger.debug("[DN] Deviz keys already aligned — skipping mapping")
        return {}

    # Step 1: local mapping (no LLM)
    mapping = _local_mapping(ref_articole, oferta_articole)
    already_mapped = set(mapping.keys())

    # Step 2: LLM for what remains unresolved
    oferta_remaining = [d for d in oferta_denums if d not in already_mapped]
    if not oferta_remaining:
        return mapping

    # Skip LLM if remaining names are already key-aligned
    remaining_keys = {_deviz_key_local(d) for d in oferta_remaining}
    if remaining_keys <= ref_keys:
        logger.debug("[DN] Remaining devize already key-aligned — skip LLM")
        return mapping

    user_content = json.dumps({
        "ref_devize": ref_denums,
        "oferta_devize": oferta_remaining
    }, ensure_ascii=False)

    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content}
            ],
            max_tokens=4000
        )
        raw = resp.choices[0].message.content
        mapping_raw = json.loads(raw)
        llm_mapping = {
            k: v for k, v in mapping_raw.items()
            if isinstance(k, str) and isinstance(v, str) and v.upper() != "NONE"
        }
        mapping.update(llm_mapping)
        logger.info(f"[DN] Total mapping: {len(mapping)} renames "
                    f"({len(mapping) - len(llm_mapping)} local + {len(llm_mapping)} LLM)")
    except Exception as e:
        logger.warning(f"[DN] LLM mapping failed — folosim doar mapping local: {e}")

    return mapping


def normalize_devize(ref_articole: list, oferta_articole: list,
                     openai_client, deployment: str) -> list:
    """
    Returns a shallow-copied list of offer articles with deviz_denumire rewritten
    to match reference section names where a mapping exists.
    Original oferta_articole list and dicts are never mutated.
    """
    if not ref_articole or not oferta_articole:
        return oferta_articole

    mapping = _build_mapping(ref_articole, oferta_articole, openai_client, deployment)
    if not mapping:
        return oferta_articole

    result = []
    for art in oferta_articole:
        den = art.get("deviz_denumire", "")
        if den in mapping:
            art = {**art, "deviz_denumire": mapping[den]}
        result.append(art)
    return result
