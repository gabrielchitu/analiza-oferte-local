# Verification Agent — Design Spec
**Data:** 2026-05-27 | **Status:** Aprobat

---

## Goal

Agent de autoverificare a calitatii output-ului pipeline-ului de analiza oferte. Ruleaza independent, detecteaza erori structurale si de extractie, invata din pattern-uri, si genereaza raport MD cu findings + actiuni aplicate.

## Architecture

3 fisiere noi + 1 modificare minima in cod existent:

```
verify_agent.py                      # orchestrator CLI
shared/pipeline_verifier.py          # 6 checks, pur Python, fara LLM
shared/agent_knowledge.json          # jurnal runs + issues + thresholds per client
shared/ocr_patterns_knowledge.json   # OCR substitutii invatate (additive)
```

Modificare existenta: `AgentComparator_local.py::_normalize_cod` — incarca `ocr_patterns_knowledge.json` la startup si face UNION cu regulile hardcodate. Regulile hardcodate NU se sterg, NU se suprascriu.

---

## CLI

```bash
# Loop auto-fix, max 3 iteratii (default)
python3 verify_agent.py --client "Camin Maneciu"

# Verificare only — zero modificari, genereaza raport
python3 verify_agent.py --client "Camin Maneciu" --verify-only

# Custom nr iteratii
python3 verify_agent.py --client "Camin Maneciu" --max-iter 5

# Skip LLM diagnosis (rapid, fara API calls)
python3 verify_agent.py --client "Camin Maneciu" --no-llm
```

---

## Flux Loop

```
run pipeline (multi_client_run.py --client X)
    ↓
run verifier → findings[]
    ↓
LLM diagnoza pentru findings complexe (skip cu --no-llm)
    ↓
update knowledge files:
  - group_match_knowledge.json  (OFERTA_ONLY / REF_ONLY groups)
  - ocr_patterns_knowledge.json (COD_SIMILAR clusters noi)
    ↓
re-run pipeline
    ↓
convergenta? total_nc scazut < 5% fata de iteratia anterioara
OR max_iter atins → STOP
    ↓
genereaza output_AO/<Client>/verify_report_YYYY-MM-DD.md
```

**--verify-only:** sare tot dupa "run verifier" — zero modificari, genereaza raport imediat.

---

## Cele 6 Checks (shared/pipeline_verifier.py)

Modulul primeste `holistic_oferta_N.json`, returneaza `findings[]`. Pur Python, fara LLM, testabil independent.

| # | Check | Conditie | Severitate |
|---|-------|----------|------------|
| 1 | SILENT_VIOLATION | `ref_main - LIPSA != off_main - EXTRA` si `len(ncs) == 0` | CRITICAL |
| 2 | OFERTA_ONLY_GROUP | orice grup in `oferta_only_groups` | HIGH |
| 3 | REF_ONLY_GROUP | orice grup in `ref_only_groups` | HIGH |
| 4 | HIGH_EXTRA | grup matched cu `ARTICOL_EXTRA > threshold_extra` (default: **3**) | MEDIUM |
| 5 | HIGH_LIPSA | grup matched cu `ARTICOL_LIPSA > threshold_lipsa` (default: **3**) | MEDIUM |
| 6 | COD_SIMILAR_CLUSTER | grup matched cu `COD_SIMILAR > threshold_cod_sim` (default: 5) | LOW |
| 7 | EMPTY_MATCHED_GROUP | grup matched cu `ref_articles=[]` sau `oferta_articles=[]` | HIGH |

**Rational threshold 3:** Din perspectiva business, un grup matched cu > 3 EXTRA sau > 3 LIPSA indica eroare de extractie sau clasificare, nu neconformitate reala.

Fiecare finding:
```python
{
  "check": "HIGH_EXTRA",
  "severity": "MEDIUM",
  "oferta_n": 1,
  "group_key": "abc123...",
  "group_den": "BLOC 1 | Instalatii | Termice",
  "value": 164,
  "threshold": 3,
  "hypothesis": None   # completat de LLM dupa diagnoza
}
```

Thresholds configurabile per client in `agent_knowledge.json`.

---

## Auto-fix vs Escalare

### Poate auto-fixa (update knowledge files)

| Finding | Actiune | Fisier |
|---------|---------|--------|
| OFERTA_ONLY_GROUP | LLM gaseste pereche ref → adauga in knowledge | `group_match_knowledge.json` |
| REF_ONLY_GROUP | Idem | `group_match_knowledge.json` |
| COD_SIMILAR_CLUSTER | LLM extrage pattern substitutie → propune in fisier | `ocr_patterns_knowledge.json` |

### Escaladeaza la human (scrie in raport, nu atinge cod)

| Finding | Motiv |
|---------|-------|
| SILENT_VIOLATION | Bug in cod — investigatie manuala obligatorie |
| HIGH_EXTRA / HIGH_LIPSA | Necesita inspectie PDF sau fix in parser |
| EMPTY_MATCHED_GROUP | Bug matching — necesita cod |

---

## agent_knowledge.json — Structura

```json
{
  "Camin Maneciu": {
    "thresholds": {"extra": 3, "lipsa": 3, "cod_sim": 5},
    "runs": [
      {
        "timestamp": "2026-05-27T21:00:00",
        "iteration": 1,
        "metrics_before": {"total_nc": 733, "silent": 0, "oferta_only_groups": 0},
        "metrics_after":  {"total_nc": 680, "silent": 0, "oferta_only_groups": 0},
        "findings_count": 12,
        "actions_taken": ["group_match_knowledge: +2 perechi"]
      }
    ],
    "open_issues": [
      {
        "id": "CM-001",
        "check": "HIGH_EXTRA",
        "group_den": "BLOC 1 | Instalatii | Termice",
        "oferta_n": 1,
        "value": 164,
        "diagnosis": "Subcomponente clasificate ca principale in oferta",
        "status": "needs_human",
        "created": "2026-05-27"
      }
    ],
    "resolved_issues": []
  }
}
```

---

## ocr_patterns_knowledge.json — Structura

Fisierul porneste **gol**. Regulile hardcodate din `_normalize_cod` NU sunt copiate aici — ele raman in cod si se aplica intotdeauna. Fisierul contine NUMAI pattern-uri invatate dupa v12.0.

```json
{
  "char_substitutions": [
    {
      "from": "S",
      "to": "5",
      "source": "llm",
      "confidence": 0.9,
      "example": "SA131 vs 5A131",
      "client": "Camin Maneciu",
      "added": "2026-05-27"
    }
  ],
  "suffix_patterns": []
}
```

`_normalize_cod` la startup: `substitutions = HARDCODED_DICT | {r["from"]: r["to"] for r in learned}`. Learned nu poate suprascrie hardcodat.

---

## Raport MD — Format

Salvat in `output_AO/<Client>/verify_report_YYYY-MM-DD.md`.

```markdown
# Verification Report — <Client>
Generated: YYYY-MM-DD HH:MM | Iterations: N | Mode: auto-fix / verify-only

## Summary
| Metric | Start | Iter 1 | Iter 2 | Final |
|--------|-------|--------|--------|-------|
| Total NC | ... | ... | ... | ... |
| Silent violations | 0 | 0 | 0 | 0 |
| Oferta-only groups | N | ... | ... | ... |
| HIGH_EXTRA findings | N | ... | ... | ... |

## Auto-fixes Applied
- [iter 1] group_match_knowledge: +2 perechi ref-oferta
- [iter 1] ocr_patterns_knowledge: +1 substitutie propusa (validare manuala)

## CRITICAL — Necesita interventie manuala
(sau: _niciuna_ ✅)

## HIGH — Grupuri oferta_only / ref_only ramase
...

## MEDIUM — HIGH_EXTRA / HIGH_LIPSA
### Oferta 1 — <group_den>
- **N EXTRA** (threshold: 3)
- Diagnoza: "..."
- Actiune recomandata: "..."

## LOW — COD_SIMILAR clusters
...

## Convergenta
Loop oprit la iter N: <motiv (convergenta / max_iter)>
```

---

## Fisiere — Rezumat

| Fisier | Nou/Modificat | Rol |
|--------|--------------|-----|
| `verify_agent.py` | NOU | Orchestrator CLI, loop, raport MD |
| `shared/pipeline_verifier.py` | NOU | 6 checks, pur Python |
| `shared/agent_knowledge.json` | NOU | Jurnal + thresholds per client |
| `shared/ocr_patterns_knowledge.json` | NOU | OCR patterns invatate (additive) |
| `AgentComparator_local.py` | MODIFICAT | `_normalize_cod` incarca ocr_patterns_knowledge.json |

---

## Constrangeri

- Agentul NU modifica cod Python direct
- `ocr_patterns_knowledge.json` e ADDITIVE — regulile hardcodate din `_normalize_cod` raman inghetate
- Patterns noi in `ocr_patterns_knowledge.json` necesita validare manuala inainte de a fi considerate definitive (`"source": "llm"` vs `"source": "manual"`)
- Loop-ul nu ruleaza mai mult de `--max-iter` iteratii (default 3) indiferent de convergenta
