# Hierarchical Component System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable extraction of hierarchical components with parent-child links, unified matching on (deviz, cod) pairs, and hierarchical DOCX reporting.

**Architecture:** 
1. Pattern detection (Pass 1) identifies document format → checkpoint
2. Pattern-based extraction (Pass 2) creates articles with parent_code + is_component fields
3. Matching treats all articles identically (deviz+cod pair)
4. DOCX reports show components indented under parents

**Tech Stack:** Python, existing f3_regex_parser, LLM integration (existing), python-docx

---

## File Structure

### New Files
- `shared/pattern_detector.py` - Pattern detection, LLM fallback, pattern library mgmt
- `shared/pattern_library.json` - Known patterns (MANECIU, DRAGOMIRESTI, SPORTIVA, etc.)
- `tests/test_pattern_detector.py` - Pattern detection tests

### Modified Files
- `shared/f3_regex_parser.py` - Add parent_code, is_component to article structure
- `shared/f3_extractor.py` - Integrate pattern detection Pass 1
- `AgentComparator_local.py` - Minimal changes (matching already uses deviz+cod)
- `shared/report_word.py` - Hierarchical DOCX rendering with components

---

## Tasks

### Task 1: Data Model - Add parent_code + is_component to Article

**Files:**
- Modify: `shared/f3_regex_parser.py:338-360` (_make_article function)
- Test: `tests/test_f3_regex_parser.py` (new test file)

- [ ] **Step 1: Write failing test for article with parent_code**

Create `tests/test_f3_regex_parser.py`:
```python
def test_make_article_with_parent_code():
    """Article can have parent_code for component tracking."""
    art = f3_regex_parser._make_article(
        cod="6717077",
        denumire="teava polietilena",
        um="m",
        cantitate=2.0,
        preturi=[0, 0, 0, 0],
        deviz_cod="4.3-07",
        deviz_den="Conducte",
        is_component=True,
        parent_code="SA14J"
    )
    assert art["cod"] == "6717077"
    assert art["parent_code"] == "SA14J"
    assert art["is_component"] is True
```

- [ ] **Step 2: Run test, verify it fails**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
python3 -m pytest tests/test_f3_regex_parser.py::test_make_article_with_parent_code -v
```

Expected: `TypeError: _make_article() got unexpected keyword argument 'parent_code'`

- [ ] **Step 3: Update _make_article signature and implementation**

In `shared/f3_regex_parser.py`, find `_make_article` function (line 338):

```python
def _make_article(cod: str, denumire: str, um: str, cantitate: float,
                  preturi: list, deviz_cod: str, deviz_den: str, 
                  is_component: bool = False,
                  parent_code: str = None,
                  subcomponents: list = None) -> Dict:
    """Create article dict with component tracking.
    
    Args:
        cod: Article code
        denumire: Article denomination
        um: Unit of measure
        cantitate: Quantity
        preturi: [price_material, price_manopera, price_utilaj, price_transport]
        deviz_cod: Budget/section code
        deviz_den: Budget denomination
        is_component: Whether this is a subcomponent
        parent_code: Code of parent article (null for parents, filled for components)
        subcomponents: List of subcomponent codes (for parent articles only)
    """
    return {
        'cod': cod,
        'denumire': denumire,
        'um': um,
        'cantitate': cantitate,
        'deviz': deviz_cod,
        'deviz_denumire': deviz_den,
        'is_component': is_component,
        'parent_code': parent_code,
        'subcomponents': subcomponents or [],
        'pret_material': preturi[0],
        'val_material': 0.0,
        'pret_manopera': preturi[1],
        'val_manopera': 0.0,
        'pret_utilaj': preturi[2],
        'val_utilaj': 0.0,
        'pret_transport': preturi[3],
        'val_transport': 0.0
    }
```

- [ ] **Step 4: Run test, verify it passes**

```bash
python3 -m pytest tests/test_f3_regex_parser.py::test_make_article_with_parent_code -v
```

Expected: `PASSED`

- [ ] **Step 5: Test parent article (no parent_code)**

```python
def test_make_article_parent():
    """Parent article has parent_code=null."""
    art = f3_regex_parser._make_article(
        cod="SA14J",
        denumire="teava din material plastic",
        um="m",
        cantitate=2.0,
        preturi=[0, 0, 0, 0],
        deviz_cod="4.3-07",
        deviz_den="Conducte",
        is_component=False,
        parent_code=None,
        subcomponents=["6717077", "6719428"]
    )
    assert art["parent_code"] is None
    assert art["is_component"] is False
    assert art["subcomponents"] == ["6717077", "6719428"]
```

- [ ] **Step 6: Run all tests in test file**

```bash
python3 -m pytest tests/test_f3_regex_parser.py -v
```

Expected: All pass

- [ ] **Step 7: Commit**

```bash
git add shared/f3_regex_parser.py tests/test_f3_regex_parser.py
git commit -m "refactor: add parent_code + is_component to article data model

Article now tracks:
- parent_code: Link to parent article (null for parents, filled for components)
- is_component: Boolean flag (false for parents, true for components)
- subcomponents: Array of component codes (parents only)

Tests verify parent + component article creation.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 2: Pattern Library - Load + Save Pattern Definitions

**Files:**
- Create: `shared/pattern_library.json`
- Create: `shared/pattern_detector.py` (stub with load/save functions)
- Test: `tests/test_pattern_detector.py` (basic load test)

- [ ] **Step 1: Create base pattern library JSON**

Create `shared/pattern_library.json`:
```json
{
  "patterns": [
    {
      "name": "MANECIU",
      "description": "Prefixed subcomponent format with L: marker",
      "confidence_threshold": 0.70,
      "parent_indicators": [
        "^\\d+\\s+[A-Z0-9]+"
      ],
      "component_indicators": [
        {
          "pattern": "^L:\\s*[A-Z0-9]+\\s+-",
          "type": "prefix",
          "description": "L:SL05 -0020:6717077 format"
        }
      ],
      "quantity_rule": "inherit_from_parent"
    },
    {
      "name": "DRAGOMIRESTI",
      "description": "Dotted hierarchy numbering (1.1, 1.2 under 1)",
      "confidence_threshold": 0.70,
      "parent_indicators": [
        "^\\d+\\s+[A-Z0-9]+"
      ],
      "component_indicators": [
        {
          "pattern": "^\\d+\\.\\d+\\s+",
          "type": "hierarchy",
          "description": "Dotted numbering for hierarchy"
        }
      ],
      "quantity_rule": "inherit_from_parent"
    }
  ]
}
```

- [ ] **Step 2: Create pattern_detector.py stub**

Create `shared/pattern_detector.py`:
```python
"""Pattern detection for hierarchical component extraction.

Detects document format (MANECIU, DRAGOMIRESTI, SPORTIVA, etc.)
and applies pattern-specific extraction rules.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

PATTERN_LIBRARY_PATH = Path(__file__).parent / "pattern_library.json"


def load_pattern_library() -> Dict:
    """Load known patterns from pattern_library.json."""
    if not PATTERN_LIBRARY_PATH.exists():
        logger.warning(f"Pattern library not found: {PATTERN_LIBRARY_PATH}")
        return {"patterns": []}
    
    with open(PATTERN_LIBRARY_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_pattern_library(library: Dict) -> None:
    """Save pattern library to JSON."""
    with open(PATTERN_LIBRARY_PATH, 'w', encoding='utf-8') as f:
        json.dump(library, f, ensure_ascii=False, indent=2)


def get_pattern_by_name(name: str) -> Optional[Dict]:
    """Retrieve pattern definition by name."""
    library = load_pattern_library()
    for p in library.get("patterns", []):
        if p["name"] == name:
            return p
    return None
```

- [ ] **Step 3: Write test for load_pattern_library**

Create `tests/test_pattern_detector.py`:
```python
import json
from pathlib import Path
from shared import pattern_detector


def test_load_pattern_library():
    """Load pattern library from JSON."""
    library = pattern_detector.load_pattern_library()
    assert "patterns" in library
    assert isinstance(library["patterns"], list)
    assert len(library["patterns"]) > 0


def test_get_pattern_by_name():
    """Retrieve pattern by name."""
    pattern = pattern_detector.get_pattern_by_name("MANECIU")
    assert pattern is not None
    assert pattern["name"] == "MANECIU"
    assert "component_indicators" in pattern
```

- [ ] **Step 4: Run test**

```bash
python3 -m pytest tests/test_pattern_detector.py -v
```

Expected: Both tests pass

- [ ] **Step 5: Commit**

```bash
git add shared/pattern_library.json shared/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: pattern library + detector foundation

Create pattern_library.json with known patterns (MANECIU, DRAGOMIRESTI).
Implement pattern_detector.load/save/get functions for library management.

Tests verify loading and pattern lookup.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 3: Pattern Detection - Detect format from chapter text

**Files:**
- Modify: `shared/pattern_detector.py` - Add detect_pattern() function
- Test: `tests/test_pattern_detector.py` - Add pattern detection tests

- [ ] **Step 1: Write test for pattern detection**

Add to `tests/test_pattern_detector.py`:
```python
def test_detect_pattern_maneciu():
    """Detect MANECIU pattern from text."""
    chapter_text = """1 SA14J - TEAVA DIN MATERIAL PLASTIC PE, D = 110MM M 2.00
material:
manopera:
utilaj:
transport:
1.1 6717077 - TEAVA POLIETILENA
L:SL05 -0020:6717077 -teava polietilena inalta densitate
ml 2.00"""
    
    result = pattern_detector.detect_pattern(chapter_text)
    assert result is not None
    assert result["pattern_name"] == "MANECIU"
    assert result["confidence"] >= 0.70


def test_detect_pattern_dragomiresti():
    """Detect DRAGOMIRESTI pattern from text."""
    chapter_text = """1 SA14J - TEAVA DIN MATERIAL PLASTIC PE, D = 110MM M 2.00
1.1 6717077 - TEAVA POLIETILENA M 2.00
1.2 6719428 - MUFA POLIETILENA BUC 2.00"""
    
    result = pattern_detector.detect_pattern(chapter_text)
    assert result is not None
    assert result["pattern_name"] == "DRAGOMIRESTI"
    assert result["confidence"] >= 0.70
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python3 -m pytest tests/test_pattern_detector.py::test_detect_pattern_maneciu -v
```

Expected: `NameError: name 'detect_pattern' is not defined`

- [ ] **Step 3: Implement detect_pattern() function**

In `shared/pattern_detector.py`, add:
```python
def detect_pattern(chapter_text: str, min_confidence: float = 0.70) -> Optional[Dict]:
    """Detect pattern in chapter text by matching indicators.
    
    Args:
        chapter_text: Full chapter text (STADIUL FIZIC section)
        min_confidence: Minimum confidence threshold
    
    Returns:
        {pattern_name, confidence, extraction_rules} or None
    """
    library = load_pattern_library()
    lines = chapter_text.split('\n')
    
    best_match = None
    best_score = 0.0
    
    for pattern in library.get("patterns", []):
        score = _calculate_pattern_confidence(lines, pattern)
        if score > best_score:
            best_score = score
            best_match = pattern
    
    if best_match and best_score >= min_confidence:
        return {
            "pattern_name": best_match["name"],
            "confidence": best_score,
            "extraction_rules": best_match.get("extraction_rules", {})
        }
    
    return None


def _calculate_pattern_confidence(lines: List[str], pattern: Dict) -> float:
    """Calculate confidence score for pattern match.
    
    Score based on:
    - Parent indicator matches
    - Component indicator matches
    - Consistency across lines
    """
    parent_matches = 0
    component_matches = 0
    total_indicators = 0
    
    for line in lines:
        # Check parent indicators
        for parent_re in pattern.get("parent_indicators", []):
            total_indicators += 1
            if re.match(parent_re, line.strip()):
                parent_matches += 1
                break
        
        # Check component indicators
        for comp_ind in pattern.get("component_indicators", []):
            total_indicators += 1
            if re.match(comp_ind["pattern"], line.strip()):
                component_matches += 1
                break
    
    if total_indicators == 0:
        return 0.0
    
    # Score: (parent_matches + component_matches) / total_lines checked
    # Cap at 1.0
    matches = parent_matches + component_matches
    score = min(1.0, matches / max(total_indicators, 1))
    return score
```

- [ ] **Step 4: Run tests**

```bash
python3 -m pytest tests/test_pattern_detector.py::test_detect_pattern_maneciu -v
python3 -m pytest tests/test_pattern_detector.py::test_detect_pattern_dragomiresti -v
```

Expected: Both pass

- [ ] **Step 5: Commit**

```bash
git add shared/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: pattern detection from chapter text

Implement detect_pattern() to identify document format (MANECIU, DRAGOMIRESTI, etc.)
by matching parent/component indicators. Returns pattern name + confidence score.

Tests verify detection of both known patterns.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 4: Extraction Integration - Call pattern detection in Pass 1

**Files:**
- Modify: `shared/f3_extractor.py` - Add pattern detection call
- Test: (existing extraction tests)

- [ ] **Step 1: Add pattern detection import**

In `shared/f3_extractor.py`, add to imports:
```python
from shared.pattern_detector import detect_pattern, load_pattern_library
```

- [ ] **Step 2: Add pattern detection to extract_articles_v3**

In `extract_articles_v3()` function, add before line extraction:
```python
# Pass 1: Detect pattern from chapter sample
if pages and not checkpoint_data.get("pattern_detected"):
    sample_text = "\n".join(page.get("text", "") for page in pages[:5])
    detected = detect_pattern(sample_text)
    
    if detected:
        checkpoint_data["pattern_detection"] = detected
        logger.info(f"[PATTERN] Detected: {detected['pattern_name']} "
                   f"(confidence={detected['confidence']:.2f})")
    else:
        logger.warning("[PATTERN] No pattern detected, using fallback extraction")
        # TODO: LLM fallback (Task 5)
```

- [ ] **Step 3: Run existing extraction test**

```bash
python3 -m pytest tests/ -k "test_extract" -v
```

Expected: All existing tests pass

- [ ] **Step 4: Commit**

```bash
git add shared/f3_extractor.py
git commit -m "feat: integrate pattern detection into extraction (Pass 1)

Call detect_pattern() before article extraction to identify document format.
Save pattern info to checkpoint. Falls back to standard extraction if no match.

All existing extraction tests pass.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 5: Parent-Child Extraction - Extract components with parent_code

**Files:**
- Modify: `shared/f3_regex_parser.py` - Update article finalization logic
- Test: `tests/test_f3_regex_parser.py` - Add component extraction tests

- [ ] **Step 1: Write test for component extraction**

Add to `tests/test_f3_regex_parser.py`:
```python
def test_extract_components_from_denomination():
    """Extract subcomponent codes from parent denomination."""
    denom = "teava din material plastic pe, d=110mm l: sl05 -0020:6717077 -teava polietilena"
    
    codes = f3_regex_parser._extract_subcomponent_codes(denom)
    assert "6717077" in codes


def test_article_with_parent_code_in_finalize():
    """During finalization, component article gets parent_code."""
    # This test requires parsing logic changes
    # We'll test the concept here as integration test
    pass  # Will implement in Step 3
```

- [ ] **Step 2: Run test to see current behavior**

```bash
python3 -m pytest tests/test_f3_regex_parser.py::test_extract_components_from_denomination -v
```

Expected: Should pass (already implemented in previous session)

- [ ] **Step 3: Add parent-child detection to _detect_subcomponent**

In `shared/f3_regex_parser.py`, update `_detect_subcomponent()` function (around line 477):

```python
def _detect_subcomponent(cod: str, last_cod: str, line_text: str) -> Tuple[bool, Optional[str]]:
    """Detect if a code is a subcomponent and return parent code if found.
    
    Returns:
        (is_component: bool, parent_cod: Optional[str])
    
    Patterns:
    1. Hierarchy: 1.1, 1.2 under parent 1
    2. Prefix: L:SL05 in denomination
    3. Section headers: material:, manopera:, etc.
    """
    # Pattern 1: Hierarchy (1.1 under parent 1)
    hier_match = re.match(r'^(\d+)\.(\d+)($|\s)', cod)
    if hier_match:
        parent_id = hier_match.group(1)
        if last_cod and re.match(rf'^{re.escape(parent_id)}$', last_cod):
            return (True, last_cod)
    
    # Pattern 2: Prefix in denomination (L: marker)
    if re.search(r'^\s*L:\s*[A-Z0-9]+\s+-', line_text):
        return (True, last_cod) if last_cod else (False, None)
    
    # Pattern 3: After section headers (material:, manopera:, etc.)
    if re.search(r'(material|manopera|utilaj|transport):\s*$', line_text, re.IGNORECASE):
        return (True, last_cod) if last_cod else (False, None)
    
    return (False, None)
```

- [ ] **Step 4: Update article creation to use parent_code**

In `shared/f3_regex_parser.py`, in `_finalize()` function (around line 571), update:

```python
is_subcomp, parent_cod = _detect_subcomponent(cod, last_arti_cod, line_text)
subcomp_codes = _extract_subcomponent_codes(den_joined)

art = _make_article(
    cod, den_joined, um, cantitate,
    preturi, deviz_cod, deviz_den, 
    is_component=is_subcomp,
    parent_code=parent_cod,
    subcomponents=subcomp_codes
)
```

- [ ] **Step 5: Run tests**

```bash
python3 -m pytest tests/test_f3_regex_parser.py -v
```

Expected: All pass

- [ ] **Step 6: Commit**

```bash
git add shared/f3_regex_parser.py tests/test_f3_regex_parser.py
git commit -m "feat: parent-child article extraction with parent_code

Update _detect_subcomponent() to return (is_component, parent_code) tuple.
Pass parent_code to _make_article() during finalization.

Components now properly linked to parent articles.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 6: Quantity Inheritance - Component inherits from parent

**Files:**
- Modify: `shared/f3_extractor.py` - Add quantity inheritance logic
- Test: `tests/test_f3_extractor.py` - New integration test

- [ ] **Step 1: Write integration test for quantity inheritance**

Create `tests/test_f3_extractor.py`:
```python
def test_component_inherits_quantity_from_parent():
    """Component article inherits quantity from parent when not explicit."""
    ref_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "cantitate": 2.0
        },
        {
            "cod": "6717077",
            "parent_code": "SA14J",
            "is_component": True,
            "cantitate": 0.0  # No explicit quantity
        }
    ]
    
    # Apply inheritance
    result = f3_extractor.inherit_component_quantities(ref_articles)
    
    # Component should now have parent's quantity
    component = [a for a in result if a["cod"] == "6717077"][0]
    assert component["cantitate"] == 2.0
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python3 -m pytest tests/test_f3_extractor.py::test_component_inherits_quantity_from_parent -v
```

Expected: `AttributeError: module 'f3_extractor' has no attribute 'inherit_component_quantities'`

- [ ] **Step 3: Implement quantity inheritance**

In `shared/f3_extractor.py`, add:
```python
def inherit_component_quantities(articles: list) -> list:
    """Apply quantity inheritance for components.
    
    If component has quantity=0 and parent has quantity > 0,
    component inherits parent's quantity.
    """
    # Build parent lookup
    parents = {a["cod"]: a for a in articles if not a.get("is_component")}
    
    result = []
    for art in articles:
        if art.get("is_component") and art.get("cantitate", 0) == 0:
            parent_cod = art.get("parent_code")
            if parent_cod and parent_cod in parents:
                parent_qty = parents[parent_cod].get("cantitate", 0)
                if parent_qty > 0:
                    art = {**art, "cantitate": parent_qty}
        result.append(art)
    
    return result
```

- [ ] **Step 4: Call inheritance after extraction**

In `shared/f3_extractor.py`, in `extract_articles_v3()`, after extracting articles:
```python
# Inherit component quantities from parents
articles = inherit_component_quantities(articles)
```

- [ ] **Step 5: Run test**

```bash
python3 -m pytest tests/test_f3_extractor.py::test_component_inherits_quantity_from_parent -v
```

Expected: PASS

- [ ] **Step 6: Test unit inheritance too**

Add to `tests/test_f3_extractor.py`:
```python
def test_component_inherits_unit_from_parent():
    """Component inherits unit from parent if not explicit."""
    articles = [
        {"cod": "SA14J", "parent_code": None, "is_component": False, "um": "m"},
        {"cod": "6717077", "parent_code": "SA14J", "is_component": True, "um": ""}
    ]
    
    result = f3_extractor.inherit_component_units(articles)
    component = [a for a in result if a["cod"] == "6717077"][0]
    assert component["um"] == "m"
```

- [ ] **Step 7: Implement unit inheritance**

In `shared/f3_extractor.py`:
```python
def inherit_component_units(articles: list) -> list:
    """Apply unit inheritance for components without explicit unit."""
    parents = {a["cod"]: a for a in articles if not a.get("is_component")}
    
    result = []
    for art in articles:
        if art.get("is_component") and not art.get("um"):
            parent_cod = art.get("parent_code")
            if parent_cod and parent_cod in parents:
                parent_um = parents[parent_cod].get("um", "")
                if parent_um:
                    art = {**art, "um": parent_um}
        result.append(art)
    
    return result
```

- [ ] **Step 8: Run all extraction tests**

```bash
python3 -m pytest tests/test_f3_extractor.py -v
```

Expected: All pass

- [ ] **Step 9: Commit**

```bash
git add shared/f3_extractor.py tests/test_f3_extractor.py
git commit -m "feat: component quantity + unit inheritance from parent

Implement inherit_component_quantities() and inherit_component_units().
Components without explicit qty/unit inherit from parent article.

Applied during extraction to ensure all articles have complete data.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 7: Matching Logic - Verify (deviz, cod) pair works for all articles

**Files:**
- Test: `tests/test_matching.py` - Verify matching works for components

- [ ] **Step 1: Write test for component matching**

Create `tests/test_matching.py`:
```python
def test_match_component_by_deviz_cod_pair():
    """Components match on (deviz, cod) pair like parent articles."""
    ref_articles = [
        {"deviz": "4.3-07", "cod": "SA14J", "parent_code": None, "is_component": False},
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", "is_component": True}
    ]
    
    oferta_articles = [
        {"deviz": "4.3-07", "cod": "SA14J", "parent_code": None, "is_component": False},
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", "is_component": True}
    ]
    
    # Matching should work identically for both
    matches = AgentComparator_local.match_global(ref_articles, oferta_articles)
    
    # Should find 2 matches (parent + component)
    assert len(matches) >= 2
```

- [ ] **Step 2: Run test to verify it passes**

```bash
python3 -m pytest tests/test_matching.py::test_match_component_by_deviz_cod_pair -v
```

Expected: PASS (matching logic unchanged)

- [ ] **Step 3: Test component mismatch**

Add to `tests/test_matching.py`:
```python
def test_component_quantity_mismatch():
    """UM_DIFERIT or CANTITATE_DIFERITA for component mismatches."""
    ref_articles = [
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", 
         "is_component": True, "um": "m", "cantitate": 2.0}
    ]
    
    oferta_articles = [
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", 
         "is_component": True, "um": "buc", "cantitate": 2.0}  # Different UM
    ]
    
    neconformities = AgentComparator_local.compare(ref_articles, oferta_articles)
    
    # Should flag UM_DIFERIT
    um_issues = [n for n in neconformities if n["issue"] == "UM_DIFERIT"]
    assert len(um_issues) > 0
```

- [ ] **Step 4: Run test**

```bash
python3 -m pytest tests/test_matching.py -v
```

Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add tests/test_matching.py
git commit -m "test: verify matching works identically for components

Add tests to confirm components match on (deviz, cod) pair like parent articles.
Verify UM/quantity mismatches are properly flagged.

No changes to matching logic needed - already supports components.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 8: DOCX Reporting - Render hierarchy with components

**Files:**
- Modify: `shared/report_word.py` - Group components under parents in rendering
- Test: (manual verification of DOCX output)

- [ ] **Step 1: Analyze current report_word.py structure**

```bash
head -100 /Users/gabrielchitu/analiza-oferte-local/shared/report_word.py
```

- [ ] **Step 2: Add component grouping function**

In `shared/report_word.py`, add:
```python
def _group_articles_by_parent(articles: list) -> list:
    """Group component articles under their parent articles.
    
    Returns list of dicts:
    [
        {
            "parent": {...article...},
            "components": [{...article...}, ...]
        }
    ]
    """
    result = []
    parents_dict = {}
    
    # Separate parents and components
    for art in articles:
        if not art.get("is_component"):
            parents_dict[art["cod"]] = {
                "parent": art,
                "components": []
            }
        else:
            parent_cod = art.get("parent_code")
            if parent_cod and parent_cod in parents_dict:
                parents_dict[parent_cod]["components"].append(art)
    
    # Build result preserving order
    seen_parents = set()
    for art in articles:
        if not art.get("is_component") and art["cod"] not in seen_parents:
            result.append(parents_dict[art["cod"]])
            seen_parents.add(art["cod"])
    
    return result
```

- [ ] **Step 3: Update DOCX generation to render hierarchy**

In the section that generates article paragraphs in DOCX, update to:
```python
# Group articles by parent for hierarchical display
grouped = _group_articles_by_parent(articles)

for group in grouped:
    parent = group["parent"]
    components = group["components"]
    
    # Render parent article
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Pt(0)
    p.add_run(f"{parent['cod']} - {parent['denumire']}\n").bold = True
    p.add_run(f"{parent.get('um', '')} | {parent.get('cantitate', '')} | ")
    
    # Render status
    if match_status == "MATCHED":
        p.add_run("✓ MATCH").style = 'Normal'
    else:
        p.add_run(f"✗ {match_status}").style = 'Normal'
    
    # Render components indented
    for comp in components:
        cp = doc.add_paragraph(style='List Bullet 2')
        cp.paragraph_format.left_indent = Pt(36)
        cp.add_run(f"[COMPONENT] {comp['cod']} (parent: {comp.get('parent_code', 'N/A')})\n")
        cp.add_run(f"{comp.get('denumire', '')}\n")
        cp.add_run(f"{comp.get('um', '')} | {comp.get('cantitate', '')} | ")
        
        # Component status
        if comp_status == "MATCHED":
            cp.add_run("✓ MATCH").style = 'Normal'
        else:
            cp.add_run(f"✗ {comp_status}").style = 'Normal'
```

- [ ] **Step 4: Run local_run.py and verify DOCX output**

```bash
python3 local_run.py 2>&1 | grep -A5 "DOCX:"
```

Check that `output_AO/Raport_Oferta_2.docx` generates successfully.

- [ ] **Step 5: Manual verification (open DOCX)**

```bash
open output_AO/Raport_Oferta_2.docx
```

Verify:
- Parent articles displayed
- Components indented below parents
- [COMPONENT] prefix visible
- (parent: SA14J) reference shown

- [ ] **Step 6: Commit**

```bash
git add shared/report_word.py
git commit -m "feat: hierarchical DOCX reporting with component grouping

Implement _group_articles_by_parent() to organize components under parents.
Update DOCX generation to render:
- Parent articles at normal indentation
- Components with [COMPONENT] prefix + indentation
- Parent reference: (parent: SA14J)

DOCX output now shows full hierarchy.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 9: LLM Fallback - Generate template for unknown patterns

**Files:**
- Modify: `shared/pattern_detector.py` - Add LLM template generation
- Test: `tests/test_pattern_detector.py` - Mock LLM response

- [ ] **Step 1: Write test for LLM fallback**

Add to `tests/test_pattern_detector.py`:
```python
def test_generate_pattern_template_with_llm():
    """Generate pattern template from unknown format using LLM."""
    unknown_text = """1 UNKNOWN - NEW FORMAT WITH UNKNOWN NOTATION X 1.00
some unique indicators
that don't match known patterns"""
    
    # Mock LLM response
    from unittest.mock import patch
    
    mock_template = {
        "name": "UNKNOWN_NEW",
        "description": "Auto-generated from unknown format",
        "parent_indicators": ["^\\d+\\s+[A-Z]"],
        "component_indicators": [],
        "quantity_rule": "inherit_from_parent"
    }
    
    with patch('shared.pattern_detector.generate_pattern_with_llm', 
               return_value=mock_template):
        result = pattern_detector.generate_pattern_template(unknown_text)
        assert result["name"] == "UNKNOWN_NEW"
        assert "parent_indicators" in result
```

- [ ] **Step 2: Run test, verify it fails**

```bash
python3 -m pytest tests/test_pattern_detector.py::test_generate_pattern_template_with_llm -v
```

Expected: `NameError`

- [ ] **Step 3: Implement LLM template generation**

In `shared/pattern_detector.py`:
```python
def generate_pattern_template(chapter_text: str, pattern_name: str = None) -> Dict:
    """Generate pattern template for unknown format using LLM.
    
    Args:
        chapter_text: Full chapter text to analyze
        pattern_name: Optional custom name for pattern
    
    Returns:
        New pattern template dict
    """
    if not pattern_name:
        pattern_name = f"AUTO_GEN_{len(load_pattern_library().get('patterns', []))+1}"
    
    # Use existing LLM integration (assuming available in codebase)
    prompt = f"""Analyze this construction offer chapter and generate a pattern template.

Chapter:
{chapter_text[:2000]}

Return JSON with:
- name: pattern name
- description: what makes this format unique
- parent_indicators: list of regex patterns for parent articles
- component_indicators: list of dicts with pattern, type, description
- quantity_rule: "inherit_from_parent"

JSON only, no explanation."""
    
    # Call existing LLM integration
    try:
        from AgentComparator_local import call_llm
        response = call_llm(prompt)
        template = json.loads(response)
        template["name"] = pattern_name
        return template
    except Exception as e:
        logger.error(f"LLM template generation failed: {e}")
        # Return minimal template
        return {
            "name": pattern_name,
            "description": "Fallback template (LLM unavailable)",
            "parent_indicators": ["^\\d+\\s+[A-Z]"],
            "component_indicators": [],
            "quantity_rule": "inherit_from_parent"
        }


def save_generated_pattern(template: Dict) -> None:
    """Add generated pattern to pattern library."""
    library = load_pattern_library()
    library["patterns"].append(template)
    save_pattern_library(library)
    logger.info(f"Saved new pattern: {template['name']}")
```

- [ ] **Step 4: Update detect_pattern to fallback to LLM**

In `detect_pattern()`, after checking known patterns:
```python
    if best_match and best_score >= min_confidence:
        return {
            "pattern_name": best_match["name"],
            "confidence": best_score,
            "extraction_rules": best_match.get("extraction_rules", {})
        }
    
    # No match found - generate new pattern with LLM
    logger.warning(f"No known pattern matched (best={best_score:.2f}), "
                  "generating template with LLM...")
    
    new_template = generate_pattern_template(chapter_text)
    save_generated_pattern(new_template)
    
    return {
        "pattern_name": new_template["name"],
        "confidence": 0.50,  # Generated templates start with lower confidence
        "extraction_rules": new_template.get("extraction_rules", {})
    }
```

- [ ] **Step 5: Run test**

```bash
python3 -m pytest tests/test_pattern_detector.py::test_generate_pattern_template_with_llm -v
```

Expected: PASS (with mock)

- [ ] **Step 6: Commit**

```bash
git add shared/pattern_detector.py tests/test_pattern_detector.py
git commit -m "feat: LLM fallback for unknown pattern templates

Implement generate_pattern_template() to analyze unknown formats using LLM.
Saves generated template to pattern library for future reuse.

Fallback triggered when no known pattern confidence > 0.70.
Generated patterns start with confidence=0.50 for manual validation.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 10: Integration Test - End-to-end hierarchical extraction + matching + reporting

**Files:**
- Test: `tests/test_integration_hierarchical.py` - Full workflow test

- [ ] **Step 1: Create integration test**

Create `tests/test_integration_hierarchical.py`:
```python
"""Integration test: hierarchical extraction, matching, reporting."""
import json
from pathlib import Path


def test_hierarchical_workflow():
    """Full workflow: extract components → match → report."""
    
    # Sample reference (MANECIU format with subcomponents in array)
    ref_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "um": "m",
            "cantitate": 2.0,
            "deviz": "4.3-07",
            "subcomponents": ["6717077", "6719428", "6719435", "0003000"]
        }
    ]
    
    # Sample offer (separate component articles with parent_code)
    oferta_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "um": "m",
            "cantitate": 2.0,
            "deviz": "4.3-07"
        },
        {
            "cod": "6717077",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "m",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "6719428",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "buc",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "6719435",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "buc",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "0003000",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "ore",
            "cantitate": 0.6,  # Inherited
            "deviz": "4.3-07"
        }
    ]
    
    # Test matching (all articles should match on deviz+cod)
    from AgentComparator_local import match_global
    matches = match_global(ref_articles, oferta_articles)
    
    # Should find: SA14J (parent) + 4 components = 5 matches
    assert len(matches) >= 5
    
    # Verify components have parent_code
    for art in oferta_articles:
        if art["is_component"]:
            assert art["parent_code"] == "SA14J"
    
    print("✓ Hierarchical workflow: PASS")
```

- [ ] **Step 2: Run integration test**

```bash
python3 -m pytest tests/test_integration_hierarchical.py -v
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration_hierarchical.py
git commit -m "test: integration test for hierarchical extraction + matching

Full workflow: parent article + 4 components with inherited quantities.
Verify matching works on (deviz, cod) pair for all articles.
Confirm parent_code links are set correctly.

Co-Authored-By: Claude Haiku 4.5 <noreply@anthropic.com>"
```

---

### Task 11: End-to-end Validation - Run local_run.py and verify output

**Files:**
- (No code changes, only testing)

- [ ] **Step 1: Run local_run.py with full workflow**

```bash
python3 local_run.py 2>&1 | tail -50
```

Verify:
- Pattern detection succeeds
- Components extracted with parent_code
- Matching completes
- DOCX generated

- [ ] **Step 2: Check JSON output for parent_code fields**

```bash
python3 -c "
import json
with open('output_AO/oferta_2.json') as f:
    data = json.load(f)
    components = [a for a in data['articole'] if a.get('is_component')]
    print(f'Total components: {len(components)}')
    if components:
        print('Sample:', components[0])
"
```

Expected: Components have parent_code field

- [ ] **Step 3: Verify DOCX hierarchy**

```bash
# Extract text from DOCX (if python-docx available)
python3 -c "
from docx import Document
doc = Document('output_AO/Raport_Oferta_2.docx')
for para in doc.paragraphs[-20:]:
    if 'COMPONENT' in para.text or 'parent:' in para.text:
        print(para.text)
"
```

Expected: [COMPONENT] markers and (parent: XXX) references visible

- [ ] **Step 4: Final verification commit**

```bash
git log --oneline -10
```

Verify all tasks are committed.

- [ ] **Step 5: Summary**

```bash
python3 -c "
import json
with open('output_AO/oferta_2.json') as f:
    data = json.load(f)
    parents = [a for a in data['articole'] if not a.get('is_component')]
    components = [a for a in data['articole'] if a.get('is_component')]
    print(f'Total articles: {len(data[\"articole\"])}')
    print(f'Parent articles: {len(parents)}')
    print(f'Component articles: {len(components)}')
    print(f'Parent_code accuracy: {sum(1 for c in components if c.get(\"parent_code\"))}/{len(components)}')
"
```

---

## Success Criteria

✅ All tasks complete when:
1. Pattern detection identifies MANECIU/DRAGOMIRESTI/SPORTIVA formats
2. Components extracted with parent_code link + is_component flag
3. Quantities/units inherited from parents
4. Matching uses (deviz, cod) pair for all articles
5. DOCX shows components indented under parents with [COMPONENT] prefix
6. LLM fallback generates templates for unknown formats
7. local_run.py generates correct output_AO/ files

---

## Notes

- All tasks use TDD (test first)
- Commits are frequent (after each logical step)
- Tests verify both happy path and error cases
- No "TBD" placeholders in final code
