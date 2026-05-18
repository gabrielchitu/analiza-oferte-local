#!/usr/bin/env python3
"""
Nonconformity Inspector - automated extraction verification tool.

For each nonconformity in the comparison report, searches the raw DI JSON
to determine if the issue is an extraction bug or a genuine data difference.

Usage:
    python3 tests/nonconformity_inspector.py [--oferta 1|2] [--tip UM_DIFERIT|DIFERENTA_CAMP|ARTICOL_LIPSA|ARTICOL_EXTRA] [--cod CODE]
"""

import json
import sys
import argparse
import re
from pathlib import Path

BASE = Path(__file__).parent.parent
OUTPUT = BASE / "output_AO"
INPUT = BASE / "input_AO"

CONTEXT_LINES = 8
CONTEXT_TABLE_ROWS = 3


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_code(code):
    """Normalize article code for searching (remove trailing symbols, uppercase)."""
    return re.sub(r"[#\-\s]+$", "", code.strip()).upper()


def search_di_pages(di_data, code, context=CONTEXT_LINES):
    """Search pages for article code, return list of (page_num, line_idx, context_lines)."""
    results = []
    code_upper = normalize_code(code)
    for page in di_data.get("pages", []):
        pnum = page["page_number"]
        lines = page.get("lines", [])
        for i, line in enumerate(lines):
            content = line.get("content", "")
            if code_upper in content.upper():
                start = max(0, i - context)
                end = min(len(lines), i + context + 1)
                ctx = [(j + 1, lines[j].get("content", "")) for j in range(start, end)]
                results.append({
                    "page": pnum,
                    "line": i + 1,
                    "match": content,
                    "context": ctx,
                })
    return results


def search_di_tables(di_data, code, context=CONTEXT_TABLE_ROWS):
    """Search tables for article code, return list of matches with surrounding rows."""
    results = []
    code_upper = normalize_code(code)
    tables = di_data.get("tables", [])
    for tidx, table in enumerate(tables):
        cells = table.get("cells", [])
        row_count = table.get("row_count", 0)
        col_count = table.get("column_count", 0)

        # Build row map: row_index -> {col_index: content}
        rows = {}
        for cell in cells:
            r = cell["row_index"]
            c = cell["column_index"]
            rows.setdefault(r, {})[c] = cell.get("content", "")

        for r_idx in sorted(rows.keys()):
            row_text = " | ".join(rows[r_idx].get(c, "") for c in range(col_count))
            if code_upper in row_text.upper():
                start = max(0, r_idx - context)
                end = min(row_count, r_idx + context + 1)
                ctx_rows = []
                for rr in range(start, end):
                    row_str = " | ".join(rows.get(rr, {}).get(c, "") for c in range(col_count))
                    marker = ">>>" if rr == r_idx else "   "
                    ctx_rows.append(f"{marker} row {rr:3d}: {row_str}")
                results.append({
                    "table_idx": tidx,
                    "row": r_idx,
                    "match_row": row_text,
                    "context": ctx_rows,
                })
    return results


def print_separator(char="=", width=80):
    print(char * width)


def print_hit(source_label, hits_pages, hits_tables, code):
    if not hits_pages and not hits_tables:
        print(f"  [{source_label}] CODE '{code}' NOT FOUND IN SOURCE")
        return

    if hits_pages:
        for h in hits_pages[:2]:  # show max 2 page hits
            print(f"  [{source_label}] Page {h['page']}, line {h['line']}:")
            for lineno, content in h["context"]:
                marker = ">>>" if content.strip().upper().startswith(code.upper()[:4]) else "   "
                print(f"       {marker} L{lineno:3d}: {content[:120]}")
            print()

    if hits_tables:
        for h in hits_tables[:2]:  # show max 2 table hits
            print(f"  [{source_label}] Table {h['table_idx']}, row {h['row']}:")
            for row_str in h["context"]:
                print(f"       {row_str[:140]}")
            print()


def inspect_nonconformity(nc, di_oferta, di_ref, oferta_num):
    tip = nc["tip"]
    print_separator()

    if tip == "UM_DIFERIT":
        code = nc.get("oferta_cod") or nc.get("ref_cod", "")
        ref_um = nc.get("ref_um", "")
        oferta_um = nc.get("oferta_um", "")
        deviz = nc.get("deviz_ref", "")
        print(f"[UM_DIFERIT] cod={code} | ref_um='{ref_um}' | oferta_um='{oferta_um}' | deviz={deviz}")
        print(f"  ref_den: {nc.get('ref_denumire','')[:80]}")
        print(f"  ofe_den: {nc.get('oferta_denumire','')[:80]}")
        print()
        print("  Searching oferta DI source:")
        pages = search_di_pages(di_oferta, code)
        tables = search_di_tables(di_oferta, code)
        print_hit("OFERTA", pages, tables, code)

    elif tip == "DIFERENTA_CAMP":
        code = nc.get("oferta_cod") or nc.get("ref_cod", "")
        camp = nc.get("camp", "")
        ref_val = nc.get("ref", "")
        ofe_val = nc.get("oferta", "")
        deviz = nc.get("deviz_ref", "")
        print(f"[DIFERENTA_CAMP] camp={camp} | cod={code} | ref={ref_val} | oferta={ofe_val} | deviz={deviz}")
        print(f"  ref_den: {nc.get('ref_denumire','')[:80]}")
        print(f"  ofe_den: {nc.get('oferta_denumire','')[:80]}")
        print()
        print("  Searching oferta DI source:")
        pages = search_di_pages(di_oferta, code)
        tables = search_di_tables(di_oferta, code)
        print_hit("OFERTA", pages, tables, code)

    elif tip == "ARTICOL_LIPSA":
        code = nc.get("ref_cod", "")
        deviz = nc.get("deviz_ref", "")
        print(f"[ARTICOL_LIPSA] cod={code} | deviz={deviz}")
        print(f"  ref_den: {nc.get('ref_denumire','')[:80]}")
        print()
        print("  Searching oferta DI (should find it if extraction bug):")
        pages = search_di_pages(di_oferta, code)
        tables = search_di_tables(di_oferta, code)
        print_hit("OFERTA-DI", pages, tables, code)
        if not pages and not tables:
            print("  => NOT in oferta DI at all: genuine omission or different code used")

    elif tip == "ARTICOL_EXTRA":
        code = nc.get("oferta_cod", "")
        deviz = nc.get("deviz_ref", "")
        print(f"[ARTICOL_EXTRA] cod={code} | deviz={deviz}")
        print(f"  ofe_den: {nc.get('oferta_denumire','')[:80]}")
        print()
        print("  Searching reference DI (should find it if extraction bug in ref):")
        pages = search_di_pages(di_ref, code)
        tables = search_di_tables(di_ref, code)
        print_hit("REF-DI", pages, tables, code)
        if not pages and not tables:
            print("  => NOT in reference DI: genuine extra article in oferta")
    else:
        print(f"[{tip}] (unhandled type)")
        print(json.dumps(nc, ensure_ascii=False, indent=2)[:300])


def main():
    parser = argparse.ArgumentParser(description="Inspect nonconformities against source DI JSON")
    parser.add_argument("--oferta", type=int, choices=[1, 2], default=2, help="Oferta number (default: 2)")
    parser.add_argument("--tip", type=str, default=None,
                        help="Filter by type: UM_DIFERIT, DIFERENTA_CAMP, ARTICOL_LIPSA, ARTICOL_EXTRA")
    parser.add_argument("--cod", type=str, default=None, help="Filter by article code (partial match)")
    parser.add_argument("--max", type=int, default=50, help="Max nonconformities to inspect")
    args = parser.parse_args()

    oferta_num = args.oferta
    comp_path = OUTPUT / f"comparatie_oferta_{oferta_num}.json"
    di_oferta_path = INPUT / f"di_oferta_{oferta_num}.json"
    di_ref_path = INPUT / "di_referinta.json"

    print(f"Loading comparison: {comp_path}")
    comp = load_json(comp_path)
    ncs = comp["neconformitati"]
    print(f"Loading DI oferta:  {di_oferta_path}")
    di_oferta = load_json(di_oferta_path)
    print(f"Loading DI ref:     {di_ref_path}")
    di_ref = load_json(di_ref_path)

    # Filter
    if args.tip:
        ncs = [n for n in ncs if n["tip"] == args.tip]
    if args.cod:
        cod_upper = args.cod.upper()
        ncs = [n for n in ncs if
               cod_upper in (n.get("ref_cod", "") + n.get("oferta_cod", "")).upper()]

    ncs = ncs[:args.max]

    print(f"\nInspecting {len(ncs)} nonconformities for OFERTA {oferta_num}:")
    print_separator("=")

    from collections import Counter
    type_counts = Counter(n["tip"] for n in ncs)
    for t, c in sorted(type_counts.items()):
        print(f"  {t}: {c}")
    print()

    for nc in ncs:
        inspect_nonconformity(nc, di_oferta, di_ref, oferta_num)

    print_separator()
    print(f"Done. {len(ncs)} nonconformities inspected.")


if __name__ == "__main__":
    main()
