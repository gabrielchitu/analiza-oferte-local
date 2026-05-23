# F3 Detection Enhancement — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add F3 end-of-table detection, same-page restart, global self-learning knowledge base, and physical PDF page numbers in Word report.

**Architecture:** New `shared/f3_knowledge.py` owns all F3 marker knowledge (load/save/query/learn). `f3_page_classifier.py` gets a post-processing step `_apply_end_detection()` that marks `f3_line_end` and `f3_restart_line` on pages. `f3_extractor.py` collects `source_pages` per deviz from `page_number` (already physical, 1-based). `report_word.py` shows `[PDF pag. X-Y]` in deviz headers.

**Tech Stack:** Python 3.11, python-docx, existing project structure

**Branch:** `refactor/v10`

**Spec:** `docs/superpowers/specs/2026-05-23-f3-detection-enhancement-design.md`

**Important context:**
- `page_number` in `page_classifications` dicts is ALREADY the physical PDF page number (1-based, read from DI JSON at `shared/f3_page_classifier.py:612`)
- `classify_pages()` returns `(results: list[dict], checkpoint: dict)` — signature at `shared/f3_page_classifier.py:963`
- `extract_articles_v3()` at `shared/f3_extractor.py:807` iterates `pages_by_deviz[deviz_cod]` and combines lines
- `_add_deviz_heading()` at `shared/report_word.py:184` — signature: `(table, deviz_cod, deviz_den, ref_count, oferta_count)`
- Run tests with: `.venv/bin/python3 -m pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py`

---

## File Map

| Fisier | Actiune |
|--------|---------|
| `shared/f3_knowledge.py` | CREATE |
| `shared/f3_markers_knowledge.json` | CREATE |
| `tests/shared/test_f3_knowledge.py` | CREATE |
| `shared/f3_page_classifier.py` | MODIFY — add `_apply_end_detection()`, wire into `classify_pages()` |
| `tests/test_f3_end_detection.py` | CREATE |
| `shared/f3_extractor.py` | MODIFY — add `source_pages` per article |
| `shared/report_word.py` | MODIFY — `_add_deviz_heading()` + `_format_page_range()` |

---

## Task 1: `shared/f3_knowledge.py` + `shared/f3_markers_knowledge.json`

**Files:**
- Create: `shared/f3_knowledge.py`
- Create: `shared/f3_markers_knowledge.json`
- Create: `tests/shared/test_f3_knowledge.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/shared/test_f3_knowledge.py
import json
import pytest
from pathlib import Path
from shared.f3_knowledge import F3Knowledge


@pytest.fixture
def tmp_knowledge(tmp_path):
    data = {
        "version": 1,
        "start_markers": [
            {"pattern": "Formular F3", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "STADIUL FIZIC:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
        "end_markers": [
            {"pattern": "TOTAL CHELT. DIRECTE", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "TOTAL GENERAL pe categorie", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
    }
    p = tmp_path / "knowledge.json"
    p.write_text(json.dumps(data))
    return F3Knowledge(path=p)


def test_find_start_marker_exact(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["col1 col2 col3", "Formular F3", "1 EA02A1 buc"])
    assert result == "Formular F3"


def test_find_start_marker_prefix(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["STADIUL FIZIC: oferta 226108 STRUCTURA"])
    assert result is not None


def test_find_start_marker_none(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["linie normala", "alt text"])
    assert result is None


def test_find_end_marker_returns_index(tmp_knowledge):
    lines = ["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"]
    result = tmp_knowledge.find_end_marker(lines)
    assert result == (1, "TOTAL CHELT. DIRECTE")


def test_find_end_marker_prefix(tmp_knowledge):
    lines = ["art1", "TOTAL GENERAL pe categorie Vo=To+Io+Po"]
    result = tmp_knowledge.find_end_marker(lines)
    assert result is not None
    assert result[0] == 1


def test_find_end_marker_none(tmp_knowledge):
    result = tmp_knowledge.find_end_marker(["1 EA02A1 buc", "2 CA01A mp"])
    assert result is None


def test_learn_adds_new_start_marker(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Lista cu cantitati", "exact", source_type="start")
    result = k.find_start_marker(["Lista cu cantitati de lucrari pe categorii"])
    assert result is not None


def test_learn_no_duplicate(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Formular F3", "exact", source_type="start")
    k.learn("Formular F3", "exact", source_type="start")
    count = sum(1 for m in k._data["start_markers"] if m["pattern"] == "Formular F3")
    assert count == 1


def test_learn_increments_seen_count(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Formular F3", "exact", source_type="start")
    k.learn("Formular F3", "exact", source_type="start")
    entry = next(m for m in k._data["start_markers"] if m["pattern"] == "Formular F3")
    assert entry["seen_count"] == 2


def test_learn_rejects_short_pattern(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("F3", "exact", source_type="start")
    assert not any(m["pattern"] == "F3" for m in k._data["start_markers"])


def test_learn_saves_to_file(tmp_path):
    p = tmp_path / "k.json"
    k = F3Knowledge(path=p)
    k.learn("Lista lucrari", "exact", source_type="start")
    k2 = F3Knowledge(path=p)
    assert k2.find_start_marker(["Lista lucrari"]) is not None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/shared/test_f3_knowledge.py -v 2>&1 | head -20
```
Expected: ImportError — `shared/f3_knowledge.py` doesn't exist yet.

- [ ] **Step 3: Create `shared/f3_knowledge.py`**

```python
# shared/f3_knowledge.py
import json
import re
from pathlib import Path
from datetime import datetime

KNOWLEDGE_PATH = Path(__file__).parent / "f3_markers_knowledge.json"


class F3Knowledge:
    def __init__(self, path: Path = KNOWLEDGE_PATH):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"version": 1, "start_markers": [], "end_markers": []}

    def save(self):
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def find_start_marker(self, lines: list) -> str | None:
        """Return first matching line or None."""
        for line in lines:
            for m in self._data.get("start_markers", []):
                if self._matches(line, m):
                    return line
        return None

    def find_end_marker(self, lines: list) -> tuple | None:
        """Return (line_index, matched_line) or None."""
        for i, line in enumerate(lines):
            for m in self._data.get("end_markers", []):
                if self._matches(line, m):
                    return (i, line)
        return None

    def learn(self, pattern: str, marker_type: str, source_type: str = "start",
              source: str = "llm", format_hint: str = "generic"):
        """Add new marker pattern. Ignores duplicates and short patterns."""
        if len(pattern.strip()) < 5:
            return
        key = "start_markers" if source_type == "start" else "end_markers"
        existing = [m for m in self._data[key] if m["pattern"] == pattern]
        if existing:
            existing[0]["seen_count"] = existing[0].get("seen_count", 0) + 1
            self.save()
            return
        self._data[key].append({
            "pattern": pattern,
            "type": marker_type,
            "format": format_hint,
            "source": source,
            "seen_count": 1,
            "learned_at": datetime.utcnow().isoformat(),
        })
        self.save()

    def _matches(self, line: str, marker: dict) -> bool:
        p = marker["pattern"]
        t = marker.get("type", "exact")
        if t == "exact":
            return p in line
        if t == "prefix":
            return line.strip().startswith(p)
        if t == "regex":
            return bool(re.search(p, line))
        return False
```

- [ ] **Step 4: Create `shared/f3_markers_knowledge.json`**

```json
{
  "version": 1,
  "start_markers": [
    {"pattern": "Formular F3", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "SECTIUNEA TEHNICA", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "STADIUL FIZIC:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": ">>> componenta", "type": "exact", "format": "edevize", "source": "manual", "seen_count": 0},
    {"pattern": "\\d{4,6} pag \\d+", "type": "regex", "format": "edevize", "source": "manual", "seen_count": 0}
  ],
  "end_markers": [
    {"pattern": "TOTAL 1 (Cheltuieli directe)", "type": "exact", "format": "edevize", "source": "manual", "seen_count": 0},
    {"pattern": "TOTAL CHELT. DIRECTE", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "Cheltuieli directe din articole:", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "Cheltuieli directe:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "TOTAL GENERAL pe categorie", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
    {"pattern": "TOTAL GENERAL DEVIZ", "type": "prefix", "format": "generic", "source": "manual", "seen_count": 0},
    {"pattern": "TOTAL GENERAL (fara TVA)", "type": "exact", "format": "edevize", "source": "manual", "seen_count": 0},
    {"pattern": "PROIECTANT", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0}
  ]
}
```

- [ ] **Step 5: Run all tests**

```bash
.venv/bin/python3 -m pytest tests/shared/test_f3_knowledge.py -v
```
Expected: 11/11 PASS

- [ ] **Step 6: Commit**

```bash
git add shared/f3_knowledge.py shared/f3_markers_knowledge.json tests/shared/test_f3_knowledge.py
git commit -m "feat(knowledge): F3Knowledge class + initial markers knowledge base"
```

---

## Task 2: `_apply_end_detection()` in `f3_page_classifier.py`

**Files:**
- Modify: `shared/f3_page_classifier.py` — add `_apply_end_detection()` + wire into `classify_pages()`
- Create: `tests/test_f3_end_detection.py`

**Context:** `classify_pages()` at line 963 returns `(results, checkpoint)`. `results` is a list of dicts with keys: `is_f3, deviz_cod, deviz_den, lines, page_number, needs_llm, header_only`. We add `f3_line_end` and `f3_restart_line` as optional fields.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_f3_end_detection.py
import json
import pytest
from pathlib import Path
from shared.f3_knowledge import F3Knowledge
from shared.f3_page_classifier import _apply_end_detection


@pytest.fixture
def knowledge(tmp_path):
    data = {
        "version": 1,
        "start_markers": [
            {"pattern": "Formular F3", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "STADIUL FIZIC:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
        "end_markers": [
            {"pattern": "TOTAL CHELT. DIRECTE", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "TOTAL GENERAL pe categorie", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
    }
    p = tmp_path / "k.json"
    p.write_text(json.dumps(data))
    return F3Knowledge(path=p)


def _make_page(lines, is_f3=True, page_number=1):
    return {"is_f3": is_f3, "lines": lines, "page_number": page_number,
            "deviz_cod": "1-01", "deviz_den": "test", "header_only": False}


def test_no_end_marker_no_change(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "2 CA01A mp 10.0"], page_number=1),
        _make_page(["3 CB01A mc 5.0"], page_number=2),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert "f3_line_end" not in result[0]
    assert "f3_line_end" not in result[1]


def test_end_marker_sets_f3_line_end(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"], page_number=3),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["f3_line_end"] == 1


def test_page_after_end_becomes_non_f3(knowledge):
    pages = [
        _make_page(["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE"], page_number=1),
        _make_page(["text fara F3"], page_number=2),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[1]["is_f3"] == False


def test_same_page_restart_detected(knowledge):
    pages = [
        _make_page([
            "1 EA02A1 buc 1.0",
            "TOTAL CHELT. DIRECTE",
            "STADIUL FIZIC: oferta 226108 CUPOLA",
            "2 CB01A mc 5.0",
        ], page_number=4),
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["f3_line_end"] == 1
    assert "f3_restart_line" in result[0]
    assert result[0]["f3_restart_line"] == 2


def test_non_f3_page_unchanged(knowledge):
    pages = [
        {"is_f3": False, "lines": ["pagina titlu"], "page_number": 1,
         "deviz_cod": "", "header_only": False},
    ]
    result = _apply_end_detection(pages, knowledge)
    assert result[0]["is_f3"] == False
    assert "f3_line_end" not in result[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_f3_end_detection.py -v 2>&1 | head -15
```
Expected: ImportError — `_apply_end_detection` not yet defined.

- [ ] **Step 3: Add `_apply_end_detection()` to `shared/f3_page_classifier.py`**

Add this function before `classify_pages()` (around line 960):

```python
def _apply_end_detection(page_classifications: list, knowledge) -> list:
    """
    Post-processing: detecteaza sfarsitul tabelelor F3 si restarteaza detectia
    pe aceeasi pagina daca incepe un nou tabel F3.

    Adauga campuri optionale la rezultate:
      f3_line_end: int — index linie unde s-a terminat tabelul F3 (exclusiv)
      f3_restart_line: int — index linie unde incepe un nou tabel F3 pe aceeasi pagina
    """
    in_f3 = False
    results = list(page_classifications)  # nu modifica lista originala

    for i, pc in enumerate(results):
        if not pc.get("is_f3", False):
            in_f3 = False
            continue

        if pc.get("header_only"):
            continue

        in_f3 = True
        lines = pc.get("lines", [])
        end_result = knowledge.find_end_marker(lines)

        if end_result is None:
            continue  # F3 continua normal pe aceasta pagina

        end_idx, _ = end_result
        results[i] = dict(pc)  # copie pentru a nu modifica originala
        results[i]["f3_line_end"] = end_idx
        in_f3 = False

        # Same-page restart: cauta start marker in liniile ramase dupa end
        remaining = lines[end_idx + 1:]
        if remaining:
            start_match = knowledge.find_start_marker(remaining)
            if start_match:
                # gasit index relativ in remaining → absolut in lines
                for j, line in enumerate(remaining):
                    if start_match in line:
                        results[i]["f3_restart_line"] = end_idx + 1 + j
                        in_f3 = True
                        break

        # Pagina urmatoare: daca nu avem restart, urmatoarele pagini F3-INHERITED
        # trebuie re-evaluate. Le marcam is_f3=False daca erau INHERITED.
        if not in_f3:
            for j in range(i + 1, len(results)):
                next_pc = results[j]
                if next_pc.get("extraction_method") == "inherited" or (
                    next_pc.get("is_f3") and not next_pc.get("deviz_cod")
                ):
                    results[j] = dict(next_pc)
                    results[j]["is_f3"] = False
                else:
                    break  # pagina cu deviz explicit — oprim

    return results
```

- [ ] **Step 4: Wire `_apply_end_detection()` into `classify_pages()` la `shared/f3_page_classifier.py:1001`**

Dupa linia `results, checkpoint = build_page_classifications(...)` (linia ~1001), adauga:

```python
    # Post-processing: end-detection + same-page restart
    from shared.f3_knowledge import F3Knowledge
    _knowledge = F3Knowledge()
    results = _apply_end_detection(results, _knowledge)
```

- [ ] **Step 5: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_f3_end_detection.py tests/shared/test_f3_knowledge.py -v
```
Expected: toate PASS.

- [ ] **Step 6: Regression — testele existente classifier netinse**

```bash
.venv/bin/python3 -m pytest tests/shared/test_f3_page_classifier_edevize.py tests/shared/test_f3_page_classifier_isdp.py tests/shared/test_f3_page_classifier_generic.py -v 2>&1 | tail -10
```
Expected: toate PASS (no regression).

- [ ] **Step 7: Commit**

```bash
git add shared/f3_page_classifier.py tests/test_f3_end_detection.py
git commit -m "feat(classifier): end-detection + same-page F3 restart via F3Knowledge"
```

---

## Task 3: `source_pages` in `shared/f3_extractor.py`

**Files:**
- Modify: `shared/f3_extractor.py:875-922` — sectiunea `pages_by_deviz` loop

**Context:** In `extract_articles_v3()`, la linia ~875 itereaza `pages_by_deviz[deviz_cod]`. Fiecare `pc` are `page_number` (physical). Articolele din deviz primesc `source_pages: list[int]`. Daca pagina are `f3_line_end`, extragerea ia doar `lines[:f3_line_end]` nu toate liniile. Daca pagina are `f3_restart_line`, liniile de la restart incolo apartin unui nou deviz — nu le includem in devizul curent.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_f3_extractor.py (fisier existent)

def test_source_pages_propagated():
    """Articolele extrase dintr-un deviz au source_pages din paginile fizice."""
    from shared.f3_extractor import extract_articles_v3

    page_classifications = [
        {
            "is_f3": True, "deviz_cod": "1-01", "deviz_den": "STRUCTURA",
            "lines": ["1 EA02A1 buc 1.0", "MONTAJ STRUCTURA"],
            "page_number": 12, "header_only": False,
        },
        {
            "is_f3": True, "deviz_cod": "1-01", "deviz_den": "STRUCTURA",
            "lines": ["2 CA01A mp 10.0", "TENCUIALA"],
            "page_number": 13, "header_only": False,
        },
    ]
    articles = extract_articles_v3(page_classifications)
    assert len(articles) > 0
    for art in articles:
        assert "source_pages" in art
        assert 12 in art["source_pages"]
        assert 13 in art["source_pages"]


def test_f3_line_end_limits_extraction():
    """Daca pagina are f3_line_end, extragerea ia doar liniile pana la end."""
    from shared.f3_extractor import extract_articles_v3

    page_classifications = [
        {
            "is_f3": True, "deviz_cod": "1-01", "deviz_den": "TEST",
            "lines": ["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"],
            "page_number": 5, "header_only": False,
            "f3_line_end": 1,  # opreste la linia 1
        },
    ]
    articles = extract_articles_v3(page_classifications)
    # Articolul EA02A1 trebuie extras (e inainte de f3_line_end)
    cods = [a["cod"] for a in articles]
    assert any("EA02A1" in c for c in cods)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_f3_extractor.py::test_source_pages_propagated tests/test_f3_extractor.py::test_f3_line_end_limits_extraction -v
```
Expected: FAIL — KeyError sau AssertionError.

- [ ] **Step 3: Modifica `extract_articles_v3()` in `shared/f3_extractor.py`**

In sectiunea `for deviz_cod, pages_in_deviz in pages_by_deviz.items():` (linia ~875), inlocuieste:

```python
        all_lines = []
        deviz_den = ""
        for pc in pages_in_deviz:
            lines = pc.get("lines", [])
            if lines:
                all_lines.extend(lines)
            if not deviz_den:
                deviz_den = pc.get("deviz_den", "")
```

cu:

```python
        all_lines = []
        deviz_den = ""
        source_pages: list = []
        for pc in pages_in_deviz:
            raw_lines = pc.get("lines", [])
            # Respecta f3_line_end daca pagina are sfarsit detectat
            f3_end = pc.get("f3_line_end")
            lines = raw_lines[:f3_end] if f3_end is not None else raw_lines
            if lines:
                all_lines.extend(lines)
            if not deviz_den:
                deviz_den = pc.get("deviz_den", "")
            phys = pc.get("page_number")
            if phys is not None:
                source_pages.append(phys)
        source_pages = sorted(set(source_pages))
```

Dupa ce `section_articles` e populat (linia ~904), adauga:

```python
        for art in section_articles:
            art["deviz"] = deviz_cod
            art["deviz_denumire"] = deviz_den
            art["source_pages"] = source_pages  # ← NOU
            art["denumire"] = _normalize_denom(art.get("denumire", ""))
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_f3_extractor.py -v 2>&1 | tail -15
```
Expected: toate testele extractor PASS inclusiv cele noi.

- [ ] **Step 5: Commit**

```bash
git add shared/f3_extractor.py tests/test_f3_extractor.py
git commit -m "feat(extractor): source_pages per article + respect f3_line_end"
```

---

## Task 4: `[PDF pag. X-Y]` in Word report

**Files:**
- Modify: `shared/report_word.py:184` — `_add_deviz_heading()` + helper `_format_page_range()`
- Modify: `shared/report_word.py:887` — sectiunea care apeleaza `_add_deviz_heading()`

**Context:** `_generate_word_hierarchical()` la linia ~887 itereaza deviz groups si apeleaza `_add_deviz_heading(table, deviz_cod, deviz_den, ref_count, oferta_count)`. Raportul ierarhic (`raport`) contine articolele cu `source_pages`. Trebuie sa colectam paginile ref si oferta per deviz si sa le pasam la heading.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_report_word.py (fisier existent)

def test_deviz_heading_shows_page_range():
    """_add_deviz_heading afiseaza [PDF pag. X-Y] cand sunt pagini."""
    from docx import Document
    from shared.report_word import _add_deviz_heading

    doc = Document()
    table = doc.add_table(rows=0, cols=11)
    _add_deviz_heading(table, "1-01", "STRUCTURA", ref_count=2, oferta_count=2,
                       ref_pages=[12, 13], oferta_pages=[28])
    cell_text = table.rows[-1].cells[0].text
    assert "PDF pag." in cell_text
    assert "12-13" in cell_text
    assert "28" in cell_text


def test_format_page_range_single():
    from shared.report_word import _format_page_range
    assert _format_page_range([5]) == "5"


def test_format_page_range_continuous():
    from shared.report_word import _format_page_range
    assert _format_page_range([3, 4, 5]) == "3-5"


def test_format_page_range_discontinuous():
    from shared.report_word import _format_page_range
    assert _format_page_range([3, 5, 7]) == "3, 5, 7"


def test_format_page_range_empty():
    from shared.report_word import _format_page_range
    assert _format_page_range([]) == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py::test_deviz_heading_shows_page_range tests/test_report_word.py::test_format_page_range_single -v
```
Expected: FAIL.

- [ ] **Step 3: Adauga `_format_page_range()` in `shared/report_word.py`**

Adauga inainte de `_add_deviz_heading` (linia 184):

```python
def _format_page_range(pages: list) -> str:
    """Formateaza lista de pagini: [5]→'5', [3,4,5]→'3-5', [3,5,7]→'3, 5, 7'."""
    if not pages:
        return ""
    pages = sorted(set(int(p) for p in pages))
    if len(pages) == 1:
        return str(pages[0])
    if pages[-1] - pages[0] == len(pages) - 1:
        return f"{pages[0]}-{pages[-1]}"
    return ", ".join(str(p) for p in pages)
```

- [ ] **Step 4: Modifica `_add_deviz_heading()` in `shared/report_word.py:184`**

Inlocuieste signatura si body:

```python
def _add_deviz_heading(table, deviz_cod: str, deviz_den: str,
                       ref_count: int, oferta_count: int,
                       ref_pages: list = None, oferta_pages: list = None) -> None:
    """Adaugă rând separator de deviz cu numărătoare ref vs ofertă + pagini PDF."""
    sep_cells = table.add_row().cells
    sep_cells[0].merge(sep_cells[10])
    delta = oferta_count - ref_count
    delta_str = f"{delta:+d}" if delta != 0 else "0 ✓"
    den_short = deviz_den[:40] + "..." if len(deviz_den) > 40 else deviz_den
    label = (
        f"Capitol de lucrări {deviz_cod}"
        + (f" — {den_short}" if den_short else "")
        + f"  │  LIPSA: {ref_count}"
        + f"  │  EXTRA: {oferta_count}"
        + f"  │  Delta: {delta_str}"
    )
    ref_range = _format_page_range(ref_pages or [])
    oferta_range = _format_page_range(oferta_pages or [])
    if ref_range:
        label += f"  │  Ref: PDF pag. {ref_range}"
    if oferta_range:
        label += f"  │  Oferta: PDF pag. {oferta_range}"
    run = sep_cells[0].paragraphs[0].add_run(label)
    run.bold = True
    _style_cell(sep_cells[0], 9, bold=True)
    _set_cell_shading(sep_cells[0], GRAY_FILL)
```

- [ ] **Step 5: Colecteaza paginile in `_generate_word_hierarchical()` si pasaza la heading**

In `_generate_word_hierarchical()`, sectiunea care apeleaza `_add_deviz_heading` (linia ~891):

Gaseste apelul:
```python
_add_deviz_heading(table, deviz_cod, deviz_den,
```

Inlocuieste cu:
```python
# Colecteaza source_pages din articolele ref si oferta din devizul curent
_ref_src_pages = []
_oferta_src_pages = []
for art in dv.get("articole", []):
    _ref_src_pages.extend(art.get("ref_source_pages", []))
    _oferta_src_pages.extend(art.get("oferta_source_pages", []))

_add_deviz_heading(table, deviz_cod, deviz_den,
                   ref_count=n_lipsa, oferta_count=n_extra,
                   ref_pages=_ref_src_pages, oferta_pages=_oferta_src_pages)
```

**Nota:** `ref_source_pages` / `oferta_source_pages` sunt setate in `report_builder.py` care construieste `raport_ierarhic`. Verifica cum e structurat `dv["articole"]` — daca nu au aceste campuri inca, adauga propagarea in `shared/report_builder.py`:

In `shared/report_builder.py`, cand construieste un articol in raportul ierarhic, adauga:
```python
art_entry["ref_source_pages"] = ref_art.get("source_pages", [])
art_entry["oferta_source_pages"] = oferta_art.get("source_pages", []) if oferta_art else []
```

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py -v 2>&1 | tail -15
```
Expected: toate PASS (12 vechi + 5 noi).

- [ ] **Step 7: Commit**

```bash
git add shared/report_word.py shared/report_builder.py tests/test_report_word.py
git commit -m "feat(report): show PDF page range in deviz header [Ref/Oferta: PDF pag. X-Y]"
```

---

## Task 5: LLM `learn()` integration

**Files:**
- Modify: `shared/f3_page_classifier.py:694` — `_classify_pages_llm()`

**Context:** `_classify_pages_llm()` la linia 694 primeste pagini `needs_llm=True`, apeleaza LLM batch si returneaza dict `{page_number: {is_f3, deviz_cod}}`. LLM returneaza si motivatie/context textual. Extrageam prima linie distinctiva din pagina ca pattern nou.

- [ ] **Step 1: Modifica `_classify_pages_llm()` sa apeleze `learn()` dupa clasificare**

In `_classify_pages_llm()`, dupa ce proceseaza rezultatele LLM (linia ~724-733), adauga:

```python
    # Self-learning: salveaza pattern-uri noi descoperite de LLM
    from shared.f3_knowledge import F3Knowledge
    _knowledge = F3Knowledge()
    _learned_count = 0
    for item in raw.get("page_classifications", []):
        page_num = item.get("page_number")
        is_f3 = item.get("is_f3", False)
        # Gaseste pagina corespunzatoare
        page_obj = next((p for p in ambiguous_pages if p.get("page_number") == page_num), None)
        if page_obj is None:
            continue
        lines = page_obj.get("lines", [])
        if not lines:
            continue
        # Extrage primul line distinctiv (>= 5 chars, nu numar pur)
        for line in lines[:10]:
            stripped = line.strip()
            if len(stripped) >= 5 and not stripped.isdigit():
                marker_type = "start" if is_f3 else "end"
                _knowledge.learn(stripped, "exact", source_type=marker_type, source="llm")
                _learned_count += 1
                break
    if _learned_count:
        logger.info(f"[PC] F3Knowledge: learned {_learned_count} new patterns from LLM")
```

- [ ] **Step 2: Run full pipeline test**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | rtk log
```
Expected: pipeline ruleaza, `[PC] F3Knowledge: learned N new patterns` apare in log, `shared/f3_markers_knowledge.json` e actualizat.

- [ ] **Step 3: Verifica knowledge file actualizat**

```bash
python3 -c "import json; d=json.load(open('shared/f3_markers_knowledge.json')); print('start:', len(d['start_markers']), 'end:', len(d['end_markers']))"
```
Expected: numarul de markeri a crescut fata de cei 5+8 initiali.

- [ ] **Step 4: Commit**

```bash
git add shared/f3_page_classifier.py shared/f3_markers_knowledge.json
git commit -m "feat(classifier): LLM learn() — save new F3 patterns to global knowledge base"
```

---

## Task 6: Regression + Integration Check

**Files:** None (verificare only)

- [ ] **Step 1: Run full test suite**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py
```
Expected: toate testele PASS, inclusiv cele noi. Testele existente fara regresie.

- [ ] **Step 2: Run pipeline Scoala Dragomiresti si verifica metrici**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | rtk log
```

Verifica metrici (trebuie sa fie identice cu baseline v9.0):
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
Expected: `matched=904, LIPSA=2, EXTRA=0/1, DEVIZ_MM=1` (identic cu baseline).

- [ ] **Step 3: Verifica raportul Word contine pagini PDF**

Deschide `output_AO/Scoala Dragomiresti/Raport_Oferta_1.docx` si verifica ca headerele de deviz contin `PDF pag.`.

- [ ] **Step 4: Commit final**

```bash
git add shared/f3_markers_knowledge.json
git commit -m "chore: update F3 knowledge base after SD pipeline run (self-learning)"
```

---

## Definition of Done

- [ ] `F3Knowledge` clasa: load/save/find_start/find_end/learn — toate testele green
- [ ] `shared/f3_markers_knowledge.json` cu markeri manuali initiali in repo
- [ ] `_apply_end_detection()` in classifier — end-detection + same-page restart
- [ ] `source_pages: list[int]` pe fiecare articol extras
- [ ] `[PDF pag. X-Y]` in header deviz Word (ref + oferta separat)
- [ ] LLM fallback apeleaza `learn()` dupa clasificare
- [ ] Metrici SD unchanged (matched=904, LIPSA=2)
- [ ] Teste existente fara regresie
