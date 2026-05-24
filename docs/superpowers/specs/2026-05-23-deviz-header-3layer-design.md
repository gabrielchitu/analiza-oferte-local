# Deviz Header 3-Layer Extraction — Implementation Spec (Sub-project B)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace flat deviz_cod matching with 3-layer classification (OBIECTIVUL + Obiectul + Categoria) extracted from F3 table headers. Generate stable `deviz_key` from all 3 layers. Match ref↔oferta on deviz_key. Report missing/extra deviz groups.

**Architecture:** New `shared/deviz_header_extractor.py` owns extraction + key generation + caching. Runs after `_apply_end_detection`, before `extract_articles_v3`. Articles get `deviz_key` field. Matching uses `deviz_key` as primary group key.

**Branch:** `refactor/v10`

---

## Context — Starea Actuala

- `deviz_cod` in articole = extras din header pagina F3 (regex/LLM in `f3_page_classifier.py`)
- Format variabil: "226108" (eDevize numeric), "1-02" (ISDP compound), "BLC2" (prefix)
- `deviz_matcher.py` mapeaza ref↔oferta devize pe cod + denumire (Strategy 0-3)
- **Problema:** Nu exista notiunea de OBIECTIVUL ca layer distinct — gruparea e incompleta
- Un fisier poate contine mai multe obiective; fara Layer 1 (OBIECTIVUL) nu putem distinge

---

## Fisiere Implicate

| Fisier | Actiune |
|--------|---------|
| `shared/deviz_header_extractor.py` | CREATE — extractie 3-layer, key generation, cache |
| `shared/deviz_header_knowledge.json` | CREATE — cache autoinvatare (header → 3 layere) |
| `local_run.py` | MODIFY — apeleaza extractor in `extract_document()` |
| `shared/f3_extractor.py` | MODIFY — articole primesc `deviz_key` field |
| `AgentComparator_local.py` | MODIFY — matching pe `(deviz_key, article_cod)` |
| `shared/report_word.py` | MODIFY — header deviz arata Obiectul + Categoria |
| `tests/test_deviz_header_extractor.py` | CREATE — unit tests |

---

## Design Detaliat

### 1. `DevizHeader` dataclass

```python
# shared/deviz_header_extractor.py
from dataclasses import dataclass
import hashlib
import json
import re
import unicodedata
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).parent / "deviz_header_knowledge.json"

@dataclass
class DevizHeader:
    obiectivul: str | None
    obiectul: str | None
    categoria: str | None
    deviz_key: str             # md5[:16] din normalized(obj1 | obj2 | cat)
    is_valid: bool             # True numai daca toate 3 sunt non-None
    source: str                # "regex" | "llm" | "cache"
    deviz_cod: str = ""        # codul original din page_classification (pastrat)
```

### 2. Regex patterns (Layer 1/2/3)

```python
_OBJ1_RE = re.compile(
    r'(?:obiectiv(?:ul)?|investment\s+object)\s*[:\-]?\s*["\']?(.+)',
    re.IGNORECASE
)
_OBJ2_RE = re.compile(
    r'(?:obiectul|obiect(?:ul)?\s+de\s+investi[tț]ii?)\s*[:\-]\s*(.+)',
    re.IGNORECASE
)
_CAT_RE = re.compile(
    r'(?:categoria\s+de\s+lucr[aă]ri?|stadiul?\s+fizic[:\-]?|category)\s*[:\-]?\s*(.+)',
    re.IGNORECASE
)
```

### 3. `_normalize(text)` — pentru key generation

```python
def _normalize(text: str) -> str:
    """Lowercase, strip diacritice, strip whitespace/punctuatie leading/trailing."""
    text = text.lower().strip()
    # Strip diacritice
    text = "".join(
        c for c in unicodedata.normalize("NFD", text)
        if unicodedata.category(c) != "Mn"
    )
    return text
```

### 4. `_make_deviz_key(obiectivul, obiectul, categoria)`

```python
def _make_deviz_key(obiectivul: str | None, obiectul: str | None, categoria: str | None) -> tuple[str, bool]:
    is_valid = all(x is not None for x in [obiectivul, obiectul, categoria])
    parts = [_normalize(x or "") for x in [obiectivul, obiectul, categoria]]
    raw = " | ".join(parts)
    key = hashlib.md5(raw.encode()).hexdigest()[:16]
    if not is_valid:
        key = f"__INCOMPLETE__:{key}"
    return key, is_valid
```

### 5. `_extract_from_lines(header_lines)` — regex pass

```python
def _extract_from_lines(header_lines: list[str]) -> tuple[str | None, str | None, str | None]:
    """Extrage OBIECTIVUL, Obiectul, Categoria din primele 30 linii ale header-ului F3."""
    obiectivul = obiectul = categoria = None
    for line in header_lines[:30]:
        s = line.strip()
        if obiectivul is None:
            m = _OBJ1_RE.match(s)
            if m:
                obiectivul = m.group(1).strip().strip('"\'')
        if obiectul is None:
            m = _OBJ2_RE.match(s)
            if m:
                obiectul = m.group(1).strip()
        if categoria is None:
            m = _CAT_RE.match(s)
            if m:
                categoria = m.group(1).strip()
        if all(x is not None for x in [obiectivul, obiectul, categoria]):
            break
    return obiectivul, obiectul, categoria
```

### 6. `DevizHeaderCache` — cache autoinvatare

```python
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
        """Returneaza (obiectivul, obiectul, categoria) sau None daca nu e in cache."""
        entry = self._data.get(cache_key)
        if entry:
            return entry.get("obiectivul"), entry.get("obiectul"), entry.get("categoria")
        return None

    def put(self, cache_key: str, obiectivul: str | None, obiectul: str | None, categoria: str | None):
        self._data[cache_key] = {
            "obiectivul": obiectivul,
            "obiectul": obiectul,
            "categoria": categoria,
        }
        try:
            self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass  # cache write failure non-critical
```

### 7. `extract_deviz_headers(page_classifications, llm_client, model)` — functia principala

```python
def extract_deviz_headers(
    page_classifications: list[dict],
    llm_client=None,
    model: str = "",
) -> dict[str, DevizHeader]:
    """
    Extrage 3-layer header din fiecare deviz F3 distinct.
    Returns: {deviz_cod → DevizHeader}
    """
    cache = DevizHeaderCache()

    # Grupeaza pagini F3 pe deviz_cod
    from collections import defaultdict
    pages_by_deviz: dict[str, list[dict]] = defaultdict(list)
    for pc in page_classifications:
        if pc.get("is_f3") and not pc.get("header_only"):
            cod = pc.get("deviz_cod", "")
            if cod:
                pages_by_deviz[cod].append(pc)

    result: dict[str, DevizHeader] = {}

    for deviz_cod, pages in pages_by_deviz.items():
        # Colecteaza primele 30 linii din prima pagina F3 a devizului
        header_lines = []
        for pc in pages[:2]:  # primele 2 pagini sunt suficiente
            header_lines.extend(pc.get("lines", [])[:30])
            if len(header_lines) >= 30:
                break

        # Cache key = md5(primele 10 linii normalize)
        cache_key = hashlib.md5(
            "\n".join(header_lines[:10]).encode()
        ).hexdigest()[:16]

        # 1. Incearca cache
        cached = cache.get(cache_key)
        if cached:
            obj1, obj2, cat = cached
            key, valid = _make_deviz_key(obj1, obj2, cat)
            result[deviz_cod] = DevizHeader(obj1, obj2, cat, key, valid, "cache", deviz_cod)
            continue

        # 2. Regex pass
        obj1, obj2, cat = _extract_from_lines(header_lines)

        # 3. LLM fallback daca lipsesc layere si avem client
        source = "regex"
        if any(x is None for x in [obj1, obj2, cat]) and llm_client:
            llm_result = _extract_via_llm(header_lines[:20], llm_client, model)
            if llm_result:
                obj1 = obj1 or llm_result.get("obiectivul")
                obj2 = obj2 or llm_result.get("obiectul")
                cat = cat or llm_result.get("categoria")
                source = "llm"

        # 4. Salveaza in cache (chiar daca incomplete — evita re-apelare LLM)
        cache.put(cache_key, obj1, obj2, cat)

        key, valid = _make_deviz_key(obj1, obj2, cat)
        if not valid:
            import logging
            logging.getLogger(__name__).warning(
                f"[DHX] Deviz {deviz_cod}: header incomplet "
                f"(obj1={'OK' if obj1 else 'NULL'}, "
                f"obj2={'OK' if obj2 else 'NULL'}, "
                f"cat={'OK' if cat else 'NULL'})"
            )

        result[deviz_cod] = DevizHeader(obj1, obj2, cat, key, valid, source, deviz_cod)

    return result
```

### 8. `_extract_via_llm(header_lines, client, model)` — LLM fallback

```python
def _extract_via_llm(header_lines: list[str], client, model: str) -> dict | None:
    """Trimite header la LLM, returneaza {obiectivul, obiectul, categoria} sau None."""
    prompt = (
        "Din urmatorul header de tabel F3 (deviz constructii romanesc), extrage:\n"
        "- obiectivul: proiectul general (cel mai larg)\n"
        "- obiectul: sub-obiectul sau cladirea specifica\n"
        "- categoria: categoria de lucrari sau stadiu fizic\n\n"
        "Header:\n"
        + "\n".join(header_lines)
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
        # Strip markdown code block if present
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text)
    except Exception:
        return None
```

### 9. Integrare in `local_run.py::extract_document()`

Dupa `_apply_end_detection`, inainte de `extract_articles_v3`:

```python
    # Extract 3-layer deviz headers
    from shared.deviz_header_extractor import extract_deviz_headers
    deviz_headers = extract_deviz_headers(page_classes, client, model)
    logger.info(f"  {len(deviz_headers)} devize cu header extras "
                f"({sum(1 for h in deviz_headers.values() if h.is_valid)} valide)")

    articles = extract_articles_v3(page_classes)

    # Ataseaza deviz_key la fiecare articol
    for art in articles:
        dh = deviz_headers.get(art.get("deviz", ""))
        art["deviz_key"] = dh.deviz_key if dh else art.get("deviz", "")
        art["deviz_header"] = {
            "obiectivul": dh.obiectivul if dh else None,
            "obiectul": dh.obiectul if dh else None,
            "categoria": dh.categoria if dh else None,
        }
```

### 10. Matching in `AgentComparator_local.py`

Cheia de matching devine `(deviz_key, article_cod)` in loc de `(deviz_cod, article_cod)`:

```python
# Layer 1: exact match pe (deviz_key, article_cod)
key = (art.get("deviz_key", art.get("deviz", "")), art.get("cod", ""))
```

Backward compat: daca `deviz_key` lipseste (articole vechi fara header extras), fallback la `deviz` (deviz_cod).

### 11. Raport Word — header deviz

In `_add_deviz_heading()`, daca avem header info:
```
Capitol: 2.6 Instalatii Termice  [Ref: PDF pag. 12-14]
  Obiectul: Reabilitare, extindere și modernizare sediu de școală
```

### 12. Corner case: `is_valid=False`

Articolele cu `deviz_key` ce incepe cu `__INCOMPLETE__` primesc:
- Neconformitate noua: `DEVIZ_INCOMPLETE` (tip nou)
- Vizibile in raport cu culoare portocalie (distincta de LIPSA/EXTRA)

---

## Testing

```python
# tests/test_deviz_header_extractor.py

def test_regex_extracts_all_3_layers():
    lines = [
        'OBIECTIVUL: Reabilitare sediu scoala',
        'Obiectul: Reabilitare scoala',
        'Categoria de lucrari: 2.6 Instalatii Termice',
    ]
    from shared.deviz_header_extractor import _extract_from_lines
    obj1, obj2, cat = _extract_from_lines(lines)
    assert obj1 == 'Reabilitare sediu scoala'
    assert obj2 == 'Reabilitare scoala'
    assert cat == '2.6 Instalatii Termice'

def test_make_deviz_key_stable():
    from shared.deviz_header_extractor import _make_deviz_key
    k1, v1 = _make_deviz_key('A', 'B', 'C')
    k2, v2 = _make_deviz_key('A', 'B', 'C')
    assert k1 == k2
    assert v1 is True

def test_make_deviz_key_incomplete():
    from shared.deviz_header_extractor import _make_deviz_key
    k, v = _make_deviz_key('A', None, 'C')
    assert v is False
    assert k.startswith('__INCOMPLETE__')

def test_deviz_header_cache_roundtrip(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / 'cache.json')
    cache.put('key1', 'Obiectiv', 'Obiect', 'Categorie')
    result = cache.get('key1')
    assert result == ('Obiectiv', 'Obiect', 'Categorie')

def test_deviz_header_cache_miss(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / 'cache.json')
    assert cache.get('missing_key') is None

def test_extract_deviz_headers_from_page_classifications(tmp_path):
    from shared.deviz_header_extractor import extract_deviz_headers
    page_classes = [
        {
            'is_f3': True, 'deviz_cod': '1-01', 'header_only': False,
            'lines': [
                'OBIECTIVUL: Reabilitare scoala',
                'Obiectul: Corp A',
                'Categoria de lucrari: 2.1 Structuri',
                '1 EA02A1 buc 1.0',
            ],
        }
    ]
    headers = extract_deviz_headers(page_classes)
    assert '1-01' in headers
    h = headers['1-01']
    assert h.obiectivul == 'Reabilitare scoala'
    assert h.obiectul == 'Corp A'
    assert h.categoria == '2.1 Structuri'
    assert h.is_valid is True
    assert h.source == 'regex'

def test_extract_deviz_headers_incomplete(tmp_path):
    from shared.deviz_header_extractor import extract_deviz_headers
    page_classes = [
        {
            'is_f3': True, 'deviz_cod': '2-01', 'header_only': False,
            'lines': ['Obiectul: Corp B', '1 CA01A mp 5.0'],
        }
    ]
    headers = extract_deviz_headers(page_classes)
    h = headers['2-01']
    assert h.is_valid is False
    assert h.deviz_key.startswith('__INCOMPLETE__')
```

---

## Known Constraints

- `deviz_cod` pastrat in articole — backward compat cu rapoarte existente
- `deviz_key` field NOU — matching foloseste `deviz_key`, fallback la `deviz_cod`
- `DEVIZ_INCOMPLETE` tip nou de neconformitate — adaugat in `comparator.py` si raport
- LLM fallback apelat numai daca lipsesc layere SI avem `llm_client` valid
- Cache write failure = non-critical (pipeline continua fara cache)
- Nu rescrie `deviz_matcher.py` complet — Strategy 0-3 raman ca fallback daca `deviz_key` matching esueaza

---

## Definition of Done

- [ ] `DevizHeader` dataclass + `_make_deviz_key` + `_normalize`
- [ ] `DevizHeaderCache` load/save/get/put cu error handling
- [ ] `_extract_from_lines` regex (Layer 1/2/3)
- [ ] `_extract_via_llm` fallback (Claude API)
- [ ] `extract_deviz_headers(page_classes)` — orchestrator
- [ ] `deviz_header_knowledge.json` — fisier gol initial
- [ ] Integrare in `extract_document()`: extrage headers + ataseaza deviz_key la articole
- [ ] Matching pe `deviz_key` in `AgentComparator_local.py`
- [ ] `DEVIZ_INCOMPLETE` tip nou raportat
- [ ] Header deviz in Word: Obiectul + Categoria vizibile
- [ ] 7 teste green
- [ ] Metrici SD: matched=904 nemodificat
