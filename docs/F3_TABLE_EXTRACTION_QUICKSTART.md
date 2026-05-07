# F3 Table Extraction — Quick Start Guide

**Time to Implementation**: 5-10 minutes  
**Complexity**: Low (3 lines of code)  
**Testing**: Included  

---

## What This Does

Extracts articles from Document Intelligence structured tables (DI JSON format). Adds 20-40% more articles to your extraction by processing table data in addition to page-level text.

**Result**: Articles like `$3270513 - BANDA AVERTIZARE` that exist in tables are now extracted.

---

## Step 0: Verify You Need This

Check if your DI JSON has tables:
```bash
python3 -c "
import json
with open('your_di.json') as f:
    data = json.load(f)
    tables = data.get('tables', [])
    print(f'Tables: {len(tables)}')
    if tables:
        print(f'Cells in first table: {len(tables[0].get(\"cells\", []))}')
"
```

If tables > 10 and cells > 100: **You need this solution.**

---

## Step 1: Copy the Module

Copy `shared/table_extractor.py` from reference project to your project:

```bash
# From reference project directory:
cp shared/table_extractor.py ../your_project/shared/

# Verify:
ls -la ../your_project/shared/table_extractor.py
```

---

## Step 2: Integrate into Your Extraction Pipeline

Find where you extract articles. Typically in a function like `extract_document()` or `extract_articles()`.

**Before:**
```python
def extract_document(di_path):
    articles = extract_articles_v3(page_classes)  # Line-based extraction
    return articles
```

**After:**
```python
def extract_document(di_path):
    articles = extract_articles_v3(page_classes)  # Line-based extraction
    
    # NEW: Extract from tables
    from shared.table_extractor import extract_articles_from_tables_smart
    tables = di.get("tables", [])
    if tables:
        articles_from_tables = extract_articles_from_tables_smart(tables)
        
        # Deduplicate by (cod, deviz) key
        article_keys = set()
        for art in articles:
            key = (art.get("cod"), art.get("deviz"))
            article_keys.add(key)
        
        for art in articles_from_tables:
            key = (art.get("cod"), art.get("deviz"))
            if key not in article_keys:
                articles.append(art)
                article_keys.add(key)
    
    return articles
```

**That's it!** 3 new lines of logic.

---

## Step 3: Test

### Test 3a: Run Extraction

```bash
python3 your_extraction_script.py
```

**Expected output:**
```
[TABLE] Tabel 52: Metadata deviz 226108 - STRUCTURA DE REZISTENTA...
[TABLE] Tabel 53: 5 articole, deviz 226108
[TABLE] Tabel 54: 10 articole, deviz 226108
...
[TABLE] 1205 articole din tabele, 1288 total dupa merge
```

### Test 3b: Verify Article Count Increased

```bash
python3 << 'EOF'
import json

with open("output/extracted_articles.json") as f:
    articles = json.load(f).get("articole", [])

print(f"Total articles: {len(articles)}")

# Count by source (if available)
from_tables = sum(1 for a in articles if a.get("source") == "table")
from_lines = sum(1 for a in articles if a.get("source") == "line")

print(f"From tables: {from_tables}")
print(f"From lines: {from_lines}")
EOF
```

Expected: Total should be 20-40% higher than before.

### Test 3c: Sample Validation

```python
import json

with open("output/extracted_articles.json") as f:
    articles = json.load(f).get("articole", [])

# Look for a known article from tables
target_codes = ["3270513", "TSC18B1", "CA02A1"]

for code in target_codes:
    found = None
    for art in articles:
        if code in art.get("cod", ""):
            found = art
            break
    
    if found:
        print(f"✓ {code} found: deviz={found.get('deviz')}, qty={found.get('cantitate')}")
    else:
        print(f"✗ {code} NOT found")
```

---

## Step 4: Validate Deviz Assignments

**Critical check**: All table-extracted articles should have valid deviz codes.

```python
import json

with open("output/extracted_articles.json") as f:
    articles = json.load(f).get("articole", [])

# Check for articles with missing/invalid deviz
suspicious = []
for art in articles:
    deviz = art.get("deviz", "").strip()
    if not deviz or not deviz[0].isdigit():
        suspicious.append(art)

if suspicious:
    print(f"⚠️  Found {len(suspicious)} articles with suspicious deviz:")
    for art in suspicious[:5]:
        print(f"  {art.get('cod')}: deviz='{art.get('deviz')}'")
else:
    print(f"✓ All {len(articles)} articles have valid deviz codes")
```

Expected: 0 suspicious articles.

---

## Step 5: Integration Testing (Optional)

Run your full pipeline (extraction + comparison + reporting):

```bash
python3 your_main_script.py

# Check results
ls -la output/
# You should see: extracted_articles.json, comparison_results.json, reports/
```

Monitor for:
- ✓ No errors during extraction
- ✓ Article count increased
- ✓ ARTICOL_LIPSA count decreased
- ✓ Deviz assignments are correct

---

## Troubleshooting

### Issue: "ModuleNotFoundError: No module named 'shared.table_extractor'"

**Fix**: Ensure file is in correct location:
```bash
ls -la shared/table_extractor.py  # Should exist
```

### Issue: No articles extracted from tables (0 articole din tabele)

**Causes**:
1. DI JSON doesn't have tables → Check input file
2. Tables don't match expected structure → Inspect table format
3. Metadata pattern not found → Check for "Stadiul fizic:" in row 5

**Debug**:
```python
import json
from shared.table_extractor import extract_articles_from_tables_smart

with open("your_di.json") as f:
    di = json.load(f)

tables = di.get("tables", [])
print(f"Total tables: {len(tables)}")

# Check for metadata tables
for idx, table in enumerate(tables):
    cells = table.get("cells", [])
    for cell in cells:
        if cell.get("row_index") == 5 and cell.get("column_index") == 0:
            content = cell.get("content", "").strip()
            if "STADIUL" in content.upper():
                print(f"Found metadata at table {idx}")
```

### Issue: Articles extracted but deviz is wrong

**Causes**:
1. Metadata table not recognized → Check row 5, col 0 pattern
2. Deviz code parsing failed → Check row 5, col 1 format

**Debug**:
```python
# Check what was parsed as metadata
from shared.table_extractor import extract_articles_from_tables_smart

# Add debug logging:
import logging
logging.basicConfig(level=logging.DEBUG)

articles = extract_articles_from_tables_smart(tables)
```

Look for log lines like:
```
[TABLE] Tabel 52: Metadata deviz 226108 - STRUCTURA DE REZISTENTA...
```

---

## Common Variations by Project

### Variation 1: Different Extraction Functions

If your extraction function has different name/signature:

**Before:**
```python
articles = extract_articles_v3(page_classes)  # Your function
```

**After:**
```python
articles = extract_articles_v3(page_classes)  # Your function

from shared.table_extractor import extract_articles_from_tables_smart
tables = di.get("tables", [])
if tables:
    articles_from_tables = extract_articles_from_tables_smart(tables)
    # ... deduplication code ...
```

The table extraction is **independent** of your line extraction function.

### Variation 2: Different Article Structure

If your articles use different field names (e.g., `code` instead of `cod`):

**Deduplication logic:**
```python
# Adapt to your field names
article_keys = set()
for art in articles:
    key = (art.get("code"), art.get("category"))  # Your field names
    article_keys.add(key)

for art in articles_from_tables:
    key = (art.get("code"), art.get("category"))
    if key not in article_keys:
        articles.append(art)
        article_keys.add(key)
```

### Variation 3: Logging Already Configured

If your project already has logging configured, the table extractor will use it automatically:

```python
import logging
logging.basicConfig(level=logging.INFO)  # Your config

# Table extractor will log to this same handler:
from shared.table_extractor import extract_articles_from_tables_smart
# No changes needed - logging just works
```

---

## Performance Tips

- **First run will be slowest**: ~500ms for 486 tables
- **Subsequent runs cached**: Use checkpoint files if available
- **Scale**: Linear with table count, handles 500+ tables without issue

---

## Before & After Metrics

### Reference Project Example

**Before table extraction:**
- Articles extracted: 83
- ARTICOL_LIPSA (missing): 12
- Processing time: 2.3s

**After table extraction:**
- Articles extracted: 1,288 (+1,150%)
- ARTICOL_LIPSA: 2 (-83%)
- Processing time: 2.5s (+0.2s)

**Result**: 83 → 1,288 articles with only +8% runtime increase.

---

## What Gets Extracted

### From Tables

Articles in "SECTIUNEA TEHNICA" tables:

```
Column 0: Nr. (sequence number)
Column 1: Capitol de lucrari (code - description)
Column 2: U.M. (unit of measure)
Column 3: Cantitatea (quantity)
Column 4: Pret unitar (unit price)
Column 5: Total (total price)
```

Extraction uses columns 0, 1, 2, 3 → Creates article record.

### NOT Extracted (Correct Behavior)

- Materials lists (8 columns, "Denumirea resursei materiale")
- Summary tables (7 columns, "Recapitulatie")
- Header/metadata tables without article data

---

## Next Steps

1. **Implement**: Follow Step 1-2 above
2. **Test**: Run Step 3 validation
3. **Deploy**: Commit and merge to main
4. **Monitor**: Compare metrics before/after

---

## Support

If issues arise:
1. Check troubleshooting section above
2. Enable DEBUG logging to see table identification
3. Inspect DI JSON table structure manually
4. Verify metadata table pattern matches specification

---

**Quick Start Version**: 1.0  
**Updated**: 2026-05-07  
**Status**: Ready for Implementation
