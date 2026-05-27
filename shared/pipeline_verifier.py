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
