"""Detect nr_crt sequence gaps + missing tail in extracted articles vs raw DI.

Usage:
    python3 verify_gaps.py --client "CAV Maneciu"            # referinta + all offers
    python3 verify_gaps.py --client "CAV Maneciu" --referinta
    python3 verify_gaps.py --client "CAV Maneciu" --oferta 1
    python3 verify_gaps.py --client "DT2" --tail-lookahead 20
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")

_DEFAULT_TAIL_LOOKAHEAD = 15  # max articles to search beyond extracted_max


# ── raw DI helpers ──────────────────────────────────────────────────────────

def _load_di_pages(di_path: Path) -> dict[int, list[str]]:
    """Return {page_number: [line_content, ...]} from raw DI JSON."""
    try:
        data = json.loads(di_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    result = {}
    for page in data.get("pages", []):
        pn = page.get("page_number", 0)
        lines = [ln.get("content", "").strip() for ln in page.get("lines", [])]
        result[pn] = lines
    return result


_HEADER_KEYWORDS = re.compile(
    r'OBIECTUL|OBIECTIVUL|STADIUL\s+FIZIC|Beneficiar|Proiectant|Executant|'
    r'formular\s+f3|lista\s+cu\s+cantitati|sectiunea\s+tehnica',
    re.IGNORECASE,
)


def _is_column_header_context(pages: dict[int, list[str]], page: int, idx: int) -> bool:
    """True if line is inside a table column-number header row (0 1 2 3 4 5 = 3 x 4)."""
    lines = pages.get(page, [])
    window = lines[max(0, idx - 3): idx + 4]
    standalone_ints = sum(1 for l in window if re.match(r'^\d$', l.strip()))
    return standalone_ints >= 3


def _is_deviz_header_context(pages: dict[int, list[str]], page: int, idx: int) -> bool:
    """True if line is near deviz metadata (OBIECTUL, STADIUL FIZIC, Beneficiar etc.)."""
    lines = pages.get(page, [])
    window = lines[max(0, idx - 5): idx + 5]
    return any(_HEADER_KEYWORDS.search(l) for l in window)


def _find_nr_in_pages(pages: dict[int, list[str]], nr: int, search_pages: set[int]) -> list[tuple[int, int, str]]:
    """Search for article-start lines beginning with NR in given pages.

    Accepts:
      - "NR COD..."  (nr followed by space + letter/digit = inline article)
      - "NR"         (standalone nr — next line has the code)
    Rejects:
      - "NR.ddd"     (cantitate decimal)
      - "NR,ddd"     (cantitate Romanian)
      - Lines inside column-header rows (0 1 2 3 4 5 = 3 x 4)

    Returns [(page, line_idx, content), ...].
    """
    hits = []
    for pn in sorted(search_pages):
        if pn not in pages:
            continue
        for i, line in enumerate(pages[pn]):
            stripped = line.strip()
            m = re.match(rf'^{nr}(\s|$)', stripped)
            if not m:
                continue
            if re.match(rf'^{nr}[.,]', stripped):
                continue
            if _is_column_header_context(pages, pn, i):
                continue
            if _is_deviz_header_context(pages, pn, i):
                continue
            hits.append((pn, i, line))
    return hits


def _context(pages: dict[int, list[str]], page: int, idx: int, window: int = 5) -> list[str]:
    """Return lines[idx-window : idx+window] from page, with line numbers."""
    lines = pages.get(page, [])
    start = max(0, idx - window)
    end = min(len(lines), idx + window + 1)
    result = []
    for i in range(start, end):
        marker = ">>> " if i == idx else "    "
        result.append(f"[{i}]{marker}{lines[i]!r}")
    return result


# ── checkpoint helpers ───────────────────────────────────────────────────────

def _load_deviz_pages_from_ckpt(client: str, json_stem: str) -> dict[str, set[int]]:
    """Load page_classes checkpoint → {deviz_cod: {page_numbers}} for F3 pages."""
    ckpt_dir = OUTPUT_BASE / client / "checkpoints"
    files = sorted(ckpt_dir.glob(f"{json_stem}_page_classes_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    pc = data.get("page_classes", data) if isinstance(data, dict) else data
    by_deviz: dict[str, set[int]] = defaultdict(set)
    for p in pc:
        if not p.get("is_f3"):
            continue
        cod = p.get("deviz_cod", "")
        pn = p.get("page_number", 0)
        if cod and pn:
            by_deviz[cod].add(pn)
    return dict(by_deviz)


def _load_key_to_cod(client: str, json_stem: str) -> dict[str, str]:
    """Load deviz_mapping checkpoint → {deviz_key: deviz_cod}."""
    ckpt_dir = OUTPUT_BASE / client / "checkpoints"
    files = sorted(ckpt_dir.glob(f"{json_stem}_deviz_mapping_*.json"))
    if not files:
        return {}
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    headers = data.get("deviz_headers", {})
    return {k: v.get("deviz_cod", "") for k, v in headers.items() if v.get("deviz_cod")}


def _tail_page_set(arts: list[dict], deviz_pages_by_cod: dict[str, set[int]], deviz_cod: str) -> set[int]:
    """Page set for tail search: use exact checkpoint pages (no extension = no cross-deviz FP).
    Fallback to source_pages + small extension when checkpoint unavailable."""
    ckpt_pages = deviz_pages_by_cod.get(deviz_cod, set())
    if ckpt_pages:
        return ckpt_pages  # exact checkpoint pages — no extension to avoid next-deviz FP
    # Fallback for clients without checkpoints
    last_pages: set[int] = set()
    for a in arts:
        for p in a.get("source_pages", []):
            last_pages.add(p)
    if last_pages:
        m = max(last_pages)
        return last_pages | {m + 1, m + 2, m + 3, m + 4, m + 5}
    return set()


def _find_tail_missing(
    extracted_max: int,
    di_pages: dict[int, list[str]],
    page_set: set[int],
    lookahead: int = _DEFAULT_TAIL_LOOKAHEAD,
) -> list[int]:
    """Return list of nrs (extracted_max+1 ..) found in raw DI but not extracted.

    Stops at first nr not found (sequential gap = true end of deviz).
    """
    missing = []
    for nr in range(extracted_max + 1, extracted_max + lookahead + 1):
        hits = _find_nr_in_pages(di_pages, nr, page_set)
        if hits:
            missing.append(nr)
        else:
            break
    return missing


# ── article collection ───────────────────────────────────────────────────────

def _collect_from_referinta(referinta_path: Path) -> dict[str, list[dict]]:
    """Load referinta.json and group articles by deviz_key."""
    data = json.loads(referinta_path.read_text(encoding="utf-8"))
    groups: dict[str, list[dict]] = defaultdict(list)
    for art in data.get("articole", []):
        key = art.get("deviz_key", "?")
        groups[key].append(art)
    return dict(groups)


def _collect_from_holistic(holistic_path: Path, source: str) -> dict[str, list[dict]]:
    """Load holistic JSON and collect articles for 'referinta' or 'oferta' source."""
    data = json.loads(holistic_path.read_text(encoding="utf-8"))
    art_key = "ref_articles" if source == "referinta" else "oferta_articles"
    only_key = "ref_only_groups" if source == "referinta" else "oferta_only_groups"

    groups: dict[str, list[dict]] = {}
    for group in data.get("matched_groups", []):
        arts = group.get(art_key, [])
        if arts:
            key = arts[0].get("deviz_key", id(group))
            groups[key] = arts
    for group in data.get(only_key, []):
        arts = group.get("articles", [])
        if arts:
            key = arts[0].get("deviz_key", id(group))
            groups[key] = arts
    return groups


# ── gap + tail analysis ──────────────────────────────────────────────────────

def _group_label(arts: list[dict]) -> str:
    dh = arts[0].get("deviz_header", {}) if arts else {}
    parts = [dh.get("obiectul", ""), dh.get("categoria", "")]
    return " | ".join(p for p in parts if p) or arts[0].get("deviz", "?") if arts else "?"


def _find_gaps(arts: list[dict]) -> tuple[list[int], list[int]]:
    """Return (extracted_main_nrs, gap_nrs) for main articles only."""
    nrs = sorted(
        int(a["nr_ordine"])
        for a in arts
        if not a.get("is_component") and isinstance(a.get("nr_ordine"), int)
    )
    if len(nrs) < 2:
        return nrs, []
    full = set(range(nrs[0], nrs[-1] + 1))
    gaps = sorted(full - set(nrs))
    return nrs, gaps


def _search_pages_for_group(arts: list[dict]) -> set[int]:
    """Build candidate page set from source_pages of all group articles."""
    pages: set[int] = set()
    for a in arts:
        for p in a.get("source_pages", []):
            pages.add(p)
    expanded: set[int] = set()
    for p in pages:
        expanded.update([p - 1, p, p + 1])
    return {p for p in expanded if p > 0}


# ── report ────────────────────────────────────────────────────────────────────

def analyze_groups(
    groups: dict[str, list[dict]],
    di_pages: dict[int, list[str]],
    label: str,
    key_to_cod: dict[str, str] | None = None,
    deviz_pages_by_cod: dict[str, set[int]] | None = None,
    tail_lookahead: int = _DEFAULT_TAIL_LOOKAHEAD,
) -> dict:
    """Print gap + tail report. Returns counts dict."""
    groups_with_gaps = 0
    groups_with_tail = 0

    for key, arts in groups.items():
        nrs, gaps = _find_gaps(arts)
        extracted_max = max(nrs) if nrs else 0

        # Tail check: articles beyond extracted_max
        tail_missing: list[int] = []
        if extracted_max > 0 and key_to_cod is not None and deviz_pages_by_cod is not None:
            deviz_cod = key_to_cod.get(str(key), "")
            page_set = _tail_page_set(arts, deviz_pages_by_cod, deviz_cod)
            if page_set:
                tail_missing = _find_tail_missing(extracted_max, di_pages, page_set, tail_lookahead)

        has_issue = bool(gaps) or bool(tail_missing)
        if not has_issue:
            continue

        if gaps:
            groups_with_gaps += 1
        if tail_missing:
            groups_with_tail += 1

        glabel = _group_label(arts)
        print(f"\n{'─' * 70}")
        print(f"[{label}] {glabel}")
        print(f"  Extras nr_crt: {nrs[0]}..{extracted_max}  ({len(nrs)} articole main)")

        # ── gap report ──
        if gaps:
            print(f"  Gaps interne:  {gaps}")
            search_pages = _search_pages_for_group(arts)
            for nr in gaps:
                hits = _find_nr_in_pages(di_pages, nr, search_pages)
                if hits:
                    print(f"\n  Gap nr={nr} — GĂSIT în raw DI (bug extractor):")
                    for page, idx, content in hits[:3]:
                        print(f"    pagina {page}, linia {idx}: {content!r}")
                        ctx = _context(di_pages, page, idx, window=4)
                        for cl in ctx:
                            print(f"      {cl}")
                else:
                    all_pages = set(di_pages.keys())
                    hits_wide = _find_nr_in_pages(di_pages, nr, all_pages)
                    if hits_wide:
                        print(f"\n  Gap nr={nr} — GĂSIT pe alte pagini (deviz greșit?):")
                        for page, idx, content in hits_wide[:2]:
                            print(f"    pagina {page}, linia {idx}: {content!r}")
                    else:
                        print(f"\n  Gap nr={nr} — NU există în raw DI (salt de numerotare)")

        # ── tail report ──
        if tail_missing:
            print(f"\n  ⚠ MISSING_TAIL: articolele {tail_missing} există în raw DI dar NU au fost extrase")
            deviz_cod = (key_to_cod or {}).get(str(key), "")
            tail_pages = _tail_page_set(arts, deviz_pages_by_cod or {}, deviz_cod)
            for nr in tail_missing:
                hits = _find_nr_in_pages(di_pages, nr, tail_pages)
                if hits:
                    page, idx, content = hits[0]
                    print(f"\n  Tail nr={nr} — pagina {page}, linia {idx}: {content!r}")
                    ctx = _context(di_pages, page, idx, window=4)
                    for cl in ctx:
                        print(f"      {cl}")

    return {"gaps": groups_with_gaps, "tail": groups_with_tail}


# ── entry points ──────────────────────────────────────────────────────────────

def check_referinta(client: str, tail_lookahead: int = _DEFAULT_TAIL_LOOKAHEAD) -> None:
    ref_path = OUTPUT_BASE / client / "referinta.json"
    di_path = INPUT_BASE / client / "di_referinta.json"
    if not ref_path.exists():
        print(f"[ERROR] {ref_path} not found — rulați pipeline-ul mai întâi")
        return

    groups = _collect_from_referinta(ref_path)
    di_pages = _load_di_pages(di_path)
    key_to_cod = _load_key_to_cod(client, "di_referinta")
    deviz_pages_by_cod = _load_deviz_pages_from_ckpt(client, "di_referinta")

    print(f"\n=== REFERINTA — {client} ({len(groups)} grupuri) ===")
    if key_to_cod:
        print(f"  [checkpoint] {len(key_to_cod)} devize mapate, {len(deviz_pages_by_cod)} cu pagini F3")
    counts = analyze_groups(groups, di_pages, "REF", key_to_cod, deviz_pages_by_cod, tail_lookahead)
    if counts["gaps"] == 0 and counts["tail"] == 0:
        print("  ✓ Niciun gap și niciun MISSING_TAIL.")
    else:
        if counts["gaps"]:
            print(f"\n  {counts['gaps']} grupuri cu gap-uri interne.")
        if counts["tail"]:
            print(f"\n  {counts['tail']} grupuri cu MISSING_TAIL (articole la final neextrase).")


def check_oferta(client: str, oferta_nr: int, tail_lookahead: int = _DEFAULT_TAIL_LOOKAHEAD) -> None:
    holistic_path = OUTPUT_BASE / client / f"holistic_oferta_{oferta_nr}.json"
    di_path = INPUT_BASE / client / f"di_oferta_{oferta_nr}.json"
    if not holistic_path.exists():
        print(f"[ERROR] {holistic_path} not found")
        return

    groups = _collect_from_holistic(holistic_path, source="oferta")
    di_pages = _load_di_pages(di_path)
    json_stem = f"di_oferta_{oferta_nr}"
    key_to_cod = _load_key_to_cod(client, json_stem)
    deviz_pages_by_cod = _load_deviz_pages_from_ckpt(client, json_stem)

    print(f"\n=== OFERTA {oferta_nr} — {client} ({len(groups)} grupuri) ===")
    if key_to_cod:
        print(f"  [checkpoint] {len(key_to_cod)} devize mapate, {len(deviz_pages_by_cod)} cu pagini F3")
    counts = analyze_groups(groups, di_pages, f"O{oferta_nr}", key_to_cod, deviz_pages_by_cod, tail_lookahead)
    if counts["gaps"] == 0 and counts["tail"] == 0:
        print("  ✓ Niciun gap și niciun MISSING_TAIL.")
    else:
        if counts["gaps"]:
            print(f"\n  {counts['gaps']} grupuri cu gap-uri interne.")
        if counts["tail"]:
            print(f"\n  {counts['tail']} grupuri cu MISSING_TAIL.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Detect nr_crt gaps + missing tail in extracted articles")
    parser.add_argument("--client", required=True)
    parser.add_argument("--referinta", action="store_true")
    parser.add_argument("--oferta", type=int, metavar="N")
    parser.add_argument("--tail-lookahead", type=int, default=_DEFAULT_TAIL_LOOKAHEAD,
                        help=f"Max articles to search beyond extracted_max (default: {_DEFAULT_TAIL_LOOKAHEAD})")
    args = parser.parse_args()

    client = args.client
    output_dir = OUTPUT_BASE / client
    input_dir = INPUT_BASE / client

    if not output_dir.exists():
        print(f"[ERROR] output_AO/{client}/ nu există")
        sys.exit(1)
    if not input_dir.exists():
        print(f"[ERROR] input_AO/{client}/ nu există")
        sys.exit(1)

    if args.referinta:
        check_referinta(client, args.tail_lookahead)
    elif args.oferta:
        check_oferta(client, args.oferta, args.tail_lookahead)
    else:
        check_referinta(client, args.tail_lookahead)
        holistic_files = sorted(output_dir.glob("holistic_oferta_*.json"))
        for hf in holistic_files:
            if "_v2" in hf.name:
                continue
            m = re.search(r"holistic_oferta_(\d+)\.json", hf.name)
            if m:
                check_oferta(client, int(m.group(1)), args.tail_lookahead)


if __name__ == "__main__":
    main()
