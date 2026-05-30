# Group Discovery v2 — Design Spec

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactorizare incrementală a detecției și matching-ului de grupuri pentru a funcționa autonom pe clienți noi, fără intervenție manuală de regex.

**Architecture:** DocumentProfiler detectează formatul per-fișier DI JSON (tables[] vs lines[]), GroupExtractor v2 extrage grupurile folosind structura Azure nativă când e disponibilă, AutonomousGroupMatcher converge autonom cu RapidFuzz + semnal oferta_only_count. Skill autoverify-groups orchestrează loop-ul.

**Tech Stack:** Python 3, pandas, rapidfuzz, Azure Document Intelligence JSON, Claude API (fallback LLM), pytest

---

## Constrângeri și invariante

- **Nicio regresie** pe clienții verificați: BR, CM, DT, SD. Baseline = valorile actuale `matched_groups / ref_only / oferta_only` din `holistic_oferta_N.json`.
- **Output identic** din GroupExtractor indiferent de modul TABLE/LINES: `{deviz_cod, obiectivul, obiectul, categoria}`.
- **`f3_regex_parser.py`, `f3_extractor.py`, `AgentComparator_local.py` — neatinse** în această iterație.
- **Phase 1 + Phase 1.5** din `group_comparator.py` — neschimbate. Refactorizăm doar Phase 2.
- **Knowledge cache existent** (`shared/group_match_knowledge.json`) rămâne valid și compatibil.
- **`f3_markers_knowledge.json`** — MANUAL ONLY, nu se atinge.

---

## Semnal de convergență (invariant business)

Grupurile din ofertă fără corespondent în referință (`oferta_only`) sunt **nenaturale** în domeniu: nu pot exista lucrări ofertate fără specificație tehnică. Deci:

| Semnal | Interpretare | Acțiune |
|--------|-------------|---------|
| `oferta_only > 3` | Referința n-a descoperit toate grupurile | Re-extracție referință cu profiler alternativ |
| `oferta_only` scade după retry | Extracție converge | Continuă loop |
| `oferta_only` stabil după 2 retry | Format nesuportat / document atipic | Escaladare raport |
| `ref_only` stabil după 2 retry | Diferență reală (ofertant a omis lucrări) | Raport final, fără fix |

---

## Componenta 1 — DocumentProfiler

**Fișier:** `shared/document_profiler.py` (fișier nou)

**Responsabilitate:** Inspectează un DI JSON și returnează profilul documentului.

### Interface

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class DocumentProfile:
    mode: Literal["TABLE", "LINES"]
    table_count: int          # câte tables[] cu ≥3 coloane și ≥5 rânduri
    has_header_row: bool      # dacă a găsit rând cu "nr.", "denumire", "cantitate"
    estimated_article_rows: int  # estimare rânduri de date (nu header)
    profiler_version: str = "1.0"

def profile_document(di_json: dict) -> DocumentProfile:
    """
    Inspectează di_json['tables'] și di_json['pages'].
    Returnează DocumentProfile cu mode TABLE sau LINES.
    """
```

### Logica de decizie TABLE vs LINES

```python
def _is_table_mode(di_json: dict) -> bool:
    tables = di_json.get("tables", [])
    for table in tables:
        cells = table.get("cells", [])
        row_count = max((c["rowIndex"] for c in cells), default=0) + 1
        col_count = max((c["columnIndex"] for c in cells), default=0) + 1
        if col_count >= 3 and row_count >= 5:
            # Verifică dacă există rând header cu keywords F3
            header_cells = [c for c in cells if c["rowIndex"] == 0]
            header_text = " ".join(c.get("content", "") for c in header_cells).lower()
            if any(kw in header_text for kw in ["nr.", "denumire", "cantitate", "u.m.", "um"]):
                return True
    return False
```

### Checkpoint

Profilul e salvat în `output_AO/<client>/checkpoints/profile_<hash>.json` (hash = MD5 primele 1000 bytes DI JSON). Reutilizat automat la re-run.

---

## Componenta 2 — GroupExtractor v2

**Fișier:** `shared/group_extractor.py` (fișier nou)

**Responsabilitate:** Extrage lista de grupuri `{deviz_cod, obiectivul, obiectul, categoria}` dintr-un DI JSON, folosind modul detectat de DocumentProfiler.

### Interface

```python
def extract_groups(di_json: dict, profile: DocumentProfile) -> list[dict]:
    """
    Returnează lista de grupuri unice.
    Fiecare grup: {deviz_cod, obiectivul, obiectul, categoria, source_mode}
    source_mode: "TABLE" sau "LINES"
    """
    if profile.mode == "TABLE":
        return _extract_groups_table(di_json)
    else:
        return _extract_groups_lines(di_json)
```

### Modul TABLE

```python
def _extract_groups_table(di_json: dict) -> list[dict]:
    """
    Reconstruiește matricea din tables[].cells cu pandas.
    Rândurile înainte de header = metadate deviz (obiectivul/obiectul/categoria).
    """
    import pandas as pd
    groups = []
    for table in di_json.get("tables", []):
        cells = table.get("cells", [])
        if not cells:
            continue
        # Reconstruiește matrice
        max_row = max(c["rowIndex"] for c in cells) + 1
        max_col = max(c["columnIndex"] for c in cells) + 1
        matrix = [[""] * max_col for _ in range(max_row)]
        for cell in cells:
            matrix[cell["rowIndex"]][cell["columnIndex"]] = cell.get("content", "").strip()
        df = pd.DataFrame(matrix)
        # Rândurile de deasupra tabelului de date conțin obiectivul/obiectul/categoria
        # Detectăm rândul header (primul rând cu "nr." sau "denumire")
        header_row_idx = _find_header_row(df)
        if header_row_idx is None:
            continue
        meta_rows = df.iloc[:header_row_idx]
        group = _parse_meta_rows(meta_rows)
        if group:
            group["source_mode"] = "TABLE"
            groups.append(group)
    return _dedup_groups(groups)
```

### Modul LINES

```python
def _extract_groups_lines(di_json: dict) -> list[dict]:
    """
    Delegă la deviz_header_extractor existent.
    Wrappuiește output în formatul standard.
    """
    from shared.deviz_header_extractor import extract_deviz_headers
    headers = extract_deviz_headers(di_json)
    groups = []
    for h in headers:
        groups.append({
            "deviz_cod": h.get("deviz_cod"),
            "obiectivul": h.get("obiectivul"),
            "obiectul": h.get("obiectul"),
            "categoria": h.get("categoria"),
            "source_mode": "LINES"
        })
    return groups
```

### Parsing meta-rânduri (TABLE mode)

```python
def _parse_meta_rows(meta_df) -> dict | None:
    """
    Caută pattern-uri în rândurile de metadate:
    - "Obiectivul:" urmat de valoare
    - "Obiectul:" urmat de valoare  
    - "Categoria de lucrari:" urmat de valoare
    - "Deviz oferta XXXXX" → deviz_cod
    """
    result = {}
    for _, row in meta_df.iterrows():
        text = " ".join(str(v) for v in row.values if v).strip()
        if not text:
            continue
        if "obiectivul" in text.lower():
            result["obiectivul"] = _extract_value_after_colon(text)
        elif "obiectul" in text.lower():
            result["obiectul"] = _extract_value_after_colon(text)
        elif "categoria" in text.lower():
            result["categoria"] = _extract_value_after_colon(text)
        elif re.search(r"deviz\s+oferta?\s+([A-Z0-9]{3,8})", text, re.IGNORECASE):
            m = re.search(r"deviz\s+oferta?\s+([A-Z0-9]{3,8})", text, re.IGNORECASE)
            result["deviz_cod"] = m.group(1)
    return result if result else None
```

---

## Componenta 3 — AutonomousGroupMatcher (refactor Phase 2)

**Fișier modificat:** `shared/group_comparator.py`

**Responsabilitate:** Extinde Phase 2 cu RapidFuzz similarity înainte de LLM. Adaugă convergence loop și `convergence_trace` în output.

### RapidFuzz Phase 2a (nou, înainte de LLM)

```python
from rapidfuzz import fuzz

def _match_by_rapidfuzz(ref_groups: list, oferta_groups: list, threshold: int = 85) -> list[tuple]:
    """
    Compară obiectul + categoria din ref vs ofertă.
    Returnează perechi (ref_idx, oferta_idx) cu score >= threshold.
    """
    matches = []
    used_oferta = set()
    for ri, rg in enumerate(ref_groups):
        ref_text = f"{rg.get('obiectul', '')} {rg.get('categoria', '')}".strip()
        best_score, best_oi = 0, -1
        for oi, og in enumerate(oferta_groups):
            if oi in used_oferta:
                continue
            off_text = f"{og.get('obiectul', '')} {og.get('categoria', '')}".strip()
            score = fuzz.token_sort_ratio(ref_text, off_text)
            if score > best_score:
                best_score, best_oi = score, oi
        if best_score >= threshold and best_oi >= 0:
            matches.append((ri, best_oi, best_score))
            used_oferta.add(best_oi)
    return matches
```

### Convergence loop

```python
def match_groups_autonomous(
    ref_groups: list,
    oferta_groups: list,
    di_ref_json: dict,
    client_name: str,
    max_iter: int = 3
) -> dict:
    """
    Loop de convergență:
    1. Phase 1 + Phase 1.5 (neschimbate)
    2. Phase 2a: RapidFuzz
    3. Phase 2b: Knowledge cache
    4. Phase 2c: LLM fallback
    5. Dacă oferta_only > MAX_OFERTA_ONLY → re-profil referință + retry
    """
    MAX_OFERTA_ONLY = 3
    trace = []
    
    for iteration in range(max_iter):
        result = _run_matching_phases(ref_groups, oferta_groups, client_name)
        oferta_only_count = len(result["oferta_only_groups"])
        
        trace.append({
            "iteration": iteration,
            "oferta_only_count": oferta_only_count,
            "ref_only_count": len(result["ref_only_groups"]),
            "matched_count": len(result["matched_groups"]),
            "strategy": result.get("strategy_used")
        })
        
        if oferta_only_count <= MAX_OFERTA_ONLY:
            break  # converged
            
        if iteration < max_iter - 1:
            # Re-profil referință cu strategie alternativă
            alt_profile = _alternate_profile(di_ref_json, iteration)
            ref_groups = extract_groups(di_ref_json, alt_profile)
    
    result["convergence_trace"] = trace
    result["converged"] = len(result["oferta_only_groups"]) <= MAX_OFERTA_ONLY
    return result
```

### Modificare în group_comparator.py

- Adaugă import `rapidfuzz`
- Inserează `_match_by_rapidfuzz` ca Phase 2a (înainte de `_match_by_knowledge`)
- Wrappuiește `match_groups` existent în `match_groups_autonomous`
- Adaugă `convergence_trace` la output `matching_debug_oferta_N.json`

---

## Componenta 4 — Skill autoverify-groups

**Fișier:** `.claude/commands/autoverify-groups.md` (fișier nou)

### Algoritmul skill-ului

```
Pas 1 — Citește starea curentă
  holistic_oferta_N.json → oferta_only_groups, ref_only_groups, matched_groups
  Dacă oferta_only == 0 și ref_only < 5 → STOP, totul e bine

Pas 2 — Diagnostică oferta_only
  Dacă oferta_only > 3:
    → Inspectează di_referinta.json: are tables[]? 
    → Compară cu modul curent din profile checkpoint
    → Dacă mod diferit disponibil → rerun pipeline cu profiler alternativ
    → Recompară oferta_only_count

Pas 3 — Diagnostică ref_only
  Pentru fiecare ref_only grup:
    → Caută denumire în di_oferta_N.json (fuzzy search, prag 70%)
    → Dacă găsit → propune adăugare în group_match_knowledge.json
    → Dacă negăsit → marchează ca diferență reală

Pas 4 — Aplică fix-uri și rerun
  Dacă s-au propus intrări knowledge → adaugă automat
  Rulează: python3 multi_client_run.py --client "<client>"
  Verifică: oferta_only a scăzut?

Pas 5 — Convergence check
  Dacă oferta_only == 0 → SUCCES
  Dacă 3 iterații fără reducere → ESCALADARE
    → Generează raport MD cu grupurile nerezolvate
    → Propune intervenție manuală

Pas 6 — Commit
  git add shared/group_match_knowledge.json
  git commit -m "fix(groups): autonomous group match <client> iteration N"
```

### Stop conditions
- `oferta_only == 0` → succes complet
- `oferta_only` stabil (±0) pe 2 iterații consecutive → escaladare
- `ref_only` stabil pe 2 iterații → diferență reală, raport final

---

## Integrare în pipeline

`local_run.py` se modifică minimal:

```python
# ÎNAINTE (actual):
from shared.deviz_header_extractor import extract_deviz_headers

# DUPĂ:
from shared.document_profiler import profile_document
from shared.group_extractor import extract_groups

profile = profile_document(di_json)
groups = extract_groups(di_json, profile)
# Dacă groups e gol → fallback la deviz_header_extractor (backward compat)
if not groups:
    groups = _legacy_extract_groups(di_json)
```

Modificarea e additivă — dacă `GroupExtractor v2` returnează gol, pipeline-ul cade pe comportamentul actual.

---

## Testare și validare

### Baseline (înainte de implementare)
Rulăm pe toți clienții verificați și salvăm:
```
BR:  matched=35, ref_only=0, oferta_only=0
CM:  matched=X,  ref_only=Y, oferta_only=Z
DT:  matched=189, ref_only=0, oferta_only=0 (O1), 189/0/0 (O2)
SD:  matched=X,  ref_only=Y, oferta_only=Z
```

### Criteriu de succes post-implementare
- Valorile de mai sus NU scad
- Pe un client nou, `autoverify-groups` converge în ≤3 iterații fără intervenție manuală

### Teste unitare noi
- `tests/shared/test_document_profiler.py` — TABLE vs LINES detection (mock DI JSON cu/fără tables[])
- `tests/shared/test_group_extractor.py` — output identic din ambele moduri pentru aceleași date
- `tests/shared/test_group_comparator_rapidfuzz.py` — Phase 2a matches corect cu threshold 85

### Dependențe noi
```
rapidfuzz>=3.0
pandas>=2.0  # dacă nu e deja instalat
```

Verificat cu: `pip show rapidfuzz pandas`

---

## Fișiere create/modificate

| Fișier | Acțiune | Note |
|--------|---------|------|
| `shared/document_profiler.py` | Creat | DocumentProfile, profile_document |
| `shared/group_extractor.py` | Creat | extract_groups (TABLE + LINES) |
| `shared/group_comparator.py` | Modificat | +Phase 2a RapidFuzz, +convergence_trace |
| `local_run.py` | Modificat minimal | +import profiler/extractor, fallback la legacy |
| `.claude/commands/autoverify-groups.md` | Creat | Skill autonom |
| `tests/shared/test_document_profiler.py` | Creat | 5+ teste |
| `tests/shared/test_group_extractor.py` | Creat | 5+ teste |
| `tests/shared/test_group_comparator_rapidfuzz.py` | Creat | 5+ teste |

**Neatinse:** `f3_regex_parser.py`, `f3_extractor.py`, `f3_page_classifier.py`, `AgentComparator_local.py`, `f3_markers_knowledge.json`
