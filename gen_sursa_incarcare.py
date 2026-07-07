#!/usr/bin/env python3
"""Generate F3 Lista-proiect-XXX.docx/xlsx/pdf from a single di_*.json.

Usage:
    python3 gen_sursa_incarcare.py                                  # interactive
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --no-pdf
    python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --force
"""

import argparse
import json
import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv

from shared.client_config import ClientConfig
from shared.f3_price_extractor import extract_prices, extract_footer_totals
from shared.lista_verifier import verify, max_nr_crt_in_page_classes
from shared.sursa_incarcare_writer import make_acronym, write_docx, write_docx_v2, write_xlsx, write_pdf, write_pdf_native


def _convert_docx_to_pdf(docx_path: Path, pdf_path: Path) -> bool:
    """Convert DOCX to PDF via Microsoft Word AppleScript (macOS) or LibreOffice."""
    import subprocess, time
    docx_abs = str(docx_path.resolve())
    pdf_abs = str(pdf_path.resolve())
    try:
        subprocess.run(['open', '-a', 'Microsoft Word', docx_abs],
                       check=True, capture_output=True, timeout=10)
        time.sleep(5)
        script = f'''
tell application "Microsoft Word"
    set n to count of documents
    tell document n
        save as file name "{pdf_abs}" file format format PDF
        close saving no
    end tell
end tell
'''
        r = subprocess.run(['osascript'], input=script, capture_output=True,
                           text=True, timeout=30)
        if r.returncode == 0 and pdf_path.exists():
            return True
    except Exception:
        pass
    return write_pdf(docx_path, pdf_path.parent)

INPUT_BASE = Path("input_AO")
OUTPUT_BASE = Path("output_AO")
_DEFAULT_MODEL = "claude-sonnet-4-6"


def _make_llm_client():
    load_dotenv()
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)
    from anthropic_adapter import AnthropicAdapter
    model = os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)
    base_url = os.environ.get("ANTHROPIC_BASE_URL")
    raw = anthropic.Anthropic(base_url=base_url, api_key=api_key) if base_url else anthropic.Anthropic(api_key=api_key)
    print(f"  LLM: {model} @ {base_url or 'Anthropic direct'}")
    return AnthropicAdapter(raw, model=model), model


def _pick_client(args_client) -> str:
    clients = ClientConfig.detect_clients(INPUT_BASE)
    if not clients:
        print(f"No clients found in {INPUT_BASE}/")
        sys.exit(1)
    if args_client:
        if args_client not in clients:
            print(f"Client '{args_client}' not found. Available: {clients}")
            sys.exit(1)
        return args_client
    print("\nClienti disponibili:")
    for i, c in enumerate(clients, 1):
        print(f"  {i}. {c}")
    choice = input("Client [numar]: ").strip()
    try:
        return clients[int(choice) - 1]
    except (ValueError, IndexError):
        print("Selectie invalida.")
        sys.exit(1)


def _pick_json(client_name: str, args_json) -> Path:
    input_dir = INPUT_BASE / client_name
    json_files = sorted(input_dir.glob("di_*.json"))
    if not json_files:
        print(f"No di_*.json files found in {input_dir}")
        sys.exit(1)
    if args_json:
        name = args_json if args_json.endswith(".json") else args_json + ".json"
        path = input_dir / name
        if not path.exists():
            print(f"File {path} not found.")
            sys.exit(1)
        return path
    print(f"\nFisiere JSON disponibile in {input_dir}:")
    for i, f in enumerate(json_files, 1):
        print(f"  {i}. {f.name}")
    choice = input("JSON [numar]: ").strip()
    try:
        return json_files[int(choice) - 1]
    except (ValueError, IndexError):
        print("Selectie invalida.")
        sys.exit(1)


def _run_pipeline(client_name: str, json_path: Path, no_pdf: bool = False, force: bool = False, ofertant: str = "") -> None:
    from shared.f3_page_classifier import classify_pages
    from shared.deviz_header_extractor import extract_deviz_headers

    config = ClientConfig.from_folder(client_name, INPUT_BASE, OUTPUT_BASE)
    config.ensure_output_dirs()

    json_stem = json_path.stem
    print(f"\nProcesare {client_name} / {json_path.name}...")

    # Step 1: Page classification
    ckpt_pages = config.output_dir / f"{json_stem}_page_classes.json"
    di = json.loads(json_path.read_text(encoding="utf-8"))
    pages = di.get("pages", [])

    if ckpt_pages.exists() and not force:
        print(f"  [1/4] Clasificare pagini (cached)...", end="", flush=True)
        ckpt = json.loads(ckpt_pages.read_text(encoding="utf-8"))
        page_classes = ckpt.get("page_classes", ckpt.get("results", [])) if isinstance(ckpt, dict) else ckpt
    else:
        print(f"  [1/4] Clasificare pagini (LLM, poate dura 2-5 min)...", end="", flush=True)
        llm_client, llm_model = _make_llm_client()
        page_classes, ckpt_data = classify_pages(
            pages, llm_client, llm_model, document_type="reference", source_path=str(json_path)
        )
        ckpt_pages.write_text(
            json.dumps({"page_classes": page_classes, "metadata": ckpt_data},
                       ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    f3_count = sum(1 for pc in page_classes if pc.get("is_f3"))
    print(f" OK {f3_count} pagini F3")

    # Step 2: Deviz headers
    print(f"  [2/4] Extragere devize...", end="", flush=True)
    deviz_headers = extract_deviz_headers(page_classes)
    valid = len(deviz_headers)
    print(f" OK {valid} deviz(e)")

    # Step 3: Extract prices
    print(f"  [3/4] Extragere articole + preturi...", end="", flush=True)
    ckpt_extracted = config.output_dir / f"sursa_extracted_{json_stem}.json"
    extracted = extract_prices(
        page_classes, deviz_headers,
        checkpoint_path=ckpt_extracted,
        force=force,
    )
    total_arts = sum(len(cap.get("articole", [])) for deviz in extracted for cap in deviz.get("capitole", []))
    bd_count = sum(
        1 for deviz in extracted
        for cap in deviz.get("capitole", [])
        for art in cap.get("articole", [])
        if art.get("breakdown")
    )
    print(f" OK {total_arts} articole, {bd_count} cu breakdown")
    footer_totals = extract_footer_totals(page_classes)

    # Step 4: Verify
    print(f"  [4/4] Verificare...", end="", flush=True)
    raw_max_nr = max_nr_crt_in_page_classes(page_classes)
    verification = verify(extracted, deviz_headers, raw_max_nr=raw_max_nr)

    ckpt_verified = config.output_dir / f"sursa_verified_{json_stem}.json"
    ckpt_verified.write_text(
        json.dumps(verification, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    iters = verification["iterations"]
    status = verification["status"]
    sym = "OK" if status == "OK" else ("WARN" if status == "WARN" else "RED")
    print(f" {sym} {status} (iteratii: {iters})")

    if not extracted:
        print("  AVERTISMENT: Nu s-au extras devize. Fisierul nu contine pagini F3 valide.")
        return

    # Generate output files
    obiectivul = extracted[0].get("obiectivul", "") if extracted else ""
    acronym = make_acronym(obiectivul) if obiectivul else "PRJ"
    base_name = f"Lista-proiect-{acronym}-{json_stem}"

    docx_path = config.output_dir / f"{base_name}.docx"
    xlsx_path = config.output_dir / f"{base_name}.xlsx"
    pdf_path = config.output_dir / f"{base_name}.pdf"

    for deviz in extracted:
        deviz['status'] = verification['status']

    json_stem_num = ''.join(filter(str.isdigit, json_stem)) or '1'
    metadata = {
        "offer_label": f"Oferta {json_stem_num}",
        "client": client_name,
        "ofertant": ofertant,
    }
    write_docx_v2(extracted, docx_path, metadata=metadata, footer=footer_totals)
    print(f"\nOutput generat:")
    print(f"  {docx_path}  OK")

    write_xlsx(extracted, xlsx_path, footer=footer_totals)
    print(f"  {xlsx_path}  OK")

    if not no_pdf:
        ok = _convert_docx_to_pdf(docx_path, pdf_path)
        print(f"  {pdf_path}  {'OK' if ok else 'WARN (PDF generation failed)'}")
    else:
        print(f"  PDF omis (--no-pdf)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Genereaza Lista-proiect din di_*.json")
    parser.add_argument("--client", help="Numele clientului")
    parser.add_argument("--json", dest="json_name", help="Numele fisierului JSON (fara .json)")
    parser.add_argument("--no-pdf", action="store_true", dest="no_pdf")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--ofertant", default="", help="Numele ofertantului (apare in header DOCX)")
    args = parser.parse_args()

    client_name = _pick_client(args.client)
    json_path = _pick_json(client_name, args.json_name)
    _run_pipeline(client_name, json_path, no_pdf=args.no_pdf, force=args.force, ofertant=args.ofertant)


if __name__ == "__main__":
    main()
