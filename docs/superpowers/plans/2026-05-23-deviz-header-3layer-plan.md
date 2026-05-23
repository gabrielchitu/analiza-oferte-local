# Deviz Header 3-Layer Extraction — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract OBIECTIVUL + Obiectul + Categoria from each F3 table header, generate stable `deviz_key`, attach to articles, and use `deviz_key` in matching.

**Architecture:** New `shared/deviz_header_extractor.py` module (extraction + cache). Called in `local_run.py::extract_document()` after `_apply_end_detection`, before `extract_articles_v3`. Articles get `deviz_key` + `deviz_header` fields. `AgentComparator_local.py::_deviz_key()` uses `deviz_key` field when present.

**Tech Stack:** Python 3.11, anthropic SDK (LLM fallback), hashlib, unicodedata, dataclasses

**Branch:** `refactor/v10`

**Spec:** `docs/superpowers/specs/2026-05-23-deviz-header-3layer-design.md`

**Important context:**
- `AgentComparator_local.py:143` — `_deviz_key(art)` reads `art.get("deviz")` as primary key. We extend it to prefer `art.get("deviz_key")` when present.
- `local_run.py:673` — `_apply_end_detection` called here. Insert header extraction RIGHT AFTER (line ~674).
- `local_run.py:675` — `articles = extract_articles_v3(page_classes)`. Attach `deviz_key` to articles AFTER this call.
- Run tests: `.venv/bin/python3 -m pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py --ignore=tests/shared/test_f3_regex_parser_multiline.py --ignore=tests/test_normalize_cod.py`

---

## File Map

| File | Action |
|------|--------|
| `shared/deviz_header_extractor.py` | CREATE |
| `shared/deviz_header_knowledge.json` | CREATE (empty cache) |
| `tests/test_deviz_header_extractor.py` | CREATE |
| `local_run.py` | MODIFY — call extractor + attach deviz_key to articles |
| `AgentComparator_local.py` | MODIFY — `_deviz_key()` prefers `deviz_key` field |

---

## Task 1: Core module — `shared/deviz_header_extractor.py`

**Files:**
- Create: `shared/deviz_header_extractor.py`
- Create: `shared/deviz_header_knowledge.json`
- Create: `tests/test_deviz_header_extractor.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_deviz_header_extractor.py
import json
import pytest
from pathlib import Path


def test_extract_from_lines_all_3():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "OBIECTIVUL: Reabilitare sediu scoala",
        "Obiectul: Corp A scoala",
        "Categoria de lucrari: 2.6 Instalatii Termice",
        "1 EA02A1 buc 1.0",
    ]
    obj1, obj2, cat = _extract_from_lines(lines)
    assert obj1 == "Reabilitare sediu scoala"
    assert obj2 == "Corp A scoala"
    assert cat == "2.6 Instalatii Termice"


def test_extract_from_lines_stadiu_fizic():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "OBIECTIVUL: Sediu primarie",
        "Obiectul: Cladire administrativa",
        "Stadiul fizic: 226108 STRUCTURA DE REZISTENTA",
    ]
    _, _, cat = _extract_from_lines(lines)
    assert cat is not None
    assert "226108" in cat


def test_extract_from_lines_missing_layer():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "Obiectul: Corp B",
        "Categoria de lucrari: 3.1 Finisaje",
    ]
    obj1, obj2, cat = _extract_from_lines(lines)
    assert obj1 is None
    assert obj2 == "Corp B"
    assert cat == "3.1 Finisaje"


def test_make_deviz_key_stable():
    from shared.deviz_header_extractor import _make_deviz_key
    k1, v1 = _make_deviz_key("A", "B", "C")
    k2, v2 = _make_deviz_key("A", "B", "C")
    assert k1 == k2
    assert v1 is True
    assert not k1.startswith("__INCOMPLETE__")


def test_make_deviz_key_incomplete():
    from shared.deviz_header_extractor import _make_deviz_key
    k, v = _make_deviz_key("A", None, "C")
    assert v is False
    assert k.startswith("__INCOMPLETE__")


def test_cache_roundtrip(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / "cache.json")
    cache.put("key1", "Obiectiv", "Obiect", "Cat")
    result = cache.get("key1")
    assert result == ("Obiectiv", "Obiect", "Cat")


def test_cache_miss(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / "cache.json")
    assert cache.get("missing") is None


def test_extract_deviz_headers_full(tmp_path):
    from shared.deviz_header_extractor import extract_deviz_headers
    page_classes = [
        {
            "is_f3": True, "deviz_cod": "1-01", "header_only": False,
            "lines": [
                "OBIECTIVUL: Reabilitare scoala",
                "Obiectul: Corp A",
                "Categoria de lucrari: 2.1 Structuri",
                "1 EA02A1 buc 1.0",
            ],
        }
    ]
    headers = extract_deviz_headers(page_classes)
    assert "1-01" in headers
    h = headers["1-01"]
    assert h.obiectivul == "Reabilitare scoala"
    assert h.obiectul == "Corp A"
    assert h.categoria == "2.1 Structuri"
    assert h.is_valid is True
    assert h.source == "regex"
    assert not h.deviz_key.startswith("__INCOMPLETE__")


def test_extract_deviz_headers_incomplete(tmp_path):
    from shared.deviz_header_extractor import extract_deviz_headers
    page_classes = [
        {
            "is_f3": True, "deviz_cod": "2-01", "header_only": False,
            "lines": ["Obiectul: Corp B", "1 CA01A mp 5.0"],
        }
    ]
    headers = extract_deviz_headers(page_classes)
    h = headers["2-01"]
    assert h.is_valid is False
    assert h.deviz_key.startswith("__INCOMPLETE__")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_deviz_header_extractor.py -v 2>&1 | head -15
```
Expected: `ImportError: cannot import name '_extract_from_lines' from 'shared.deviz_header_extractor'`

- [ ] **Step 3: Create `shared/deviz_header_extractor.py`**

```python
# shared/deviz_header_extractor.py
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
    r'(?:obiectiv(?:ul)?|investment\s+object)\s*[:\-]?\s*["\']?(.+)',
    re.IGNORECASE
)
_OBJ2_RE = re.compile(
    r'(?:obiectul|obiect(?:ul)?\s+de\s+investi[tți]ii?)\s*[:\-]\s*(.+)',
    re.IGNORECASE
)
_CAT_RE = re.compile(
    r'(?:categoria\s+de\s+lucr[aă]ri?|stadiul?\s+fizic[:\-]?|category)\s*[:\-]?\s*(.+)',
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


def _make_deviz_key(
    obiectivul: str | None,
    obiectul: str | None,
    categoria: str | None,
) -> tuple[str, bool]:
    is_valid = all(x is not None for x in [obiectivul, obiectul, categoria])
    parts = [_normalize(x or "") for x in [obiectivul, obiectul, categoria]]
    raw = " | ".join(parts)
    key = hashlib.md5(raw.encode()).hexdigest()[:16]
    if not is_valid:
        key = f"__INCOMPLETE__:{key}"
    return key, is_valid


def _extract_from_lines(
    header_lines: list[str],
) -> tuple[str | None, str | None, str | None]:
    """Regex pass: extrage OBIECTIVUL, Obiectul, Categoria din primele 30 linii."""
    obiectivul = obiectul = categoria = None
    for line in header_lines[:30]:
        s = line.strip()
        if obiectivul is None:
            m = _OBJ1_RE.match(s)
            if m:
                obiectivul = m.group(1).strip().strip("\"'")
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
            pass  # non-critical


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
            parts = text.split("```")
            text = parts[1] if len(parts) > 1 else text
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception as e:
        logger.debug(f"[DHX] LLM extraction failed: {e}")
        return None


def extract_deviz_headers(
    page_classifications: list[dict],
    llm_client=None,
    model: str = "",
) -> dict[str, "DevizHeader"]:
    """
    Extrage 3-layer header (OBIECTIVUL, Obiectul, Categoria) pentru fiecare deviz F3.
    Returns: {deviz_cod -> DevizHeader}
    """
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
            "\n".join(header_lines[:10]).encode()
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
```

- [ ] **Step 4: Create `shared/deviz_header_knowledge.json`**

```json
{}
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python3 -m pytest tests/test_deviz_header_extractor.py -v
```
Expected: 9/9 PASS

- [ ] **Step 6: Commit**

```bash
git add shared/deviz_header_extractor.py shared/deviz_header_knowledge.json tests/test_deviz_header_extractor.py
git commit -m "feat(deviz-header): 3-layer extractor + cache (OBIECTIVUL/Obiectul/Categoria)"
```

---

## Task 2: Integrare in `local_run.py`

**Files:**
- Modify: `local_run.py:673-675` — insert after `_apply_end_detection`, before `extract_articles_v3`

**Context:** Dupa linia 673 (`page_classes = _apply_end_detection(...)`), adauga extractia de headers si atasarea `deviz_key` la articole.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_f3_extractor.py
def test_articles_have_deviz_key_after_pipeline():
    """Articolele trebuie sa aiba deviz_key setat dupa extract_document."""
    # Test simplu: verifica ca extract_deviz_headers + attach functioneaza impreuna
    from shared.deviz_header_extractor import extract_deviz_headers

    page_classes = [
        {
            "is_f3": True, "deviz_cod": "1-01", "header_only": False,
            "lines": [
                "OBIECTIVUL: Reabilitare scoala",
                "Obiectul: Corp A",
                "Categoria de lucrari: 2.1 Structuri",
                "1 EA02A1 buc 1.0",
            ],
        }
    ]
    headers = extract_deviz_headers(page_classes)

    # Simuleaza atasarea deviz_key la articole
    articles = [{"cod": "EA02A1", "deviz": "1-01", "cantitate": 1.0}]
    for art in articles:
        dh = headers.get(art.get("deviz", ""))
        art["deviz_key"] = dh.deviz_key if dh else art.get("deviz", "")
        art["deviz_header"] = {
            "obiectivul": dh.obiectivul if dh else None,
            "obiectul": dh.obiectul if dh else None,
            "categoria": dh.categoria if dh else None,
        }

    assert articles[0]["deviz_key"] != ""
    assert not articles[0]["deviz_key"].startswith("__INCOMPLETE__")
    assert articles[0]["deviz_header"]["obiectivul"] == "Reabilitare scoala"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_f3_extractor.py::test_articles_have_deviz_key_after_pipeline -v 2>&1 | tail -5
```
Expected: PASS (testul testeaza helper-e deja implementate, nu `local_run.py` direct)

- [ ] **Step 3: Modifica `local_run.py` — insereaza dupa linia 673**

Gaseste blocul (linia ~670-676):
```python
    # Apply end-detection in-memory AFTER checkpoint is loaded/saved (never persisted)
    from shared.f3_page_classifier import _apply_end_detection
    from shared.f3_knowledge import F3Knowledge
    page_classes = _apply_end_detection(page_classes, F3Knowledge())

    articles = extract_articles_v3(page_classes)
```

Inlocuieste cu:
```python
    # Apply end-detection in-memory AFTER checkpoint is loaded/saved (never persisted)
    from shared.f3_page_classifier import _apply_end_detection
    from shared.f3_knowledge import F3Knowledge
    page_classes = _apply_end_detection(page_classes, F3Knowledge())

    # Extract 3-layer deviz headers (OBIECTIVUL / Obiectul / Categoria)
    from shared.deviz_header_extractor import extract_deviz_headers
    deviz_headers = extract_deviz_headers(page_classes, client, model)
    valid_count = sum(1 for h in deviz_headers.values() if h.is_valid)
    logger.info(f"  {len(deviz_headers)} devize cu header extras ({valid_count} valide, "
                f"{len(deviz_headers) - valid_count} incomplete)")

    articles = extract_articles_v3(page_classes)

    # Ataseaza deviz_key si deviz_header la fiecare articol
    for art in articles:
        dh = deviz_headers.get(art.get("deviz", ""))
        art["deviz_key"] = dh.deviz_key if dh else art.get("deviz", "")
        art["deviz_header"] = {
            "obiectivul": dh.obiectivul if dh else None,
            "obiectul": dh.obiectul if dh else None,
            "categoria": dh.categoria if dh else None,
        }
```

- [ ] **Step 4: Verifica import OK**

```bash
.venv/bin/python3 -c "import local_run; print('import OK')"
```
Expected: `import OK`

- [ ] **Step 5: Verifica SD pipeline nu se sparge**

```bash
.venv/bin/python3 -m pytest tests/test_f3_extractor.py -v 2>&1 | tail -8
```
Expected: toate testele existente PASS.

- [ ] **Step 6: Commit**

```bash
git add local_run.py tests/test_f3_extractor.py
git commit -m "feat(pipeline): extract 3-layer deviz headers + attach deviz_key to articles"
```

---

## Task 3: `_deviz_key()` prefer `deviz_key` field

**Files:**
- Modify: `AgentComparator_local.py:143-161` — `_deviz_key(art)` function

**Context:** Functia `_deviz_key(art)` la linia 143 citeste `art.get("deviz")`. Articolele acum au si `deviz_key` field. Trebuie sa prefere `deviz_key` cand exista.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_matching.py (fisier existent)
def test_deviz_key_field_preferred_over_deviz():
    """_deviz_key() trebuie sa prefere campul deviz_key al articolului."""
    import sys
    sys.path.insert(0, '.')
    from AgentComparator_local import _deviz_key

    art_with_key = {
        "deviz": "226108",
        "deviz_key": "abc123def456789a",  # deviz_key explicit
        "cod": "EA02A1",
    }
    art_without_key = {
        "deviz": "226108",
        "cod": "CA01A",
    }

    assert _deviz_key(art_with_key) == "abc123def456789a"
    # Fara deviz_key, fallback la comportamentul actual (deviz_cod normalizat)
    assert _deviz_key(art_without_key) == "226108"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_matching.py::test_deviz_key_field_preferred_over_deviz -v 2>&1 | tail -5
```
Expected: FAIL — `assert "abc123def456789a" == "226108"` (functia ignora `deviz_key`)

- [ ] **Step 3: Modifica `_deviz_key()` in `AgentComparator_local.py:143`**

Inlocuieste functia:
```python
def _deviz_key(art: dict) -> str:
    """Returneaza cheia de deviz normalizata pentru un articol.

    Prefera campul deviz_key (generat din 3-layer header) daca exista.
    Fallback la deviz_cod normalizat sau deviz_denumire.
    """
    # Prefer deviz_key din 3-layer extraction (Sub-project B)
    explicit_key = (art.get("deviz_key") or "").strip()
    if explicit_key and not explicit_key.startswith("__INCOMPLETE__"):
        return explicit_key

    # Fallback: use deviz code (reliable, numeric) - normalized for OCR variations
    deviz_cod = (art.get("deviz") or "").strip()
    if deviz_cod:
        return _normalize_deviz_code(deviz_cod)

    # Last fallback: use normalized denomination if no code
    raw = (art.get("deviz_denumire") or "").strip().upper()
    raw = re.sub(r'^(\d+\s+)+', '', raw).strip()
    raw = re.sub(r'\b(OB|NR|CAP|ART)[\s.]*(\d+)', r'\1\2', raw)
    raw = re.sub(r'\s+', ' ', raw).strip()
    return raw
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_matching.py -v 2>&1 | tail -10
```
Expected: noul test PASS + toate testele existente PASS.

- [ ] **Step 5: Commit**

```bash
git add AgentComparator_local.py tests/test_matching.py
git commit -m "feat(matching): _deviz_key() prefers deviz_key field from 3-layer extraction"
```

---

## Task 4: Regression + Integration Check

**Files:** Nicio modificare de cod — doar verificare.

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py \
  2>&1 | tail -10
```
Expected: 183+ passed, aceleasi 4 pre-existing failures ca inainte.

- [ ] **Step 2: Run SD pipeline si verifica metrici**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | rtk log
```

Verifica metrici (trebuie sa ramana identice):
```bash
python3 -c "
import json; from pathlib import Path; from collections import Counter
for i in range(1,3):
    f = Path(f'output_AO/Scoala Dragomiresti/comparatie_oferta_{i}.json')
    if not f.exists(): continue
    comp = json.loads(f.read_text())
    tips = Counter(n['tip'] for n in comp['neconformitati'])
    print(f'SD O{i}: matched={comp[\"matches\"]} LIPSA={tips.get(\"ARTICOL_LIPSA\",0)} EXTRA={tips.get(\"ARTICOL_EXTRA\",0)} DEVIZ_MM={tips.get(\"DEVIZ_MISMATCH\",0)}')
"
```
Expected: `matched=904, LIPSA=2` (identic cu baseline).

- [ ] **Step 3: Verifica deviz_key in comparatie JSON**

```bash
python3 -c "
import json
from pathlib import Path
comp = json.loads(Path('output_AO/Scoala Dragomiresti/comparatie_oferta_1.json').read_text())
# Gaseste un match si verifica deviz_key
matches = comp.get('matches', [])
if matches:
    m = matches[0]
    ref = m.get('ref_art', {})
    print('deviz_key in ref art:', ref.get('deviz_key', 'ABSENT'))
    print('deviz_header in ref art:', ref.get('deviz_header', 'ABSENT'))
"
```
Expected: `deviz_key` prezent (hash 16-char sau `__INCOMPLETE__:...`).

- [ ] **Step 4: Commit final**

```bash
git add shared/deviz_header_knowledge.json
git commit -m "chore: update deviz header knowledge cache after SD pipeline run"
```

---

## Definition of Done

- [ ] `DevizHeader` dataclass + `_extract_from_lines` + `_make_deviz_key` + cache
- [ ] `extract_deviz_headers(page_classes)` — orchestrator cu regex → cache → LLM
- [ ] `deviz_header_knowledge.json` — fisier gol initial (se populeaza la rulare)
- [ ] 9 teste green in `test_deviz_header_extractor.py`
- [ ] `local_run.py` apeleaza extractor + ataseaza `deviz_key` la articole
- [ ] `_deviz_key(art)` in AgentComparator prefera `deviz_key` field
- [ ] Metrici SD: matched=904 nemodificat
- [ ] `deviz_key` prezent in JSON output pentru articolele extrase
