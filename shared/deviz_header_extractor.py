from __future__ import annotations

import hashlib
import json
import logging
import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

KNOWLEDGE_PATH = Path(__file__).parent / "deviz_header_knowledge.json"

_OBJ1_RE = re.compile(
    r'(?:obiectiv(?:ul)?|investment\s+object)\s*[:\-]\s*["\']?(.*)',
    re.IGNORECASE
)
_OBJ2_RE = re.compile(
    r'(?:obiectul|obiect(?:ul)?\s+de\s+investi[tți]ii?)\s*[:\-]\s*(.*)',
    re.IGNORECASE
)
_CAT_RE = re.compile(
    r'(?:categoria\s+de\s+lucr[aă]ri?|stadiul?\s+fizic|category)\s*[:\-]\s*(.*)',
    re.IGNORECASE
)
# "Deviz oferta ZO0001 Terasamente..." (DT), "Deviz oferta 226108 STRUCTURA..." (SSR numeric),
# "Deviz oferta 226U28 ALIMENTARE..." (SSR hybrid, letter in middle)
# Used as categoria when "Categoria de lucrari: 0120/0169" would otherwise collapse all devizes per obiect
_DEVIZ_OFERTA_LETTERED_RE = re.compile(
    r'Deviz\s+oferta\s+([A-Z0-9]{3,8})\s+(.+?)(?:\s+Categoria|\s+Lista\s+cu|\s+Nr\.|$)',
    re.IGNORECASE
)
# "Deviz oferta INSTALATII SANITARE INTERIOARE" (Gura Foii ref) — denumire pura, FARA cod.
# Fallback cand pattern-ul lettered nu se aplica (primul cuvant >8 caractere, ex. INFRASTRUCTURA).
# Fara el, categoria cade pe "Categoria de lucrari:" gol → junk din headerul tabelului
# ("= NR. SIMBOL ART. CANTITATE") → toate devizele unui obiect colapseaza intr-un singur grup.
_DEVIZ_OFERTA_PLAIN_RE = re.compile(
    r'Deviz\s+oferta\s+(.+?)(?:\s+Categoria|\s+Lista\s+cu|\s+Nr\.|$)',
    re.IGNORECASE
)
# Structural lines that should not be merged into obiectivul/obiectul values
_STRUCT_LINES = frozenset([
    'formularul f3', 'lista cu cantitatile de lucrari', 'lista de cantitati',
    'deviz oferta', 'categoria de lucrari', 'stadiul fizic',
    'beneficiar', 'executant', 'proiectant',
])


@dataclass
class DevizHeader:
    obiectivul: str | None
    obiectul: str | None
    categoria: str | None
    deviz_key: str
    is_valid: bool
    source: str          # "regex" | "llm" | "cache"
    deviz_cod: str = ""


def _normalize(text: str) -> str:
    """Normalize text for consistent deviz_key hashing.

    Operations (in order):
    1. Strip leading/trailing whitespace
    2. Lowercase
    3. Remove diacritics (NFD normalization)
    4. Collapse multiple spaces to single space
    5. Remove extra punctuation that varies across PDFs
    """
    import re as _re
    text = text.strip().lower()
    # Remove diacritics
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    # Collapse multiple spaces
    text = _re.sub(r'\s+', ' ', text)
    # Normalize spaces after commas ("A, B,C" → "A,B,C") — OCR/PDF variation
    text = _re.sub(r',\s+', ',', text)
    return text


def _strip_page_prefix(text: str) -> str:
    """Strip zero-padded page prefix from Obiect/Categoria (e.g. '001 ', '002 ', '01 ').

    Only strips prefixes that start with 0 (PDF page numbering), not content.
    Examples:
    - '001 LUCRARI' → 'LUCRARI'
    - '002 2 LUCRARI' → '2 LUCRARI' (only first "002 " stripped, not the "2")
    - '1 LUCRARI' → '1 LUCRARI' (no zero prefix, unchanged)
    """
    if not text:
        return text
    import re as _re
    text = text.strip()
    # Strip leading zero-padded prefix (0 followed by 1-2 digits, followed by space(s))
    # Matches: "001 ", "002 ", "01 ", "099 " but NOT "1 " or "123 "
    text = _re.sub(r'^0\d{1,2}\s+', '', text)
    return text


def _make_deviz_key(
    obiectivul: str | None,
    obiectul: str | None,
    categoria: str | None,
) -> tuple[str, bool]:
    is_valid = all(x is not None for x in [obiectivul, obiectul, categoria])

    # Strip "00X " prefix from Obiect/Categoria (from oferta pages)
    clean_obiectul = _strip_page_prefix(obiectul) if obiectul else None
    clean_categoria = _strip_page_prefix(categoria) if categoria else None

    parts = [_normalize(x) if x is not None else "\x00" for x in [obiectivul, clean_obiectul, clean_categoria]]
    raw = " | ".join(parts)
    key = hashlib.md5(raw.encode()).hexdigest()[:16]
    if not is_valid:
        key = f"__INCOMPLETE__:{key}"
    return key, is_valid


def _extract_from_lines(
    header_lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Extrage OBIECTIVUL, Obiectul, Categoria din primele 30 linii.

    Suporta trei formate:
    - Inline:      'Obiectivul: EFICIENTIZARE ENERGETICA...'
    - Multi-line:  'Obiectivul:\\n' + 'EFICIENTIZARE ENERGETICA...'
    - DT multi-line: 'Obiectivul:\\n' + '0232 000000232\\n' + 'DRUMURI TATARANI'
                   Categoria vine din 'Deviz oferta ZO0001 Terasamente 7.70 smp'
    """
    obiectivul = obiectul = categoria = None
    lines = header_lines[:30]

    def _is_label(s: str) -> bool:
        return bool(
            _OBJ1_RE.match(s) or _OBJ2_RE.match(s) or _CAT_RE.match(s)
            or any(s.lower().startswith(p) for p in _STRUCT_LINES)
        )

    def _next_lines_value(idx: int) -> str:
        """Take 1-2 continuation lines as value (for multi-line DT headers)."""
        parts = []
        for j in range(idx + 1, min(idx + 3, len(lines))):
            nxt = lines[j].strip()
            if not nxt or _is_label(nxt):
                break
            parts.append(nxt)
        return ' '.join(parts)

    # Priority: scan for DT-format "Deviz oferta [LETTERS+DIGITS] [text]" first
    # This overrides "Categoria de lucrari: 0169" which would collapse all devizes
    full_joined = ' '.join(lines)
    m_dt = _DEVIZ_OFERTA_LETTERED_RE.search(full_joined)
    if m_dt:
        # DT format: use "CODE denomination" as categoria
        categoria = f"{m_dt.group(1).upper()} {m_dt.group(2).strip()}"
    else:
        # Gura Foii ref format: "Deviz oferta DENUMIRE" fara cod — denumirea e categoria
        m_plain = _DEVIZ_OFERTA_PLAIN_RE.search(full_joined)
        if m_plain:
            categoria = m_plain.group(1).strip()

    for i, line in enumerate(lines):
        s = line.strip()

        if obiectivul is None:
            m = _OBJ1_RE.match(s)
            if m:
                val = m.group(1).strip().strip("\"'")
                obiectivul = val if val else _next_lines_value(i)

        if obiectul is None:
            m = _OBJ2_RE.match(s)
            if m:
                val = m.group(1).strip()
                obiectul = val if val else _next_lines_value(i)

        # Only extract categoria from _CAT_RE if DT format didn't already set it
        if categoria is None:
            m = _CAT_RE.match(s)
            if m:
                val = m.group(1).strip()
                categoria = val if val else _next_lines_value(i)

        if all(x is not None for x in [obiectivul, obiectul, categoria]):
            break

    # Curata valorile goale -> None; strip "Beneficiar:..." artifact suffix
    _beneficiar_re = re.compile(r'\s*beneficiar\s*:.*$', re.IGNORECASE)
    # Strip OCR double-number prefix: "2 2 Platforma" → "2 Platforma"
    _double_num_re = re.compile(r'^(\d+)\s+\1\b')
    if obiectivul:
        obiectivul = _beneficiar_re.sub('', obiectivul).strip() or None
    if obiectul:
        obiectul = _beneficiar_re.sub('', obiectul).strip() or None
    if categoria:
        categoria = _beneficiar_re.sub('', categoria).strip() or None
        if categoria:
            categoria = _double_num_re.sub(r'\1', categoria).strip() or None
    return obiectivul, obiectul, categoria


class DevizHeaderCache:
    def __init__(self, path: Path = KNOWLEDGE_PATH):
        self.path = path
        self._data: dict = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def get(self, cache_key: str) -> tuple[str | None, str | None, str | None] | None:
        entry = self._data.get(cache_key)
        if entry:
            return entry.get("obiectivul"), entry.get("obiectul"), entry.get("categoria")
        return None

    def put(self, cache_key: str, obiectivul: str | None, obiectul: str | None, categoria: str | None) -> None:
        self._data[cache_key] = {
            "obiectivul": obiectivul,
            "obiectul": obiectul,
            "categoria": categoria,
        }
        try:
            self.path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
        except Exception:
            pass


def _extract_via_llm(header_lines: list[str], client, model: str) -> dict | None:
    prompt = (
        "Din urmatorul header de tabel F3 (deviz constructii romanesc), extrage:\n"
        "- obiectivul: proiectul general (cel mai larg)\n"
        "- obiectul: sub-obiectul sau cladirea specifica\n"
        "- categoria: categoria de lucrari sau stadiu fizic\n\n"
        "Header:\n"
        + "\n".join(header_lines[:20])
        + "\n\nRaspunde STRICT JSON, fara text suplimentar:\n"
        '{"obiectivul": "...", "obiectul": "...", "categoria": "..."}\n'
        "Daca un camp nu poate fi determinat, pune null."
    )
    try:
        resp = client.messages.create(
            model=model,
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()
        if text.startswith("```"):
            # Strip markdown code blocks: ```json\n{...}\n``` or ```\n{...}\n```
            text = re.sub(r'^```(?:json)?\s*', '', text)
            text = re.sub(r'\s*```\s*$', '', text)
        return json.loads(text.strip())
    except Exception as e:
        logger.debug(f"[DHX] LLM extraction failed: {e}")
        return None


def extract_deviz_headers(
    page_classifications: list[dict],
    llm_client=None,
    model: str = "",
) -> dict[str, "DevizHeader"]:
    """Extract deviz headers, return dict keyed by deviz_key (hash).

    Mirrors extract_articles_v3() page logic: each distinct building
    (unique OBIECTIVUL + Obiectul + Categoria) gets its own entry,
    even when multiple buildings share the same deviz_cod (e.g. BLC5
    covers BLOC A, A2, A3, A4, B, C — each gets its own deviz_key).
    """
    cache = DevizHeaderCache()

    # Per-page header extraction, same inheritance logic as extract_articles_v3()
    group_data: dict = {}  # deviz_key → {obj1, obj2, cat, deviz_cod, header_lines}
    _last_obj1 = _last_obj2 = _last_cat = None
    _last_deviz_key: str = ""

    for pc in page_classifications:
        if not pc.get("is_f3") or pc.get("header_only"):
            continue
        cod = (pc.get("deviz_cod") or "").strip()
        if not cod:
            continue

        lines = pc.get("lines", [])[:30]
        obj1, obj2, cat = _extract_from_lines(lines)

        if obj2 or cat:
            # Page has its own header — inherit OBIECTIVUL if missing
            if obj1 is None and _last_obj1 is not None:
                obj1 = _last_obj1
            # Inherit obj2 for continuation pages with inline cat but no Obiectul: line
            # e.g. "STADIUL FIZIC: BLC1 ARHITECTURA" without "OBIECTUL:" → obj2=None, cat truthy
            if obj2 is None and _last_obj2 is not None:
                obj2 = _last_obj2
            _last_obj1, _last_obj2, _last_cat = obj1, obj2, cat
            dkey, _ = _make_deviz_key(obj1, obj2, cat)
            _last_deviz_key = dkey
            if dkey not in group_data:
                group_data[dkey] = {
                    'obj1': obj1, 'obj2': obj2, 'cat': cat,
                    'deviz_cod': cod, 'header_lines': lines,
                }
        # Continuation pages (no new header) don't create new groups

    result: dict[str, DevizHeader] = {}

    for dkey, gd in group_data.items():
        obj1, obj2, cat = gd['obj1'], gd['obj2'], gd['cat']
        deviz_cod = gd['deviz_cod']
        header_lines = gd['header_lines']

        cache_key = hashlib.md5(
            "\n".join(header_lines[:20]).encode()
        ).hexdigest()[:16]

        cached = cache.get(cache_key)
        if cached:
            obj1, obj2, cat = cached
            # Apply cleanup to stale cache values (Beneficiar: strip, double-prefix strip)
            _ben_re = re.compile(r'\s*beneficiar\s*:.*$', re.IGNORECASE)
            _dbl_re = re.compile(r'^(\d+)\s+\1\b')
            if obj1:
                obj1 = _ben_re.sub('', obj1).strip() or None
            if obj2:
                obj2 = _ben_re.sub('', obj2).strip() or None
            if cat:
                cat = _ben_re.sub('', cat).strip() or None
                if cat:
                    cat = _dbl_re.sub(r'\1', cat).strip() or None
            key, valid = _make_deviz_key(obj1, obj2, cat)
            result[key] = DevizHeader(obj1, obj2, cat, key, valid, "cache", deviz_cod)
            continue

        source = "regex"
        if any(x is None for x in [obj1, obj2, cat]) and llm_client:
            llm_result = _extract_via_llm(header_lines, llm_client, model)
            if llm_result:
                obj1 = obj1 or llm_result.get("obiectivul")
                obj2 = obj2 or llm_result.get("obiectul")
                cat = cat or llm_result.get("categoria")
                source = "llm"

        cache.put(cache_key, obj1, obj2, cat)
        key, valid = _make_deviz_key(obj1, obj2, cat)

        if not valid:
            logger.warning(
                f"[DHX] Deviz {deviz_cod}: header incomplet "
                f"(obj1={'OK' if obj1 else 'NULL'}, "
                f"obj2={'OK' if obj2 else 'NULL'}, "
                f"cat={'OK' if cat else 'NULL'})"
            )

        result[key] = DevizHeader(obj1, obj2, cat, key, valid, source, deviz_cod)

    return result
