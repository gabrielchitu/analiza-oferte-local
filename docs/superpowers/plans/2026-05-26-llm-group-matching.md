# LLM Group Matching + Diagnostic Trace — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add LLM-assisted group matching (knowledge-first caching) + diagnostic JSON trace so text-different deviz groups are correctly matched instead of generating false ref_only/oferta_only.

**Architecture:** 4 new functions in `shared/group_comparator.py` (`_den_string`, `_apply_knowledge`, `_save_knowledge`, `_llm_match_groups`) + `match_trace` field in `HolisticComparison`. After 3-layer matching leaves groups unmatched, a secondary phase runs: knowledge lookup → LLM → save new pairs. `local_run.py` writes `matching_debug_oferta_N.json` from `match_trace`. Knowledge persists in `shared/group_match_knowledge.json` keyed by client name.

**Tech Stack:** Python 3.12+, OpenAI-compatible client (same pattern as `shared/article_matcher.py` line 127), pathlib JSON, pytest, monkeypatch for LLM mock.

**Spec:** `docs/superpowers/specs/2026-05-26-llm-group-matching-design.md`

---

## File Map

| File | Change |
|---|---|
| `shared/group_comparator.py` | Extract `_den_string`; add `_KNOWLEDGE_PATH`, `_apply_knowledge`, `_save_knowledge`, `_llm_match_groups`; update `compare_by_groups` signature + secondary matching phase + `match_trace` |
| `shared/group_match_knowledge.json` | Create new — empty `{}` |
| `local_run.py` | Pass `client_name` to `compare_by_groups`; write `matching_debug_oferta_N.json` |
| `tests/test_group_comparator.py` | Add tests for each new function |

---

## Codebase context (read before coding)

- `shared/group_comparator.py` — all new code goes here. `_articles_by_deviz` groups by `deviz_key` (MD5 hash). `ref_deviz_headers` / `oferta_deviz_headers` are `dict[str, DevizHeader]` keyed by deviz_key hash. `DevizHeader` is a dataclass with `.obiectivul`, `.obiectul`, `.categoria`, `.is_valid`, `.deviz_key` attributes.
- `compare_by_groups` (line 128): builds `full_mapping` (oferta_key → ref_key), runs main matching loop, then ref_only/oferta_only loops. Secondary phase inserts BETWEEN the main loop and the ref_only loop.
- `_header_to_string` local closure (lines 247-251): extract this to module-level `_den_string`.
- `local_run.py` line 1091: `compare_by_groups(ref_articles, oferta_norm, _ref_dh, _oferta_dh, client, model)` — add `client_name=` kwarg.
- LLM call pattern (from `shared/article_matcher.py` line 127):
  ```python
  resp = openai_client.chat.completions.create(
      model=deployment, temperature=0.0,
      response_format={"type": "json_object"},
      messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_msg}],
      max_tokens=1000,
  )
  result = json.loads(resp.choices[0].message.content)
  ```

---

## Task 1: `_den_string` + `match_trace` in `HolisticComparison`

**Files:**
- Modify: `shared/group_comparator.py`
- Modify: `tests/test_group_comparator.py`

- [ ] **Step 1.1: Write failing test**

Add to `tests/test_group_comparator.py`:
```python
def test_holistic_comparison_has_match_trace():
    from shared.group_comparator import HolisticComparison
    hc = HolisticComparison()
    assert hasattr(hc, "match_trace")
    assert isinstance(hc.match_trace, dict)
```

- [ ] **Step 1.2: Run to verify FAIL**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_holistic_comparison_has_match_trace -v
```
Expected: FAIL — `AttributeError: 'HolisticComparison' object has no attribute 'match_trace'`

- [ ] **Step 1.3: Add `import json`, `from pathlib import Path`, `_den_string`, update dataclass**

At the top of `shared/group_comparator.py`, after `from collections import defaultdict`, add:
```python
import json
from pathlib import Path
```

After `logger = logging.getLogger(__name__)`, add:
```python
def _den_string(hdr) -> str:
    """Canonical denomination for a DevizHeader: 'obj1 | obj2 | cat'."""
    if not hdr:
        return ""
    parts = [
        getattr(hdr, "obiectivul", None),
        getattr(hdr, "obiectul", None),
        getattr(hdr, "categoria", None),
    ]
    return " | ".join(p for p in parts if p)
```

Update `HolisticComparison` dataclass — add `match_trace` as last field:
```python
@dataclass
class HolisticComparison:
    matched_groups: list = field(default_factory=list)
    ref_only_groups: list = field(default_factory=list)
    oferta_only_groups: list = field(default_factory=list)
    ungrouped: list = field(default_factory=list)
    unassigned_articles: list = field(default_factory=list)
    match_trace: dict = field(default_factory=dict)
```

In `compare_by_groups`, find and delete the local `_header_to_string` closure (lines ~247-252 in current file):
```python
# DELETE this block:
def _header_to_string(hdr):
    if not hdr:
        return ""
    parts = [hdr.obiectivul, hdr.obiectul, hdr.categoria]
    return " | ".join(p for p in parts if p)
```
Replace all its call sites with `_den_string(...)`. There are 5 call sites in `compare_by_groups` — find with `grep -n "_header_to_string" shared/group_comparator.py`.

- [ ] **Step 1.4: Run test to verify PASS**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_holistic_comparison_has_match_trace -v
```
Expected: PASS

- [ ] **Step 1.5: Run full suite to check no regressions**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v
```
Expected: all existing 6 tests + new test PASS (7 total)

- [ ] **Step 1.6: Commit**

```bash
git add shared/group_comparator.py tests/test_group_comparator.py
git commit -m "feat(group_comparator): extract _den_string to module level, add match_trace to HolisticComparison"
```

---

## Task 2: `_apply_knowledge` + `_save_knowledge` + knowledge file

**Files:**
- Modify: `shared/group_comparator.py`
- Create: `shared/group_match_knowledge.json`
- Modify: `tests/test_group_comparator.py`

- [ ] **Step 2.1: Create empty knowledge file**

Create `shared/group_match_knowledge.json` with content:
```json
{}
```

- [ ] **Step 2.2: Write failing tests**

Add to `tests/test_group_comparator.py`:
```python
import json


def test_apply_knowledge_returns_pairs(tmp_path, monkeypatch):
    """_apply_knowledge matches known ref_den/oferta_den pairs to deviz keys."""
    from shared import group_comparator as gc
    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key

    def _make_hdr(obj1, obj2, cat, cod="X"):
        key, valid = _make_deviz_key(obj1, obj2, cat)
        return DevizHeader(obj1, obj2, cat, key, valid, "test", cod)

    ref_hdr = _make_hdr("Proj", "Obj1", "Cat1")
    oferta_hdr = _make_hdr("Proj", "Obj1", "Cat1 tip I")
    rkey = ref_hdr.deviz_key
    okey = oferta_hdr.deviz_key

    kf = tmp_path / "group_match_knowledge.json"
    kf.write_text(json.dumps({
        "TestClient": [
            {"ref_den": "Proj | Obj1 | Cat1", "oferta_den": "Proj | Obj1 | Cat1 tip I"}
        ]
    }))
    monkeypatch.setattr(gc, "_KNOWLEDGE_PATH", kf)

    result = gc._apply_knowledge(
        remaining_ref={rkey},
        remaining_oferta={okey},
        ref_deviz_headers={rkey: ref_hdr},
        oferta_deviz_headers={okey: oferta_hdr},
        client_name="TestClient",
    )
    assert (rkey, okey) in result


def test_save_knowledge_deduplicates(tmp_path, monkeypatch):
    """_save_knowledge deduplicates on (ref_den, oferta_den)."""
    from shared import group_comparator as gc

    kf = tmp_path / "group_match_knowledge.json"
    kf.write_text("{}")
    monkeypatch.setattr(gc, "_KNOWLEDGE_PATH", kf)

    pair = {"ref_den": "A | B | C", "oferta_den": "A | B | C tip I"}
    gc._save_knowledge("MyClient", [pair])
    gc._save_knowledge("MyClient", [pair])  # second call — same pair

    data = json.loads(kf.read_text())
    assert len(data["MyClient"]) == 1
    assert data["MyClient"][0]["ref_den"] == "A | B | C"
```

- [ ] **Step 2.3: Run to verify FAIL**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_apply_knowledge_returns_pairs tests/test_group_comparator.py::test_save_knowledge_deduplicates -v
```
Expected: FAIL — `AttributeError: module 'shared.group_comparator' has no attribute '_apply_knowledge'`

- [ ] **Step 2.4: Implement `_KNOWLEDGE_PATH`, `_apply_knowledge`, `_save_knowledge`**

Add to `shared/group_comparator.py` immediately after `_den_string`:

```python
_KNOWLEDGE_PATH = Path(__file__).parent / "group_match_knowledge.json"


def _apply_knowledge(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    client_name: str,
) -> list[tuple[str, str]]:
    """Return (ref_key, oferta_key) pairs from persisted knowledge for this client."""
    if not client_name or not remaining_ref or not remaining_oferta:
        return []
    try:
        knowledge = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    pairs = knowledge.get(client_name, [])
    if not pairs:
        return []
    ref_den_to_key = {
        _den_string(ref_deviz_headers.get(k)): k
        for k in remaining_ref
        if _den_string(ref_deviz_headers.get(k))
    }
    oferta_den_to_key = {
        _den_string(oferta_deviz_headers.get(k)): k
        for k in remaining_oferta
        if _den_string(oferta_deviz_headers.get(k))
    }
    result = []
    for p in pairs:
        rk = ref_den_to_key.get(p.get("ref_den", ""))
        ok = oferta_den_to_key.get(p.get("oferta_den", ""))
        if rk and ok:
            result.append((rk, ok))
    return result


def _save_knowledge(client_name: str, new_pairs: list[dict]) -> None:
    """Append new (ref_den, oferta_den) pairs to knowledge file, deduplicating."""
    if not client_name or not new_pairs:
        return
    try:
        knowledge = json.loads(_KNOWLEDGE_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        knowledge = {}
    existing = knowledge.get(client_name, [])
    seen = {(p["ref_den"], p["oferta_den"]) for p in existing}
    for p in new_pairs:
        key = (p.get("ref_den", ""), p.get("oferta_den", ""))
        if key[0] and key[1] and key not in seen:
            existing.append({"ref_den": key[0], "oferta_den": key[1]})
            seen.add(key)
    knowledge[client_name] = existing
    _KNOWLEDGE_PATH.write_text(
        json.dumps(knowledge, ensure_ascii=False, indent=2), encoding="utf-8"
    )
```

- [ ] **Step 2.5: Run tests to verify PASS**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_apply_knowledge_returns_pairs tests/test_group_comparator.py::test_save_knowledge_deduplicates -v
```
Expected: PASS

- [ ] **Step 2.6: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v
```
Expected: all 9 tests PASS

- [ ] **Step 2.7: Commit**

```bash
git add shared/group_comparator.py shared/group_match_knowledge.json tests/test_group_comparator.py
git commit -m "feat(group_comparator): add _apply_knowledge, _save_knowledge, create group_match_knowledge.json"
```

---

## Task 3: `_llm_match_groups`

**Files:**
- Modify: `shared/group_comparator.py`
- Modify: `tests/test_group_comparator.py`

- [ ] **Step 3.1: Write failing tests**

Add to `tests/test_group_comparator.py`:
```python
def test_llm_match_groups_valid_response():
    """_llm_match_groups parses valid LLM JSON and returns matched pairs."""
    from shared import group_comparator as gc
    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key

    def _make_hdr(obj1, obj2, cat):
        key, valid = _make_deviz_key(obj1, obj2, cat)
        return DevizHeader(obj1, obj2, cat, key, valid, "test", "X")

    ref_hdr = _make_hdr("Proj", "Obj1", "Cat ref")
    oferta_hdr = _make_hdr("Proj", "Obj1", "Cat oferta")
    rkey = ref_hdr.deviz_key
    okey = oferta_hdr.deviz_key

    class FakeMessage:
        content = json.dumps({"matches": [
            {"ref": "Proj | Obj1 | Cat ref", "oferta": "Proj | Obj1 | Cat oferta"}
        ]})

    class FakeChoice:
        message = FakeMessage()

    class FakeResp:
        choices = [FakeChoice()]

    class FakeClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    return FakeResp()

    result = gc._llm_match_groups(
        remaining_ref={rkey},
        remaining_oferta={okey},
        ref_deviz_headers={rkey: ref_hdr},
        oferta_deviz_headers={okey: oferta_hdr},
        llm_client=FakeClient(),
        llm_model="test-model",
    )
    assert len(result) == 1
    assert result[0][0] == rkey   # ref_key
    assert result[0][1] == okey   # oferta_key


def test_llm_match_groups_api_error():
    """_llm_match_groups returns [] when LLM call raises."""
    from shared import group_comparator as gc

    class BadClient:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise ConnectionError("API down")

    result = gc._llm_match_groups(
        remaining_ref={"k1"},
        remaining_oferta={"k2"},
        ref_deviz_headers={},
        oferta_deviz_headers={},
        llm_client=BadClient(),
        llm_model="test",
    )
    assert result == []
```

- [ ] **Step 3.2: Run to verify FAIL**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_llm_match_groups_valid_response tests/test_group_comparator.py::test_llm_match_groups_api_error -v
```
Expected: FAIL — `AttributeError: module has no attribute '_llm_match_groups'`

- [ ] **Step 3.3: Implement `_LLM_GROUP_SYSTEM_PROMPT` + `_llm_match_groups`**

Add to `shared/group_comparator.py` immediately after `_save_knowledge`:

```python
_LLM_GROUP_SYSTEM_PROMPT = (
    "Ești expert în devize de construcții românești.\n"
    "Mai jos sunt grupuri din REFERINȚĂ și OFERTĂ care nu s-au potrivit automat.\n"
    "Textele pot fi abreviate diferit pentru aceeași categorie. "
    "Pot fi de lungimi diferite, în schimb înseamnă același obiectiv sau obiect "
    "sau categorie de lucrări / stadiu fizic.\n\n"
    'Returnează JSON cu cheia "matches":\n'
    '{"matches": [{"ref": "<ref_den_exact>", "oferta": "<oferta_den_exact>"}]}\n\n'
    "Omite perechile nesigure. Dacă nu există nicio potrivire clară, returnează "
    '{"matches": []}.'
)


def _llm_match_groups(
    remaining_ref: set,
    remaining_oferta: set,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client,
    llm_model: str,
) -> list[tuple[str, str, str, str]]:
    """LLM-assisted group matching. Returns [(ref_key, oferta_key, ref_den, oferta_den)]."""
    if not llm_client or not remaining_ref or not remaining_oferta:
        return []
    ref_den_to_key = {
        _den_string(ref_deviz_headers.get(k)): k
        for k in remaining_ref
        if _den_string(ref_deviz_headers.get(k))
    }
    oferta_den_to_key = {
        _den_string(oferta_deviz_headers.get(k)): k
        for k in remaining_oferta
        if _den_string(oferta_deviz_headers.get(k))
    }
    if not ref_den_to_key or not oferta_den_to_key:
        return []
    ref_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(ref_den_to_key))
    oferta_list = "\n".join(f'{i + 1}. "{d}"' for i, d in enumerate(oferta_den_to_key))
    user_prompt = (
        f"REFERINȚĂ (grupuri nematched):\n{ref_list}\n\n"
        f"OFERTĂ (grupuri nematched):\n{oferta_list}"
    )
    try:
        resp = llm_client.chat.completions.create(
            model=llm_model,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": _LLM_GROUP_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1000,
        )
        parsed = json.loads(resp.choices[0].message.content)
    except Exception as e:
        logger.warning(f"[GC] LLM group match failed: {e}")
        return []
    pairs_raw = parsed.get("matches", []) if isinstance(parsed, dict) else []
    result = []
    for item in pairs_raw:
        ref_den = item.get("ref", "")
        oferta_den = item.get("oferta", "")
        rk = ref_den_to_key.get(ref_den)
        ok = oferta_den_to_key.get(oferta_den)
        if not rk:
            logger.warning(f"[GC] LLM suggested unknown ref_den: {ref_den!r}")
            continue
        if not ok:
            logger.warning(f"[GC] LLM suggested unknown oferta_den: {oferta_den!r}")
            continue
        result.append((rk, ok, ref_den, oferta_den))
    logger.info(f"[GC] LLM matched {len(result)} additional groups")
    return result
```

- [ ] **Step 3.4: Run tests to verify PASS**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_llm_match_groups_valid_response tests/test_group_comparator.py::test_llm_match_groups_api_error -v
```
Expected: PASS

- [ ] **Step 3.5: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v
```
Expected: all 11 tests PASS

- [ ] **Step 3.6: Commit**

```bash
git add shared/group_comparator.py tests/test_group_comparator.py
git commit -m "feat(group_comparator): add _llm_match_groups with system prompt, JSON validation, API error handling"
```

---

## Task 4: Wire into `compare_by_groups` + populate `match_trace`

**Files:**
- Modify: `shared/group_comparator.py`
- Modify: `tests/test_group_comparator.py`

- [ ] **Step 4.1: Write failing test**

Add to `tests/test_group_comparator.py`:
```python
def test_compare_by_groups_match_trace_structure():
    """compare_by_groups populates match_trace with all required keys."""
    ref_arts = [_make_article("EA02A1", "D1")]
    oferta_arts = [_make_article("EA02A1", "D1")]
    ref_dh = {"key_D1": _make_header("Proj A", "Obj D1", "Cat D1", "D1")}
    oferta_dh = {"key_D1": _make_header("Proj A", "Obj D1", "Cat D1", "D1")}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh, client_name="TestClient")
    trace = result.match_trace
    for key in ("ref_groups", "oferta_groups", "matched", "ref_only", "oferta_only"):
        assert key in trace, f"match_trace missing key: {key}"
    assert len(trace["matched"]) == 1
    assert trace["matched"][0]["match_type"] in ("same_code", "cross_3layer", "knowledge", "llm")
    assert "ref_key" in trace["matched"][0]
    assert "oferta_key" in trace["matched"][0]
    assert "ref_den" in trace["matched"][0]
    assert "ref_groups" in trace and len(trace["ref_groups"]) == 1
    assert trace["ref_groups"][0]["n_articles"] == 1
```

- [ ] **Step 4.2: Run to verify FAIL**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_compare_by_groups_match_trace_structure -v
```
Expected: FAIL — `compare_by_groups() got unexpected keyword argument 'client_name'` or `match_trace` keys missing.

- [ ] **Step 4.3: Update `compare_by_groups` signature**

Change the function signature (line 128) from:
```python
def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
) -> HolisticComparison:
```
To:
```python
def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
    client_name: str = "",
) -> HolisticComparison:
```

- [ ] **Step 4.4: Track match types during `full_mapping` construction**

In `compare_by_groups`, find the `full_mapping: dict[str, str] = {}` block. Change it to also track `match_type_for`:

```python
match_type_for: dict[str, str] = {}
full_mapping: dict[str, str] = {}
for oferta_cod in oferta_cods:
    if oferta_cod in group_mapping:
        full_mapping[oferta_cod] = group_mapping[oferta_cod]
        match_type_for[oferta_cod] = "cross_3layer"
    elif oferta_cod in ref_cods:
        rh = ref_deviz_headers.get(oferta_cod)
        oh = oferta_deviz_headers.get(oferta_cod)
        if rh and oh and rh.is_valid and oh.is_valid:
            sim = _quick_3layer_sim(rh, oh)
            if sim >= _SAME_CODE_THRESHOLD:
                full_mapping[oferta_cod] = oferta_cod
                match_type_for[oferta_cod] = "same_code"
            else:
                logger.info(
                    f"[GC] Acelasi cod {oferta_cod} dar continut DIFERIT "
                    f"(sim={sim:.2f} < {_SAME_CODE_THRESHOLD}) → oferta-only"
                )
        else:
            full_mapping[oferta_cod] = oferta_cod
            match_type_for[oferta_cod] = "same_code"
```

- [ ] **Step 4.5: Add `_trace_matched` to the main matching loop**

Add `_trace_matched: list = []` before the `for oferta_cod, ref_cod in sorted(full_mapping.items()):` loop.

At the END of the loop body (after `matched_oferta_cods.add(oferta_cod)` and the existing `logger.info`), add:
```python
        _trace_matched.append({
            "ref_key": ref_cod,
            "oferta_key": oferta_cod,
            "match_type": match_type_for.get(oferta_cod, "same_code"),
            "ref_den": _den_string(ref_deviz_headers.get(ref_cod)),
            "oferta_den": _den_string(oferta_deviz_headers.get(oferta_cod)),
        })
```

- [ ] **Step 4.6: Insert secondary matching phase BEFORE ref_only loop**

The current code order is: [main loop] → [ref_only loop] → [oferta_only loop] → [final logger.info].

Insert the following block BETWEEN the main loop and the ref_only loop (between `matched_oferta_cods.add(oferta_cod)` and `for ref_cod in sorted(ref_cods - matched_ref_cods):`):

```python
    # Phase 2: knowledge + LLM for remaining unmatched groups.
    # Runs BEFORE ref_only/oferta_only population so those loops see final matched state.
    remaining_ref_keys = ref_cods - matched_ref_cods
    remaining_oferta_keys = oferta_cods - matched_oferta_cods

    def _run_secondary_match(pairs_with_type):
        """pairs_with_type: [(ref_key, oferta_key, match_type, ref_den, oferta_den)]"""
        for ref_key, oferta_key, mtype, ref_den, oferta_den in pairs_with_type:
            if ref_key in matched_ref_cods or oferta_key in matched_oferta_cods:
                continue
            r_arts = ref_by_deviz.get(ref_key, [])
            o_arts = oferta_by_deviz.get(oferta_key, [])
            ncs2, matches2 = _compare_articles_in_group(
                r_arts, o_arts, ref_key, llm_client, llm_model
            )
            r_hdr2 = ref_deviz_headers.get(ref_key)
            o_hdr2 = oferta_deviz_headers.get(oferta_key)
            den2 = _den_string(r_hdr2) or _den_string(o_hdr2)
            for nc in ncs2:
                nc["deviz_denumire"] = den2
            result.matched_groups.append({
                "ref_deviz_cod": ref_key,
                "oferta_deviz_cod": oferta_key,
                "ref_header": r_hdr2,
                "oferta_header": o_hdr2,
                "deviz_denumire": den2,
                "ref_articles": r_arts,
                "oferta_articles": o_arts,
                "neconformitati": ncs2,
                "matches": matches2,
            })
            matched_ref_cods.add(ref_key)
            matched_oferta_cods.add(oferta_key)
            _trace_matched.append({
                "ref_key": ref_key, "oferta_key": oferta_key,
                "match_type": mtype,
                "ref_den": ref_den,
                "oferta_den": oferta_den,
            })
            logger.info(f"[GC] {mtype.capitalize()} match: ref {ref_key} ↔ oferta {oferta_key}")

    if remaining_ref_keys and remaining_oferta_keys:
        # Knowledge phase
        knowledge_pairs = _apply_knowledge(
            remaining_ref_keys, remaining_oferta_keys,
            ref_deviz_headers, oferta_deviz_headers, client_name,
        )
        _run_secondary_match([
            (rk, ok, "knowledge", _den_string(ref_deviz_headers.get(rk)), _den_string(oferta_deviz_headers.get(ok)))
            for rk, ok in knowledge_pairs
        ])

        # Update remaining for LLM phase
        remaining_ref_keys -= matched_ref_cods
        remaining_oferta_keys -= matched_oferta_cods

        # LLM phase
        _new_llm_pairs: list[dict] = []
        if remaining_ref_keys and remaining_oferta_keys and llm_client:
            llm_results = _llm_match_groups(
                remaining_ref_keys, remaining_oferta_keys,
                ref_deviz_headers, oferta_deviz_headers,
                llm_client, llm_model,
            )
            _run_secondary_match([
                (rk, ok, "llm", rd, od) for rk, ok, rd, od in llm_results
            ])
            _new_llm_pairs = [
                {"ref_den": rd, "oferta_den": od}
                for rk, ok, rd, od in llm_results
                if rk in matched_ref_cods  # only actually matched
            ]
        _save_knowledge(client_name, _new_llm_pairs)
```

- [ ] **Step 4.7: Populate `match_trace` BEFORE `return result`**

Replace the existing `logger.info` at the end of `compare_by_groups` with:
```python
    logger.info(
        f"[GC] Groups: {len(result.matched_groups)} matched, "
        f"{len(result.ref_only_groups)} ref-only, "
        f"{len(result.oferta_only_groups)} oferta-only, "
        f"{len(result.ungrouped)} ungrouped"
    )
    result.match_trace = {
        "ref_groups": [
            {"deviz_key": k, "den": _den_string(ref_deviz_headers.get(k)), "n_articles": len(ref_by_deviz.get(k, []))}
            for k in sorted(ref_cods)
        ],
        "oferta_groups": [
            {"deviz_key": k, "den": _den_string(oferta_deviz_headers.get(k)), "n_articles": len(oferta_by_deviz.get(k, []))}
            for k in sorted(oferta_cods)
        ],
        "matched": _trace_matched,
        "ref_only": [
            {"deviz_key": k, "den": _den_string(ref_deviz_headers.get(k)), "n_articles": len(ref_by_deviz.get(k, []))}
            for k in sorted(ref_cods - matched_ref_cods)
        ],
        "oferta_only": [
            {"deviz_key": k, "den": _den_string(oferta_deviz_headers.get(k)), "n_articles": len(oferta_by_deviz.get(k, []))}
            for k in sorted(oferta_cods - matched_oferta_cods)
        ],
    }
    return result
```

- [ ] **Step 4.8: Run failing test to verify PASS**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py::test_compare_by_groups_match_trace_structure -v
```
Expected: PASS

- [ ] **Step 4.9: Run full suite**

```bash
.venv/bin/python3 -m pytest tests/test_group_comparator.py -v
```
Expected: all 12 tests PASS

- [ ] **Step 4.10: Commit**

```bash
git add shared/group_comparator.py tests/test_group_comparator.py
git commit -m "feat(group_comparator): wire knowledge+LLM secondary matching phase, populate match_trace"
```

---

## Task 5: `local_run.py` — pass `client_name`, write `matching_debug_oferta_N.json`

**Files:**
- Modify: `local_run.py`

- [ ] **Step 5.1: Pass `client_name` to `compare_by_groups`**

In `local_run.py` around line 1091, change:
```python
# Before:
_holistic = compare_by_groups(
    ref_articles, oferta_norm, _ref_dh, _oferta_dh, client, model
)

# After:
_holistic = compare_by_groups(
    ref_articles, oferta_norm, _ref_dh, _oferta_dh, client, model,
    client_name=client_config.name if client_config else "",
)
```

- [ ] **Step 5.2: Write `matching_debug_oferta_N.json` after holistic JSON write**

After the existing holistic JSON write block (lines ~1148-1157), add:
```python
    # Matching debug trace
    try:
        debug_path = output_dir / f"matching_debug_oferta_{oferta_nr}.json"
        debug_path.write_text(
            json.dumps(_holistic.match_trace, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  Matching debug: {debug_path.name}")
    except Exception as e:
        logger.warning(f"  Matching debug failed: {e}")
```

- [ ] **Step 5.3: Run pipeline for CM to verify**

```bash
.venv/bin/python3 multi_client_run.py --client "Camin Maneciu" 2>&1 | rtk log
```
Expected in logs: `Matching debug: matching_debug_oferta_1.json` and `matching_debug_oferta_2.json`. No errors.

- [ ] **Step 5.4: Inspect debug file**

```bash
python3 -c "
import json
from pathlib import Path
d = json.loads(Path('output_AO/Camin Maneciu/matching_debug_oferta_1.json').read_text())
print('ref_groups:', len(d['ref_groups']))
print('oferta_groups:', len(d['oferta_groups']))
print('matched:', len(d['matched']))
for m in d['matched'][:3]:
    print(f'  type={m[\"match_type\"]} ref_den={m[\"ref_den\"][:40]!r}')
print('ref_only:', len(d['ref_only']))
print('oferta_only:', len(d['oferta_only']))
for g in d['oferta_only'][:3]:
    print(f'  {g[\"den\"]!r}')
"
```
Expected: `matched` = number of matched_groups from holistic sumar. `oferta_only` shows 16 groups with their full denomination strings. If LLM fired: some appear in `matched` with `match_type=llm`.

- [ ] **Step 5.5: Verify knowledge file if LLM ran**

```bash
python3 -c "
import json
from pathlib import Path
k = json.loads(Path('shared/group_match_knowledge.json').read_text())
for client, pairs in k.items():
    print(f'{client}: {len(pairs)} pairs')
    for p in pairs[:2]:
        print(f'  {p[\"ref_den\"][:50]!r}')
        print(f'  -> {p[\"oferta_den\"][:50]!r}')
"
```
Expected: if LLM successfully matched any groups, they appear here.

- [ ] **Step 5.6: Reset `shared/pattern_library.json` if AUTO_GEN_ patterns accumulated**

```bash
python3 -c "
import json
from pathlib import Path
p_path = Path('shared/pattern_library.json')
pl = json.loads(p_path.read_text())
for cat in pl.get('categories', []):
    cat['patterns'] = [x for x in cat['patterns'] if not x.get('name','').startswith('AUTO_GEN')]
p_path.write_text(json.dumps(pl, ensure_ascii=False, indent=2))
print('pattern_library reset')
"
```

- [ ] **Step 5.7: Commit**

```bash
git add local_run.py shared/group_match_knowledge.json shared/pattern_library.json
git commit -m "feat(local_run): pass client_name to compare_by_groups, write matching_debug_oferta_N.json"
```

---

## Self-Review Checklist (done)

- [x] **Spec coverage:** S1 (diagnostic JSON) → Task 5; S2 (LLM matching) → Tasks 2-4; S3 (knowledge file) → Task 2. All requirements covered.
- [x] **Placeholder scan:** No TBD/TODO. All code blocks complete.
- [x] **Type consistency:**
  - `_llm_match_groups` returns `list[tuple[str, str, str, str]]` → destructured as `rk, ok, rd, od` in Task 4. ✅
  - `_apply_knowledge` returns `list[tuple[str, str]]` → destructured as `rk, ok` in Task 4. ✅
  - `_den_string` used consistently everywhere. ✅
  - `match_trace` is `dict` in dataclass, populated as dict in Task 4. ✅
  - `client_name` added to `compare_by_groups` signature (Task 4) and passed from `local_run.py` (Task 5). ✅
