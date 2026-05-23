# F3 Detection Enhancement — Implementation Spec (Sub-project A)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance F3 page classification with end-of-table detection, same-page restart, global self-learning knowledge base, physical PDF page number tracking, and page number display in Word report.

**Architecture:** New `shared/f3_knowledge.py` module owns all marker knowledge. `f3_page_classifier.py` becomes stateful (tracks in_f3_table). Physical page numbers flow from DI JSON → extractor → report.

**Branch:** `refactor/v10`

---

## Context — Starea Actuala

- `shared/f3_page_classifier.py` (1045 linii) — detecteaza F3 per pagina, stateless
- Pagini F3 continuate = INHERITED (mostenire de la pagina anterioara)
- Nu detecteaza sfarsitul unui tabel F3
- Nu stie daca un nou tabel F3 incepe pe aceeasi pagina cu sfarsitul altuia
- `page_number_physical` exista in DI JSON (`page_number` field, 1-based) dar nu e propagat
- Knowledge de detectie F3 e hardcodat in classifier

---

## Fisiere Implicate

| Fisier | Tip | Schimbare |
|--------|-----|-----------|
| `shared/f3_knowledge.py` | CREATE | Knowledge base — load/save/query/learn |
| `shared/f3_markers_knowledge.json` | CREATE | Date persistente markeri F3 |
| `shared/f3_page_classifier.py` | MODIFY | Stateful, end-detection, same-page restart, foloseste f3_knowledge |
| `shared/f3_extractor.py` | MODIFY | `source_pages: list[int]` per articol |
| `shared/report_word.py` | MODIFY | `[PDF pag. X-Y]` in header deviz |
| `local_run.py` | MODIFY | Pass-through `page_number_physical` |
| `tests/shared/test_f3_knowledge.py` | CREATE | Unit tests knowledge module |
| `tests/test_f3_page_classifier_enddetection.py` | CREATE | Tests end-detection + restart |

---

## Design Detaliat

### 1. `shared/f3_knowledge.py`

```python
import json, re
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
        self.path.write_text(json.dumps(self._data, ensure_ascii=False, indent=2), encoding="utf-8")

    def find_start_marker(self, lines: list[str]) -> str | None:
        """Return matched line or None."""
        return self._scan(lines, self._data["start_markers"])

    def find_end_marker(self, lines: list[str]) -> tuple[int, str] | None:
        """Return (line_index, matched_line) or None."""
        return self._scan_with_index(lines, self._data["end_markers"])

    def learn(self, pattern: str, marker_type: str, source_type: str = "start", source: str = "llm", format_hint: str = "generic"):
        if len(pattern) < 5:
            return  # prea generic
        key = "start_markers" if source_type == "start" else "end_markers"
        existing = [m for m in self._data[key] if m["pattern"] == pattern]
        if existing:
            existing[0]["seen_count"] = existing[0].get("seen_count", 0) + 1
            self.save()
            return
        self._data[key].append({
            "pattern": pattern,
            "type": marker_type,  # "exact" | "prefix" | "regex"
            "format": format_hint,
            "source": source,
            "seen_count": 1,
            "learned_at": datetime.utcnow().isoformat(),
        })
        self.save()

    def _scan(self, lines, markers) -> str | None:
        for line in lines:
            for m in markers:
                if self._matches(line, m):
                    return line
        return None

    def _scan_with_index(self, lines, markers) -> tuple[int, str] | None:
        for i, line in enumerate(lines):
            for m in markers:
                if self._matches(line, m):
                    return (i, line)
        return None

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

### 2. `shared/f3_markers_knowledge.json` — continut initial

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

### 3. `shared/f3_page_classifier.py` — logica stateful

Classifier devine stateful per document. Adauga metoda `classify_pages_stateful(pages)`:

```python
def classify_pages_stateful(pages: list[dict], knowledge: F3Knowledge) -> list[dict]:
    results = []
    in_f3 = False
    current_deviz = None

    for page in pages:
        lines = page.get("lines", [])
        phys_num = page.get("page_number", len(results) + 1)

        if not in_f3:
            # cauta START
            match = knowledge.find_start_marker(lines)
            if match:
                in_f3 = True
                current_deviz = _extract_deviz_cod(lines)  # logica existenta
                results.append({**_classify_f3(page, current_deviz),
                                 "page_number_physical": phys_num,
                                 "f3_line_start": _find_line_index(lines, match),
                                 "f3_line_end": None})
            else:
                results.append({**_classify_non_f3(page),
                                 "page_number_physical": phys_num})
        else:
            # in tabel F3 — cauta END
            end_result = knowledge.find_end_marker(lines)
            if end_result is None:
                # continuare F3 normala
                results.append({**_classify_f3(page, current_deviz),
                                 "page_number_physical": phys_num,
                                 "f3_line_start": 0,
                                 "f3_line_end": None})
            else:
                end_idx, _ = end_result
                # pagina contine sfarsit F3 la linia end_idx
                # liniile 0..end_idx = F3
                # liniile end_idx+1..end = cauta START nou
                in_f3 = False
                remaining = lines[end_idx + 1:]
                new_start = knowledge.find_start_marker(remaining)

                page_entry = {**_classify_f3(page, current_deviz),
                               "page_number_physical": phys_num,
                               "f3_line_start": 0,
                               "f3_line_end": end_idx}

                if new_start:
                    in_f3 = True
                    current_deviz = _extract_deviz_cod(remaining)
                    page_entry["f3_restart_line"] = end_idx + 1 + _find_line_index(remaining, new_start)

                results.append(page_entry)

    return results
```

**Fallback LLM:** Daca `find_start_marker` nu gaseste nimic si pagina are semne ambigue → LLM call ca acum. Dupa LLM, `knowledge.learn()` cu pattern extras din raspuns.

### 4. `shared/f3_extractor.py` — `source_pages`

In `extract_articles_v3()`, cand grupeaza paginile per deviz_cod:

```python
# Colecteaza paginile fizice ale devizului
source_pages = sorted(set(
    pc["page_number_physical"]
    for pc in deviz_pages
    if "page_number_physical" in pc
))

# Atribuie la fiecare articol din deviz
for art in deviz_articles:
    art["source_pages"] = source_pages
```

### 5. `shared/report_word.py` — header deviz cu pagini

In `_generate_word_hierarchical`, la randul de header deviz:

```python
# Colecteaza source_pages din articolele devizului
ref_pages = _format_page_range(deviz_ref_pages)    # ex: "12-14"
oferta_pages = _format_page_range(deviz_oferta_pages)  # ex: "28"

header_text = f"{deviz_cod} — {deviz_den}"
if ref_pages:
    header_text += f"  [Ref: PDF pag. {ref_pages}]"
if oferta_pages:
    header_text += f"  [Oferta: PDF pag. {oferta_pages}]"

def _format_page_range(pages: list[int]) -> str:
    if not pages:
        return ""
    pages = sorted(set(pages))
    if len(pages) == 1:
        return str(pages[0])
    if pages[-1] - pages[0] == len(pages) - 1:
        return f"{pages[0]}-{pages[-1]}"  # interval continuu
    return ", ".join(str(p) for p in pages)  # lista discontinua
```

---

## Reguli Self-Learning

1. LLM returneaza motivatie → extrage pattern (primul string distinctiv din liniile paginii care a declansat clasificarea)
2. `learn()` nu adauga:
   - Duplicate exacte
   - Pattern < 5 caractere
   - Pattern care contine doar cifre
3. `f3_markers_knowledge.json` se comite la fiecare sesiune daca s-a invatat ceva nou
4. `seen_count` creste la fiecare match — pattern-urile cu seen_count mare = mai de incredere

---

## Testing

### `tests/shared/test_f3_knowledge.py`
```python
def test_find_start_marker_exact():
    k = F3Knowledge(path=tmp_knowledge_with_manual_markers)
    assert k.find_start_marker(["Formular F3", "col1 col2"]) == "Formular F3"

def test_find_end_marker_returns_index():
    k = F3Knowledge(...)
    result = k.find_end_marker(["art1", "TOTAL CHELT. DIRECTE", "profit"])
    assert result == (1, "TOTAL CHELT. DIRECTE")

def test_learn_adds_new_pattern():
    k = F3Knowledge(path=tmp_path)
    k.learn("Lista cu cantitati", "exact", "start")
    assert k.find_start_marker(["Lista cu cantitati de lucrari"]) is not None

def test_learn_no_duplicate():
    k = F3Knowledge(...)
    k.learn("Formular F3", "exact", "start")
    k.learn("Formular F3", "exact", "start")
    count = sum(1 for m in k._data["start_markers"] if m["pattern"] == "Formular F3")
    assert count == 1

def test_learn_rejects_short_pattern():
    k = F3Knowledge(...)
    k.learn("F3", "exact", "start")
    assert not any(m["pattern"] == "F3" for m in k._data["start_markers"])
```

### `tests/test_f3_page_classifier_enddetection.py`
```python
def test_end_marker_stops_f3():
    pages = [make_page(["1 EA02A1 buc 1.0", "2 CA01A mp 10.0"]),
             make_page(["TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"]),
             make_page(["text non-f3"])]
    results = classify_pages_stateful(pages, knowledge)
    assert results[0]["is_f3"] == True
    assert results[1]["is_f3"] == True
    assert results[1]["f3_line_end"] == 0  # sfarsit la linia 0
    assert results[2]["is_f3"] == False

def test_same_page_restart():
    pages = [make_page(["TOTAL CHELT. DIRECTE", "Formular F3", "1 EA02A1 buc 1.0"])]
    results = classify_pages_stateful(pages, knowledge)
    assert "f3_restart_line" in results[0]
    assert results[0]["f3_line_end"] == 0
    assert results[0]["f3_restart_line"] == 1

def test_source_pages_propagated():
    # articolele extrase dintr-un deviz pe paginile 12-13 au source_pages=[12,13]
    ...
```

---

## Known Constraints

- `f3_page_classifier.py` are logica LLM batch complexa — stateful wrapper adaugat ca metoda noua, nu rescrie classify existent. Backward compat mentinuta.
- `f3_markers_knowledge.json` comis in repo (nu in .gitignore) — creste organic
- Testele existente `tests/shared/test_f3_page_classifier_*.py` nu trebuie sa regreseze

---

## Definition of Done

- [ ] `F3Knowledge` clasa cu load/save/find_start/find_end/learn
- [ ] `f3_markers_knowledge.json` cu toti martorii manuali din imagini
- [ ] `classify_pages_stateful()` cu end-detection + same-page restart
- [ ] `source_pages` propagat din extractor pana in JSON output
- [ ] `[PDF pag. X-Y]` in header deviz Word report (ref + oferta separat)
- [ ] LLM fallback apeleaza `learn()` dupa clasificare
- [ ] Toate testele noi green
- [ ] Testele existente classifier netinse (no regression)
- [ ] `f3_markers_knowledge.json` comis in repo
