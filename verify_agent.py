#!/usr/bin/env python3
"""
verify_agent.py — Pipeline verification agent.

Usage:
    python3 verify_agent.py --client "Camin Maneciu"
    python3 verify_agent.py --client "Camin Maneciu" --verify-only
    python3 verify_agent.py --client "Camin Maneciu" --max-iter 5
"""
import argparse
import json
import datetime
import sys
from pathlib import Path

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
    mode = "verify-only" if not iterations else "loop"
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
                        help="Run checks only, no re-run")
    parser.add_argument("--max-iter", type=int, default=3,
                        help="Max loop iterations (default: 3)")
    args = parser.parse_args()

    cfg = ClientConfig.from_folder(args.client, INPUT_BASE, OUTPUT_BASE)
    if not cfg.validate():
        print(f"[ERROR] Client '{args.client}' not found in {INPUT_BASE}/")
        sys.exit(1)

    knowledge = load_agent_knowledge()
    thresholds = get_client_thresholds(knowledge, args.client)

    print(f"[AGENT] Running pipeline for '{args.client}'...")
    _run_pipeline(cfg)

    if args.verify_only:
        findings = verify_client(cfg.output_dir, thresholds)
        report = _generate_md_report(args.client, [], findings, "verify-only")
        report_path = cfg.output_dir / f"verify_report_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
        report_path.write_text(report)
        print(f"[AGENT] Report saved: {report_path}")
        _print_summary(findings)
        return

    # Loop
    iterations: list[dict] = []
    prev_nc = count_total_nc(cfg.output_dir)
    stopped_reason = f"max-iter ({args.max_iter})"

    for i in range(1, args.max_iter + 1):
        print(f"[AGENT] Iteration {i}/{args.max_iter} — checking...")
        findings = verify_client(cfg.output_dir, thresholds)
        nc_after = count_total_nc(cfg.output_dir)

        _record_run(knowledge, args.client, i, prev_nc, nc_after,
                    len(findings), [])
        save_agent_knowledge(knowledge)

        iterations.append({
            "iteration": i, "nc_before": prev_nc, "nc_after": nc_after,
            "findings_count": len(findings), "actions": [],
        })

        if i > 1:
            reduction = (prev_nc - nc_after) / max(prev_nc, 1)
            if reduction < CONVERGENCE_THRESHOLD:
                stopped_reason = f"convergenta (reducere {reduction:.1%} < {CONVERGENCE_THRESHOLD:.0%})"
                print(f"[AGENT] Convergenta la iter {i}: {stopped_reason}")
                break

        prev_nc = nc_after

        if i < args.max_iter:
            print(f"[AGENT] Re-running pipeline...")
            _run_pipeline(cfg)

    report = _generate_md_report(args.client, iterations, findings, stopped_reason)
    report_path = cfg.output_dir / f"verify_report_{datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')}.md"
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
        flag = "ok" if n == 0 else "warn"
        print(f"  [{flag}] {sev}: {n}")


if __name__ == "__main__":
    main()
