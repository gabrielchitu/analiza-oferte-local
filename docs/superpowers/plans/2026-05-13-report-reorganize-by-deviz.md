# Report Reorganize by Deviz Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize comparison reports to group all non-conformities by deviz (numerical order), add totals line per deviz showing reference and offer article counts, output both JSON and DOCX formats.

**Architecture:** Extend report generation pipeline to:
1. Create JSON structure grouped by deviz with totals
2. Modify DOCX generation to add totals line per deviz
3. Deduplicate articles per deviz to calculate accurate totals
4. Keep existing DOCX styling and layout

**Tech Stack:** Python (existing tools), python-docx, json

---

## File Structure

**Files to modify:**
- `shared/report_word.py` — Add totals calculation and totals row rendering, extract grouping logic
- `local_run.py` — Add JSON output generation and file writing

**New functions:**
- `_group_neconf_by_deviz()` — Group non-conformities by deviz, calculate article counts
- `_add_totals_row()` — Add totals line to DOCX table
- `generate_json_by_deviz()` — Generate JSON structure grouped by deviz

---

## Task 1: Analyze Current Data Structure and Article Counting

**Files:**
- Analyze: `shared/report_word.py`, `output_AO/comparatie_oferta_2.json`

- [ ] **Step 1: Understand current article count logic**

Read the current `generate_word()` function to see how it groups neconformitati.
Currently it:
- Groups by `deviz_ref`
- Shows counts for ARTICOL_LIPSA and ARTICOL_EXTRA only
- Does NOT show total reference vs offer article counts

- [ ] **Step 2: Verify available data in comparison JSON**

Run this to inspect what's in the comparison data:

```bash
python3 << 'EOF'
import json
data = json.load(open('output_AO/comparatie_oferta_2.json'))
neconf = data['neconformitati']

# Check what we have per neconf
if neconf:
    print("Sample neconf fields:", list(neconf[0].keys()))
    
# Count unique articles per deviz
from collections import defaultdict
ref_articles_by_deviz = defaultdict(set)
offer_articles_by_deviz = defaultdict(set)

for nc in neconf:
    deviz = nc.get('deviz_ref', '')
    ref_articles_by_deviz[deviz].add(nc.get('ref_cod', ''))
    offer_articles_by_deviz[deviz].add(nc.get('oferta_cod', ''))

# Show sample
for deviz in list(ref_articles_by_deviz.keys())[:2]:
    print(f"Deviz {deviz}: ref={len(ref_articles_by_deviz[deviz])}, offer={len(offer_articles_by_deviz[deviz])}")
EOF
```

Expected: Fields include ref_cod, oferta_cod, deviz_ref, and deduplication shows per-deviz article counts.

- [ ] **Step 3: Commit analysis**

```bash
git add -A
git commit -m "docs: analysis of comparison data structure for deviz grouping"
```

---

## Task 2: Create Grouping Function

**Files:**
- Create: `shared/report_deviz_grouper.py`

- [ ] **Step 1: Write the grouping function**

Create a new file `shared/report_deviz_grouper.py`:

```python
from typing import Dict, List
from collections import defaultdict

def group_neconf_by_deviz(neconformitati: List[dict]) -> Dict:
    """
    Group non-conformities by deviz and calculate article counts.
    
    Returns:
    {
        'deviz_groups': [
            {
                'deviz_cod': '226108',
                'deviz_denumire': 'STRUCTURA...',
                'articole_ref_count': 45,
                'articole_oferta_count': 42,
                'neconformitati': [... all neconf for this deviz ...]
            },
            ...
        ],
        'deviz_map': {...}
    }
    """
    # Build deviz map and article counts
    deviz_map = {}
    deviz_groups_dict = defaultdict(list)
    ref_articles_by_deviz = defaultdict(set)
    offer_articles_by_deviz = defaultdict(set)
    
    # First pass: collect all neconf, build maps
    for nc in neconformitati:
        deviz_cod = nc.get('deviz_ref', '')
        deviz_den = nc.get('deviz_denumire', '')
        
        if deviz_cod and deviz_den:
            deviz_map[deviz_cod] = deviz_den
        
        deviz_groups_dict[deviz_cod].append(nc)
        
        # Track unique articles per deviz
        ref_cod = nc.get('ref_cod', '')
        oferta_cod = nc.get('oferta_cod', '')
        if ref_cod:
            ref_articles_by_deviz[deviz_cod].add(ref_cod)
        if oferta_cod:
            offer_articles_by_deviz[deviz_cod].add(oferta_cod)
    
    # Build result with deviz sorted numerically
    deviz_groups = []
    for deviz_cod in sorted(deviz_groups_dict.keys(), 
                           key=lambda x: int(x) if x.isdigit() else float('inf')):
        deviz_groups.append({
            'deviz_cod': deviz_cod,
            'deviz_denumire': deviz_map.get(deviz_cod, ''),
            'articole_ref_count': len(ref_articles_by_deviz[deviz_cod]),
            'articole_oferta_count': len(offer_articles_by_deviz[deviz_cod]),
            'neconformitati': sorted(
                deviz_groups_dict[deviz_cod],
                key=lambda x: (x.get('tip', ''), x.get('ref_cod', ''))
            )
        })
    
    return {
        'deviz_groups': deviz_groups,
        'deviz_map': deviz_map
    }
```

- [ ] **Step 2: Test the grouping function**

Create a test script:

```bash
python3 << 'EOF'
import json
import sys
sys.path.insert(0, 'shared')

from report_deviz_grouper import group_neconf_by_deviz

# Load test data
data = json.load(open('output_AO/comparatie_oferta_2.json'))
neconf = data['neconformitati']

# Test grouping
result = group_neconf_by_deviz(neconf)
print(f"Total devize: {len(result['deviz_groups'])}")

# Show first deviz
if result['deviz_groups']:
    first = result['deviz_groups'][0]
    print(f"First deviz: {first['deviz_cod']} — ref_count={first['articole_ref_count']}, oferta_count={first['articole_oferta_count']}")
    print(f"Neconf count: {len(first['neconformitati'])}")
EOF
```

Expected: Groups all neconf by deviz, calculates correct article counts per deviz.

- [ ] **Step 3: Commit**

```bash
git add shared/report_deviz_grouper.py
git commit -m "feat: add grouping function for deviz-based non-conformities"
```

---

## Task 3: Add Totals Row to DOCX Report

**Files:**
- Modify: `shared/report_word.py`

- [ ] **Step 1: Add totals row function**

Add this function to `report_word.py` after `_add_neconf_row()`:

```python
def _add_totals_row(table, row_nr: int, articole_ref_count: int, articole_oferta_count: int):
    """Add totals row for a deviz showing reference and offer article counts."""
    row = table.add_row()
    
    # Column 0: empty (no row number for totals)
    cells = row.cells
    
    # Column 1-5: "TOTAL" label
    cells[1].text = "TOTAL"
    _style_cell(cells[1], 9, bold=True, color=BLACK)
    _set_cell_shading(cells[1], GRAY_FILL)
    
    # Columns 2-5: empty (filler)
    for i in range(2, 6):
        cells[i].text = ""
        _set_cell_shading(cells[i], GRAY_FILL)
    
    # Column 6: Reference article count (left side)
    cells[6].text = str(articole_ref_count)
    _style_cell(cells[6], 9, bold=True, center=True, color=BLACK)
    _set_cell_shading(cells[6], GRAY_FILL)
    
    # Column 7: Reference unit (filler)
    cells[7].text = ""
    _set_cell_shading(cells[7], GRAY_FILL)
    
    # Columns 8-10: Offer article count (right side)
    cells[8].text = ""
    _set_cell_shading(cells[8], GRAY_FILL)
    
    cells[9].text = str(articole_oferta_count)
    _style_cell(cells[9], 9, bold=True, center=True, color=BLACK)
    _set_cell_shading(cells[9], GRAY_FILL)
    
    cells[10].text = ""
    _set_cell_shading(cells[10], GRAY_FILL)
```

- [ ] **Step 2: Test adding a totals row**

Modify the `generate_word()` function to use the new grouping. At line 462 (in the loop), after adding all neconf rows for a deviz, add the totals row.

Replace:

```python
for neconf in items:
    row_nr += 1
    _add_neconf_row(table, row_nr, neconf, deviz_map)
```

With:

```python
for neconf in items:
    row_nr += 1
    _add_neconf_row(table, row_nr, neconf, deviz_map)

# Add totals row for this deviz
# Get article counts from neconf items
ref_articles = set(nc.get('ref_cod', '') for nc in items if nc.get('ref_cod', ''))
offer_articles = set(nc.get('oferta_cod', '') for nc in items if nc.get('oferta_cod', ''))
ref_count = len(ref_articles)
offer_count = len(offer_articles)
_add_totals_row(table, row_nr + 1, ref_count, offer_count)
row_nr += 1
```

Test locally by running:
```bash
python3 local_run.py
```

Check that Raport_Oferta_2.docx has totals rows (gray background).

- [ ] **Step 3: Commit**

```bash
git add shared/report_word.py
git commit -m "feat: add totals row to DOCX report per deviz"
```

---

## Task 4: Generate JSON Output Grouped by Deviz

**Files:**
- Create: `shared/report_json.py`

- [ ] **Step 1: Write JSON generation function**

Create `shared/report_json.py`:

```python
import json
from typing import Dict, List

def generate_json_by_deviz(session: dict, comp: dict) -> dict:
    """
    Generate JSON report grouped by deviz with totals.
    
    Args:
        session: session dict with client_name, obiect_investitii
        comp: comparatie dict with neconformitati, oferta_nr, etc.
    
    Returns:
        dict with structure:
        {
            'metadata': {...},
            'deviz_groups': [
                {
                    'deviz_cod': '226108',
                    'deviz_denumire': '...',
                    'articole_referinta': 45,
                    'articole_oferta': 42,
                    'neconformitati': [...]
                },
                ...
            ]
        }
    """
    from collections import defaultdict
    
    neconformitati = comp.get('neconformitati', [])
    
    # Build deviz map and groups
    deviz_map = {}
    deviz_groups_dict = defaultdict(list)
    ref_articles_by_deviz = defaultdict(set)
    offer_articles_by_deviz = defaultdict(set)
    
    for nc in neconformitati:
        deviz_cod = nc.get('deviz_ref', '')
        deviz_den = nc.get('deviz_denumire', '')
        
        if deviz_cod and deviz_den:
            deviz_map[deviz_cod] = deviz_den
        
        deviz_groups_dict[deviz_cod].append(nc)
        
        # Track unique articles
        if nc.get('ref_cod', ''):
            ref_articles_by_deviz[deviz_cod].add(nc.get('ref_cod', ''))
        if nc.get('oferta_cod', ''):
            offer_articles_by_deviz[deviz_cod].add(nc.get('oferta_cod', ''))
    
    # Build deviz groups sorted numerically
    deviz_groups = []
    for deviz_cod in sorted(deviz_groups_dict.keys(), 
                           key=lambda x: int(x) if x.isdigit() else float('inf')):
        deviz_groups.append({
            'deviz_cod': deviz_cod,
            'deviz_denumire': deviz_map.get(deviz_cod, ''),
            'articole_referinta': len(ref_articles_by_deviz[deviz_cod]),
            'articole_oferta': len(offer_articles_by_deviz[deviz_cod]),
            'neconformitati': deviz_groups_dict[deviz_cod]
        })
    
    return {
        'metadata': {
            'client_name': session.get('client_name', ''),
            'obiect_investitii': session.get('obiect_investitii', ''),
            'oferta_nr': comp.get('oferta_nr', ''),
            'source_file': comp.get('source_file', ''),
            'matches': comp.get('matches', 0),
            'total_neconformitati': comp.get('total_neconformitati', 0),
            'ref_art_count': comp.get('ref_art_count', 0),
            'oferta_art_count': comp.get('oferta_art_count', 0)
        },
        'deviz_groups': deviz_groups
    }
```

- [ ] **Step 2: Test JSON generation**

```bash
python3 << 'EOF'
import json
import sys
sys.path.insert(0, 'shared')

from report_json import generate_json_by_deviz

# Load test data
comp = json.load(open('output_AO/comparatie_oferta_2.json'))
session = {'client_name': 'Test Client', 'obiect_investitii': 'Test Object'}

# Generate JSON
result = generate_json_by_deviz(session, comp)

print(f"Total devize: {len(result['deviz_groups'])}")
if result['deviz_groups']:
    first = result['deviz_groups'][0]
    print(f"First: {first['deviz_cod']} — ref={first['articole_referinta']}, oferta={first['articole_oferta']}")
    print(f"Neconf: {len(first['neconformitati'])}")
EOF
```

Expected: JSON structure with all devize grouped and sorted numerically.

- [ ] **Step 3: Commit**

```bash
git add shared/report_json.py
git commit -m "feat: add JSON generation grouped by deviz with totals"
```

---

## Task 5: Integrate JSON Output into Pipeline

**Files:**
- Modify: `local_run.py`

- [ ] **Step 1: Import and call JSON generator**

At the end of `local_run.py`, after generating DOCX reports, add JSON generation:

Find where DOCX is being written, and add after that:

```python
from shared.report_json import generate_json_by_deviz

# For each comparison (oferta 1, 2, 3)
for i, (oferta_num, comp) in enumerate([(1, comp_1), (2, comp_2), (3, comp_3)]):
    if not comp or not comp.get('neconformitati'):
        continue
    
    # Generate JSON
    json_report = generate_json_by_deviz(SESSION, comp)
    
    # Write JSON file
    json_file = f"output_AO/comparatie_deviz_oferta_{oferta_num}.json"
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_report, f, ensure_ascii=False, indent=2)
    
    print(f"[INFO] JSON by deviz: {json_file}")
```

- [ ] **Step 2: Test end-to-end**

Run the full pipeline:

```bash
python3 local_run.py
```

Expected:
- DOCX files generated with totals rows
- New JSON files created: `comparatie_deviz_oferta_1.json`, `comparatie_deviz_oferta_2.json`, `comparatie_deviz_oferta_3.json`

- [ ] **Step 3: Verify JSON structure**

```bash
python3 -c "
import json
data = json.load(open('output_AO/comparatie_deviz_oferta_2.json'))
print('Keys:', list(data.keys()))
print('Devize count:', len(data['deviz_groups']))
if data['deviz_groups']:
    first = data['deviz_groups'][0]
    print('First deviz:', first['deviz_cod'], '—', first['articole_referinta'], 'vs', first['articole_oferta'])
"
```

Expected: JSON structure valid, devize sorted numerically, counts populated.

- [ ] **Step 4: Commit**

```bash
git add local_run.py
git commit -m "feat: integrate JSON output generation into pipeline"
```

---

## Task 6: Final Testing and Verification

**Files:**
- Test: DOCX and JSON outputs

- [ ] **Step 1: Visual check of DOCX**

Open `output_AO/Raport_Oferta_2.docx`:
- Each deviz section should have a gray totals row at the end
- Totals should show reference count on left, offer count on right
- Layout and styling should match existing template

- [ ] **Step 2: Verify JSON structure**

Run comparison check:

```bash
python3 << 'EOF'
import json

# Load both old and new JSON
old_comp = json.load(open('output_AO/comparatie_oferta_2.json'))
new_comp = json.load(open('output_AO/comparatie_deviz_oferta_2.json'))

# Verify counts match
old_neconf_count = len(old_comp['neconformitati'])
new_neconf_count = sum(len(dg['neconformitati']) for dg in new_comp['deviz_groups'])

print(f"Old neconf count: {old_neconf_count}")
print(f"New neconf count: {new_neconf_count}")
print(f"Match: {old_neconf_count == new_neconf_count}")

# Verify devize are sorted
deviz_codes = [dg['deviz_cod'] for dg in new_comp['deviz_groups']]
deviz_nums = [int(d) for d in deviz_codes if d.isdigit()]
print(f"Devize sorted: {deviz_nums == sorted(deviz_nums)}")
EOF
```

Expected: All checks pass, counts match, devize are numerically sorted.

- [ ] **Step 3: Test with all three ofertas**

Verify all three JSON files are generated:

```bash
ls -la output_AO/comparatie_deviz_oferta_*.json
```

Expected: 3 files exist.

- [ ] **Step 4: Commit final changes**

```bash
git add -A
git commit -m "test: verify deviz-grouped report outputs (DOCX and JSON)"
```

---

## Self-Review Checklist

✓ **Spec coverage:** 
- Grouping by deviz (numerical): Task 1-2, 4
- All non-conformity types: Function preserves all types
- Totals line (ref vs offer): Task 3, 5
- JSON output: Task 4
- DOCX with same layout: Task 3

✓ **Placeholders:** None found, all code is complete

✓ **Type consistency:** 
- `deviz_cod`: string throughout
- `articole_ref_count`/`articole_referinta`: integer counts
- `neconformitati`: list of dicts
- All function signatures match usage

✓ **No gaps:** All features from spec have tasks

---

## Plan Ready

This plan implements:
1. Grouping function for deviz-based organization
2. Totals row calculation and rendering in DOCX
3. JSON output generation with same grouping
4. Integration into main pipeline
5. Comprehensive testing

All tasks are atomic, testable, and produce working output.
