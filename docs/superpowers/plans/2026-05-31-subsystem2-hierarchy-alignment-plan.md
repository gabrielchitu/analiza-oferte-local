# Subsystem 2: Hierarchy Alignment with pandas ffill — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to execute this plan task-by-task.

**Goal:** Fix parent-child article misalignments in v2 extraction using pandas operations and forward-fill logic

**Architecture:** 
- Input: v2 extracted articles (oferta_N_v2.json) with parent_nr, is_component, nr fields
- Process: Detect broken hierarchies → ffill missing parents → validate parent-child chains
- Output: Corrected articles JSON with fixed parent_nr + hierarchy_corrected flag

**Tech Stack:** pandas, numpy, v2 extraction output (JSON)

---

## Task 1: Analyze v2 Extraction Hierarchy Issues

**Files:**
- Read: `output_AO/Drum_Tatarani/oferta_1_v2.json`
- Create: `shared/hierarchy_analyzer.py`
- Test: `tests/test_hierarchy_analyzer.py`

- [ ] **Step 1: Write test for hierarchy detection**

```python
def test_detect_broken_hierarchy():
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},  # Missing parent context
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Should be parent_nr="2"
    ]
    issues = detect_broken_hierarchy(articles)
    assert len(issues) == 1
    assert issues[0]["nr"] == "2.1"
    assert issues[0]["issue"] == "MISSING_PARENT"
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
pytest tests/test_hierarchy_analyzer.py::test_detect_broken_hierarchy -v
```

Expected: FAIL — function not found

- [ ] **Step 3: Implement hierarchy analyzer**

```python
# shared/hierarchy_analyzer.py
import pandas as pd
from typing import List, Dict

def detect_broken_hierarchy(articles: List[Dict]) -> List[Dict]:
    """
    Detect broken parent-child relationships.
    Returns list of issues: {nr, parent_nr, issue, severity}
    """
    df = pd.DataFrame(articles)
    df['nr_base'] = df['nr'].str.split('.').str[0]
    df['depth'] = df['nr'].str.count(r'\.') + 1
    
    issues = []
    
    # Issue 1: Component with no parent_nr
    no_parent_comps = df[(df['is_component'] == True) & (df['parent_nr'].isna())]
    for idx, row in no_parent_comps.iterrows():
        issues.append({
            "index": idx,
            "nr": row['nr'],
            "parent_nr": None,
            "issue": "MISSING_PARENT",
            "severity": "HIGH"
        })
    
    # Issue 2: Parent reference doesn't exist in articles
    for idx, row in df.iterrows():
        if pd.notna(row['parent_nr']):
            parent_exists = (df['nr'] == row['parent_nr']).any()
            if not parent_exists:
                issues.append({
                    "index": idx,
                    "nr": row['nr'],
                    "parent_nr": row['parent_nr'],
                    "issue": "PARENT_NOT_FOUND",
                    "severity": "HIGH"
                })
    
    return issues

def fix_hierarchy_ffill(articles: List[Dict]) -> List[Dict]:
    """
    Fix missing parents using forward-fill logic.
    Strategy: propagate last non-null parent_nr through component sequences.
    """
    df = pd.DataFrame(articles).copy()
    
    # For each article, if is_component=True and parent_nr is null,
    # ffill from previous parent_nr
    df['parent_nr_ffill'] = df['parent_nr'].fillna(method='ffill')
    
    # Update parent_nr where needed
    mask = (df['is_component'] == True) & (df['parent_nr'].isna())
    df.loc[mask, 'parent_nr'] = df.loc[mask, 'parent_nr_ffill']
    
    # Mark corrected articles
    df['hierarchy_corrected'] = mask
    
    return df.drop(columns=['parent_nr_ffill']).to_dict('records')
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
pytest tests/test_hierarchy_analyzer.py::test_detect_broken_hierarchy -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/hierarchy_analyzer.py tests/test_hierarchy_analyzer.py
git commit -m "feat: add hierarchy analyzer with broken-hierarchy detection"
```

---

## Task 2: Implement Hierarchy Corrector with pandas

**Files:**
- Modify: `shared/hierarchy_analyzer.py`
- Create: `tests/test_hierarchy_corrector.py`

- [ ] **Step 1: Write ffill correction test**

```python
def test_fix_hierarchy_ffill():
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},  # Should ffill to "1"
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Should ffill to "2"
    ]
    fixed = fix_hierarchy_ffill(articles)
    assert fixed[2]['parent_nr'] == "1"
    assert fixed[4]['parent_nr'] == "2"
    assert fixed[2]['hierarchy_corrected'] == True
```

- [ ] **Step 2: Run test (expect FAIL)**

```bash
pytest tests/test_hierarchy_corrector.py::test_fix_hierarchy_ffill -v
```

- [ ] **Step 3: Refine ffill logic in hierarchy_analyzer.py**

Key insight: ffill works for consecutive components under same parent, but breaks across groups.

```python
def fix_hierarchy_ffill(articles: List[Dict]) -> List[Dict]:
    """Enhanced ffill with group awareness."""
    df = pd.DataFrame(articles).copy()
    
    # Group by implied parent (articles with is_component=False are group starts)
    groups = []
    current_parent = None
    for idx, row in df.iterrows():
        if not row['is_component']:
            current_parent = row['nr']
        groups.append(current_parent)
    
    df['implied_parent'] = groups
    
    # Within each group, ffill parent_nr for components
    df['parent_nr_ffill'] = df.groupby('implied_parent')['parent_nr'].fillna(method='ffill')
    
    # Apply correction
    mask = (df['is_component'] == True) & (df['parent_nr'].isna())
    df.loc[mask, 'parent_nr'] = df.loc[mask, 'parent_nr_ffill']
    df['hierarchy_corrected'] = mask
    
    return df.drop(columns=['parent_nr_ffill', 'implied_parent']).to_dict('records')
```

- [ ] **Step 4: Run test (expect PASS)**

```bash
pytest tests/test_hierarchy_corrector.py::test_fix_hierarchy_ffill -v
```

- [ ] **Step 5: Commit**

```bash
git add shared/hierarchy_analyzer.py tests/test_hierarchy_corrector.py
git commit -m "feat: implement hierarchy correction with group-aware ffill"
```

---

## Task 3: Create Hierarchy Validator

**Files:**
- Modify: `shared/hierarchy_analyzer.py` (add validator functions)
- Create: `tests/test_hierarchy_validator.py`

- [ ] **Step 1: Write validator test**

```python
def test_validate_hierarchy():
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},  # 3-level nesting OK
        {"nr": "2", "parent_nr": None, "is_component": False},
    ]
    validation = validate_hierarchy(articles)
    assert validation['is_valid'] == True
    assert validation['error_count'] == 0
```

- [ ] **Step 2: Write validator for invalid hierarchy**

```python
def test_validate_hierarchy_invalid():
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},
        {"nr": "1.1.1.1", "parent_nr": "1.1.1", "is_component": True},  # 4-level (too deep)
        {"nr": "2", "parent_nr": "NONEXISTENT", "is_component": False},  # Bad parent ref
    ]
    validation = validate_hierarchy(articles)
    assert validation['is_valid'] == False
    assert validation['error_count'] == 2
```

- [ ] **Step 3: Implement validator**

```python
def validate_hierarchy(articles: List[Dict]) -> Dict:
    """
    Validate hierarchy constraints:
    1. All parent_nr references exist
    2. Max nesting depth <= 3
    3. Components have valid parent_nr
    4. No circular references
    """
    df = pd.DataFrame(articles)
    errors = []
    
    # Check 1: Parent references exist
    for idx, row in df.iterrows():
        if pd.notna(row['parent_nr']):
            if not (df['nr'] == row['parent_nr']).any():
                errors.append({
                    "index": idx,
                    "nr": row['nr'],
                    "error": "PARENT_NOT_FOUND",
                    "parent_nr": row['parent_nr']
                })
    
    # Check 2: Max nesting depth
    for idx, row in df.iterrows():
        depth = row['nr'].count('.')
        if depth > 2:  # 0=main, 1=sub, 2=subsub
            errors.append({
                "index": idx,
                "nr": row['nr'],
                "error": "NESTING_TOO_DEEP",
                "depth": depth
            })
    
    # Check 3: All components have parent_nr
    for idx, row in df.iterrows():
        if row['is_component'] and pd.isna(row['parent_nr']):
            errors.append({
                "index": idx,
                "nr": row['nr'],
                "error": "COMPONENT_NO_PARENT"
            })
    
    return {
        "is_valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": errors
    }
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_hierarchy_validator.py -v
```

Expected: 2/2 PASS

- [ ] **Step 5: Commit**

```bash
git add shared/hierarchy_analyzer.py tests/test_hierarchy_validator.py
git commit -m "feat: add hierarchy validator with constraint checks"
```

---

## Task 4: Integrate Hierarchy Corrector into v2 Pipeline

**Files:**
- Create: `shared/hierarchy_corrector.py` (orchestrator)
- Modify: `shared/extraction_v2.py` (add post-processing step)
- Test: `tests/test_extraction_v2_with_hierarchy.py`

- [ ] **Step 1: Create hierarchy corrector orchestrator**

```python
# shared/hierarchy_corrector.py
from shared.hierarchy_analyzer import detect_broken_hierarchy, fix_hierarchy_ffill, validate_hierarchy

class HierarchyCorrector:
    def __init__(self):
        self.stats = {"detected": 0, "corrected": 0, "validation_pass": False}
    
    def correct(self, articles):
        """
        Full correction pipeline:
        1. Detect issues
        2. Apply ffill correction
        3. Validate result
        """
        # Detect
        issues = detect_broken_hierarchy(articles)
        self.stats['detected'] = len(issues)
        
        # Correct
        corrected = fix_hierarchy_ffill(articles)
        self.stats['corrected'] = sum(1 for a in corrected if a.get('hierarchy_corrected'))
        
        # Validate
        validation = validate_hierarchy(corrected)
        self.stats['validation_pass'] = validation['is_valid']
        
        return corrected, validation
```

- [ ] **Step 2: Modify extraction_v2.py to use corrector**

Add to `ExtractionOrchestrator.extract_from_di()`:

```python
def extract_from_di(self, di_json, client_name):
    # ... existing extraction code ...
    
    # NEW: Post-process hierarchy
    from shared.hierarchy_corrector import HierarchyCorrector
    corrector = HierarchyCorrector()
    
    for grupo in extracted.get("grupos", []):
        articles = grupo.get("articole", [])
        corrected_articles, validation = corrector.correct(articles)
        grupo["articole"] = corrected_articles
        grupo["hierarchy_stats"] = corrector.stats
    
    return extracted
```

- [ ] **Step 3: Write integration test**

```python
def test_extraction_v2_with_hierarchy_correction():
    di_json = load_json("input_AO/Drum Tatarani/di_oferta_1.json")
    orchestrator = ExtractionOrchestrator()
    result = orchestrator.extract_from_di(di_json, "Drum Tatarani")
    
    # Check: all grupos have hierarchy_stats
    for grupo in result['grupos']:
        assert 'hierarchy_stats' in grupo
        assert grupo['hierarchy_stats']['validation_pass'] == True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_extraction_v2_with_hierarchy.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shared/hierarchy_corrector.py shared/extraction_v2.py tests/test_extraction_v2_with_hierarchy.py
git commit -m "feat: integrate hierarchy correction into v2 extraction pipeline"
```

---

## Task 5: End-to-End Test on All Clients

**Files:**
- Test: `tests/test_subsystem2_e2e.py`

- [ ] **Step 1: Write E2E test for all clients**

```python
def test_hierarchy_correction_all_clients():
    clients = ["Blocuri Racari", "Camin Maneciu", "Scoala Dragomiresti", "Drum Tatarani"]
    
    for client in clients:
        config = ClientConfig.from_folder(client, INPUT_BASE, OUTPUT_BASE)
        ref_di = json.load(open(config.reference_file))
        
        orchestrator = ExtractionOrchestrator()
        result = orchestrator.extract_from_di(ref_di, client)
        
        # Assert: no broken hierarchies after correction
        for grupo in result['grupos']:
            validation = grupo.get('hierarchy_stats', {})
            assert validation.get('validation_pass', False), f"{client}: hierarchy validation failed"
```

- [ ] **Step 2: Run E2E test**

```bash
pytest tests/test_subsystem2_e2e.py -v
```

Expected: 4/4 PASS (all clients)

- [ ] **Step 3: Commit**

```bash
git add tests/test_subsystem2_e2e.py
git commit -m "feat: add E2E hierarchy correction tests on all clients"
```

---

## Task 6: Generate Hierarchy Report

**Files:**
- Create: `generate_hierarchy_report.py`

- [ ] **Step 1: Create report generator**

```python
def generate_hierarchy_report(client_name, oferta_num):
    """Generate Word report showing hierarchy corrections."""
    client_dir = OUTPUT_BASE / client_name
    extracted_file = client_dir / f"oferta_{oferta_num}_v2.json"
    
    with open(extracted_file) as f:
        data = json.load(f)
    
    doc = Document()
    doc.add_heading(f"Hierarchy Correction Report - {client_name} Oferta {oferta_num}", 0)
    
    total_detected = 0
    total_corrected = 0
    
    for grupo in data['grupos']:
        stats = grupo.get('hierarchy_stats', {})
        total_detected += stats.get('detected', 0)
        total_corrected += stats.get('corrected', 0)
        
        deviz = grupo.get('deviz_cod')
        doc.add_paragraph(
            f"{deviz}: {stats.get('corrected', 0)} corrections, "
            f"validation {'PASS' if stats.get('validation_pass') else 'FAIL'}"
        )
    
    doc.save(str(client_dir / f"Raport_Hierarchy_{oferta_num}_v2.docx"))
```

- [ ] **Step 2: Run report generator on DT**

```bash
python3 generate_hierarchy_report.py "Drum Tatarani" 1
```

- [ ] **Step 3: Commit**

```bash
git add generate_hierarchy_report.py
git commit -m "feat: add hierarchy correction report generator"
```

---

## Success Criteria

- ✅ All 5 unit test suites pass (analyzer, corrector, validator, integration, E2E)
- ✅ Hierarchy validation passes on all clients (4/4)
- ✅ No broken parent references in corrected articles
- ✅ Nesting depth ≤ 3 for all articles
- ✅ Hierarchy report generates successfully
- ✅ v2 extraction pipeline includes hierarchy correction
- ✅ Zero regressions in article counts (hierarchy correction doesn't drop articles)

---

## Dependencies

- **Input:** v2 extracted articles (oferta_N_v2.json) with parent_nr, is_component fields
- **Output:** Corrected articles JSON with hierarchy_corrected flag + hierarchy_stats
- **Next:** Subsystem 3 (Set-Based Matching) consumes corrected hierarchy
