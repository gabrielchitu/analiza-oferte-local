# Subsystem 3: Set-Based Matching with Unique Key Detection — Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to execute this plan task-by-task.

**Goal:** Replace v1 LLM-based layer matching with set-theoretic matching using unique keys. Produce holistic JSON matching results (matched_groups, ref_only_groups, oferta_only_groups) identical to v1 format.

**Architecture:** 
- Input: v2 extracted + hierarchy-corrected articles (with comparison metadata from S1)
- Process: Extract unique keys per article → detect key type (NR, descriere, um+cant) → set-based matching → generate holistic output
- Output: holistic_oferta_N_v2.json (same structure as v1, ready for report generation)

**Tech Stack:** pandas, set theory, RapidFuzz (string similarity), existing v1 matching patterns

---

## Task 1: Unique Key Detection

**Files:**
- Create: `shared/unique_key_detector.py`
- Test: `tests/test_unique_key_detector.py`

- [ ] **Step 1: Write test for key detection**

```python
def test_detect_article_keys():
    articles = [
        {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125", "cod": "ABC123"},
        {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500", "cod": "XYZ789"},
    ]
    keys = detect_article_keys(articles)
    assert keys[0] == "1"  # Primary key: NR
    assert keys[1] == "2"
```

- [ ] **Step 2: Run test (expect FAIL)**

- [ ] **Step 3: Implement unique key detector**

```python
# shared/unique_key_detector.py
def detect_article_keys(articles: List[Dict]) -> List[str]:
    """
    Extract unique keys per article for matching.
    Priority: nr → cod → descriere+um+cant hash
    """
    keys = []
    for art in articles:
        # Primary: NR (article number)
        if pd.notna(art.get('nr')):
            key = art['nr']
        # Secondary: COD (catalog code)
        elif pd.notna(art.get('cod')):
            key = art['cod']
        # Tertiary: Hash(descriere+um+cant)
        else:
            descriere = str(art.get('descriere', '')).lower().strip()
            um = str(art.get('um', '')).lower().strip()
            cant = str(art.get('cant', ''))
            key = hashlib.md5(f"{descriere}|{um}|{cant}".encode()).hexdigest()[:8]
        keys.append(key)
    return keys

def get_unique_articles(articles: List[Dict]) -> Dict[str, Dict]:
    """
    Build dict: key -> article (first occurrence wins)
    """
    unique = {}
    for art in articles:
        key = detect_article_key(art)
        if key not in unique:
            unique[key] = art
    return unique

def detect_article_key(article: Dict) -> str:
    """Single article key detection (used by set matcher)"""
    if pd.notna(article.get('nr')):
        return article['nr']
    elif pd.notna(article.get('cod')):
        return article['cod']
    else:
        descriere = str(article.get('descriere', '')).lower().strip()
        um = str(article.get('um', '')).lower().strip()
        cant = str(article.get('cant', ''))
        return hashlib.md5(f"{descriere}|{um}|{cant}".encode()).hexdigest()[:8]
```

- [ ] **Step 4: Run test (expect PASS)**

- [ ] **Step 5: Commit**

```bash
git add shared/unique_key_detector.py tests/test_unique_key_detector.py
git commit -m "feat: add unique key detection for set-based matching"
```

---

## Task 2: Set-Based Matcher

**Files:**
- Create: `shared/set_based_matcher.py`
- Test: `tests/test_set_based_matcher.py`

- [ ] **Step 1: Write test for set matching**

```python
def test_set_based_match_articles():
    ref_articles = [
        {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},
        {"nr": "2", "descriere": "OTEL", "um": "KG", "cant": "500"},
    ]
    oferta_articles = [
        {"nr": "1", "descriere": "CIMENT", "um": "T", "cant": "125"},  # Exact match
        {"nr": "3", "descriere": "NISIP", "um": "M3", "cant": "50"},    # Oferta only
    ]
    
    result = match_articles_by_key(ref_articles, oferta_articles)
    assert len(result['matched']) == 1
    assert result['matched'][0]['nr'] == "1"
    assert len(result['ref_only']) == 1
    assert len(result['oferta_only']) == 1
```

- [ ] **Step 2: Implement set-based matcher**

```python
# shared/set_based_matcher.py
from shared.unique_key_detector import get_unique_articles

def match_articles_by_key(ref_articles: List[Dict], oferta_articles: List[Dict]) -> Dict:
    """
    Set-based matching: exact key match determines pairs.
    Returns: {matched: [], ref_only: [], oferta_only: []}
    """
    ref_unique = get_unique_articles(ref_articles)
    oferta_unique = get_unique_articles(oferta_articles)
    
    ref_keys = set(ref_unique.keys())
    oferta_keys = set(oferta_unique.keys())
    
    matched_keys = ref_keys & oferta_keys
    ref_only_keys = ref_keys - oferta_keys
    oferta_only_keys = oferta_keys - ref_keys
    
    matched = [{"ref": ref_unique[k], "oferta": oferta_unique[k]} for k in matched_keys]
    ref_only = [ref_unique[k] for k in ref_only_keys]
    oferta_only = [oferta_unique[k] for k in oferta_only_keys]
    
    return {
        "matched": matched,
        "ref_only": ref_only,
        "oferta_only": oferta_only,
        "stats": {
            "matched_count": len(matched),
            "ref_only_count": len(ref_only),
            "oferta_only_count": len(oferta_only),
            "ref_total": len(ref_unique),
            "oferta_total": len(oferta_unique)
        }
    }
```

- [ ] **Step 3: Run tests (expect PASS)**

- [ ] **Step 4: Commit**

```bash
git add shared/set_based_matcher.py tests/test_set_based_matcher.py
git commit -m "feat: implement set-based article matching with unique keys"
```

---

## Task 3: Group Matching Orchestrator

**Files:**
- Create: `shared/group_set_matcher.py`
- Test: `tests/test_group_set_matcher.py`

- [ ] **Step 1: Write test for group matching**

```python
def test_match_groups_by_key():
    ref_groups = [
        {"deviz_cod": "0001", "articole": [...5 articles...]},
        {"deviz_cod": "0002", "articole": [...3 articles...]},
    ]
    oferta_groups = [
        {"deviz_cod": "0001", "articole": [...6 articles...]},
        {"deviz_cod": "0003", "articole": [...2 articles...]},
    ]
    
    result = match_groups_by_deviz(ref_groups, oferta_groups)
    assert len(result['matched_groups']) == 1
    assert len(result['ref_only_groups']) == 1
    assert len(result['oferta_only_groups']) == 1
```

- [ ] **Step 2: Implement group matcher**

```python
# shared/group_set_matcher.py
from shared.set_based_matcher import match_articles_by_key

def match_groups_by_deviz(ref_groups: List[Dict], oferta_groups: List[Dict]) -> Dict:
    """
    Match groups by deviz_cod, then articles within each matched group.
    Returns: {matched_groups: [], ref_only_groups: [], oferta_only_groups: []}
    """
    ref_deviz_map = {g.get('deviz_cod'): g for g in ref_groups}
    oferta_deviz_map = {g.get('deviz_cod'): g for g in oferta_groups}
    
    ref_devizes = set(ref_deviz_map.keys())
    oferta_devizes = set(oferta_deviz_map.keys())
    
    matched_devizes = ref_devizes & oferta_devizes
    ref_only_devizes = ref_devizes - oferta_devizes
    oferta_only_devizes = oferta_devizes - ref_devizes
    
    matched_groups = []
    for deviz in matched_devizes:
        ref_group = ref_deviz_map[deviz]
        oferta_group = oferta_deviz_map[deviz]
        
        # Match articles within group
        article_match = match_articles_by_key(
            ref_group.get('articole', []),
            oferta_group.get('articole', [])
        )
        
        matched_groups.append({
            "deviz_cod": deviz,
            "deviz_den": ref_group.get('deviz_den'),
            "articole": article_match['matched'],
            "stats": article_match['stats']
        })
    
    ref_only_groups = [
        {**g, "articole": g.get('articole', [])}
        for g in [ref_deviz_map[d] for d in ref_only_devizes]
    ]
    
    oferta_only_groups = [
        {**g, "articole": g.get('articole', [])}
        for g in [oferta_deviz_map[d] for d in oferta_only_devizes]
    ]
    
    return {
        "matched_groups": matched_groups,
        "ref_only_groups": ref_only_groups,
        "oferta_only_groups": oferta_only_groups
    }
```

- [ ] **Step 3: Run tests (expect PASS)**

- [ ] **Step 4: Commit**

```bash
git add shared/group_set_matcher.py tests/test_group_set_matcher.py
git commit -m "feat: implement group matching by deviz code with article set matching"
```

---

## Task 4: Holistic JSON Generator

**Files:**
- Create: `shared/holistic_generator.py`
- Test: `tests/test_holistic_generator.py`

- [ ] **Step 1: Write test for holistic output**

```python
def test_generate_holistic_v2():
    ref_extracted = load_json("output_AO/DT/referinta_v2.json")
    oferta_extracted = load_json("output_AO/DT/oferta_1_v2.json")
    
    holistic = generate_holistic_v2(ref_extracted, oferta_extracted)
    
    assert 'matched_groups' in holistic
    assert 'ref_only_groups' in holistic
    assert 'oferta_only_groups' in holistic
    assert 'stats' in holistic
    assert holistic['stats']['matched_count'] > 0
```

- [ ] **Step 2: Implement holistic generator**

```python
# shared/holistic_generator.py
from shared.group_set_matcher import match_groups_by_deviz

def generate_holistic_v2(ref_extracted: Dict, oferta_extracted: Dict) -> Dict:
    """
    Generate holistic JSON (v1 format) from v2 extracted + matched data.
    """
    ref_groups = ref_extracted.get('grupos', [])
    oferta_groups = oferta_extracted.get('grupos', [])
    
    match_result = match_groups_by_deviz(ref_groups, oferta_groups)
    
    matched_count = sum(len(g.get('articole', [])) for g in match_result['matched_groups'])
    ref_only_count = sum(len(g.get('articole', [])) for g in match_result['ref_only_groups'])
    oferta_only_count = sum(len(g.get('articole', [])) for g in match_result['oferta_only_groups'])
    
    return {
        "client": oferta_extracted.get('client'),
        "di_file": oferta_extracted.get('di_file'),
        "extraction_version": "2.0",
        "matched_groups": match_result['matched_groups'],
        "ref_only_groups": match_result['ref_only_groups'],
        "oferta_only_groups": match_result['oferta_only_groups'],
        "stats": {
            "matched_articles": matched_count,
            "ref_only_articles": ref_only_count,
            "oferta_only_articles": oferta_only_count,
            "matched_groups_count": len(match_result['matched_groups']),
            "ref_only_groups_count": len(match_result['ref_only_groups']),
            "oferta_only_groups_count": len(match_result['oferta_only_groups'])
        }
    }
```

- [ ] **Step 3: Run tests (expect PASS)**

- [ ] **Step 4: Commit**

```bash
git add shared/holistic_generator.py tests/test_holistic_generator.py
git commit -m "feat: implement holistic JSON generator for v2 matching results"
```

---

## Task 5: Integration into v2 Extraction Pipeline

**Files:**
- Create: `shared/matching_orchestrator_v2.py`
- Modify: `shared/extraction_v2.py`
- Test: `tests/test_extraction_v2_with_matching.py`

- [ ] **Step 1: Write integration test**

```python
def test_extraction_v2_with_matching():
    di_json = load_json("input_AO/Drum Tatarani/di_oferta_1.json")
    orchestrator = ExtractionOrchestrator()
    
    # Extract
    result = orchestrator.extract_from_di(di_json, "Drum Tatarani")
    
    # Should include matching results (will be added in Task 5)
    assert 'matched_groups' in result or 'grupos' in result
```

- [ ] **Step 2: Create orchestrator**

```python
# shared/matching_orchestrator_v2.py
from shared.holistic_generator import generate_holistic_v2

class MatchingOrchestratorV2:
    def __init__(self):
        self.stats = {"matched": 0, "ref_only": 0, "oferta_only": 0}
    
    def match(self, ref_extracted: Dict, oferta_extracted: Dict) -> Dict:
        holistic = generate_holistic_v2(ref_extracted, oferta_extracted)
        self.stats = holistic['stats']
        return holistic
```

- [ ] **Step 3: Modify extraction_v2.py**

Add to ExtractionOrchestrator:

```python
def match_reference_with_offer(self, ref_extracted, oferta_extracted):
    """Match extracted reference with offer."""
    from shared.matching_orchestrator_v2 import MatchingOrchestratorV2
    matcher = MatchingOrchestratorV2()
    holistic = matcher.match(ref_extracted, oferta_extracted)
    return holistic
```

- [ ] **Step 4: Run tests (expect PASS)**

- [ ] **Step 5: Commit**

```bash
git add shared/matching_orchestrator_v2.py shared/extraction_v2.py tests/test_extraction_v2_with_matching.py
git commit -m "feat: integrate set-based matching into v2 extraction pipeline"
```

---

## Task 6: E2E Matching Tests on All Clients

**Files:**
- Test: `tests/test_subsystem3_e2e.py`

- [ ] **Step 1: Write E2E test for all 4 clients**

```python
def test_set_based_matching_all_clients():
    clients = ["Blocuri Racari", "Camin Maneciu", "Scoala Dragomiresti", "Drum Tatarani"]
    
    for client in clients:
        config = ClientConfig.from_folder(client, INPUT_BASE, OUTPUT_BASE)
        ref_di = json.load(open(config.reference_file))
        
        orchestrator = ExtractionOrchestrator()
        ref_extracted = orchestrator.extract_from_di(ref_di, client)
        
        for offer_file in config.offer_files[:2]:  # Test first 2 offers
            oferta_di = json.load(open(offer_file))
            oferta_extracted = orchestrator.extract_from_di(oferta_di, client)
            
            holistic = orchestrator.match_reference_with_offer(ref_extracted, oferta_extracted)
            
            assert 'matched_groups' in holistic
            assert 'stats' in holistic
            assert holistic['stats']['matched_articles'] > 0
```

- [ ] **Step 2: Run E2E tests (expect PASS on all 4)**

```bash
pytest tests/test_subsystem3_e2e.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_subsystem3_e2e.py
git commit -m "feat: add E2E set-based matching tests on all clients"
```

---

## Task 7: Comparison Report Generation

**Files:**
- Create: `generate_matching_report.py`
- Test: Run on DT oferta 1 & 2

- [ ] **Step 1: Create report generator**

Similar to Task 6 (Subsystem 2), but for matching results:
- Show matched groups count
- Show ref-only and oferta-only groups
- Per-group matching statistics
- Save as Raport_Matching_{oferta_num}_v2.docx

- [ ] **Step 2: Run on DT (expect PASS)**

- [ ] **Step 3: Commit**

```bash
git add generate_matching_report.py
git commit -m "feat: add set-based matching report generator"
```

---

## Success Criteria

- ✅ All 7 task test suites pass (70+ tests)
- ✅ Set-based matching produces holistic JSON matching v1 format
- ✅ All 4 clients match successfully (matched_articles > 0)
- ✅ Matching reports generate for DT oferta 1 & 2
- ✅ Zero regressions (Subsystem 1-2 tests still pass)
- ✅ v2 pipeline ready for report generation (v1-compatible holistic data)

---

## Dependencies

- **Input:** v2 extracted + hierarchy-corrected articles (from Subsystems 1-2)
- **Output:** holistic_oferta_N_v2.json (v1-compatible matching format)
- **Next:** Subsystem 4 (Autonomous Agent) consumes matching results
- **Final:** Report generation uses holistic data (identical to v1 reports)
