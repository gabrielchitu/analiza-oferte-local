# Verification Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent de autoverificare pipeline: 6 checks structurale, loop auto-fix cu convergenta, diagnoza LLM, raport MD.

**Architecture:** `shared/pipeline_verifier.py` (6 checks, pur Python) + `verify_agent.py` (orchestrator CLI, loop, MD report) + `shared/ocr_patterns_knowledge.json` (OCR patterns additive). `_normalize_cod` incarca patterns din fisier la startup, UNION cu hardcodate.

**Tech Stack:** Python 3.14, python-docx (deja instalat), anthropic SDK (deja in proiect via `anthropic_adapter.py`), pathlib, argparse.

---

## Context obligatoriu pentru agentic workers

Proiect: pipeline analiza oferte constructii. Entry point: `multi_client_run.py`.
- `local_run.run_pipeline(ClientConfig)` — ruleaza pipeline complet pentru un client
- `ClientConfig.from_folder(name, input_base, output_base)` — construieste config din folder
- `input_AO/<Client>/` — input JSON (di_referinta.json + di_oferta_N.json)
- `output_AO/<Client>/holistic_oferta_N.json` — output principal cu grupuri si neconformitati
- `shared/group_match_knowledge.json` — cache LLM perechi grupuri per client
- `shared/ocr_patterns_knowledge.json` — CREAT in Task 1 (additive OCR patterns)
- `AgentComparator_local.py:51-84` — `_normalize_cod()` care trebuie modificat in Task 1
- `shared/agent_knowledge.json` — CREAT in Task 3 (jurnal agent per client)

---

## Task 1: OCR Patterns Knowledge File + _normalize_cod Additive Loading

**Files:**
- Create: `shared/ocr_patterns_knowledge.json`
- Modify: `AgentComparator_local.py:1-10` (imports) + `AgentComparator_local.py:51-84` (_normalize_cod)
- Test: `tests/shared/test_ocr_patterns_knowledge.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/shared/test_ocr_patterns_knowledge.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch


def test_normalize_cod_applies_learned_substitution(tmp_path):
    """Learned pattern B→8 applied on top of hardcoded rules."""
    patterns = {
        "char_substitutions": [
            {"from": "B", "to": "8", "source": "llm", "confidence": 0.9,
             "example": "BC35A vs 8C35A", "client": "Test", "added": "2026-05-27"}
        ],
        "suffix_patterns": []
    }
    ocr_file = tmp_path / "ocr_patterns_knowledge.json"
    ocr_file.write_text(json.dumps(patterns))

    with patch("AgentComparator_local._OCR_PATTERNS_FILE", ocr_file):
        # reload learned dict
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("BC35A")
    assert result == "8C35A"


def test_normalize_cod_learned_does_not_override_hardcoded(tmp_path):
    """Learned pattern cannot override hardcoded I→1."""
    patterns = {
        "char_substitutions": [
            {"from": "I", "to": "9", "source": "llm", "confidence": 0.9,
             "example": "bad idea", "client": "Test", "added": "2026-05-27"}
        ],
        "suffix_patterns": []
    }
    ocr_file = tmp_path / "ocr_patterns_knowledge.json"
    ocr_file.write_text(json.dumps(patterns))

    with patch("AgentComparator_local._OCR_PATTERNS_FILE", ocr_file):
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("IC35D")
    # I must still → 1 (hardcoded), not 9 (learned)
    assert result == "1C35D"


def test_normalize_cod_missing_ocr_file(tmp_path):
    """Missing ocr_patterns_knowledge.json → behaves exactly as before."""
    missing = tmp_path / "nonexistent.json"
    with patch("AgentComparator_local._OCR_PATTERNS_FILE", missing):
        import AgentComparator_local as ac
        ac._OCR_LEARNED = ac._load_ocr_learned()
        result = ac._normalize_cod("SA13I")
    assert result == "SA131"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/shared/test_ocr_patterns_knowledge.py -v
```
Expected: FAIL — `_OCR_PATTERNS_FILE` and `_load_ocr_learned` not defined.

- [ ] **Step 3: Create `shared/ocr_patterns_knowledge.json` (empty)**

```json
{
  "char_substitutions": [],
  "suffix_patterns": []
}
```

- [ ] **Step 4: Modify `AgentComparator_local.py`**

Adauga dupa imports existente (linia ~10, dupa `import re`):

```python
import json as _json
from pathlib import Path as _Path

_OCR_PATTERNS_FILE = _Path(__file__).parent / "shared" / "ocr_patterns_knowledge.json"
_HARDCODED_FROM = {'L', 'I', 'O'}  # chars handled by hardcoded rules in _normalize_cod


def _load_ocr_learned() -> dict:
    """Load additive OCR substitutions from knowledge file. Never overrides hardcoded."""
    try:
        data = _json.loads(_OCR_PATTERNS_FILE.read_text())
        return {
            r["from"].upper(): r["to"]
            for r in data.get("char_substitutions", [])
            if r["from"].upper() not in _HARDCODED_FROM
        }
    except Exception:
        return {}


_OCR_LEARNED: dict = _load_ocr_learned()
```

Modifica `_normalize_cod` (linia 58, dupa `cod = (cod or "").strip().upper()`):

```python
def _normalize_cod(cod: str) -> str:
    """
    DEPRECATED: Use clean_code() instead for general code cleaning.

    This function applies aggressive transformations that break valid codes.
    Kept for backward compatibility with Layer 2 fuzzy matching only.
    """
    cod = (cod or "").strip().upper()
    # OCR fix: lowercase 'l' often confused with digit '1'
    cod = cod.replace('l', '1').replace('L', '1')
    # OCR fix: letter 'I' often confused with digit '1' — normalize I to 1
    # SA13I# vs SA131# should be treated as identical
    cod = cod.replace('I', '1')
    # OCR fix: letter 'O' often confused with digit '0' — normalize to '0'
    # IZDO4D1 → IZD04D1 (O becomes 0 in PDF)
    cod = cod.replace('O', '0')
    # Apply learned OCR patterns (additive — never override hardcoded above)
    for src, dst in _OCR_LEARNED.items():
        cod = cod.replace(src, dst)
    if cod.startswith('$'):
        num = re.sub(r'[^0-9]', '', cod[1:])
        if len(num) >= 8:
            num = num[:7]
        return '$' + num if num else cod
    if re.match(r'^\d+$', cod):
        return '$' + cod
    m_util = re.match(r'^[A-Z]{2,5}(\d{4,5})$', cod)
    if m_util:
        return '$' + m_util.group(1)
    m = re.match(r'^([A-Z]{2,5}\d{2,4}[A-Z]?\d{0,2})', cod)
    return m.group(1) if m else re.sub(r'[^A-Z0-9]', '', cod)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/shared/test_ocr_patterns_knowledge.py -v
```
Expected: 3 PASS.

- [ ] **Step 6: Commit**

```bash
git add shared/ocr_patterns_knowledge.json AgentComparator_local.py \
        tests/shared/test_ocr_patterns_knowledge.py
git commit -m "feat(ocr): additive OCR patterns knowledge file + _normalize_cod union loading"
```

---

## Task 2: shared/pipeline_verifier.py — 6 Checks

**Files:**
- Create: `shared/pipeline_verifier.py`
- Test: `tests/shared/test_pipeline_verifier.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/shared/test_pipeline_verifier.py
import pytest
from shared.pipeline_verifier import verify_holistic, Finding, DEFAULT_THRESHOLDS


def _make_group(ref_arts=None, oferta_arts=None, ncs=None,
                ref_cod="DEV1", oferta_cod="DEV1", den="Test deviz"):
    return {
        "ref_deviz_cod": ref_cod,
        "oferta_deviz_cod": oferta_cod,
        "deviz_denumire": den,
        "ref_articles": ref_arts or [],
        "oferta_articles": oferta_arts or [],
        "neconformitati": ncs or [],
    }


def _art(is_component=False, cant=1.0):
    return {"is_component": is_component, "cantitate": cant, "cod": "A01"}


def _nc(tip):
    return {"tip": tip}


def _holistic(matched=None, ref_only=None, oferta_only=None):
    return {
        "matched_groups": matched or [],
        "ref_only_groups": ref_only or [],
        "oferta_only_groups": oferta_only or [],
    }


# --- SILENT_VIOLATION ---

def test_silent_violation_detected():
    g = _make_group(ref_arts=[_art(), _art()], oferta_arts=[_art()], ncs=[])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    silent = [f for f in findings if f.check == "SILENT_VIOLATION"]
    assert len(silent) == 1
    assert silent[0].severity == "CRITICAL"


def test_no_silent_violation_when_nc_present():
    g = _make_group(ref_arts=[_art(), _art()], oferta_arts=[_art()],
                    ncs=[_nc("ARTICOL_LIPSA")])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    silent = [f for f in findings if f.check == "SILENT_VIOLATION"]
    assert len(silent) == 0


# --- OFERTA_ONLY_GROUP ---

def test_oferta_only_group_detected():
    g = {"oferta_deviz_cod": "OFF1", "deviz_denumire": "Extra group",
         "articles": [_art()], "neconformitati": []}
    data = _holistic(oferta_only=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "OFERTA_ONLY_GROUP"]
    assert len(found) == 1
    assert found[0].severity == "HIGH"


# --- REF_ONLY_GROUP ---

def test_ref_only_group_detected():
    g = {"ref_deviz_cod": "REF1", "deviz_denumire": "Missing group",
         "articles": [_art()], "neconformitati": []}
    data = _holistic(ref_only=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "REF_ONLY_GROUP"]
    assert len(found) == 1


# --- HIGH_EXTRA ---

def test_high_extra_detected_above_threshold():
    ncs = [_nc("ARTICOL_EXTRA")] * 5
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"extra": 3})
    found = [f for f in findings if f.check == "HIGH_EXTRA"]
    assert len(found) == 1
    assert found[0].value == 5
    assert found[0].threshold == 3


def test_high_extra_not_triggered_at_threshold():
    ncs = [_nc("ARTICOL_EXTRA")] * 3
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"extra": 3})
    found = [f for f in findings if f.check == "HIGH_EXTRA"]
    assert len(found) == 0


# --- HIGH_LIPSA ---

def test_high_lipsa_detected():
    ncs = [_nc("ARTICOL_LIPSA")] * 4
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"lipsa": 3})
    found = [f for f in findings if f.check == "HIGH_LIPSA"]
    assert len(found) == 1


# --- COD_SIMILAR_CLUSTER ---

def test_cod_similar_cluster_detected():
    ncs = [_nc("COD_SIMILAR")] * 6
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"cod_sim": 5})
    found = [f for f in findings if f.check == "COD_SIMILAR_CLUSTER"]
    assert len(found) == 1


# --- EMPTY_MATCHED_GROUP ---

def test_empty_matched_group_detected():
    g = _make_group(ref_arts=[], oferta_arts=[_art()])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "EMPTY_MATCHED_GROUP"]
    assert len(found) == 1
    assert found[0].severity == "HIGH"
```

- [ ] **Step 2: Run to verify fail**

```bash
python3 -m pytest tests/shared/test_pipeline_verifier.py -v
```
Expected: FAIL — `shared.pipeline_verifier` does not exist.

- [ ] **Step 3: Implement `shared/pipeline_verifier.py`**

```python
# shared/pipeline_verifier.py
"""
Pipeline output verifier — 6 structural checks on holistic_oferta_N.json.
Pure Python, no LLM, no side effects. Returns list of Finding objects.
"""
from __future__ import annotations
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_THRESHOLDS = {"extra": 3, "lipsa": 3, "cod_sim": 5}


@dataclass
class Finding:
    check: str           # "SILENT_VIOLATION" | "OFERTA_ONLY_GROUP" | "REF_ONLY_GROUP"
                         # | "HIGH_EXTRA" | "HIGH_LIPSA" | "COD_SIMILAR_CLUSTER"
                         # | "EMPTY_MATCHED_GROUP"
    severity: str        # "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"
    oferta_n: int
    group_key: str
    group_den: str
    value: int           # the count that triggered the check (e.g. nr EXTRA)
    threshold: int       # threshold that was exceeded (0 if not applicable)
    hypothesis: Optional[str] = None   # filled later by LLM diagnosis


def _get_main_count(articles: list) -> int:
    return sum(
        1 for a in articles
        if not a.get("is_component", False) and (a.get("cantitate") or 0) > 0
    )


def verify_holistic(data: dict, oferta_n: int, thresholds: dict) -> list[Finding]:
    """Run all 6 checks on a single holistic_oferta_N.json dict."""
    thr = {**DEFAULT_THRESHOLDS, **thresholds}
    findings: list[Finding] = []

    for g in data.get("matched_groups", []):
        ref_main = _get_main_count(g.get("ref_articles", []))
        off_main = _get_main_count(g.get("oferta_articles", []))
        ncs = g.get("neconformitati", [])
        lipsa  = sum(1 for nc in ncs if nc.get("tip") == "ARTICOL_LIPSA")
        extra  = sum(1 for nc in ncs if nc.get("tip") == "ARTICOL_EXTRA")
        cod_sim = sum(1 for nc in ncs if nc.get("tip") == "COD_SIMILAR")
        key = g.get("ref_deviz_cod") or g.get("oferta_deviz_cod") or ""
        den = g.get("deviz_denumire") or key

        # Check 1: SILENT_VIOLATION
        if ref_main - lipsa != off_main - extra and not ncs:
            findings.append(Finding(
                check="SILENT_VIOLATION", severity="CRITICAL",
                oferta_n=oferta_n, group_key=key, group_den=den,
                value=ref_main - off_main, threshold=0,
            ))

        # Check 4: HIGH_EXTRA
        if extra > thr["extra"]:
            findings.append(Finding(
                check="HIGH_EXTRA", severity="MEDIUM",
                oferta_n=oferta_n, group_key=key, group_den=den,
                value=extra, threshold=thr["extra"],
            ))

        # Check 5: HIGH_LIPSA
        if lipsa > thr["lipsa"]:
            findings.append(Finding(
                check="HIGH_LIPSA", severity="MEDIUM",
                oferta_n=oferta_n, group_key=key, group_den=den,
                value=lipsa, threshold=thr["lipsa"],
            ))

        # Check 6: COD_SIMILAR_CLUSTER
        if cod_sim > thr["cod_sim"]:
            findings.append(Finding(
                check="COD_SIMILAR_CLUSTER", severity="LOW",
                oferta_n=oferta_n, group_key=key, group_den=den,
                value=cod_sim, threshold=thr["cod_sim"],
            ))

        # Check 7: EMPTY_MATCHED_GROUP
        if not g.get("ref_articles") or not g.get("oferta_articles"):
            findings.append(Finding(
                check="EMPTY_MATCHED_GROUP", severity="HIGH",
                oferta_n=oferta_n, group_key=key, group_den=den,
                value=0, threshold=0,
            ))

    # Check 2: OFERTA_ONLY_GROUP
    for g in data.get("oferta_only_groups", []):
        key = g.get("oferta_deviz_cod") or ""
        den = g.get("deviz_denumire") or key
        findings.append(Finding(
            check="OFERTA_ONLY_GROUP", severity="HIGH",
            oferta_n=oferta_n, group_key=key, group_den=den,
            value=len(g.get("articles", [])), threshold=0,
        ))

    # Check 3: REF_ONLY_GROUP
    for g in data.get("ref_only_groups", []):
        key = g.get("ref_deviz_cod") or ""
        den = g.get("deviz_denumire") or key
        findings.append(Finding(
            check="REF_ONLY_GROUP", severity="HIGH",
            oferta_n=oferta_n, group_key=key, group_den=den,
            value=len(g.get("articles", [])), threshold=0,
        ))

    return findings


def verify_client(output_dir: str | Path, thresholds: dict | None = None) -> list[Finding]:
    """Run verify_holistic across all holistic_oferta_N.json for a client."""
    thresholds = thresholds or {}
    findings: list[Finding] = []
    for n in range(1, 10):
        path = Path(output_dir) / f"holistic_oferta_{n}.json"
        if not path.exists():
            break
        data = json.loads(path.read_text())
        findings.extend(verify_holistic(data, n, thresholds))
    return findings


def count_total_nc(output_dir: str | Path) -> int:
    """Count all neconformitati across all holistic files for a client."""
    total = 0
    for n in range(1, 10):
        path = Path(output_dir) / f"holistic_oferta_{n}.json"
        if not path.exists():
            break
        data = json.loads(path.read_text())
        for g in data.get("matched_groups", []) + data.get("ref_only_groups", []):
            total += len(g.get("neconformitati", []))
    return total
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/shared/test_pipeline_verifier.py -v
```
Expected: 9 PASS.

- [ ] **Step 5: Commit**

```bash
git add shared/pipeline_verifier.py tests/shared/test_pipeline_verifier.py
git commit -m "feat(verifier): pipeline_verifier.py — 6 structural checks on holistic output"
```

---

## Task 3: verify_agent.py — Orchestrator CLI + Loop + MD Report (fara LLM)

**Files:**
- Create: `verify_agent.py`
- Create: `shared/agent_knowledge.json` (empty init)
- Test: `tests/test_verify_agent.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_verify_agent.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from verify_agent import (
    load_agent_knowledge, save_agent_knowledge,
    get_client_thresholds, _generate_md_report, _record_run,
)


def test_load_agent_knowledge_missing_file(tmp_path):
    kb_file = tmp_path / "agent_knowledge.json"
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        result = load_agent_knowledge()
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    kb_file = tmp_path / "agent_knowledge.json"
    data = {"Test Client": {"thresholds": {"extra": 3}}}
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        save_agent_knowledge(data)
        loaded = load_agent_knowledge()
    assert loaded == data


def test_get_client_thresholds_default():
    knowledge = {}
    result = get_client_thresholds(knowledge, "Nonexistent")
    assert result == {}


def test_get_client_thresholds_custom():
    knowledge = {"CM": {"thresholds": {"extra": 5, "lipsa": 2}}}
    result = get_client_thresholds(knowledge, "CM")
    assert result == {"extra": 5, "lipsa": 2}


def test_record_run_appends(tmp_path):
    kb_file = tmp_path / "ak.json"
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        knowledge = {}
        _record_run(knowledge, "CM", iteration=1,
                    nc_before=100, nc_after=80, findings_count=5, actions=[])
        assert "CM" in knowledge
        assert len(knowledge["CM"]["runs"]) == 1
        run = knowledge["CM"]["runs"][0]
        assert run["iteration"] == 1
        assert run["nc_before"] == 100
        assert run["nc_after"] == 80


def test_generate_md_report_contains_client_name():
    from shared.pipeline_verifier import Finding
    findings = [
        Finding("HIGH_EXTRA", "MEDIUM", 1, "DEV1", "Test deviz", 10, 3,
                hypothesis="Subcomponente clasificate gresit")
    ]
    iterations = [
        {"iteration": 1, "nc_before": 100, "nc_after": 80,
         "findings_count": 5, "actions": ["group_match: +1 pereche"]}
    ]
    report = _generate_md_report("Camin Maneciu", iterations, findings,
                                 stopped_reason="convergenta")
    assert "Camin Maneciu" in report
    assert "HIGH_EXTRA" in report
    assert "Test deviz" in report
    assert "convergenta" in report
```

- [ ] **Step 2: Run to verify fail**

```bash
python3 -m pytest tests/test_verify_agent.py -v
```
Expected: FAIL — `verify_agent` does not exist.

- [ ] **Step 3: Create `shared/agent_knowledge.json`**

```json
{}
```

- [ ] **Step 4: Implement `verify_agent.py`**

```python
#!/usr/bin/env python3
"""
verify_agent.py — Pipeline verification agent.

Usage:
    python3 verify_agent.py --client "Camin Maneciu"
    python3 verify_agent.py --client "Camin Maneciu" --verify-only
    python3 verify_agent.py --client "Camin Maneciu" --max-iter 5 --no-llm
"""
import argparse
import json
import datetime
import sys
from pathlib import Path
from typing import Optional

from shared.client_config import ClientConfig
from shared.pipeline_verifier import verify_client, count_total_nc, Finding

AGENT_KNOWLEDGE_FILE = Path("shared/agent_knowledge.json")
INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")
CONVERGENCE_THRESHOLD = 0.05  # stop if nc reduction < 5%


# ── Knowledge helpers ─────────────────────────────────────────────────────────

def load_agent_knowledge() -> dict:
    if AGENT_KNOWLEDGE_FILE.exists():
        return json.loads(AGENT_KNOWLEDGE_FILE.read_text())
    return {}


def save_agent_knowledge(knowledge: dict) -> None:
    AGENT_KNOWLEDGE_FILE.write_text(
        json.dumps(knowledge, indent=2, ensure_ascii=False)
    )


def get_client_thresholds(knowledge: dict, client_name: str) -> dict:
    return knowledge.get(client_name, {}).get("thresholds", {})


def _record_run(knowledge: dict, client_name: str, iteration: int,
                nc_before: int, nc_after: int, findings_count: int,
                actions: list[str]) -> None:
    if client_name not in knowledge:
        knowledge[client_name] = {"thresholds": {}, "runs": [], "open_issues": []}
    knowledge[client_name]["runs"].append({
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "iteration": iteration,
        "nc_before": nc_before,
        "nc_after": nc_after,
        "findings_count": findings_count,
        "actions": actions,
    })


# ── Report generation ─────────────────────────────────────────────────────────

def _generate_md_report(client_name: str, iterations: list[dict],
                         findings: list[Finding], stopped_reason: str) -> str:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    mode = "verify-only" if not iterations else "auto-fix"
    n_iter = len(iterations)

    lines = [
        f"# Verification Report — {client_name}",
        f"Generated: {now} | Iterations: {n_iter} | Mode: {mode}",
        "",
    ]

    # Summary table
    if iterations:
        lines += ["## Summary", ""]
        header = "| Metric |" + "".join(f" Iter {i['iteration']} |" for i in iterations)
        sep    = "|--------|" + "".join("--------|" for _ in iterations)
        nc_row = "| Total NC |" + "".join(f" {i['nc_after']} |" for i in iterations)
        lines += [header, sep, nc_row, ""]

    # Auto-fixes
    if iterations:
        lines += ["## Auto-fixes Applied", ""]
        any_action = False
        for it in iterations:
            for action in it.get("actions", []):
                lines.append(f"- [iter {it['iteration']}] {action}")
                any_action = True
        if not any_action:
            lines.append("_niciuna_")
        lines.append("")

    # Group by severity
    for severity, label in [
        ("CRITICAL", "CRITICAL — Necesita interventie manuala"),
        ("HIGH", "HIGH — Grupuri lipsa / extra / goale"),
        ("MEDIUM", "MEDIUM — HIGH_EXTRA / HIGH_LIPSA (eroare extractie probabila)"),
        ("LOW", "LOW — COD_SIMILAR clusters"),
    ]:
        bucket = [f for f in findings if f.severity == severity]
        lines += [f"## {label}", ""]
        if not bucket:
            lines += ["_niciuna_ ✅", ""]
            continue
        for f in bucket:
            lines.append(f"### Oferta {f.oferta_n} — {f.group_den}")
            lines.append(f"- **Check:** {f.check}  |  **Value:** {f.value}  |  **Threshold:** {f.threshold}")
            if f.hypothesis:
                lines.append(f"- **Diagnoza:** {f.hypothesis}")
            lines.append("")

    lines += [
        "## Convergenta",
        f"Loop oprit: **{stopped_reason}**",
        "",
    ]

    return "\n".join(lines)


# ── Pipeline runner ───────────────────────────────────────────────────────────

def _run_pipeline(cfg: ClientConfig) -> None:
    from local_run import run_pipeline
    run_pipeline(cfg)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline verification agent")
    parser.add_argument("--client", required=True, help="Client name (must match input_AO folder)")
    parser.add_argument("--verify-only", action="store_true",
                        help="Run checks only, no knowledge updates, no re-run")
    parser.add_argument("--max-iter", type=int, default=3,
                        help="Max auto-fix iterations (default: 3)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Skip LLM diagnosis and auto-fix")
    args = parser.parse_args()

    cfg = ClientConfig.from_folder(args.client, INPUT_BASE, OUTPUT_BASE)
    if not cfg.validate():
        print(f"[ERROR] Client '{args.client}' not found in {INPUT_BASE}/")
        sys.exit(1)

    knowledge = load_agent_knowledge()
    thresholds = get_client_thresholds(knowledge, args.client)

    # First pipeline run
    print(f"[AGENT] Running pipeline for '{args.client}'...")
    _run_pipeline(cfg)

    if args.verify_only:
        findings = verify_client(cfg.output_dir, thresholds)
        report = _generate_md_report(args.client, [], findings, "verify-only")
        report_path = cfg.output_dir / f"verify_report_{datetime.date.today()}.md"
        report_path.write_text(report)
        print(f"[AGENT] Report saved: {report_path}")
        _print_summary(findings)
        return

    # Auto-fix loop
    iterations: list[dict] = []
    prev_nc = count_total_nc(cfg.output_dir)
    stopped_reason = f"max-iter ({args.max_iter})"

    for i in range(1, args.max_iter + 1):
        print(f"[AGENT] Iteration {i}/{args.max_iter} — checking...")
        findings = verify_client(cfg.output_dir, thresholds)
        nc_after = count_total_nc(cfg.output_dir)

        actions: list[str] = []
        if not args.no_llm:
            actions = _diagnose_and_fix(findings, args.client, knowledge)
            if actions:
                save_agent_knowledge(knowledge)

        _record_run(knowledge, args.client, i, prev_nc, nc_after,
                    len(findings), actions)
        save_agent_knowledge(knowledge)

        iterations.append({
            "iteration": i, "nc_before": prev_nc, "nc_after": nc_after,
            "findings_count": len(findings), "actions": actions,
        })

        # Convergence check (from iter 2 onward)
        if i > 1:
            reduction = (prev_nc - nc_after) / max(prev_nc, 1)
            if reduction < CONVERGENCE_THRESHOLD:
                stopped_reason = f"convergenta (reducere {reduction:.1%} < {CONVERGENCE_THRESHOLD:.0%})"
                print(f"[AGENT] Convergenta atinsa la iter {i}: {stopped_reason}")
                break

        prev_nc = nc_after

        if i < args.max_iter:
            print(f"[AGENT] Re-running pipeline...")
            _run_pipeline(cfg)

    # Final check after last pipeline run
    findings = verify_client(cfg.output_dir, thresholds)
    report = _generate_md_report(args.client, iterations, findings, stopped_reason)
    report_path = cfg.output_dir / f"verify_report_{datetime.date.today()}.md"
    report_path.write_text(report)
    print(f"[AGENT] Report saved: {report_path}")
    _print_summary(findings)


def _print_summary(findings: list[Finding]) -> None:
    by_severity = {}
    for f in findings:
        by_severity[f.severity] = by_severity.get(f.severity, 0) + 1
    print("[AGENT] Findings summary:")
    for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
        n = by_severity.get(sev, 0)
        flag = "✅" if n == 0 else "⚠️"
        print(f"  {flag} {sev}: {n}")


def _diagnose_and_fix(findings: list[Finding], client_name: str,
                      knowledge: dict) -> list[str]:
    """LLM diagnosis — implemented in Task 4. Returns list of action strings."""
    return []  # stub — filled in Task 4


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_verify_agent.py -v
```
Expected: 6 PASS.

- [ ] **Step 6: Smoke test — verify-only on Camin Maneciu**

```bash
python3 verify_agent.py --client "Camin Maneciu" --verify-only --no-llm
```
Expected: prints findings summary, creates `output_AO/Camin Maneciu/verify_report_2026-05-27.md`.

- [ ] **Step 7: Commit**

```bash
git add verify_agent.py shared/agent_knowledge.json tests/test_verify_agent.py
git commit -m "feat(agent): verify_agent.py — CLI orchestrator, loop, MD report"
```

---

## Task 4: LLM Diagnosis Integration

**Files:**
- Modify: `verify_agent.py` — `_diagnose_and_fix()` (linia cu `return []`)
- Test: `tests/test_verify_agent_llm.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_verify_agent_llm.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from shared.pipeline_verifier import Finding
from verify_agent import _diagnose_and_fix


def _finding(check, severity="MEDIUM", oferta_n=1,
             group_key="DEV1", group_den="Test grup", value=10, threshold=3):
    return Finding(check, severity, oferta_n, group_key, group_den, value, threshold)


def _mock_llm_client(response_text: str):
    mock = MagicMock()
    mock.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=response_text))
    ]
    return mock


def test_high_extra_gets_hypothesis(tmp_path):
    """HIGH_EXTRA finding gets a hypothesis string from LLM."""
    findings = [_finding("HIGH_EXTRA")]
    knowledge = {}

    llm_response = "Articolele sunt subcomponente clasificate ca principale in oferta."
    mock_client = _mock_llm_client(llm_response)

    with patch("verify_agent._get_llm_client", return_value=(mock_client, "claude-sonnet-4-6")):
        _diagnose_and_fix(findings, "TestClient", knowledge)

    assert findings[0].hypothesis is not None
    assert len(findings[0].hypothesis) > 10


def test_oferta_only_adds_to_group_knowledge(tmp_path):
    """OFERTA_ONLY_GROUP: LLM match → written to group_match_knowledge.json."""
    findings = [_finding("OFERTA_ONLY_GROUP", severity="HIGH",
                         group_den="BLOC 1 | Arhitectura | Finisaje")]
    knowledge = {}

    llm_json = json.dumps([{
        "ref_den": "BLOC 1 | Arhitectura | Finisaje interioare",
        "oferta_den": "BLOC 1 | Arhitectura | Finisaje",
        "confidence": 0.9
    }])
    mock_client = _mock_llm_client(llm_json)

    gm_file = tmp_path / "group_match_knowledge.json"
    gm_file.write_text(json.dumps({}))

    with patch("verify_agent._get_llm_client", return_value=(mock_client, "model")), \
         patch("verify_agent.GROUP_MATCH_KNOWLEDGE_FILE", gm_file):
        actions = _diagnose_and_fix(findings, "TestClient", knowledge)

    data = json.loads(gm_file.read_text())
    assert "TestClient" in data
    assert len(data["TestClient"]) == 1
    assert len(actions) == 1


def test_no_llm_skips_diagnosis():
    """When LLM client unavailable, _diagnose_and_fix returns empty actions."""
    findings = [_finding("HIGH_EXTRA")]
    with patch("verify_agent._get_llm_client", return_value=(None, "")):
        actions = _diagnose_and_fix(findings, "TestClient", {})
    assert actions == []
    assert findings[0].hypothesis is None
```

- [ ] **Step 2: Run to verify fail**

```bash
python3 -m pytest tests/test_verify_agent_llm.py -v
```
Expected: FAIL — `_get_llm_client` and full `_diagnose_and_fix` not implemented.

- [ ] **Step 3: Implement `_diagnose_and_fix` in `verify_agent.py`**

Inlocuieste stub-ul `_diagnose_and_fix` si adauga `_get_llm_client` si `GROUP_MATCH_KNOWLEDGE_FILE`:

```python
import os
GROUP_MATCH_KNOWLEDGE_FILE = Path("shared/group_match_knowledge.json")

_DIAGNOSIS_PROMPT = """\
Esti un expert in analiza ofertelor de constructii. Ti se da un finding din pipeline-ul de analiza.
Explica in 1-2 propozitii cauza probabila si actiunea recomandata. Raspunde in romana. Fii concis.

Finding: {check}
Grup: {group_den}
Valoare: {value} (threshold: {threshold})
"""

_GROUP_MATCH_PROMPT = """\
Esti un expert in analiza ofertelor de constructii romanesti.
Ai urmatoarele grupuri de deviz DIN OFERTA care nu au corespondent in referinta:
{oferta_groups}

Returneaza un JSON array cu perechile probabile ref→oferta. Format strict:
[{{"ref_den": "...", "oferta_den": "...", "confidence": 0.0-1.0}}]
Daca nu esti sigur (confidence < 0.7), nu include perechea.
Daca nu gasesti nicio pereche, returneaza [].
"""


def _get_llm_client():
    """Returns (client, model) or (None, '') if unavailable."""
    try:
        import anthropic
        from anthropic_adapter import AnthropicAdapter
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return None, ""
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
        client = AnthropicAdapter(anthropic.Anthropic(api_key=api_key), model=model)
        return client, model
    except Exception:
        return None, ""


def _diagnose_and_fix(findings: list[Finding], client_name: str,
                      knowledge: dict) -> list[str]:
    """LLM diagnosis + auto-fix for eligible findings. Returns action strings."""
    llm_client, model = _get_llm_client()
    if not llm_client:
        return []

    actions: list[str] = []

    # Diagnose HIGH_EXTRA and HIGH_LIPSA (text only, no auto-fix)
    for f in findings:
        if f.check in ("HIGH_EXTRA", "HIGH_LIPSA") and f.hypothesis is None:
            try:
                prompt = _DIAGNOSIS_PROMPT.format(
                    check=f.check, group_den=f.group_den,
                    value=f.value, threshold=f.threshold,
                )
                resp = llm_client.chat.completions.create(
                    model=model, max_tokens=200,
                    messages=[{"role": "user", "content": prompt}],
                )
                f.hypothesis = resp.choices[0].message.content.strip()
            except Exception as e:
                print(f"[AGENT] LLM diagnosis failed for {f.check}: {e}")

    # Auto-fix OFERTA_ONLY_GROUP via group_match_knowledge
    oferta_only = [f for f in findings if f.check == "OFERTA_ONLY_GROUP"]
    if oferta_only:
        oferta_dens = "\n".join(f"- {f.group_den}" for f in oferta_only)
        try:
            prompt = _GROUP_MATCH_PROMPT.format(oferta_groups=oferta_dens)
            resp = llm_client.chat.completions.create(
                model=model, max_tokens=500,
                messages=[{"role": "user", "content": prompt}],
            )
            content = resp.choices[0].message.content.strip()
            # strip markdown fences
            if content.startswith("```"):
                content = "\n".join(content.split("\n")[1:-1])
            pairs = json.loads(content)
            valid = [p for p in pairs if isinstance(p, dict)
                     and p.get("confidence", 0) >= 0.7
                     and "ref_den" in p and "oferta_den" in p]
            if valid:
                gm = json.loads(GROUP_MATCH_KNOWLEDGE_FILE.read_text()) \
                    if GROUP_MATCH_KNOWLEDGE_FILE.exists() else {}
                existing = gm.get(client_name, [])
                existing_oferta_dens = {e.get("oferta_den") for e in existing}
                new_pairs = [p for p in valid
                             if p["oferta_den"] not in existing_oferta_dens]
                if new_pairs:
                    gm[client_name] = existing + [
                        {"ref_den": p["ref_den"], "oferta_den": p["oferta_den"]}
                        for p in new_pairs
                    ]
                    GROUP_MATCH_KNOWLEDGE_FILE.write_text(
                        json.dumps(gm, indent=2, ensure_ascii=False)
                    )
                    actions.append(
                        f"group_match_knowledge: +{len(new_pairs)} perechi "
                        f"({', '.join(p['oferta_den'][:40] for p in new_pairs)})"
                    )
        except Exception as e:
            print(f"[AGENT] LLM group match failed: {e}")

    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python3 -m pytest tests/test_verify_agent_llm.py -v
```
Expected: 3 PASS.

- [ ] **Step 5: Run full suite to verify no regressions**

```bash
python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py
```
Expected: toate testele noi + existente PASS (16 pre-existente failures acceptate).

- [ ] **Step 6: Smoke test full loop pe Camin Maneciu**

```bash
python3 verify_agent.py --client "Camin Maneciu" --max-iter 2
```
Expected:
- Ruleaza pipeline × 2
- Genereaza `output_AO/Camin Maneciu/verify_report_<data>.md`
- Printeaza summary cu findings per severitate

- [ ] **Step 7: Commit + push**

```bash
git add verify_agent.py tests/test_verify_agent_llm.py
git commit -m "feat(agent): LLM diagnosis + OFERTA_ONLY auto-fix via group_match_knowledge"
git push origin main
```
