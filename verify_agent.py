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
    parser.add_argument("--semantic", action="store_true",
                        help="LLM semantic analysis of EXTRA/LIPSA pairs within same deviz")
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
        if args.semantic:
            _run_semantic(cfg, args.client)
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


def _build_llm_client():
    from dotenv import load_dotenv
    import os
    import anthropic
    from anthropic_adapter import AnthropicAdapter
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("[semantic] ERROR: ANTHROPIC_API_KEY not set in .env")
        return None, None
    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    raw = anthropic.Anthropic(base_url=base_url, api_key=api_key) if base_url else anthropic.Anthropic(api_key=api_key)
    print(f"[semantic] LLM: {model} @ {base_url or 'Anthropic direct'}")
    return AnthropicAdapter(raw, model=model), model


def _run_semantic(cfg, client_name: str) -> None:
    from shared.semantic_reconciler import find_candidates, analyze_pairs, summarize
    import glob, re

    llm_client, model = _build_llm_client()
    if llm_client is None:
        return

    all_results = []
    for n in range(1, 10):
        # Support both V1 and V2 holistic files (prefer V2 if present)
        v2_path = Path(cfg.output_dir) / f"holistic_oferta_{n}_v2.json"
        v1_path = Path(cfg.output_dir) / f"holistic_oferta_{n}.json"
        path = v2_path if v2_path.exists() else (v1_path if v1_path.exists() else None)
        if path is None:
            break
        data = json.loads(path.read_text())
        pairs = find_candidates(data)
        if not pairs:
            print(f"[semantic] Oferta {n}: 0 perechi EXTRA+LIPSA în același deviz")
            continue
        print(f"[semantic] Oferta {n}: {len(pairs)} perechi → analiză LLM...")
        results = analyze_pairs(pairs, llm_client, model, verbose=True)
        all_results.extend(results)

        summary = summarize(results)
        print(f"[semantic] Oferta {n} rezultat: SAME={summary['SAME']}  DIFFERENT={summary['DIFFERENT']}  UNCERTAIN={summary['UNCERTAIN']}")
        if summary["same_pairs"]:
            print(f"[semantic] Candidați SAME (potențial match ratat):")
            for sp in summary["same_pairs"]:
                print(f"  deviz: {sp['deviz'][:60]}")
                print(f"    EXTRA: {sp['extra_cod']} | {sp['extra_den'][:60]}")
                print(f"    LIPSĂ: {sp['lipsa_cod']} | {sp['lipsa_den'][:60]}")
                print(f"    Motiv: {sp['reason']}")

        # Save per-oferta JSON report
        out_path = Path(cfg.output_dir) / f"semantic_oferta_{n}.json"
        out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))
        print(f"[semantic] Salvat: {out_path}")

    if all_results:
        from shared.semantic_reconciler import summarize as _summarize
        total_summary = _summarize(all_results)
        print(f"\n[semantic] TOTAL: {total_summary['total_pairs']} perechi | SAME={total_summary['SAME']} | DIFFERENT={total_summary['DIFFERENT']} | UNCERTAIN={total_summary['UNCERTAIN']}")


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
