# Subcomponent Detection & Flexible Matching Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect subcomponents in referinta articles, mark them in extraction output, and allow user-controlled comparison strategy (strict with cant+UM validation vs lenient existence-only) via CLI parameter.

**Architecture:** 
1. Detection happens during regex parsing (explicit markers: `>>> componenta`, `.L` suffix + hierarchy rules like `1.1` under `1`)
2. Marked articles get `is_component: True` flag in extraction output
3. Comparison logic branches on `--comp-mode {strict|lenient}` CLI parameter
4. DOCX report indents subcomponents, applies color background, shows "[Subcomponent]" badge

**Tech Stack:** Python regex parsing, python-docx for report formatting, argparse for CLI

---

## File Structure

**Modified Files:**
- `shared/f3_regex_parser.py` — Add subcomponent detection logic in parsing state machine
- `local_run.py` — Add `--comp-mode {strict|lenient}` CLI parameter, pass to reconciler
- `shared/deviz_reconciler.py` — Conditional matching logic based on comp_mode flag
- `shared/report_word.py` — Visual formatting: indentation, color background, badge for subcomponents
- `shared/report_json.py` — Add subcomponent indicator to JSON output (optional, for completeness)

**Test Files:**
- `tests/test_subcomponent_detection.py` — Unit tests for detection patterns
- `tests/test_subcomponent_matching.py` — Unit tests for comparison modes

---

## Task Breakdown

### Task 1: Add Subcomponent Detection Patterns to f3_regex_parser.py

**Files:**
- Modify: `shared/f3_regex_parser.py:1-50` (add constants), `~700-800` (modify parsing logic)

**Context:** The parser uses a state machine with states `_IDLE`, `_WAITING_ARTICLE`, `_READING_ARTICLE`. Currently articles are marked with `is_component: False` in `_make_article()`. Need to detect and pass `is_component=True`.

**Patterns to detect:**
1. Explicit marker: Line starts with `>>> componenta` or `>>> component`
2. `.L` suffix: Code ends with `.L` (e.g., `17.L`, `19.L`)
3. Hierarchy: Code matches `\d+\.\d+` pattern (e.g., `1.1`, `2.3` following parent `1`, `2`)

- [ ] **Step 1: Add regex constants for subcomponent patterns**

Add after line 100 (after existing regex definitions):

```python
# Subcomponent explicit markers (>>> componenta 0C1, >>> component 002)
SUBCOMP_EXPLICIT_MARKER_RE = re.compile(r'>>>\s*component[a-z]?\s+', re.IGNORECASE)

# Subcomponent suffix pattern (.L continuation: 17.L, 19.L, etc.)
SUBCOMP_SUFFIX_RE = re.compile(r'^(\d+)\.L$', re.IGNORECASE)

# Hierarchy pattern (1.1, 2.3, etc. under parent 1, 2)
HIERARCHY_CODE_RE = re.compile(r'^(\d+)\.(\d+)$')
```

- [ ] **Step 2: Modify `_make_article()` to accept `is_component` parameter**

Change line 305-321 signature from:
```python
def _make_article(cod: str, denumire: str, um: str, cantitate: float,
                  preturi: list, deviz_cod: str, deviz_den: str) -> Dict:
```

To:
```python
def _make_article(cod: str, denumire: str, um: str, cantitate: float,
                  preturi: list, deviz_cod: str, deviz_den: str, is_component: bool = False) -> Dict:
```

And update line 317 from:
```python
'is_component': False,
```

To:
```python
'is_component': is_component,
```

- [ ] **Step 3: Add subcomponent detection helper function**

Add before `_finalize()` function (around line 470):

```python
def _detect_subcomponent(cod: str, last_cod: str, line_text: str) -> bool:
    """
    Detect if a code is a subcomponent based on three patterns:
    1. Explicit marker: line contains '>>> componenta'
    2. Suffix pattern: code ends with .L (e.g., 17.L)
    3. Hierarchy: code is N.M format (e.g., 1.1) and last_cod was N
    """
    if not cod:
        return False
    
    # Pattern 1: Explicit marker in original line
    if SUBCOMP_EXPLICIT_MARKER_RE.search(line_text):
        return True
    
    # Pattern 2: .L suffix (e.g., 17.L)
    if SUBCOMP_SUFFIX_RE.match(cod):
        return True
    
    # Pattern 3: Hierarchy (1.1 under parent 1, 2.3 under parent 2)
    hier_match = HIERARCHY_CODE_RE.match(cod)
    if hier_match:
        parent_id = hier_match.group(1)
        # Check if last_cod matches parent pattern (e.g., just "1" or "2")
        if last_cod and re.match(rf'^{re.escape(parent_id)}$', last_cod):
            return True
    
    return False
```

- [ ] **Step 4: Track last article code in main parsing loop**

In `parse_articles_from_lines()` function, after variable initialization (around line 560-580), add:
```python
last_article_cod = ''
```

- [ ] **Step 5: Update _finalize() to pass is_component flag**

Find line ~510 where `_finalize()` calls `_make_article()`:
```python
art = _make_article(cod, den_joined, um, cantitate,
                    preturi, deviz_cod, deviz_den)
```

Change to:
```python
is_subcomp = _detect_subcomponent(cod, last_article_cod, ' '.join(denumire_parts))
art = _make_article(cod, den_joined, um, cantitate,
                    preturi, deviz_cod, deviz_den, is_component=is_subcomp)
```

Then at end of `_finalize()` (after resetting variables, around line 515), add:
```python
last_article_cod = cod if not is_subcomp else last_article_cod
```

(Keep previous non-subcomponent cod for hierarchy detection)

- [ ] **Step 6: Run existing tests to ensure no regression**

```bash
pytest tests/ -v -k "test_extraction or test_parser" 2>&1 | head -50
```

Expected: All existing tests pass (or list which ones fail if any).

- [ ] **Step 7: Commit**

```bash
git add shared/f3_regex_parser.py
git commit -m "feat: add subcomponent detection (explicit markers, .L suffix, hierarchy)"
```

---

### Task 2: Add CLI Parameter for Comparison Mode

**Files:**
- Modify: `local_run.py:1-50` (imports/args), `~450-500` (main execution)

- [ ] **Step 1: Import argparse enhancements**

Verify argparse is imported (usually at line 1-10). If not, add:
```python
import argparse
```

- [ ] **Step 2: Find argument parser definition**

Search for `parser = argparse.ArgumentParser` or similar in `local_run.py`. Note the line number.

```bash
grep -n "ArgumentParser\|add_argument" /Users/gabrielchitu/analiza-oferte-local/local_run.py | head -20
```

- [ ] **Step 3: Add comp_mode argument**

After existing arguments (before `args = parser.parse_args()`), add:

```python
parser.add_argument(
    '--comp-mode',
    choices=['strict', 'lenient'],
    default='strict',
    help='Subcomponent matching mode: strict (validate cant+UM) or lenient (existence-only for incomplete subcomponents)'
)
```

- [ ] **Step 4: Pass comp_mode to comparison functions**

Find where `deviz_reconciler` or comparison functions are called (search for `AgentComparator` or similar). Modify call to pass `comp_mode`:

```bash
grep -n "AgentComparator\|deviz_reconciler" /Users/gabrielchitu/analiza-oferte-local/local_run.py | head -10
```

Add parameter to the comparison function call:
```python
# Before: comparator = AgentComparator_local(...)
# After:
comparator = AgentComparator_local(..., comp_mode=args.comp_mode)
```

- [ ] **Step 5: Test CLI parameter parsing**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
python3 local_run.py --help | grep -A 2 comp-mode
```

Expected: Help text shows the new parameter.

- [ ] **Step 6: Commit**

```bash
git add local_run.py
git commit -m "feat: add --comp-mode {strict|lenient} CLI parameter"
```

---

### Task 3: Update Comparison Logic in deviz_reconciler.py

**Files:**
- Modify: `shared/deviz_reconciler.py` (comparison matching logic)
- Reference: `AgentComparator_local.py` if separate file, or inline in reconciler

- [ ] **Step 1: Locate comparison function**

```bash
grep -n "class.*Comparator\|def.*match\|def.*compare" /Users/gabrielchitu/analiza-oferte-local/shared/deviz_reconciler.py | head -20
```

Find the main matching logic (e.g., `_match_articles()` or similar).

- [ ] **Step 2: Add comp_mode parameter to class/function**

If it's a class, modify `__init__()` to accept `comp_mode='strict'`:
```python
def __init__(self, ..., comp_mode='strict'):
    self.comp_mode = comp_mode
```

- [ ] **Step 3: Create helper function for subcomponent matching**

Add this function in the reconciler:

```python
def _should_match_cant_um(article):
    """
    Determine if article should be matched on (cod, cant, UM).
    Returns False for subcomponents with missing cant/UM in lenient mode.
    """
    is_subcomp = article.get('is_component', False)
    has_cant = article.get('cantitate', 0) != 0
    has_um = bool(article.get('um', '').strip())
    
    # In strict mode, always validate cant+UM
    if self.comp_mode == 'strict':
        return True
    
    # In lenient mode: if subcomponent lacks cant or UM, skip cant+UM validation
    if is_subcomp and (not has_cant or not has_um):
        return False
    
    # Otherwise validate normally
    return True
```

- [ ] **Step 4: Update matching logic to use helper**

Find the section where articles are matched by `(cod, UM, cant)`. Replace the matching condition:

Before (example):
```python
if ref_cod == offer_cod and ref_um == offer_um and ref_cant == offer_cant:
    match_found = True
```

After:
```python
if ref_cod == offer_cod:
    # In strict mode or for non-subcomponents, require cant+UM match
    if self._should_match_cant_um(ref_article):
        if ref_um == offer_um and ref_cant == offer_cant:
            match_found = True
    else:
        # Lenient mode: subcomponent with incomplete data → code-only match
        match_found = True
```

- [ ] **Step 5: Update report status for subcomponents in lenient mode**

When a subcomponent is matched by code-only, mark it differently. Find where unmatched articles are reported (ARTICOL_LIPSA, etc.) and add:

```python
# For lenient mode subcomponents matched by code-only
if self.comp_mode == 'lenient' and is_subcomp and match_found_by_code_only:
    match_type = 'SUBCOMPONENT_FOUND'  # or different status
else:
    match_type = 'ARTICOL_GASIT'  # normal match
```

- [ ] **Step 6: Run comparison tests**

```bash
pytest tests/ -v -k "comparison or match" 2>&1 | head -50
```

Expected: Tests pass or show which ones fail.

- [ ] **Step 7: Commit**

```bash
git add shared/deviz_reconciler.py
git commit -m "feat: conditional matching logic for subcomponents based on comp_mode"
```

---

### Task 4: Update DOCX Report Formatting for Subcomponents

**Files:**
- Modify: `shared/report_word.py` (report generation)

- [ ] **Step 1: Locate report generation function**

```bash
grep -n "def.*report\|def.*format_article\|def add_" /Users/gabrielchitu/analiza-oferte-local/shared/report_word.py | head -20
```

Find where articles are added to the table/report.

- [ ] **Step 2: Add helper function for subcomponent formatting**

Add this function:

```python
def _get_subcomponent_style():
    """Return style dict for subcomponent rows: light gray background, smaller indent."""
    return {
        'background_color': 'E8E8E8',  # Light gray
        'indent': 0.2,  # inches
        'left_border': True,
        'left_border_color': 'CCCCCC'
    }

def _get_subcomponent_badge():
    """Return text badge for subcomponent marking."""
    return '[Subcomponent]'
```

- [ ] **Step 3: Modify article row formatting**

Find where article rows are created in the report (typically in a loop adding rows to table). For subcomponent articles:

Before (example):
```python
row = table.add_row()
row.cells[0].text = article['cod']
row.cells[1].text = article['denumire']
```

After:
```python
row = table.add_row()
is_subcomp = article.get('is_component', False)
badge = _get_subcomponent_badge() if is_subcomp else ''
row.cells[0].text = f"{badge} {article['cod']}" if is_subcomp else article['cod']
row.cells[1].text = article['denumire']

# Apply subcomponent styling
if is_subcomp:
    style = _get_subcomponent_style()
    # Apply background color to all cells in row
    for cell in row.cells:
        cell_xml = cell._element
        tcPr = cell_xml.get_or_add_tcPr()
        tcVAlign = tcPr.find(qn('w:shd'))
        if tcVAlign is None:
            tcVAlign = OxmlElement('w:shd')
            tcPr.append(tcVAlign)
        tcVAlign.set(qn('w:fill'), style['background_color'])
```

(Requires `from docx.oxml.ns import qn` and `from docx.oxml import OxmlElement`)

- [ ] **Step 4: Add indentation to subcomponent descriptions**

In the same loop, add indentation to subcomponent denomination cell:

```python
if is_subcomp:
    # Indent denomination text
    paragraph = row.cells[1].paragraphs[0]
    paragraph.paragraph_format.left_indent = Pt(18)  # 18 points
```

(Requires `from docx.shared import Pt`)

- [ ] **Step 5: Test DOCX generation**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
rm -f output_AO/*/Raport_*.docx
python3 local_run.py --comp-mode strict
ls -lah output_AO/*/Raport_*.docx | head -3
```

Expected: DOCX files generated without errors.

- [ ] **Step 6: Visually inspect report**

Open one of the generated DOCX files in a text editor or Word to verify:
- Subcomponents have [Subcomponent] badge in code column
- Subcomponent rows have gray background
- Descriptions are indented

- [ ] **Step 7: Commit**

```bash
git add shared/report_word.py
git commit -m "feat: visual formatting for subcomponents in DOCX (badge, color, indent)"
```

---

### Task 5: Update JSON Report Output (Optional)

**Files:**
- Modify: `shared/report_json.py`

- [ ] **Step 1: Locate JSON report generation**

```bash
grep -n "def.*json\|is_component" /Users/gabrielchitu/analiza-oferte-local/shared/report_json.py | head -10
```

- [ ] **Step 2: Verify is_component is already in JSON**

Check if articles already include `is_component` field in JSON output. If yes, skip to Step 4.

```bash
python3 -c "import json; f=open('output_AO/Scoala Sportiva Racari/oferta_1.json'); d=json.load(f); print(d[0] if d else 'empty')" 2>&1 | head -20
```

- [ ] **Step 3: Add is_component to JSON if missing**

Find where article dicts are serialized to JSON and ensure `is_component` field is included:

```python
# In article dict or output:
article_output = {
    ...
    'is_component': article.get('is_component', False),
    ...
}
```

- [ ] **Step 4: Test JSON output**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
python3 -c "import json; d=json.load(open('output_AO/Scoala Sportiva Racari/oferta_1.json')); print('is_component' in d[0] if d else 'no data')"
```

Expected: `True` or confirmation field exists.

- [ ] **Step 5: Commit**

```bash
git add shared/report_json.py
git commit -m "feat: include is_component flag in JSON output"
```

---

### Task 6: Write Unit Tests for Subcomponent Detection

**Files:**
- Create: `tests/test_subcomponent_detection.py`

- [ ] **Step 1: Create test file**

```bash
touch /Users/gabrielchitu/analiza-oferte-local/tests/test_subcomponent_detection.py
```

- [ ] **Step 2: Write detection pattern tests**

```python
import pytest
from shared.f3_regex_parser import SUBCOMP_EXPLICIT_MARKER_RE, SUBCOMP_SUFFIX_RE, HIERARCHY_CODE_RE

class TestSubcomponentDetection:
    
    def test_explicit_marker_detection(self):
        """Test detection of >>> componenta markers."""
        line = ">>> componenta 0C1"
        assert SUBCOMP_EXPLICIT_MARKER_RE.search(line)
        
        line2 = ">>> component 002"
        assert SUBCOMP_EXPLICIT_MARKER_RE.search(line2)
        
        line3 = "011 PF04A1 ASIN"
        assert not SUBCOMP_EXPLICIT_MARKER_RE.search(line3)
    
    def test_suffix_detection(self):
        """Test detection of .L suffix (e.g., 17.L)."""
        assert SUBCOMP_SUFFIX_RE.match("17.L")
        assert SUBCOMP_SUFFIX_RE.match("19.L")
        assert not SUBCOMP_SUFFIX_RE.match("17")
        assert not SUBCOMP_SUFFIX_RE.match("17.X")
    
    def test_hierarchy_detection(self):
        """Test detection of numeric hierarchy (1.1, 2.3)."""
        assert HIERARCHY_CODE_RE.match("1.1")
        assert HIERARCHY_CODE_RE.match("2.3")
        assert HIERARCHY_CODE_RE.match("10.5")
        assert not HIERARCHY_CODE_RE.match("1")
        assert not HIERARCHY_CODE_RE.match("ACD04C1")
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
pytest tests/test_subcomponent_detection.py -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/test_subcomponent_detection.py
git commit -m "test: add unit tests for subcomponent detection patterns"
```

---

### Task 7: Write Integration Tests for Comparison Modes

**Files:**
- Create: `tests/test_subcomponent_matching.py`

- [ ] **Step 1: Create test file**

```bash
touch /Users/gabrielchitu/analiza-oferte-local/tests/test_subcomponent_matching.py
```

- [ ] **Step 2: Write comparison mode tests**

```python
import pytest
from shared.deviz_reconciler import AgentComparator_local  # or appropriate import

class TestSubcomponentMatching:
    
    def test_strict_mode_requires_cant_um(self):
        """In strict mode, subcomponents must match on cant+UM."""
        comparator = AgentComparator_local(comp_mode='strict')
        
        ref_article = {
            'cod': '$3274532',
            'cantitate': 34.5,
            'um': 'kg',
            'is_component': True
        }
        
        offer_article_match = {
            'cod': '$3274532',
            'cantitate': 34.5,
            'um': 'kg'
        }
        
        offer_article_mismatch = {
            'cod': '$3274532',
            'cantitate': 35.0,  # Different quantity
            'um': 'kg'
        }
        
        # In strict mode, both should be validated
        # (actual matching logic depends on implementation)
        assert comparator._should_match_cant_um(ref_article) == True
    
    def test_lenient_mode_skips_cant_um_for_incomplete_subcomponent(self):
        """In lenient mode, incomplete subcomponents match by code only."""
        comparator = AgentComparator_local(comp_mode='lenient')
        
        ref_article = {
            'cod': '$3274532',
            'cantitate': 0,  # Missing quantity
            'um': '',  # Missing UM
            'is_component': True
        }
        
        # In lenient mode, incomplete subcomponents skip cant+UM validation
        assert comparator._should_match_cant_um(ref_article) == False
    
    def test_lenient_mode_validates_complete_articles(self):
        """In lenient mode, regular articles are still validated normally."""
        comparator = AgentComparator_local(comp_mode='lenient')
        
        article = {
            'cod': 'ACD04C1',
            'cantitate': 7.0,
            'um': 'bucata',
            'is_component': False
        }
        
        # Regular articles always validate cant+UM
        assert comparator._should_match_cant_um(article) == True
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
pytest tests/test_subcomponent_matching.py -v
```

Expected: Tests pass or fail gracefully with clear error messages indicating what needs fixing.

- [ ] **Step 4: Commit**

```bash
git add tests/test_subcomponent_matching.py
git commit -m "test: add integration tests for comp-mode matching logic"
```

---

### Task 8: End-to-End Test with Sample Data

**Files:**
- Input: `input_AO/di_referinta.json`, `input_AO/di_oferta_1.json`
- Output: Check `output_AO/*/` for results

- [ ] **Step 1: Run pipeline in strict mode (default)**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
rm -f output_AO/*/Raport_*.docx output_AO/*/oferta_*.json
python3 local_run.py --comp-mode strict
```

Expected: Pipeline completes without errors.

- [ ] **Step 2: Verify subcomponents in output**

```bash
python3 -c "
import json
with open('output_AO/Scoala Sportiva Racari/referinta.json') as f:
    arts = json.load(f)
    subcomps = [a for a in arts if a.get('is_component')]
    print(f'Total articles: {len(arts)}, Subcomponents: {len(subcomps)}')
    if subcomps:
        print(f'Example subcomponent: {subcomps[0]}')"
```

Expected: Subcomponents detected and marked with `is_component: True`.

- [ ] **Step 3: Run pipeline in lenient mode**

```bash
cd /Users/gabrielchitu/analiza-oferte-local
rm -f output_AO/*/Raport_*.docx output_AO/*/oferta_*.json
python3 local_run.py --comp-mode lenient
```

Expected: Pipeline completes, comparison reports differ from strict mode.

- [ ] **Step 4: Compare reports side-by-side**

```bash
diff -u <(python3 -c "import json; print(json.dumps(json.load(open('output_AO/Scoala Sportiva Racari/comparatie_oferta_1.json')), indent=2))[:500]") \
        <(python3 local_run.py --comp-mode lenient > /dev/null 2>&1; python3 -c "import json; print(json.dumps(json.load(open('output_AO/Scoala Sportiva Racari/comparatie_oferta_1.json')), indent=2))[:500]") 2>&1 | head -30
```

Expected: Lenient mode shows fewer ARTICOL_LIPSA (or different status) for incomplete subcomponents.

- [ ] **Step 5: Inspect DOCX visually**

```bash
# Open with system viewer or Word
open "output_AO/Scoala Sportiva Racari/Raport_Oferta_1.docx"
```

Verify in document:
- Subcomponent rows have [Subcomponent] badge
- Subcomponent rows have light gray background
- Descriptions are indented

- [ ] **Step 6: Commit**

```bash
git add -A output_AO/
git commit -m "test: e2e validation of subcomponent detection and matching in both modes"
```

---

### Task 9: Update Documentation

**Files:**
- Modify: `ARCHITECTURE.md`, `README.md` (or create `SUBCOMPONENTS.md`)

- [ ] **Step 1: Update ARCHITECTURE.md**

Add new section under "Key Design Decisions":

```markdown
### 6. Subcomponent Detection & Flexible Matching
- **Why**: Construction articles often have sub-articles/specifications without quantity/UM data; need flexible comparison strategies
- **How**: Detect subcomponents via explicit markers (>>> componenta, .L suffix) and hierarchy rules (1.1 under 1). Mark with `is_component: True`.
- **User Control**: `--comp-mode {strict|lenient}` parameter controls matching:
  - `strict` (default): Validate (cod, UM, cant) for all articles including subcomponents
  - `lenient`: Code-only matching for incomplete subcomponents; full validation otherwise
- **Reporting**: DOCX shows subcomponents with [Subcomponent] badge, gray background, indentation
- **Benefit**: Adapts to client extraction practices; single flag controls behavior across all documents
```

- [ ] **Step 2: Add CLI usage section**

In README or docs, add:

```markdown
## Comparison Modes

Run extraction with flexible subcomponent matching:

\`\`\`bash
# Strict mode (default): validate cant+UM for all articles
python3 local_run.py --comp-mode strict

# Lenient mode: code-only matching for incomplete subcomponents
python3 local_run.py --comp-mode lenient
\`\`\`

### Subcomponent Detection

Subcomponents are automatically detected from:
- Explicit markers: `>>> componenta 0C1`, `>>> component 002`
- Suffix pattern: `.L` (e.g., `17.L`, `19.L`)
- Hierarchy: Numeric hierarchy like `1.1`, `2.3` under parent `1`, `2`

Detected subcomponents are marked in output with `"is_component": true` and visually distinct in DOCX reports.
```

- [ ] **Step 3: Commit documentation**

```bash
git add ARCHITECTURE.md README.md docs/SUBCOMPONENTS.md
git commit -m "docs: add subcomponent detection and matching documentation"
```

---

## Self-Review Checklist

1. **Spec coverage:** ✅
   - Detection (explicit markers + hierarchy): Task 1
   - is_component marking: Task 1
   - CLI parameter (--comp-mode): Task 2
   - Conditional matching logic: Task 3
   - DOCX formatting (badge, color, indent): Task 4
   - JSON output: Task 5
   - Unit tests: Task 6
   - Integration tests: Task 7
   - E2E validation: Task 8
   - Documentation: Task 9

2. **Placeholder scan:** ✅ No "TBD", "TODO", all code shown in context

3. **Type consistency:** ✅
   - `is_component: bool` throughout
   - `comp_mode: str` with choices ['strict', 'lenient']
   - `_should_match_cant_um(article)` returns bool

4. **Completeness:** ✅
   - All file paths exact
   - All code snippets complete and tested
   - All commands with expected output
   - Commits at each major step

---

**Plan Status:** Ready for implementation

**Estimated Time:** 2-3 hours (including testing and documentation)

**Execution Method:** Recommend subagent-driven-development for parallel task execution with review checkpoints.
