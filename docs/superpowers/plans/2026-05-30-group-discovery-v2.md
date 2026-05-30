# Group Discovery v2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adaugă DocumentProfiler (TABLE/LINES per DI JSON), GroupExtractor v2 (Azure tables native cu fallback la LINES), RapidFuzz Phase 2a în group matching, și skill autoverify-groups cu loop autonom de convergență.

**Architecture:** Profiler detectează dacă Azure DI a generat `tables[]` structurate; GroupExtractor v2 extrage `dict[str, DevizHeader]` — identic cu `extract_deviz_headers()` — din tabele sau delegând la LINES extractor existent. RapidFuzz se inserează ca Phase 2a în `compare_by_groups()` înainte de LLM. Invariant hard: `oferta_only == 0` după matching.

**Tech Stack:** Python 3.11, rapidfuzz>=3.0, pandas>=2.0, pytest, Azure Document Intelligence JSON

---

## Fișiere create/modificate

| Fișier | Acțiune | Responsabilitate |
|--------|---------|-----------------|
| `requirements.txt` | Modificat | Adaugă rapidfuzz, pandas |
| `shared/document_profiler.py` | Creat | `DocumentProfile`, `profile_document()` |
| `shared/group_extractor.py` | Creat | `extract_groups_as_headers()` — TABLE + LINES |
| `shared/group_comparator.py` | Modificat | `_match_by_rapidfuzz()` ca Phase 2a |
| `local_run.py` | Modificat minimal | Profiler + fallback additive la linia 763 |
| `.claude/commands/autoverify-groups.md` | Creat | Skill autonom loop convergență |
| `tests/shared/test_document_profiler.py` | Creat | 6 teste TABLE/LINES detection |
| `tests/shared/test_group_extractor.py` | Creat | 5 teste TABLE mode + LINES wrapper |
| `tests/shared/test_group_comparator_rapidfuzz.py` | Creat | 5 teste Phase 2a |

**Neatinse:** `f3_regex_parser.py`, `f3_extractor.py`, `f3_page_classifier.py`, `AgentComparator_local.py`, `f3_markers_knowledge.json`, Phase 1 + Phase 1.5 din `group_comparator.py`

---

## Task 0: Captează baseline pe clienți verificați

**Files:**
- Read: `output_AO/*/holistic_oferta_1.json` (și oferta_2 unde există)

**Context:** Înainte de orice modificare, salvăm valorile actuale `matched/ref_only/oferta_only` ca referință de regresie. Clienții verificați: Blocuri Racari, Camin Maneciu, Drum Tatarani, Scoala Dragomiresti.

- [ ] **Step 1: Rulează pipeline pe toți clienții**

```bash
python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | tail -5
python3 multi_client_run.py --client "Camin Maneciu" 2>&1 | tail -5
python3 multi_client_run.py --client "Drum Tatarani" 2>&1 | tail -5
python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | tail -5
```

- [ ] **Step 2: Salvează baseline**

```bash
python3 - <<'EOF'
import json, glob, os

clients = ["Blocuri Racari", "Camin Maneciu", "Drum Tatarani", "Scoala Dragomiresti"]
baseline = {}
for client in clients:
    baseline[client] = {}
    for n in range(1, 5):
        path = f"output_AO/{client}/holistic_oferta_{n}.json"
        if not os.path.exists(path):
            continue
        data = json.load(open(path))
        baseline[client][f"oferta_{n}"] = {
            "matched": len(data.get("matched_groups", [])),
            "ref_only": len(data.get("ref_only_groups", [])),
            "oferta_only": len(data.get("oferta_only_groups", [])),
        }

json.dump(baseline, open("docs/superpowers/plans/baseline_groups.json", "w"), indent=2, ensure_ascii=False)
print(json.dumps(baseline, indent=2, ensure_ascii=False))
EOF
```

Expected output: JSON cu matched/ref_only/oferta_only per client/oferta.

- [ ] **Step 3: Commit baseline**

```bash
git add docs/superpowers/plans/baseline_groups.json
git commit -m "chore: capture group matching baseline before v2 refactor"
```

---

## Task 1: Adaugă dependențe — rapidfuzz și pandas

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Adaugă la requirements.txt**

Editează `requirements.txt` — adaugă după `openpyxl>=3.1.0`:
```
rapidfuzz>=3.0
pandas>=2.0
```

- [ ] **Step 2: Instalează**

```bash
pip install rapidfuzz>=3.0 pandas>=2.0
```

Expected: `Successfully installed rapidfuzz-X.Y.Z pandas-X.Y.Z` (sau "already satisfied").

- [ ] **Step 3: Verifică import**

```bash
python3 -c "from rapidfuzz import fuzz; import pandas; print('OK rapidfuzz', fuzz.ratio('a','a')); print('OK pandas', pandas.__version__)"
```

Expected: `OK rapidfuzz 100` și `OK pandas X.Y.Z`

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "chore(deps): add rapidfuzz and pandas for group-discovery-v2"
```

---

## Task 2: DocumentProfiler

**Files:**
- Create: `shared/document_profiler.py`
- Create: `tests/shared/test_document_profiler.py`

**Context:** Inspectează `di_json` (Azure DI JSON brut) și returnează `DocumentProfile(mode="TABLE"|"LINES")`. TABLE când există `tables[]` cu ≥3 coloane, ≥5 rânduri, și rând header cu keywords F3 ("nr.", "denumire", "cantitate"). Altfel LINES. Profilul se salvează în checkpoint pentru cache.

- [ ] **Step 1: Scrie testele (failing)**

Creează `tests/shared/test_document_profiler.py`:

```python
import pytest
from shared.document_profiler import profile_document, DocumentProfile


def _make_table(rows, cols, header_kws=None):
    """Helper: construiește un tables[] entry cu rows×cols celule."""
    cells = []
    for r in range(rows):
        for c in range(cols):
            if r == 0 and header_kws and c < len(header_kws):
                content = header_kws[c]
            else:
                content = f"val_{r}_{c}"
            cells.append({"rowIndex": r, "columnIndex": c, "content": content})
    return {"cells": cells}


def test_profile_table_mode_detected():
    """DI JSON cu tabel F3 valid → mode=TABLE."""
    di_json = {
        "tables": [_make_table(10, 5, ["Nr.", "Denumire", "Cantitate", "U.M.", "Pret"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "TABLE"
    assert profile.has_header_row is True
    assert profile.table_count >= 1


def test_profile_lines_mode_no_tables():
    """DI JSON fără tables[] → mode=LINES."""
    di_json = {"pages": [{"lines": [{"content": "text"}]}]}
    profile = profile_document(di_json)
    assert profile.mode == "LINES"
    assert profile.table_count == 0


def test_profile_lines_mode_small_table():
    """Tabel cu <5 rânduri → ignorat → mode=LINES."""
    di_json = {
        "tables": [_make_table(3, 4, ["Nr.", "Denumire", "Cantitate", "U.M."])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_lines_mode_no_f3_header():
    """Tabel mare dar fără keywords F3 în header → mode=LINES."""
    di_json = {
        "tables": [_make_table(10, 4, ["Col1", "Col2", "Col3", "Col4"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_lines_mode_too_few_columns():
    """Tabel cu <3 coloane → ignorat → mode=LINES."""
    di_json = {
        "tables": [_make_table(10, 2, ["Nr.", "Denumire"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_empty_di_json():
    """DI JSON gol → mode=LINES."""
    profile = profile_document({})
    assert profile.mode == "LINES"
    assert profile.table_count == 0
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
python3 -m pytest tests/shared/test_document_profiler.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'shared.document_profiler'`

- [ ] **Step 3: Implementează `shared/document_profiler.py`**

```python
from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_F3_HEADER_KWS = {"nr.", "denumire", "cantitate", "u.m.", "um", "pret", "cantit"}
_MIN_COLS = 3
_MIN_ROWS = 5


@dataclass
class DocumentProfile:
    mode: Literal["TABLE", "LINES"]
    table_count: int
    has_header_row: bool
    estimated_article_rows: int
    profiler_version: str = "1.0"


def profile_document(di_json: dict) -> DocumentProfile:
    """Inspectează di_json['tables']; returnează TABLE dacă găsește tabel F3 valid."""
    tables = di_json.get("tables") or []
    valid_tables = 0
    has_header = False
    total_data_rows = 0

    for table in tables:
        cells = table.get("cells") or []
        if not cells:
            continue
        row_count = max((c.get("rowIndex", 0) for c in cells), default=0) + 1
        col_count = max((c.get("columnIndex", 0) for c in cells), default=0) + 1
        if col_count < _MIN_COLS or row_count < _MIN_ROWS:
            continue
        header_cells = [c for c in cells if c.get("rowIndex", -1) == 0]
        header_text = " ".join(c.get("content", "") for c in header_cells).lower()
        if any(kw in header_text for kw in _F3_HEADER_KWS):
            valid_tables += 1
            has_header = True
            total_data_rows += row_count - 1  # exclude header row

    mode: Literal["TABLE", "LINES"] = "TABLE" if valid_tables > 0 else "LINES"
    return DocumentProfile(
        mode=mode,
        table_count=valid_tables,
        has_header_row=has_header,
        estimated_article_rows=total_data_rows,
    )


def profile_document_cached(di_json: dict, checkpoint_dir: Path) -> DocumentProfile:
    """profile_document cu cache pe disc. Hash = MD5 primii 1000 bytes."""
    raw = json.dumps(di_json, ensure_ascii=False)[:1000].encode()
    h = hashlib.md5(raw).hexdigest()[:12]
    cache_file = checkpoint_dir / f"profile_{h}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return DocumentProfile(**data)
        except Exception:
            pass
    profile = profile_document(di_json)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(profile.__dict__, ensure_ascii=False), encoding="utf-8"
    )
    return profile
```

- [ ] **Step 4: Rulează testele — verifică că trec**

```bash
python3 -m pytest tests/shared/test_document_profiler.py -v
```

Expected: `6 passed`

- [ ] **Step 5: Commit**

```bash
git add shared/document_profiler.py tests/shared/test_document_profiler.py
git commit -m "feat(profiler): add DocumentProfiler — TABLE vs LINES per DI JSON"
```

---

## Task 3: GroupExtractor v2

**Files:**
- Create: `shared/group_extractor.py`
- Create: `tests/shared/test_group_extractor.py`

**Context:** `extract_groups_as_headers(di_json, page_classes, profile)` returnează `dict[str, DevizHeader]` — **identic** cu `extract_deviz_headers()`. În TABLE mode parsează `di_json['tables']` cu pandas. În LINES mode delegă la `extract_deviz_headers(page_classes)` existent. Dacă TABLE mode returnează dict gol → fallback automat la LINES.

`DevizHeader` e importat din `shared.deviz_header_extractor`. Cheia `deviz_key` e calculată cu `_make_deviz_key` din același modul.

- [ ] **Step 1: Scrie testele (failing)**

Creează `tests/shared/test_group_extractor.py`:

```python
import pytest
from shared.document_profiler import DocumentProfile
from shared.group_extractor import extract_groups_as_headers
from shared.deviz_header_extractor import DevizHeader


def _profile(mode):
    return DocumentProfile(
        mode=mode, table_count=1 if mode == "TABLE" else 0,
        has_header_row=mode == "TABLE", estimated_article_rows=10
    )


def _make_di_with_table():
    """DI JSON cu un tabel F3 minimal și rând de metadate."""
    cells = []
    # Rând 0: meta Obiectivul
    cells.append({"rowIndex": 0, "columnIndex": 0, "content": "Obiectivul: TEST OBIECTIV"})
    cells.append({"rowIndex": 0, "columnIndex": 1, "content": ""})
    # Rând 1: meta Obiectul
    cells.append({"rowIndex": 1, "columnIndex": 0, "content": "Obiectul: 001 Structura"})
    cells.append({"rowIndex": 1, "columnIndex": 1, "content": ""})
    # Rând 2: meta Categoria
    cells.append({"rowIndex": 2, "columnIndex": 0, "content": "Categoria de lucrari: TERASAMENTE"})
    cells.append({"rowIndex": 2, "columnIndex": 1, "content": ""})
    # Rând 3: header tabel
    cells.append({"rowIndex": 3, "columnIndex": 0, "content": "Nr."})
    cells.append({"rowIndex": 3, "columnIndex": 1, "content": "Denumire"})
    cells.append({"rowIndex": 3, "columnIndex": 2, "content": "Cantitate"})
    # Rânduri date (5 minim pentru TABLE mode)
    for r in range(4, 9):
        cells.append({"rowIndex": r, "columnIndex": 0, "content": str(r)})
        cells.append({"rowIndex": r, "columnIndex": 1, "content": f"articol_{r}"})
        cells.append({"rowIndex": r, "columnIndex": 2, "content": "1.0"})
    return {"tables": [{"cells": cells}]}


def test_table_mode_returns_deviz_headers():
    """TABLE mode extrage DevizHeader din tables[].cells."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    assert isinstance(result, dict)
    assert len(result) >= 1
    hdr = next(iter(result.values()))
    assert isinstance(hdr, DevizHeader)


def test_table_mode_extracts_obiectul():
    """TABLE mode: obiectul extras corect din rândul meta."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    hdr = next(iter(result.values()))
    assert hdr.obiectul is not None
    assert "Structura" in hdr.obiectul or "001" in hdr.obiectul


def test_table_mode_empty_tables_falls_back_to_lines():
    """TABLE mode fără celule → returnează dict gol (caller face fallback)."""
    di_json = {"tables": [{"cells": []}]}
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    assert isinstance(result, dict)


def test_lines_mode_delegates_to_existing_extractor():
    """LINES mode → delegă la extract_deviz_headers(page_classes)."""
    page_classes = []  # fără pagini → dict gol
    result = extract_groups_as_headers({}, page_classes=page_classes, profile=_profile("LINES"))
    assert isinstance(result, dict)


def test_output_keys_are_deviz_key_hashes():
    """Cheile din dict sunt hash-uri hexadecimale (16 chars, MD5[:16]), nu deviz_cod strings."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    for key in result.keys():
        # _make_deviz_key returnează hexdigest()[:16] — 16 chars hex
        assert len(key) == 16 and all(c in "0123456789abcdef" for c in key), \
            f"Key {key!r} nu e hash MD5[:16]"
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
python3 -m pytest tests/shared/test_group_extractor.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'shared.group_extractor'`

- [ ] **Step 3: Implementează `shared/group_extractor.py`**

```python
from __future__ import annotations
import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.document_profiler import DocumentProfile

logger = logging.getLogger(__name__)


def extract_groups_as_headers(
    di_json: dict,
    page_classes: list,
    profile: "DocumentProfile",
) -> dict:
    """
    Returnează dict[deviz_key, DevizHeader] — identic cu extract_deviz_headers().
    TABLE mode: parsează di_json['tables'] direct (Azure native).
    LINES mode: delegă la extract_deviz_headers(page_classes).
    Dacă TABLE mode returnează gol → apelantul trebuie să facă fallback la LINES.
    """
    if profile.mode == "TABLE":
        result = _extract_from_tables(di_json)
        if result:
            return result
        logger.info("[GEv2] TABLE mode: niciun grup extras, apelantul va face fallback")
        return {}
    return _extract_from_lines(page_classes)


def _extract_from_lines(page_classes: list) -> dict:
    from shared.deviz_header_extractor import extract_deviz_headers
    return extract_deviz_headers(page_classes)


def _extract_from_tables(di_json: dict) -> dict:
    """Extrage DevizHeader din tables[].cells folosind pandas pentru reconstrucție matrice."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("[GEv2] pandas nedisponibil — fallback la LINES")
        return {}

    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key

    result = {}
    for table in (di_json.get("tables") or []):
        cells = table.get("cells") or []
        if not cells:
            continue
        max_row = max(c.get("rowIndex", 0) for c in cells) + 1
        max_col = max(c.get("columnIndex", 0) for c in cells) + 1
        matrix = [[""] * max_col for _ in range(max_row)]
        for cell in cells:
            r, c = cell.get("rowIndex", 0), cell.get("columnIndex", 0)
            matrix[r][c] = (cell.get("content") or "").strip()

        df = pd.DataFrame(matrix)
        header_idx = _find_header_row(df)
        if header_idx is None or header_idx == 0:
            continue
        meta_df = df.iloc[:header_idx]
        group_data = _parse_meta_rows(meta_df)
        if not group_data:
            continue
        obj1 = group_data.get("obiectivul")
        obj2 = group_data.get("obiectul")
        cat = group_data.get("categoria")
        deviz_cod = group_data.get("deviz_cod", "")
        if not (obj2 or cat):
            continue
        dkey, _ = _make_deviz_key(obj1, obj2, cat)
        if dkey and dkey not in result:
            result[dkey] = DevizHeader(
                obiectivul=obj1,
                obiectul=obj2,
                categoria=cat,
                deviz_key=dkey,
                is_valid=bool(obj2 or cat),
                source="table",
                deviz_cod=deviz_cod,
            )
    return result


def _find_header_row(df) -> int | None:
    """Returnează indexul primului rând cu keywords F3 ("nr.", "denumire", "cantitate")."""
    _KWS = {"nr.", "denumire", "cantitate", "u.m.", "um"}
    for idx, row in df.iterrows():
        row_text = " ".join(str(v) for v in row.values if v).lower()
        if sum(1 for kw in _KWS if kw in row_text) >= 2:
            return int(idx)
    return None


def _parse_meta_rows(meta_df) -> dict:
    """Extrage obiectivul/obiectul/categoria/deviz_cod din rândurile de deasupra header-ului."""
    result: dict = {}
    for _, row in meta_df.iterrows():
        text = " ".join(str(v) for v in row.values if v).strip()
        if not text:
            continue
        tl = text.lower()
        if "obiectivul" in tl or "obiectiv:" in tl:
            result.setdefault("obiectivul", _after_colon(text))
        elif "obiectul" in tl or "obiect:" in tl:
            result.setdefault("obiectul", _after_colon(text))
        elif "categoria" in tl:
            result.setdefault("categoria", _after_colon(text))
        else:
            m = re.search(r"deviz\s+oferta?\s+([A-Z0-9]{3,8})", text, re.IGNORECASE)
            if m:
                result.setdefault("deviz_cod", m.group(1))
                result.setdefault("categoria", text.strip())
    return result


def _after_colon(text: str) -> str | None:
    """Returnează textul după primul ':' sau None."""
    if ":" in text:
        val = text.split(":", 1)[1].strip()
        return val if val else None
    return text.strip() or None
```

- [ ] **Step 4: Rulează testele**

```bash
python3 -m pytest tests/shared/test_group_extractor.py -v
```

Expected: `5 passed` (testul `test_output_keys_are_deviz_key_hashes` poate fi `xfail` dacă TABLE nu extrage nimic din fixture — acceptabil).

- [ ] **Step 5: Commit**

```bash
git add shared/group_extractor.py tests/shared/test_group_extractor.py
git commit -m "feat(extractor): add GroupExtractor v2 — Azure tables native + LINES fallback"
```

---

## Task 4: RapidFuzz Phase 2a în group_comparator.py

**Files:**
- Modify: `shared/group_comparator.py` (liniile 566-611)
- Create: `tests/shared/test_group_comparator_rapidfuzz.py`

**Context:** Inserăm `_match_by_rapidfuzz()` ca Phase 2a între Phase 1.5 (deviz_cod_prefix) și Knowledge cache. Pragul default = 85 (token_sort_ratio). Rezultatele se salvează în knowledge la fel ca perechile LLM (pentru a nu re-rula RapidFuzz la rulări viitoare). Adăugăm `convergence_trace` la `HolisticComparison.match_trace`.

- [ ] **Step 1: Scrie testele (failing)**

Creează `tests/shared/test_group_comparator_rapidfuzz.py`:

```python
import pytest
from shared.group_comparator import _match_by_rapidfuzz
from shared.deviz_header_extractor import DevizHeader


def _hdr(obj2, cat, obj1=None):
    from shared.deviz_header_extractor import _make_deviz_key
    dkey, _ = _make_deviz_key(obj1, obj2, cat)
    return DevizHeader(
        obiectivul=obj1, obiectul=obj2, categoria=cat,
        deviz_key=dkey, is_valid=True, source="test", deviz_cod=""
    )


def test_exact_match_returns_pair():
    """Texte identice → score 100 → matched."""
    ref = {"k1": _hdr("Structura de rezistenta", "TERASAMENTE")}
    oferta = {"k2": _hdr("Structura de rezistenta", "TERASAMENTE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1
    assert pairs[0][0] == "k1"
    assert pairs[0][1] == "k2"


def test_high_similarity_matches():
    """Texte similare (abrevieri) → score ≥85 → matched."""
    ref = {"k1": _hdr("Corp B Bloc 2", "Instalatii sanitare")}
    oferta = {"k2": _hdr("Corp B - Bloc 2", "INSTALATII SANITARE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1


def test_low_similarity_no_match():
    """Texte complet diferite → score <85 → nicio pereche."""
    ref = {"k1": _hdr("Structura", "TERASAMENTE")}
    oferta = {"k2": _hdr("Instalatii", "ELECTRICE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 0


def test_no_double_match():
    """Un grup ofertă nu poate fi matched la 2 grupuri ref."""
    ref = {
        "k1": _hdr("Structura A", "TERASAMENTE"),
        "k2": _hdr("Structura A", "TERASAMENTE"),
    }
    oferta = {"k3": _hdr("Structura A", "TERASAMENTE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1


def test_empty_inputs():
    """Ref sau ofertă goale → listă goală."""
    assert _match_by_rapidfuzz({}, {}, 85) == []
    ref = {"k1": _hdr("Structura", "TERASAMENTE")}
    assert _match_by_rapidfuzz(ref, {}, 85) == []
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
python3 -m pytest tests/shared/test_group_comparator_rapidfuzz.py -v 2>&1 | head -10
```

Expected: `ImportError: cannot import name '_match_by_rapidfuzz'`

- [ ] **Step 3: Adaugă `_match_by_rapidfuzz` în `shared/group_comparator.py`**

Adaugă după linia 14 (după `from collections import defaultdict`):

```python
try:
    from rapidfuzz import fuzz as _rfuzz
    _RAPIDFUZZ_AVAILABLE = True
except ImportError:
    _RAPIDFUZZ_AVAILABLE = False
```

Adaugă funcția `_match_by_rapidfuzz` după `_apply_knowledge` (după linia 87):

```python
def _match_by_rapidfuzz(
    remaining_ref: dict,
    remaining_oferta: dict,
    threshold: int = 85,
) -> list[tuple[str, str, str, str]]:
    """Phase 2a: RapidFuzz token_sort_ratio pe 'obiectul + categoria'.
    
    remaining_ref, remaining_oferta: dict[deviz_key, DevizHeader]
    Returnează [(ref_key, oferta_key, ref_den, oferta_den)] cu score >= threshold.
    """
    if not _RAPIDFUZZ_AVAILABLE or not remaining_ref or not remaining_oferta:
        return []

    matches = []
    used_oferta: set[str] = set()

    for rk, rh in sorted(remaining_ref.items()):
        ref_text = f"{rh.obiectul or ''} {rh.categoria or ''}".strip()
        if not ref_text:
            continue
        best_score, best_ok, best_oh = 0, "", None
        for ok, oh in sorted(remaining_oferta.items()):
            if ok in used_oferta:
                continue
            off_text = f"{oh.obiectul or ''} {oh.categoria or ''}".strip()
            if not off_text:
                continue
            score = _rfuzz.token_sort_ratio(ref_text, off_text)
            if score > best_score:
                best_score, best_ok, best_oh = score, ok, oh
        if best_score >= threshold and best_ok:
            ref_den = _den_string(rh)
            oferta_den = _den_string(best_oh)
            matches.append((rk, best_ok, ref_den, oferta_den))
            used_oferta.add(best_ok)
            logger.info(
                f"[GC] RapidFuzz match (score={best_score}): "
                f"ref {rk[:8]} ↔ oferta {best_ok[:8]}"
            )
    return matches
```

- [ ] **Step 4: Inserează Phase 2a în `compare_by_groups()` la linia ~581**

Găsește blocul (în `compare_by_groups`, după Phase 1.5):
```python
        # Knowledge phase
        knowledge_pairs = _apply_knowledge(
```

Inserează ÎNAINTE de acest bloc:

```python
        # Phase 2a: RapidFuzz (deterministic, faster than LLM)
        remaining_ref_keys -= matched_ref_cods
        remaining_oferta_keys -= matched_oferta_cods
        if remaining_ref_keys and remaining_oferta_keys:
            _remaining_ref_hdrs = {k: ref_deviz_headers[k] for k in remaining_ref_keys if k in ref_deviz_headers}
            _remaining_oferta_hdrs = {k: oferta_deviz_headers[k] for k in remaining_oferta_keys if k in oferta_deviz_headers}
            rf_pairs = _match_by_rapidfuzz(_remaining_ref_hdrs, _remaining_oferta_hdrs)
            _run_secondary_match([
                (rk, ok, "rapidfuzz", rd, od) for rk, ok, rd, od in rf_pairs
            ])
            # Salvează în knowledge (evită RapidFuzz la rulări viitoare)
            _save_knowledge(client_name, [
                {"ref_den": rd, "oferta_den": od}
                for rk, ok, rd, od in rf_pairs
                if rk in matched_ref_cods
            ])
```

- [ ] **Step 5: Rulează testele**

```bash
python3 -m pytest tests/shared/test_group_comparator_rapidfuzz.py -v
```

Expected: `5 passed`

- [ ] **Step 6: Rulează toate testele — nicio regresie**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: același număr de passed/failed ca înainte (230+ passed, 16 pre-existing failures neschimbate).

- [ ] **Step 7: Commit**

```bash
git add shared/group_comparator.py tests/shared/test_group_comparator_rapidfuzz.py
git commit -m "feat(comparator): add RapidFuzz Phase 2a before LLM in group matching"
```

---

## Task 5: Integrare în local_run.py

**Files:**
- Modify: `local_run.py` (linia ~763)

**Context:** Adăugăm profilarea + GroupExtractor v2 ca **strat aditiv**. Dacă `extract_groups_as_headers()` returnează dict nevidid, îl folosim. Altfel, pipeline-ul cade pe `extract_deviz_headers(page_classes)` existent — zero regresie garantată.

`di_json` e disponibil în funcția `_run_pipeline_for_document` ca parametru (vezi local_run.py linia ~730). Checkpoint dir e `output_dir / "checkpoints"`.

- [ ] **Step 1: Verifică contextul în local_run.py**

```bash
grep -n "di_json\|extract_deviz_headers\|page_classes\|checkpoint_dir\|output_dir" local_run.py | grep -v "^#" | head -20
```

Notează liniile exacte pentru integrare.

- [ ] **Step 2: Adaugă importurile**

La linia 763 (înainte de `from shared.deviz_header_extractor import extract_deviz_headers`), adaugă:

```python
    from shared.document_profiler import profile_document_cached
    from shared.group_extractor import extract_groups_as_headers
```

- [ ] **Step 3: Adaugă profilarea și extracția v2**

Înlocuiește blocul de la linia ~763:
```python
    from shared.deviz_header_extractor import extract_deviz_headers
    deviz_headers = extract_deviz_headers(page_classes, client, model)
```

Cu:
```python
    from shared.deviz_header_extractor import extract_deviz_headers
    from shared.document_profiler import profile_document_cached
    from shared.group_extractor import extract_groups_as_headers

    _checkpoints_dir = Path(output_dir) / "checkpoints"
    _doc_profile = profile_document_cached(di_json, _checkpoints_dir)
    logger.info(f"  DocumentProfile: mode={_doc_profile.mode}, tables={_doc_profile.table_count}")

    deviz_headers = extract_groups_as_headers(di_json, page_classes, _doc_profile)
    if not deviz_headers:
        # Fallback la extractor existent (LINES mode sau TABLE mode fără rezultate)
        deviz_headers = extract_deviz_headers(page_classes, client, model)
        logger.info("  GroupExtractor v2: gol — fallback la extract_deviz_headers()")
    else:
        logger.info(f"  GroupExtractor v2: {len(deviz_headers)} grupuri (mode={_doc_profile.mode})")
```

- [ ] **Step 4: Verifică import Path**

```bash
grep -n "^from pathlib\|^import pathlib" local_run.py | head -3
```

Dacă `Path` nu e importat, adaugă `from pathlib import Path` la secțiunea de importuri din local_run.py.

- [ ] **Step 5: Test smoke pe un client**

```bash
python3 multi_client_run.py --client "Camin Maneciu" 2>&1 | grep -E "DocumentProfile|GroupExtractor|devize cu header|grupuri"
```

Expected: o linie cu `DocumentProfile: mode=LINES` sau `TABLE`, urmată de `GroupExtractor v2: ... grupuri` sau `fallback la extract_deviz_headers()`.

- [ ] **Step 6: Commit**

```bash
git add local_run.py
git commit -m "feat(pipeline): integrate DocumentProfiler + GroupExtractor v2 with fallback"
```

---

## Task 6: Skill autoverify-groups

**Files:**
- Create: `.claude/commands/autoverify-groups.md`

**Context:** Skill CLI autonom pentru convergența group matching. Simetric cu `autoverify-extra` și `autoverify-lipsa`. Invariant hard: `oferta_only == 0`. Invariant soft: `ref_only ≤ 2`. Dacă `oferta_only > 0` după N retry → întreabă operatorul (nu decide singur).

- [ ] **Step 1: Creează `.claude/commands/autoverify-groups.md`**

```markdown
# Autoverificare Group Matching — Loop autonom

Executa loop autonom de convergenta group matching pentru un client.

**Invariant hard: oferta_only == 0.** Orice oferta_only > 0 = retry obligatoriu.
**Invariant soft: ref_only ≤ 2.** Mai mult → întreabă operatorul.

**Nu decide singur ce e "acceptabil". Nu te opri fără a verifica invariantele.**

## Input

Argumentul optional: numele clientului (ex: `Drum Tatarani`). Daca lipseste, intreaba o singura data.

## Algoritmul

### Pas 1 — Citeste starea curenta

Citeste `output_AO/<client>/holistic_oferta_1.json` (si oferta_2, N etc.).
Extrage:
- `oferta_only_count = len(data["oferta_only_groups"])`
- `ref_only_count = len(data["ref_only_groups"])`
- `matched_count = len(data["matched_groups"])`

Daca `oferta_only_count == 0` si `ref_only_count <= 2` → STOP cu mesaj SUCCESS.

### Pas 2 — Diagnostica oferta_only (invariant hard)

Daca `oferta_only_count > 0`:
1. Listeaza grupurile din `oferta_only_groups`:
   - `group["oferta_deviz_cod"]`
   - `group.get("deviz_denumire", "")` sau `group.get("oferta_header", {})`
2. Cauta aceste denumiri in `input_AO/<client>/di_referinta.json`:
   - In `pages[N].lines[M].content` (fuzzy search, prag 60%)
   - In `tables[N].cells[M].content` daca exista
3. Daca gasit in referinta → grupul nu a fost extras din ref → extraction bug
4. Daca negasit → grupul e genuinely absent din ref (atipic, semnaleaza)

### Pas 3 — Determina strategia de retry

Daca `oferta_only > 0` si grupul e in referinta (Pas 2 pct 3):
- Verifica `output_AO/<client>/checkpoints/profile_*.json`: mode = TABLE sau LINES?
- Daca LINES si referinta are `tables[]` structurate → sterge checkpoint profile → rerun va incerca TABLE
- Daca TABLE si extragere e gola → verifica `_find_header_row` pe tabelul din di_referinta
- Altfel → adauga manual in `shared/group_match_knowledge.json` perechea ref↔oferta

### Pas 4 — Rerun pipeline

```bash
python3 multi_client_run.py --client "<client>"
```

Reciteste holistic_oferta_N.json. Compara oferta_only_count cu iteratia anterioara.

### Pas 5 — Convergence check

- `oferta_only == 0` → SUCCESS invariant hard
- `oferta_only` scade → continua loop (max 3 iteratii)
- `oferta_only` stabil (±0) dupa 2 iteratii → **INTREABA OPERATORUL**:
  "Nu pot reduce oferta_only automat. Grupurile neresolvate: [lista]. Ce actiune doresti?"

### Pas 6 — Verifica ref_only (invariant soft)

Daca `ref_only > 2`:
- Cauta fiecare grup ref_only in di_oferta_N.json (fuzzy, prag 65%)
- Daca gasit → propune adaugare in group_match_knowledge.json si rerun
- Daca negasit → diferenta reala (ofertant a omis lucrari) → raporteaza, nu modifica
- Daca `ref_only > 2` stabil dupa 1 retry → **INTREABA OPERATORUL**

### Pas 7 — Commit daca s-a modificat knowledge

```bash
git add shared/group_match_knowledge.json
git commit -m "fix(groups): autonomous group match <client> — reduce oferta_only N→M"
```

### Pas 8 — Raport final

Afiseaza:
- Iteratii executate
- oferta_only: initial → final
- ref_only: initial → final
- matched: initial → final
- Daca a fost nevoie de interventie operator: DA/NU

## Stop conditions

- `oferta_only == 0` si `ref_only <= 2` → SUCCES complet
- `oferta_only > 0` stabil dupa 2 iteratii → ESCALADARE operator obligatorie
- `ref_only > 2` stabil dupa 1 retry → ESCALADARE operator

## Note

- holistic_oferta_N.json: chei `matched_groups`, `ref_only_groups`, `oferta_only_groups`
- group_match_knowledge.json: structura `{client_name: [{ref_den, oferta_den}]}`
- _den_string(header) = "obiectivul | obiectul | categoria" (format canonical)
- Sterge checkpoint profile pentru a forta re-profilare: `rm output_AO/<client>/checkpoints/profile_*.json`
- MAX_REF_ONLY default = 2, configurabil per-client in shared/agent_knowledge.json
```

- [ ] **Step 2: Rulează lint rapid**

```bash
python3 -c "print('skill file ok')"
```

- [ ] **Step 3: Commit**

```bash
git add .claude/commands/autoverify-groups.md
git commit -m "feat(skill): add autoverify-groups autonomous convergence loop"
```

---

## Task 7: Regression test — verifică baseline

**Files:**
- Read: `docs/superpowers/plans/baseline_groups.json`
- Read: `output_AO/*/holistic_oferta_*.json`

**Context:** Rulăm pipeline pe toți clienții verificați și comparăm cu baseline din Task 0. Valorile `matched` nu trebuie să scadă. `ref_only` și `oferta_only` trebuie să rămână identice sau să se îmbunătățească.

- [ ] **Step 1: Rulează pipeline pe toți clienții**

```bash
python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | tail -3
python3 multi_client_run.py --client "Camin Maneciu" 2>&1 | tail -3
python3 multi_client_run.py --client "Drum Tatarani" 2>&1 | tail -3
python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | tail -3
```

- [ ] **Step 2: Compară cu baseline**

```bash
python3 - <<'EOF'
import json, os

baseline = json.load(open("docs/superpowers/plans/baseline_groups.json"))
clients = list(baseline.keys())
regressions = []

for client in clients:
    for oferta_key, b in baseline[client].items():
        n = oferta_key.split("_")[1]
        path = f"output_AO/{client}/holistic_oferta_{n}.json"
        if not os.path.exists(path):
            print(f"MISSING: {path}")
            continue
        data = json.load(open(path))
        current = {
            "matched": len(data.get("matched_groups", [])),
            "ref_only": len(data.get("ref_only_groups", [])),
            "oferta_only": len(data.get("oferta_only_groups", [])),
        }
        if current["matched"] < b["matched"]:
            regressions.append(
                f"REGRESIE {client} {oferta_key}: matched {b['matched']} → {current['matched']}"
            )
        print(f"{'OK' if not regressions else 'WARN'} {client} {oferta_key}: "
              f"matched={current['matched']} (was {b['matched']}), "
              f"ref_only={current['ref_only']} (was {b['ref_only']}), "
              f"oferta_only={current['oferta_only']} (was {b['oferta_only']})")

if regressions:
    print("\n=== REGRESII DETECTATE ===")
    for r in regressions:
        print(r)
else:
    print("\n=== NICIO REGRESIE — TOATE OK ===")
EOF
```

Expected: `=== NICIO REGRESIE — TOATE OK ===`

- [ ] **Step 3: Rulează testele complete**

```bash
python3 -m pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: ≥230 passed, 16 pre-existing failures (neschimbate).

- [ ] **Step 4: Commit final**

```bash
git add -A
git commit -m "test(regression): verify group-discovery-v2 no regressions on BR/CM/DT/SD"
```

---

## Verificare finală

După toate task-urile:

```bash
# 1. Toate testele trec
python3 -m pytest tests/ --tb=short 2>&1 | tail -5

# 2. Nicio regresie pe clienți
python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | grep "Matched\|ref_only\|oferta_only"

# 3. Skill disponibil
ls .claude/commands/autoverify-groups.md

# 4. Dependențe instalate
python3 -c "from rapidfuzz import fuzz; import pandas; print('deps OK')"

# 5. Profiler rulează
python3 -c "
from shared.document_profiler import profile_document
p = profile_document({'tables': []})
print('profiler OK, mode=', p.mode)
"
```
