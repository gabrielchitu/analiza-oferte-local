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
    text = text.lower().strip()
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text


def _strip_page_prefix(text: str) -> str:
    """Strip numeric page prefix (e.g. '001 ', '002 ') from Obiect."""
    if not text:
        return text
    import re
    return re.sub(r'^00\d\s+', '', text.strip())


def _make_deviz_key(
    obiectivul: str | None,
    obiectul: str | None,
    categoria: str | None,
) -> tuple[str, bool]:
    is_valid = all(x is not None for x in [obiectivul, obiectul, categoria])

    # Strip "00X " prefix from Obiect (from oferta pages)
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

    Suporta doua formate:
    - Inline:     'Obiectivul: EFICIENTIZARE ENERGETICA...'
    - Multi-line: 'Obiectivul:\\n' + 'EFICIENTIZARE ENERGETICA...' (eticheta + valoare pe linii separate)
    """
    obiectivul = obiectul = categoria = None
    lines = header_lines[:30]

    for i, line in enumerate(lines):
        s = line.strip()

        def _next_line_value(idx: int) -> str:
            """Valoarea de pe linia urmatoare, daca linia curenta e doar eticheta."""
            if idx + 1 < len(lines):
                nxt = lines[idx + 1].strip()
                # Nu lua urmatoarea linie daca e ea insasi o eticheta
                if nxt and not _OBJ1_RE.match(nxt) and not _OBJ2_RE.match(nxt) and not _CAT_RE.match(nxt):
                    return nxt
            return ""

        if obiectivul is None:
            m = _OBJ1_RE.match(s)
            if m:
                val = m.group(1).strip().strip("\"'")
                obiectivul = val if val else _next_line_value(i)

        if obiectul is None:
            m = _OBJ2_RE.match(s)
            if m:
                val = m.group(1).strip()
                obiectul = val if val else _next_line_value(i)

        if categoria is None:
            m = _CAT_RE.match(s)
            if m:
                val = m.group(1).strip()
                categoria = val if val else _next_line_value(i)

        if all(x is not None for x in [obiectivul, obiectul, categoria]):
            break

    # Curata valorile goale -> None
    obiectivul = obiectivul or None
    obiectul = obiectul or None
    categoria = categoria or None
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
    cache = DevizHeaderCache()
    pages_by_deviz: dict[str, list[dict]] = defaultdict(list)

    for pc in page_classifications:
        if pc.get("is_f3") and not pc.get("header_only"):
            cod = (pc.get("deviz_cod") or "").strip()
            if cod:
                pages_by_deviz[cod].append(pc)

    result: dict[str, DevizHeader] = {}

    for deviz_cod, pages in pages_by_deviz.items():
        header_lines: list[str] = []
        for pc in pages[:2]:
            header_lines.extend(pc.get("lines", [])[:30])
            if len(header_lines) >= 30:
                break

        cache_key = hashlib.md5(
            "\n".join(header_lines[:20]).encode()
        ).hexdigest()[:16]

        cached = cache.get(cache_key)
        if cached:
            obj1, obj2, cat = cached
            key, valid = _make_deviz_key(obj1, obj2, cat)
            result[deviz_cod] = DevizHeader(obj1, obj2, cat, key, valid, "cache", deviz_cod)
            continue

        obj1, obj2, cat = _extract_from_lines(header_lines)
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

        result[deviz_cod] = DevizHeader(obj1, obj2, cat, key, valid, source, deviz_cod)

    return result
