# Holistic Group-Based Comparison — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace article-level matching with group-level analysis: every article belongs to a deviz group (OBIECTIVUL + Obiectul + Categoria); groups are matched 3-layer ref↔oferta; unmatched ref groups = LIPSA, unmatched oferta groups = EXTRA, ungrouped articles = "probleme ciudate".

**Architecture:** New `shared/group_comparator.py` owns the full holistic comparison logic. It uses existing `match_devize_by_3layer()` for group matching and `match_global()` for article-level comparison within matched group pairs. New `build_raport_holistic()` in `report_builder.py` and `_generate_word_holistic()` in `report_word.py` render the result. `compare_and_report()` in `local_run.py` switches to the holistic flow.

**Tech Stack:** Python 3.11, dataclasses, python-docx, existing match_global + 3-layer infrastructure

**Branch:** `refactor/v10`

**Domain context:**
- Deviz group = {OBIECTIVUL (project), Obiectul (sub-object/building), Categoria (work category)}
- Every article MUST belong to a deviz group (deviz_cod field). Articles without group → "ungrouped".
- Ref group ↔ Oferta group match = same 3-layer content (similarity ≥ 0.75, per-layer: obj2≥0.85, cat≥0.90)
- Ref group NO oferta match → all its articles = ARTICOL_LIPSA
- Oferta group NO ref match → all its articles = ARTICOL_EXTRA
- Matched group pair → run existing article-level match_global() within the pair
- Prices are NOT included in article metadata for this report

**Key existing code:**
- `shared/deviz_matcher.py::match_devize_by_3layer(ref_dh, oferta_dh)` → `{oferta_cod → ref_cod}` — REUSE
- `AgentComparator_local.py::match_global(ref_arts, oferta_arts, client, model)` → `(neconformitati, matches, matched_keys, fara_deviz)` — REUSE per matched group
- `shared/deviz_header_extractor.py::_headers_from_articles(arts)` → `{deviz_cod → DevizHeader}` — REUSE (available via local_run.py helper)
- `shared/report_word.py::_add_deviz_heading()`, `_add_neconf_row()` — REUSE as helpers

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `shared/group_comparator.py` | CREATE | GroupMatchResult, HolisticComparison, compare_by_groups() |
| `tests/test_group_comparator.py` | CREATE | Unit tests for group comparison logic |
| `shared/report_builder.py` | MODIFY | Add build_raport_holistic() |
| `shared/report_word.py` | MODIFY | Add _generate_word_holistic(), _add_group_heading() |
| `local_run.py` | MODIFY | compare_and_report() uses holistic flow |

---

## Task 1: `shared/group_comparator.py` — core logic

**Files:**
- Create: `shared/group_comparator.py`
- Create: `tests/test_group_comparator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_group_comparator.py
import pytest
from shared.group_comparator import compare_by_groups, GroupMatchResult, HolisticComparison


def _make_article(cod, deviz, deviz_header=None, cantitate=1.0, um="mp", denumire="test"):
    art = {
        "cod": cod, "deviz": deviz, "cantitate": cantitate, "um": um,
        "denumire": denumire, "is_component": False, "parent_cod": "",
        "deviz_key": f"key_{deviz}", "source_pages": [],
    }
    if deviz_header:
        art["deviz_header"] = deviz_header
    else:
        art["deviz_header"] = {"obiectivul": "Proiect A", "obiectul": f"Obiect {deviz}", "categoria": f"Cat {deviz}"}
    return art


def _make_header(obj1, obj2, cat, deviz_cod=""):
    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key
    key, valid = _make_deviz_key(obj1, obj2, cat)
    return DevizHeader(obj1, obj2, cat, key, valid, "test", deviz_cod)


def test_matched_groups_basic():
    """Ref si oferta cu acelasi grup → matched."""
    ref_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    oferta_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    ref_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    oferta_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}

    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)

    assert isinstance(result, HolisticComparison)
    assert len(result.matched_groups) == 1
    assert len(result.ref_only_groups) == 0
    assert len(result.oferta_only_groups) == 0
    mg = result.matched_groups[0]
    assert mg["ref_deviz_cod"] == "D1"
    assert mg["oferta_deviz_cod"] == "D1"


def test_ref_only_group_all_lipsa():
    """Ref grup fara corespondent oferta → toate articolele LIPSA."""
    ref_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    oferta_arts = []
    ref_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    oferta_dh = {}

    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)

    assert len(result.ref_only_groups) == 1
    rg = result.ref_only_groups[0]
    assert rg["ref_deviz_cod"] == "D1"
    assert len(rg["neconformitati"]) == 2  # ambele articole = LIPSA
    assert all(n["tip"] == "ARTICOL_LIPSA" for n in rg["neconformitati"])


def test_oferta_only_group_all_extra():
    """Oferta grup fara corespondent ref → toate articolele EXTRA."""
    ref_arts = []
    oferta_arts = [_make_article("EA02A1", "D2"), _make_article("CA01A", "D2")]
    ref_dh = {}
    oferta_dh = {"D2": _make_header("Proiect B", "Obiect D2", "Cat D2", "D2")}

    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)

    assert len(result.oferta_only_groups) == 1
    og = result.oferta_only_groups[0]
    assert og["oferta_deviz_cod"] == "D2"
    assert len(og["neconformitati"]) == 2  # ambele articole = EXTRA
    assert all(n["tip"] == "ARTICOL_EXTRA" for n in og["neconformitati"])


def test_ungrouped_articles():
    """Articole fara deviz → ungrouped."""
    art_no_deviz = {"cod": "XX01A", "deviz": "", "cantitate": 1.0, "is_component": False}
    result = compare_by_groups([art_no_deviz], [], {}, {})
    assert len(result.ungrouped) > 0
    assert any(a["cod"] == "XX01A" for a in result.ungrouped)


def test_group_match_different_codes_same_content():
    """Ref D1 si Oferta D2 cu acelasi 3-layer content → matched + remaped."""
    ref_arts = [_make_article("EA02A1", "D1")]
    oferta_arts = [_make_article("EA02A1", "D2")]
    ref_dh = {"D1": _make_header("Proiect A", "Organizare Santier", "BLC1 Organizare", "D1")}
    oferta_dh = {"D2": _make_header("Proiect A", "003 Organizare Santier", "001 BLC1 Organizare", "D2")}

    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)

    # Should match D1(ref) ↔ D2(oferta) via 3-layer similarity
    assert len(result.matched_groups) == 1
    mg = result.matched_groups[0]
    assert mg["ref_deviz_cod"] == "D1"
    assert mg["oferta_deviz_cod"] == "D2"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v 2>&1 | head -10
```
Expected: `ImportError: cannot import name 'compare_by_groups'`

- [ ] **Step 3: Create `shared/group_comparator.py`**

```python
# shared/group_comparator.py
"""
Holistic group-based comparison.

Every article belongs to a deviz group (OBIECTIVUL + Obiectul + Categoria).
Groups are matched 3-layer ref↔oferta. Unmatched ref groups → LIPSA.
Unmatched oferta groups → EXTRA. Ungrouped articles → probleme ciudate.
"""
import logging
from dataclasses import dataclass, field
from collections import defaultdict

logger = logging.getLogger(__name__)


@dataclass
class HolisticComparison:
    matched_groups: list = field(default_factory=list)
    # Each: {ref_deviz_cod, oferta_deviz_cod, ref_header, oferta_header,
    #        neconformitati, matches, ref_articles, oferta_articles}
    ref_only_groups: list = field(default_factory=list)
    # Each: {ref_deviz_cod, ref_header, articles, neconformitati (all LIPSA)}
    oferta_only_groups: list = field(default_factory=list)
    # Each: {oferta_deviz_cod, oferta_header, articles, neconformitati (all EXTRA)}
    ungrouped: list = field(default_factory=list)
    # Articles with no deviz (neither ref nor oferta)


def _articles_by_deviz(articles: list) -> dict:
    """Group articles by deviz_cod."""
    result = defaultdict(list)
    for a in articles:
        cod = (a.get("deviz") or "").strip()
        if cod:
            result[cod].append(a)
    return dict(result)


def _lipsa_neconf(art: dict, deviz_cod: str, deviz_den: str = "") -> dict:
    return {
        "tip": "ARTICOL_LIPSA",
        "deviz_ref": deviz_cod,
        "deviz_denumire": deviz_den,
        "ref_cod": art.get("cod", ""),
        "ref_denumire": art.get("denumire", ""),
        "ref_um": art.get("um", ""),
        "ref_cantitate": art.get("cantitate", 0),
        "nr_ordine_ref": art.get("nr_ordine", 0),
        "oferta_cod": "", "oferta_denumire": "", "oferta_um": "", "oferta_cantitate": "",
    }


def _extra_neconf(art: dict, ref_deviz_cod: str = "", deviz_den: str = "") -> dict:
    return {
        "tip": "ARTICOL_EXTRA",
        "deviz_ref": ref_deviz_cod,
        "deviz_denumire": deviz_den,
        "oferta_cod": art.get("cod", ""),
        "oferta_denumire": art.get("denumire", ""),
        "oferta_um": art.get("um", ""),
        "oferta_cantitate": art.get("cantitate", 0),
        "ref_cod": "", "ref_denumire": "", "ref_um": "", "ref_cantitate": "",
    }


def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
) -> HolisticComparison:
    """
    Holistic group-based comparison.

    Args:
        ref_articles: articles from reference
        oferta_articles: articles from offer
        ref_deviz_headers: {deviz_cod → DevizHeader} for reference
        oferta_deviz_headers: {deviz_cod → DevizHeader} for offer
        llm_client: Anthropic client (for article-level LLM matching within groups)
        llm_model: model name

    Returns:
        HolisticComparison with matched_groups, ref_only_groups, oferta_only_groups, ungrouped
    """
    from shared.deviz_matcher import match_devize_by_3layer

    result = HolisticComparison()

    # Collect ungrouped articles
    ungrouped_ref = [a for a in ref_articles if not (a.get("deviz") or "").strip()]
    ungrouped_oferta = [a for a in oferta_articles if not (a.get("deviz") or "").strip()]
    result.ungrouped = [{"source": "ref", **a} for a in ungrouped_ref] + \
                       [{"source": "oferta", **a} for a in ungrouped_oferta]

    # Only process articles with deviz
    ref_valid = [a for a in ref_articles if (a.get("deviz") or "").strip()]
    oferta_valid = [a for a in oferta_articles if (a.get("deviz") or "").strip()]

    ref_by_deviz = _articles_by_deviz(ref_valid)
    oferta_by_deviz = _articles_by_deviz(oferta_valid)

    # 3-layer group matching: {oferta_deviz_cod → ref_deviz_cod}
    group_mapping = match_devize_by_3layer(ref_deviz_headers, oferta_deviz_headers)

    # Determine matched pairs (including same-code matches)
    ref_cods = set(ref_by_deviz.keys())
    oferta_cods = set(oferta_by_deviz.keys())

    # Build complete mapping: oferta → ref
    full_mapping: dict[str, str] = {}
    for oferta_cod in oferta_cods:
        if oferta_cod in group_mapping:
            full_mapping[oferta_cod] = group_mapping[oferta_cod]
        elif oferta_cod in ref_cods:
            full_mapping[oferta_cod] = oferta_cod  # same code

    # Matched group pairs
    matched_ref_cods = set()
    matched_oferta_cods = set()

    for oferta_cod, ref_cod in sorted(full_mapping.items()):
        if ref_cod in matched_ref_cods:
            continue  # ref already matched
        ref_arts = ref_by_deviz.get(ref_cod, [])
        of_arts = oferta_by_deviz.get(oferta_cod, [])

        # Article-level comparison within matched group
        ncs, matches = _compare_articles_in_group(
            ref_arts, of_arts, ref_cod, llm_client, llm_model
        )

        result.matched_groups.append({
            "ref_deviz_cod": ref_cod,
            "oferta_deviz_cod": oferta_cod,
            "ref_header": ref_deviz_headers.get(ref_cod),
            "oferta_header": oferta_deviz_headers.get(oferta_cod),
            "ref_articles": ref_arts,
            "oferta_articles": of_arts,
            "neconformitati": ncs,
            "matches": matches,
        })
        matched_ref_cods.add(ref_cod)
        matched_oferta_cods.add(oferta_cod)
        logger.info(f"[GC] Matched: ref {ref_cod} ↔ oferta {oferta_cod} "
                    f"({len(ref_arts)} ref arts, {len(of_arts)} oferta arts)")

    # Ref-only groups (no oferta match) → all articles LIPSA
    for ref_cod in sorted(ref_cods - matched_ref_cods):
        arts = ref_by_deviz.get(ref_cod, [])
        header = ref_deviz_headers.get(ref_cod)
        deviz_den = arts[0].get("deviz_denumire", "") if arts else ""
        ncs = [_lipsa_neconf(a, ref_cod, deviz_den) for a in arts
               if a.get("cantitate")]  # skip zero-qty
        result.ref_only_groups.append({
            "ref_deviz_cod": ref_cod,
            "ref_header": header,
            "articles": arts,
            "neconformitati": ncs,
        })
        logger.info(f"[GC] Ref-only: {ref_cod} ({len(ncs)} LIPSA)")

    # Oferta-only groups (no ref match) → all articles EXTRA
    for oferta_cod in sorted(oferta_cods - matched_oferta_cods):
        arts = oferta_by_deviz.get(oferta_cod, [])
        header = oferta_deviz_headers.get(oferta_cod)
        deviz_den = arts[0].get("deviz_denumire", "") if arts else ""
        ncs = [_extra_neconf(a, "", deviz_den) for a in arts
               if a.get("cantitate")]
        result.oferta_only_groups.append({
            "oferta_deviz_cod": oferta_cod,
            "oferta_header": header,
            "articles": arts,
            "neconformitati": ncs,
        })
        logger.info(f"[GC] Oferta-only: {oferta_cod} ({len(ncs)} EXTRA)")

    logger.info(
        f"[GC] Groups: {len(result.matched_groups)} matched, "
        f"{len(result.ref_only_groups)} ref-only, "
        f"{len(result.oferta_only_groups)} oferta-only, "
        f"{len(result.ungrouped)} ungrouped articles"
    )
    return result


def _compare_articles_in_group(
    ref_arts: list,
    oferta_arts: list,
    deviz_cod: str,
    llm_client,
    llm_model: str,
) -> tuple[list, list]:
    """
    Article-level comparison within a matched group pair.
    Uses existing match_global() but scoped to this group's articles.
    Returns (neconformitati, matches).
    """
    if not ref_arts and not oferta_arts:
        return [], []
    if not ref_arts:
        ncs = [_extra_neconf(a, deviz_cod) for a in oferta_arts if a.get("cantitate")]
        return ncs, []
    if not oferta_arts:
        ncs = [_lipsa_neconf(a, deviz_cod) for a in ref_arts if a.get("cantitate")]
        return ncs, []

    from AgentComparator_local import match_global
    ncs, matches, _, _ = match_global(
        ref_arts, oferta_arts, llm_client, llm_model or "", include_prices=False
    )
    return ncs, matches
```

- [ ] **Step 4: Run all tests**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v 2>&1 | tail -15
```
Expected: 5/5 PASS

- [ ] **Step 5: Commit**

```bash
git add shared/group_comparator.py tests/test_group_comparator.py
git commit -m "feat(group-comparator): holistic group-based comparison logic"
```

---

## Task 2: `shared/report_builder.py` — `build_raport_holistic()`

**Files:**
- Modify: `shared/report_builder.py` — add `build_raport_holistic()` after existing function

**Context:** `build_raport_ierarhic()` at line 5 returns `{sumar, devize, erori_extractie, articole_nelocalizate}`. New `build_raport_holistic()` returns a different structure suited for holistic report.

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_group_comparator.py
def test_build_raport_holistic_structure():
    """build_raport_holistic() returneaza structura corecta."""
    from shared.group_comparator import HolisticComparison
    from shared.report_builder import build_raport_holistic

    hc = HolisticComparison(
        matched_groups=[{
            "ref_deviz_cod": "D1", "oferta_deviz_cod": "D1",
            "ref_header": None, "oferta_header": None,
            "ref_articles": [{"cod": "EA02A1", "deviz": "D1", "cantitate": 1.0,
                               "denumire": "test", "um": "mp", "is_component": False,
                               "nr_ordine": 1, "parent_cod": ""}],
            "oferta_articles": [],
            "neconformitati": [{"tip": "ARTICOL_LIPSA", "ref_cod": "EA02A1",
                                "deviz_ref": "D1", "deviz_denumire": ""}],
            "matches": [],
        }],
        ref_only_groups=[],
        oferta_only_groups=[{
            "oferta_deviz_cod": "D2", "oferta_header": None,
            "articles": [{"cod": "CB01A", "deviz": "D2", "cantitate": 5.0,
                          "denumire": "extra", "um": "mc", "is_component": False,
                          "nr_ordine": 1, "parent_cod": ""}],
            "neconformitati": [{"tip": "ARTICOL_EXTRA", "oferta_cod": "CB01A",
                                "deviz_ref": "", "deviz_denumire": ""}],
        }],
        ungrouped=[{"source": "ref", "cod": "??", "deviz": ""}],
    )

    raport = build_raport_holistic(hc)

    assert "matched_groups" in raport
    assert "ref_only_groups" in raport
    assert "oferta_only_groups" in raport
    assert "ungrouped" in raport
    assert "sumar" in raport
    assert raport["sumar"]["total_matched_groups"] == 1
    assert raport["sumar"]["total_ref_only_groups"] == 0
    assert raport["sumar"]["total_oferta_only_groups"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_build_raport_holistic_structure -v 2>&1 | tail -5
```
Expected: `ImportError: cannot import name 'build_raport_holistic'`

- [ ] **Step 3: Add `build_raport_holistic()` to `shared/report_builder.py`**

Append after existing `build_raport_ierarhic()`:

```python
def build_raport_holistic(holistic_comparison) -> dict:
    """
    Build holistic report structure from HolisticComparison.

    Returns dict with:
      matched_groups: list of {ref_deviz_cod, oferta_deviz_cod, ref_header, oferta_header,
                                ref_articles, oferta_articles, neconformitati, matches}
      ref_only_groups: list of {ref_deviz_cod, ref_header, articles, neconformitati}
      oferta_only_groups: list of {oferta_deviz_cod, oferta_header, articles, neconformitati}
      ungrouped: list of articles
      sumar: counts
    """
    from collections import Counter

    all_ncs = []
    for mg in holistic_comparison.matched_groups:
        all_ncs.extend(mg.get("neconformitati", []))
    for rg in holistic_comparison.ref_only_groups:
        all_ncs.extend(rg.get("neconformitati", []))
    for og in holistic_comparison.oferta_only_groups:
        all_ncs.extend(og.get("neconformitati", []))

    tips = Counter(n.get("tip", "") for n in all_ncs)
    total_matched_arts = sum(
        len(mg.get("matches", [])) for mg in holistic_comparison.matched_groups
    )

    return {
        "matched_groups": holistic_comparison.matched_groups,
        "ref_only_groups": holistic_comparison.ref_only_groups,
        "oferta_only_groups": holistic_comparison.oferta_only_groups,
        "ungrouped": holistic_comparison.ungrouped,
        "sumar": {
            "total_matched_groups": len(holistic_comparison.matched_groups),
            "total_ref_only_groups": len(holistic_comparison.ref_only_groups),
            "total_oferta_only_groups": len(holistic_comparison.oferta_only_groups),
            "total_ungrouped_articles": len(holistic_comparison.ungrouped),
            "total_matched_articles": total_matched_arts,
            "neconformitati_by_tip": dict(tips),
        },
    }
```

- [ ] **Step 4: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v 2>&1 | tail -10
```
Expected: 6/6 PASS

- [ ] **Step 5: Commit**

```bash
git add shared/report_builder.py tests/test_group_comparator.py
git commit -m "feat(report-builder): build_raport_holistic() for group-based report"
```

---

## Task 3: `shared/report_word.py` — holistic Word report

**Files:**
- Modify: `shared/report_word.py` — add `_add_group_heading()` + `_generate_word_holistic()` + update `generate_word()`

**Context:**
- `_add_deviz_heading(table, deviz_cod, deviz_den, ref_count, oferta_count, ref_pages, oferta_pages)` at line 196 — REUSE
- `_add_neconf_row(table, row_nr, neconf, deviz_map, ...)` at line 373 — REUSE
- `generate_word(raport_ierarhic, ...)` at line ~895 — ADD holistic_raport param
- `_build_header(table, ofertant_name)` at line 292 — REUSE

- [ ] **Step 1: Write failing test**

```python
# Adauga in tests/test_report_word.py
def test_generate_word_holistic_runs():
    """generate_word cu holistic_raport nu crapa."""
    from shared.report_word import generate_word
    from shared.group_comparator import HolisticComparison
    from shared.report_builder import build_raport_holistic

    hc = HolisticComparison(
        matched_groups=[{
            "ref_deviz_cod": "D1", "oferta_deviz_cod": "D1",
            "ref_header": None, "oferta_header": None,
            "ref_articles": [], "oferta_articles": [],
            "neconformitati": [], "matches": [],
        }],
        ref_only_groups=[],
        oferta_only_groups=[],
        ungrouped=[],
    )
    raport_holistic = build_raport_holistic(hc)
    raport_ierarhic = {"devize": [], "sumar": {}, "erori_extractie": [],
                       "articole_nelocalizate": []}

    # Should not raise
    doc_bytes = generate_word(
        raport_ierarhic,
        comp={"matches": 0, "neconformitati": [], "total_neconformitati": 0},
        holistic_raport=raport_holistic,
    )
    assert doc_bytes is not None and len(doc_bytes) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py::test_generate_word_holistic_runs -v 2>&1 | tail -5
```
Expected: FAIL — `generate_word()` doesn't accept `holistic_raport` param yet.

- [ ] **Step 3: Add `_add_group_heading()` to `shared/report_word.py`** before `_add_deviz_heading()`

```python
def _add_group_heading(table, group_type: str, ref_header, oferta_header,
                       ref_deviz_cod: str = "", oferta_deviz_cod: str = "") -> None:
    """
    Adauga un rand separator de grup cu informatii 3-layer.
    group_type: 'matched' | 'ref_only' | 'oferta_only'
    """
    sep_cells = table.add_row().cells
    sep_cells[0].merge(sep_cells[10])

    header = ref_header or oferta_header
    if header:
        obj1 = (header.obiectivul or "")[:60]
        obj2 = (header.obiectul or "")[:60]
        cat = (header.categoria or "")[:60]
        label = f"OBIECTIVUL: {obj1} | Obiectul: {obj2} | Categoria: {cat}"
    else:
        label = f"Deviz: {ref_deviz_cod or oferta_deviz_cod}"

    if group_type == "ref_only":
        label = f"[GRUP ABSENT DIN OFERTA] {label}"
        fill = "FFB3B3"  # light red
    elif group_type == "oferta_only":
        label = f"[GRUP ABSENT DIN REFERINTA] {label}"
        fill = "FFE0B3"  # light orange
    else:
        fill = GRAY_FILL

    run = sep_cells[0].paragraphs[0].add_run(label)
    run.bold = True
    _style_cell(sep_cells[0], 8, bold=True)
    _set_cell_shading(sep_cells[0], fill)
```

- [ ] **Step 4: Add `_generate_word_holistic()` to `shared/report_word.py`** after `_generate_word_hierarchical()`

```python
def _generate_word_holistic(doc, raport_holistic: dict, comp: dict,
                             deviz_map: dict, subcomponent_mode: str = "full") -> None:
    """
    Genereaza continut Word in structura holistica (group-based).

    Sectiuni:
    1. Grupuri matchate (ref ↔ oferta) cu neconformitatile lor
    2. Grupuri doar in referinta (toate articolele = LIPSA)
    3. Grupuri doar in oferta (toate articolele = EXTRA)
    4. Articole fara grup (probleme ciudate)
    """
    table = doc.add_table(rows=0, cols=11)
    table.style = "Table Grid"
    _set_col_widths(table)
    _build_header(table, comp.get("ofertant_name", ""))

    row_nr = 0

    # --- Sectiunea 1: Grupuri matchate ---
    for mg in raport_holistic.get("matched_groups", []):
        ref_h = mg.get("ref_header")
        of_h = mg.get("oferta_header")
        _add_group_heading(table, "matched", ref_h, of_h,
                           mg.get("ref_deviz_cod", ""), mg.get("oferta_deviz_cod", ""))

        ncs = mg.get("neconformitati", [])
        suppressed = SUPPRESSED_BY_MODE.get(subcomponent_mode, frozenset())

        def _visible(ncs_list):
            if not suppressed:
                return ncs_list
            return [n for n in ncs_list if n.get("tip") not in suppressed]

        visible_ncs = _visible(ncs)
        for nc in visible_ncs:
            row_nr += 1
            _add_neconf_row(table, row_nr, nc, deviz_map)

        if not visible_ncs:
            # Grup matched fara neconformitati — rand informativ
            row_cells = table.add_row().cells
            row_cells[0].paragraphs[0].add_run("✓ Grup conforme").italic = True
            _style_cell(row_cells[0], 8)

    # --- Sectiunea 2: Grupuri ref-only (LIPSA) ---
    for rg in raport_holistic.get("ref_only_groups", []):
        _add_group_heading(table, "ref_only", rg.get("ref_header"), None,
                           ref_deviz_cod=rg.get("ref_deviz_cod", ""))
        for nc in rg.get("neconformitati", []):
            row_nr += 1
            _add_neconf_row(table, row_nr, nc, deviz_map)

    # --- Sectiunea 3: Grupuri oferta-only (EXTRA) ---
    for og in raport_holistic.get("oferta_only_groups", []):
        _add_group_heading(table, "oferta_only", None, og.get("oferta_header"),
                           oferta_deviz_cod=og.get("oferta_deviz_cod", ""))
        for nc in og.get("neconformitati", []):
            row_nr += 1
            _add_neconf_row(table, row_nr, nc, deviz_map)

    # --- Sectiunea 4: Articole fara grup ---
    ungrouped = raport_holistic.get("ungrouped", [])
    if ungrouped:
        sep = table.add_row().cells
        sep[0].merge(sep[10])
        run = sep[0].paragraphs[0].add_run(
            f"[ARTICOLE FARA GRUP — {len(ungrouped)} articole fara deviz detectat]"
        )
        run.bold = True
        _style_cell(sep[0], 8, bold=True)
        _set_cell_shading(sep[0], "FFCCFF")  # light purple
```

- [ ] **Step 5: Update `generate_word()` to accept `holistic_raport` param**

Find `def generate_word(` in `shared/report_word.py` (around line 895). Add `holistic_raport: dict = None` param and branch:

```python
def generate_word(
    raport_ierarhic: dict,
    comp: dict = None,
    ...,  # existing params unchanged
    holistic_raport: dict = None,  # NOU
    subcomponent_mode: str = "full",
) -> bytes:
    ...
    # After existing header generation and before main content:
    if holistic_raport is not None:
        _generate_word_holistic(doc, holistic_raport, comp or {},
                                deviz_map, subcomponent_mode)
    else:
        _generate_word_hierarchical(doc, raport_ierarhic, comp or {},
                                    deviz_map, subcomponent_mode)
    ...
```

**IMPORTANT:** The branch goes INSIDE the existing `generate_word()` body, after document setup (header, cover page) but before the main content section. Find the call to `_generate_word_hierarchical(doc, ...)` and replace it with the if/else.

- [ ] **Step 6: Run tests**

```bash
.venv/bin/python3 -m pytest tests/test_report_word.py tests/test_group_comparator.py -v 2>&1 | tail -15
```
Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add shared/report_word.py tests/test_report_word.py
git commit -m "feat(report-word): holistic group-based Word report (_generate_word_holistic)"
```

---

## Task 4: `local_run.py` — pipeline integration

**Files:**
- Modify: `local_run.py:862` — `compare_and_report()` adds holistic flow

**Context:**
- Line 995: `neconformitati, matches, matched_ref_keys, articole_fara_deviz = match_global(...)`
- Line 1082: `raport_ierarhic = build_raport_ierarhic(ref_articles, neconformitati, matches, ...)`
- Line 1113: `docx_bytes = generate_word(raport_ierarhic, ...)`
- The `_headers_from_articles()` helper is already defined in `_run_analysis_pipeline()` at line ~272 — move it or duplicate it as a module-level helper

- [ ] **Step 1: Add `_headers_from_articles()` as module-level function in `local_run.py`**

Find the nested `_headers_from_articles()` at line ~272 (inside `_run_analysis_pipeline()`). Extract it to module level (right before `_run_analysis_pipeline()`):

```python
def _headers_from_articles(arts: list) -> dict:
    """Reconstruct deviz_headers dict from articles' deviz_header metadata."""
    from shared.deviz_header_extractor import DevizHeader
    headers: dict = {}
    for a in arts:
        cod = (a.get("deviz") or "").strip()
        if not cod or cod in headers:
            continue
        dh = a.get("deviz_header") or {}
        key = (a.get("deviz_key") or "").strip()
        obj1 = dh.get("obiectivul")
        obj2 = dh.get("obiectul")
        cat = dh.get("categoria")
        valid = bool(key) and not key.startswith("__INCOMPLETE__")
        headers[cod] = DevizHeader(obj1, obj2, cat, key, valid, "metadata", cod)
    return headers
```

Remove the nested definition from inside `_run_analysis_pipeline()`.

- [ ] **Step 2: Update `compare_and_report()` to produce holistic comparison**

In `compare_and_report()` at line ~995 (where `match_global()` is called), add holistic comparison AFTER existing match_global call:

```python
    # Existing: article-level matching (kept for backward compat)
    neconformitati, matches, matched_ref_keys, articole_fara_deviz = match_global(
        ref_articles, oferta_articles, client, model, include_prices=include_prices
    )

    # NEW: holistic group-based comparison
    from shared.group_comparator import compare_by_groups
    from shared.report_builder import build_raport_holistic
    ref_dh = _headers_from_articles(ref_articles)
    oferta_dh = _headers_from_articles(oferta_articles)
    holistic = compare_by_groups(
        ref_articles, oferta_articles, ref_dh, oferta_dh, client, model
    )
    raport_holistic = build_raport_holistic(holistic)
    logger.info(
        f"  [HOLISTIC] {raport_holistic['sumar']['total_matched_groups']} grupuri matchate, "
        f"{raport_holistic['sumar']['total_ref_only_groups']} ref-only, "
        f"{raport_holistic['sumar']['total_oferta_only_groups']} oferta-only"
    )
```

- [ ] **Step 3: Pass `holistic_raport` to `generate_word()`**

Find the `generate_word(raport_ierarhic, ...)` call at line ~1113. Add `holistic_raport=raport_holistic`:

```python
    docx_bytes = generate_word(
        raport_ierarhic,
        comp=comp,
        ...,  # existing params
        holistic_raport=raport_holistic,
        subcomponent_mode=subcomponent_mode,
    )
```

- [ ] **Step 4: Save `raport_holistic` to JSON alongside existing comparatie JSON**

After saving `comparatie_oferta_N.json`, add:

```python
    holistic_path = output_dir / f"holistic_oferta_{oferta_nr}.json"
    holistic_path.write_text(
        json.dumps(raport_holistic, ensure_ascii=False, default=str, indent=2),
        encoding="utf-8"
    )
    logger.info(f"  Holistic JSON: {holistic_path.name}")
```

- [ ] **Step 5: Verify import OK**

```bash
.venv/bin/python3 -c "import local_run; print('import OK')"
```

- [ ] **Step 6: Commit**

```bash
git add local_run.py
git commit -m "feat(pipeline): holistic group comparison wired into compare_and_report()"
```

---

## Task 5: Regression + Integration Check

**Files:** Nicio modificare de cod.

- [ ] **Step 1: Full test suite**

```bash
.venv/bin/python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py \
  --ignore=tests/shared/test_f3_regex_parser_multiline.py \
  --ignore=tests/test_normalize_cod.py \
  2>&1 | tail -10
```
Expected: 190+ passed, aceleasi 4 pre-existing failures.

- [ ] **Step 2: Run SD pipeline si verifica metrici + holistic output**

```bash
.venv/bin/python3 multi_client_run.py --client "Scoala Dragomiresti" 2>&1 | rtk log
```

Verifica:
```bash
python3 -c "
import json; from pathlib import Path
for i in range(1,3):
    f = Path(f'output_AO/Scoala Dragomiresti/comparatie_oferta_{i}.json')
    if not f.exists(): continue
    comp = json.loads(f.read_text())
    print(f'SD O{i}: matches={comp[\"matches\"]}')

    h = Path(f'output_AO/Scoala Dragomiresti/holistic_oferta_{i}.json')
    if h.exists():
        hd = json.loads(h.read_text())
        s = hd['sumar']
        print(f'  Holistic: {s[\"total_matched_groups\"]} matched, {s[\"total_ref_only_groups\"]} ref-only, {s[\"total_oferta_only_groups\"]} oferta-only')
"
```
Expected: matches=904, holistic JSON generat.

- [ ] **Step 3: Verifica raportul Word holistic**

Deschide `output_AO/Scoala Dragomiresti/Raport_Oferta_1.docx` si verifica:
- Headerele de grup arata OBIECTIVUL / Obiectul / Categoria
- Grupurile matched sunt vizibile
- Grupurile ref-only au fundal rosu
- Grupurile oferta-only au fundal portocaliu

- [ ] **Step 4: Commit final**

```bash
git add output_AO/  # nu adauga fisiere de output — ele nu sunt in git
git commit -m "chore: holistic comparison pipeline complete"
```

---

## Definition of Done

- [ ] `HolisticComparison` dataclass cu matched_groups, ref_only_groups, oferta_only_groups, ungrouped
- [ ] `compare_by_groups()` — group matching + article-level comparison per matched pair
- [ ] `build_raport_holistic()` — structura raport + sumar
- [ ] `_add_group_heading()` — header 3-layer in Word
- [ ] `_generate_word_holistic()` — continut Word holistic (4 sectiuni)
- [ ] `generate_word(holistic_raport=...)` — branching holistic vs ierarhic
- [ ] `holistic_oferta_N.json` salvat langa `comparatie_oferta_N.json`
- [ ] Toate testele noi green (min 7 noi)
- [ ] Metrici SD: matches=904 nemodificat
- [ ] Raport Word arata grupuri 3-layer cu sectiuni distincte
