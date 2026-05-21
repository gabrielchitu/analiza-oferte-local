# Raport Diagnostic Automat — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Script standalone `run_diagnostics.py` care citește output-urile JSON existente pentru toți clienții și generează `diagnostics.json` + `diagnostics.docx` cu analiză în 3 faze (calitate referință, articole extra, articole lipsă).

**Architecture:** 3 fișiere noi: `shared/diagnostics_builder.py` (analiză + JSON), `shared/diagnostics_word.py` (DOCX), `run_diagnostics.py` (CLI). Citesc exclusiv din `output_AO/<client>/` — nu re-rulează pipeline.

**Tech Stack:** Python 3.11, python-docx, pathlib, dataclasses, argparse

---

## Structura fișiere

```
run_diagnostics.py                     NOU — CLI entry point
shared/diagnostics_builder.py          NOU — Phase 0/1/2 + JSON
shared/diagnostics_word.py             NOU — DOCX generator
tests/test_diagnostics.py              NOU — unit tests
```

## Date cheie (câmpuri JSON confirmate din inspecție)

**`output_AO/<client>/referinta.json`:**
- Top key: `articole` (list)
- Per articol: `cod`, `denumire`, `um`, `cantitate`, `deviz`, `is_component` (bool), `parent_code` (str|None)

**`output_AO/<client>/comparatie_oferta_N.json`:**
- Top keys: `oferta_nr` (int), `matches` (int), `neconformitati` (list), `total_neconformitati` (int)
- Per NC: `tip` (str), `deviz_ref` (str), `deviz_denumire` (str)
  - EXTRA: `oferta_cod`, `oferta_denumire`, `oferta_cantitate`, `oferta_um`
  - LIPSA/DEVIZ_MISMATCH: `ref_cod`, `ref_denumire`, `ref_cantitate`, `ref_um`

**Baseline validat (state.md):**
- Blocuri Racari O1: matched=308, LIPSA=47, DEVIZ_MM=20, EXTRA=0, orfane_ref=0
- Camin Maneciu O1: matched=1056, EXTRA=36, orfane_ref=0
- Scoala Sportiva Racari O1: matched=2153, EXTRA=122, DEVIZ_MM=11, orfane_ref=154
- Scoala Dragomiresti O1: matched=651, DEVIZ_MM=624

---

## Task 1: `shared/diagnostics_builder.py` — Core analysis

**Files:**
- Create: `shared/diagnostics_builder.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Scrie testele pentru Phase 0 (referință quality)**

```python
# tests/test_diagnostics.py
import pytest
from shared.diagnostics_builder import analyze_ref_quality, Phase0Result

REF_ARTICOLE_CURATE = [
    {"cod": "TF24A", "denumire": "Beton", "um": "mc", "cantitate": 10.0,
     "deviz": "4.1-01", "is_component": False, "parent_code": None},
    {"cod": "$3274270", "denumire": "Cofraj", "um": "mp", "cantitate": 5.0,
     "deviz": "4.1-01", "is_component": True, "parent_code": "TF24A"},
]

REF_ARTICOLE_CU_PROBLEME = [
    {"cod": "TF24A", "denumire": "Beton", "um": "mc", "cantitate": 10.0,
     "deviz": "", "is_component": False, "parent_code": None},          # fara deviz
    {"cod": "XY01", "denumire": "Test", "um": "", "cantitate": 0,
     "deviz": "4.1-01", "is_component": False, "parent_code": None},   # incomplet
    {"cod": "$111", "denumire": "Sub", "um": "mp", "cantitate": 5.0,
     "deviz": "4.1-01", "is_component": True, "parent_code": None},    # orfan
    {"cod": "$222", "denumire": "Sub2", "um": "mp", "cantitate": 5.0,
     "deviz": "4.1-01", "is_component": True, "parent_code": ""},      # orfan (empty string)
]

def test_phase0_curate():
    result = analyze_ref_quality(REF_ARTICOLE_CURATE)
    assert isinstance(result, Phase0Result)
    assert len(result.fara_deviz) == 0
    assert len(result.incomplete) == 0
    assert len(result.componente_orfane) == 0
    assert result.total_ref == 2

def test_phase0_detecteaza_fara_deviz():
    result = analyze_ref_quality(REF_ARTICOLE_CU_PROBLEME)
    assert len(result.fara_deviz) == 1
    assert result.fara_deviz[0]["cod"] == "TF24A"

def test_phase0_detecteaza_incomplete():
    result = analyze_ref_quality(REF_ARTICOLE_CU_PROBLEME)
    assert len(result.incomplete) == 1
    assert result.incomplete[0]["cod"] == "XY01"

def test_phase0_detecteaza_orfane():
    result = analyze_ref_quality(REF_ARTICOLE_CU_PROBLEME)
    assert len(result.componente_orfane) == 2
    cods = {a["cod"] for a in result.componente_orfane}
    assert "$111" in cods
    assert "$222" in cods

def test_phase0_total_ref():
    result = analyze_ref_quality(REF_ARTICOLE_CU_PROBLEME)
    assert result.total_ref == 4
```

- [ ] **Step 2: Rulează testele să verifci că pică**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError: No module named 'shared.diagnostics_builder'`

- [ ] **Step 3: Implementează Phase 0 în `shared/diagnostics_builder.py`**

```python
# shared/diagnostics_builder.py
from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
import re
from datetime import datetime


@dataclass
class Phase0Result:
    total_ref: int
    fara_deviz: list[dict] = field(default_factory=list)
    incomplete: list[dict] = field(default_factory=list)
    componente_orfane: list[dict] = field(default_factory=list)

    @property
    def has_alarms(self) -> bool:
        return bool(self.fara_deviz or self.componente_orfane)

    @property
    def alarm_level(self) -> str:
        if self.fara_deviz or len(self.componente_orfane) > 10:
            return "red"
        if self.incomplete or self.componente_orfane:
            return "yellow"
        return "green"


def analyze_ref_quality(articole: list[dict]) -> Phase0Result:
    fara_deviz, incomplete, orfane = [], [], []
    for a in articole:
        deviz = a.get("deviz") or ""
        cantitate = a.get("cantitate") or 0
        um = a.get("um") or ""
        is_comp = a.get("is_component", False)
        parent = a.get("parent_code") or ""

        if not deviz:
            fara_deviz.append(a)
        if cantitate == 0 and um == "":
            incomplete.append(a)
        if is_comp and not parent:
            orfane.append(a)

    return Phase0Result(
        total_ref=len(articole),
        fara_deviz=fara_deviz,
        incomplete=incomplete,
        componente_orfane=orfane,
    )
```

- [ ] **Step 4: Rulează testele Phase 0**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py -v -k "phase0"
```

Expected: 5 tests PASS

- [ ] **Step 5: Adaugă testele pentru Phase 1 (EXTRA)**

Adaugă în `tests/test_diagnostics.py`:

```python
from shared.diagnostics_builder import analyze_extra, Phase1Result

NC_EXTRA = [
    {"tip": "ARTICOL_EXTRA", "deviz_ref": "4.1-01", "deviz_denumire": "Structura",
     "oferta_cod": "$4123381", "oferta_denumire": "niplu fonta", "oferta_cantitate": 5.0, "oferta_um": "buc"},
    {"tip": "ARTICOL_EXTRA", "deviz_ref": "4.1-01", "deviz_denumire": "Structura",
     "oferta_cod": "IZF12XC", "oferta_denumire": "Izolatie", "oferta_cantitate": 10.0, "oferta_um": "mp"},
    {"tip": "ARTICOL_EXTRA", "deviz_ref": "4.1-02", "deviz_denumire": "Finisaje",
     "oferta_cod": "$9999999", "oferta_denumire": "Material", "oferta_cantitate": 2.0, "oferta_um": "kg"},
    {"tip": "ARTICOL_LIPSA", "deviz_ref": "4.1-01", "deviz_denumire": "Structura",
     "ref_cod": "TF24A", "ref_denumire": "Beton", "ref_cantitate": 10.0, "ref_um": "mc"},
]

def test_phase1_total_extra():
    result = analyze_extra(NC_EXTRA)
    assert isinstance(result, Phase1Result)
    assert result.total_extra == 3

def test_phase1_separa_dollar_vs_principale():
    result = analyze_extra(NC_EXTRA)
    assert result.total_extra_dollar == 2
    dollar_cods = {a["oferta_cod"] for a in result.extra_dollar}
    assert "$4123381" in dollar_cods
    assert "$9999999" in dollar_cods
    assert len(result.extra_principale) == 1
    assert result.extra_principale[0]["oferta_cod"] == "IZF12XC"

def test_phase1_grupeaza_pe_deviz():
    result = analyze_extra(NC_EXTRA)
    assert "4.1-01" in result.by_deviz
    assert "4.1-02" in result.by_deviz
    assert len(result.by_deviz["4.1-01"]) == 2
    assert len(result.by_deviz["4.1-02"]) == 1

def test_phase1_ignora_non_extra():
    result = analyze_extra(NC_EXTRA)
    for art in result.extra_principale + result.extra_dollar:
        assert art["tip"] == "ARTICOL_EXTRA"
```

- [ ] **Step 6: Implementează Phase 1 în `shared/diagnostics_builder.py`**

Adaugă după `Phase0Result`:

```python
@dataclass
class Phase1Result:
    extra_principale: list[dict] = field(default_factory=list)
    extra_dollar: list[dict] = field(default_factory=list)
    by_deviz: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def total_extra(self) -> int:
        return len(self.extra_principale) + len(self.extra_dollar)

    @property
    def total_extra_dollar(self) -> int:
        return len(self.extra_dollar)


def analyze_extra(neconformitati: list[dict]) -> Phase1Result:
    principale, dollar, by_deviz = [], [], {}
    for nc in neconformitati:
        if nc.get("tip") != "ARTICOL_EXTRA":
            continue
        cod = nc.get("oferta_cod") or ""
        deviz = nc.get("deviz_ref") or ""
        if cod.startswith("$"):
            dollar.append(nc)
        else:
            principale.append(nc)
        by_deviz.setdefault(deviz, []).append(nc)
    return Phase1Result(extra_principale=principale, extra_dollar=dollar, by_deviz=by_deviz)
```

- [ ] **Step 7: Adaugă testele pentru Phase 2 (LIPSA)**

Adaugă în `tests/test_diagnostics.py`:

```python
from shared.diagnostics_builder import analyze_lipsa, Phase2Result

NC_LIPSA = [
    {"tip": "ARTICOL_LIPSA", "deviz_ref": "4.1-01", "deviz_denumire": "Structura",
     "ref_cod": "TF24A", "ref_denumire": "Beton", "ref_cantitate": 10.0, "ref_um": "mc"},
    {"tip": "ARTICOL_LIPSA", "deviz_ref": "4.1-01", "deviz_denumire": "Structura",
     "ref_cod": "CK25A", "ref_denumire": "Cofraj", "ref_cantitate": 5.0, "ref_um": "mp"},
    {"tip": "DEVIZ_MISMATCH", "deviz_ref": "4.1-02", "deviz_denumire": "Finisaje",
     "ref_cod": "RPC01", "ref_denumire": "Tencuiala", "ref_cantitate": 30.0, "ref_um": "mp"},
    {"tip": "ARTICOL_EXTRA", "deviz_ref": "4.1-01",
     "oferta_cod": "IZF12XC", "oferta_denumire": "Izolatie", "oferta_cantitate": 10.0, "oferta_um": "mp"},
]

def test_phase2_total_lipsa():
    result = analyze_lipsa(NC_LIPSA)
    assert isinstance(result, Phase2Result)
    assert result.total_lipsa == 2

def test_phase2_total_deviz_mismatch():
    result = analyze_lipsa(NC_LIPSA)
    assert result.total_deviz_mismatch == 1

def test_phase2_separa_genuine_vs_mismatch():
    result = analyze_lipsa(NC_LIPSA)
    genuine_cods = {a["ref_cod"] for a in result.lipsa_genuine}
    assert "TF24A" in genuine_cods
    assert "CK25A" in genuine_cods
    mismatch_cods = {a["ref_cod"] for a in result.deviz_mismatch}
    assert "RPC01" in mismatch_cods

def test_phase2_grupeaza_pe_deviz():
    result = analyze_lipsa(NC_LIPSA)
    assert "4.1-01" in result.by_deviz
    assert len(result.by_deviz["4.1-01"]) == 2

def test_phase2_ignora_extra():
    result = analyze_lipsa(NC_LIPSA)
    all_arts = result.lipsa_genuine + result.deviz_mismatch
    for art in all_arts:
        assert art["tip"] in ("ARTICOL_LIPSA", "DEVIZ_MISMATCH")
```

- [ ] **Step 8: Implementează Phase 2 în `shared/diagnostics_builder.py`**

Adaugă după `Phase1Result`:

```python
@dataclass
class Phase2Result:
    lipsa_genuine: list[dict] = field(default_factory=list)
    deviz_mismatch: list[dict] = field(default_factory=list)
    by_deviz: dict[str, list[dict]] = field(default_factory=dict)

    @property
    def total_lipsa(self) -> int:
        return len(self.lipsa_genuine)

    @property
    def total_deviz_mismatch(self) -> int:
        return len(self.deviz_mismatch)


def analyze_lipsa(neconformitati: list[dict]) -> Phase2Result:
    genuine, mismatch, by_deviz = [], [], {}
    for nc in neconformitati:
        tip = nc.get("tip")
        if tip not in ("ARTICOL_LIPSA", "DEVIZ_MISMATCH"):
            continue
        deviz = nc.get("deviz_ref") or ""
        if tip == "ARTICOL_LIPSA":
            genuine.append(nc)
            by_deviz.setdefault(deviz, []).append(nc)
        else:
            mismatch.append(nc)
    return Phase2Result(lipsa_genuine=genuine, deviz_mismatch=mismatch, by_deviz=by_deviz)
```

- [ ] **Step 9: Rulează toate testele**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py -v
```

Expected: 14 tests PASS

- [ ] **Step 10: Commit**

```bash
git add shared/diagnostics_builder.py tests/test_diagnostics.py
git commit -m "feat(diagnostics): Phase 0/1/2 analysis functions with tests"
```

---

## Task 2: Discover, Load, JSON output

**Files:**
- Modify: `shared/diagnostics_builder.py`
- Test: `tests/test_diagnostics.py`

- [ ] **Step 1: Adaugă testele pentru discover și load**

Adaugă în `tests/test_diagnostics.py`:

```python
import tempfile, os
from shared.diagnostics_builder import discover_clients, load_client_data, build_diagnostics_json

def _make_fake_output(tmpdir: Path, client: str, ref_articole: list, comparatii: list[dict]):
    client_dir = tmpdir / "output_AO" / client
    client_dir.mkdir(parents=True)
    (client_dir / "referinta.json").write_text(json.dumps({"articole": ref_articole}))
    for i, comp in enumerate(comparatii, 1):
        (client_dir / f"comparatie_oferta_{i}.json").write_text(json.dumps(comp))
    return client_dir

def test_discover_clients(tmp_path):
    _make_fake_output(tmp_path, "Client A", [], [])
    _make_fake_output(tmp_path, "Client B", [], [])
    (tmp_path / "output_AO" / "not_a_client").mkdir(parents=True)  # fără referinta.json
    clients = discover_clients(base_dir=tmp_path / "output_AO")
    assert set(clients) == {"Client A", "Client B"}

def test_load_client_data(tmp_path):
    ref = [{"cod": "TF24A", "deviz": "4.1-01", "um": "mc", "cantitate": 10.0,
             "is_component": False, "parent_code": None, "denumire": "Beton"}]
    comp1 = {"oferta_nr": 1, "matches": 5, "neconformitati": [], "total_neconformitati": 0}
    comp2 = {"oferta_nr": 2, "matches": 3, "neconformitati": [], "total_neconformitati": 0}
    _make_fake_output(tmp_path, "Client A", ref, [comp1, comp2])
    ref_loaded, comps = load_client_data("Client A", base_dir=tmp_path / "output_AO")
    assert len(ref_loaded) == 1
    assert len(comps) == 2
    assert comps[0]["oferta_nr"] == 1

def test_build_diagnostics_json(tmp_path):
    ref = [{"cod": "TF24A", "deviz": "4.1-01", "um": "mc", "cantitate": 10.0,
             "is_component": False, "parent_code": None, "denumire": "Beton"}]
    comp = {"oferta_nr": 1, "matches": 5, "neconformitati": [
        {"tip": "ARTICOL_EXTRA", "deviz_ref": "4.1-01", "deviz_denumire": "Str",
         "oferta_cod": "IZF12XC", "oferta_denumire": "Iz", "oferta_cantitate": 1.0, "oferta_um": "mp"}
    ], "total_neconformitati": 1}
    _make_fake_output(tmp_path, "Client A", ref, [comp])
    result = build_diagnostics_json(["Client A"], base_dir=tmp_path / "output_AO")
    assert "meta" in result
    assert "clienti" in result
    assert result["clienti"][0]["client"] == "Client A"
    oferte = result["clienti"][0]["oferte"]
    assert oferte[0]["sumar"]["matched"] == 5
    assert oferte[0]["extra"]["total"] == 1
```

- [ ] **Step 2: Rulează să pice**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py::test_discover_clients -v
```

Expected: `ImportError` sau `TypeError`

- [ ] **Step 3: Implementează `discover_clients`, `load_client_data`, `build_diagnostics_json`**

Adaugă la sfârșitul `shared/diagnostics_builder.py`:

```python
def discover_clients(base_dir: Path | None = None) -> list[str]:
    base = Path(base_dir) if base_dir else Path("output_AO")
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and (d / "referinta.json").exists()
    )


def load_client_data(client_name: str, base_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    base = Path(base_dir) if base_dir else Path("output_AO")
    client_dir = base / client_name
    ref_articole = json.loads((client_dir / "referinta.json").read_text())["articole"]
    comp_files = sorted(client_dir.glob("comparatie_oferta_*.json"))
    comparatii = [json.loads(f.read_text()) for f in comp_files]
    return ref_articole, comparatii


def _build_offer_dict(comp: dict) -> dict:
    nc = comp.get("neconformitati", [])
    p1 = analyze_extra(nc)
    p2 = analyze_lipsa(nc)
    return {
        "oferta_idx": comp.get("oferta_nr", 0),
        "sumar": {
            "matched": comp.get("matches", 0),
            "lipsa": p2.total_lipsa,
            "extra": p1.total_extra,
            "deviz_mismatch": p2.total_deviz_mismatch,
        },
        "extra": {
            "total": p1.total_extra,
            "dollar": p1.total_extra_dollar,
            "principale": len(p1.extra_principale),
            "by_deviz": {
                deviz: [
                    {"cod": a.get("oferta_cod"), "denumire": a.get("oferta_denumire"),
                     "cantitate": a.get("oferta_cantitate"), "um": a.get("oferta_um")}
                    for a in arts
                ]
                for deviz, arts in p1.by_deviz.items()
            },
        },
        "lipsa": {
            "total": p2.total_lipsa,
            "genuine": p2.total_lipsa,
            "deviz_mismatch": p2.total_deviz_mismatch,
            "by_deviz": {
                deviz: [
                    {"cod": a.get("ref_cod"), "denumire": a.get("ref_denumire"),
                     "cantitate": a.get("ref_cantitate"), "um": a.get("ref_um")}
                    for a in arts
                ]
                for deviz, arts in p2.by_deviz.items()
            },
        },
        "_phase1": p1,
        "_phase2": p2,
    }


def build_diagnostics_json(clients: list[str], base_dir: Path | None = None) -> dict:
    all_client_reports = []
    total_matched = total_lipsa = total_extra = total_deviz_mm = 0

    for client_name in clients:
        ref_articole, comparatii = load_client_data(client_name, base_dir)
        p0 = analyze_ref_quality(ref_articole)
        oferte = [_build_offer_dict(comp) for comp in comparatii]

        for o in oferte:
            total_matched += o["sumar"]["matched"]
            total_lipsa += o["sumar"]["lipsa"]
            total_extra += o["sumar"]["extra"]
            total_deviz_mm += o["sumar"]["deviz_mismatch"]

        matched_total = sum(o["sumar"]["matched"] for o in oferte) or 1

        all_client_reports.append({
            "client": client_name,
            "ref_quality": {
                "total_ref": p0.total_ref,
                "alarm_level": p0.alarm_level,
                "fara_deviz": [{"cod": a.get("cod"), "denumire": a.get("denumire")} for a in p0.fara_deviz],
                "incomplete": [{"cod": a.get("cod"), "denumire": a.get("denumire")} for a in p0.incomplete],
                "componente_orfane": [{"cod": a.get("cod"), "denumire": a.get("denumire")} for a in p0.componente_orfane],
            },
            "oferte": [{k: v for k, v in o.items() if not k.startswith("_")} for o in oferte],
            "_phase0": p0,
            "_oferte_full": oferte,
        })

    clienti_cu_alarme = [
        r["client"] for r in all_client_reports
        if r["ref_quality"]["alarm_level"] in ("red", "yellow")
    ]

    return {
        "meta": {
            "data_generare": datetime.now().isoformat(),
            "clienti_analizati": clients,
        },
        "clienti": [{k: v for k, v in r.items() if not k.startswith("_")} for r in all_client_reports],
        "sumar_global": {
            "total_matched": total_matched,
            "total_lipsa": total_lipsa,
            "total_extra": total_extra,
            "total_deviz_mismatch": total_deviz_mm,
            "clienti_cu_alarme_ref": clienti_cu_alarme,
        },
        "_client_reports": all_client_reports,
    }
```

- [ ] **Step 4: Rulează toate testele**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py -v
```

Expected: 18 tests PASS

- [ ] **Step 5: Commit**

```bash
git add shared/diagnostics_builder.py tests/test_diagnostics.py
git commit -m "feat(diagnostics): discover/load/JSON builder with tests"
```

---

## Task 3: `shared/diagnostics_word.py` — DOCX generator

**Files:**
- Create: `shared/diagnostics_word.py`

Notă: Nu există teste unitare pentru DOCX (testarea vizuală în Word). Verificare: scriptul rulează fără excepție și fișierul e deschidibil.

- [ ] **Step 1: Creează `shared/diagnostics_word.py`**

```python
# shared/diagnostics_word.py
from __future__ import annotations
from pathlib import Path
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from shared.diagnostics_builder import Phase0Result, Phase1Result, Phase2Result

_RED   = RGBColor(0xC0, 0x00, 0x00)
_ORANGE = RGBColor(0xFF, 0x80, 0x00)
_GREEN = RGBColor(0x00, 0x80, 0x00)
_GREY  = RGBColor(0x60, 0x60, 0x60)

_ALARM_EMOJI = {"red": "🔴", "yellow": "🟡", "green": "✅"}


def _heading(doc: Document, text: str, level: int = 1) -> None:
    doc.add_heading(text, level=level)


def _add_table_row(table, cells: list[str], bold: bool = False) -> None:
    row = table.add_row()
    for i, text in enumerate(cells):
        cell = row.cells[i]
        cell.text = text
        if bold:
            for run in cell.paragraphs[0].runs:
                run.bold = True


def _sumar_oferte_table(doc: Document, oferte: list[dict]) -> None:
    headers = ["Ofertă", "Matched", "LIPSA", "EXTRA", "DEVIZ_MM"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    hdr_row = table.rows[0]
    for i, h in enumerate(headers):
        hdr_row.cells[i].text = h
        for run in hdr_row.cells[i].paragraphs[0].runs:
            run.bold = True
    for o in oferte:
        s = o["sumar"]
        _add_table_row(table, [
            f"Oferta {o['oferta_idx']}",
            str(s["matched"]),
            str(s["lipsa"]),
            str(s["extra"]),
            str(s["deviz_mismatch"]),
        ])


def _phase0_section(doc: Document, p0: Phase0Result) -> None:
    _heading(doc, "Phase 0 — Calitate Referință", level=2)
    emoji = _ALARM_EMOJI[p0.alarm_level]

    def _item(label: str, items: list[dict], severity: str) -> None:
        em = _ALARM_EMOJI[severity]
        p = doc.add_paragraph()
        run = p.add_run(f"{em} {len(items)} {label}")
        run.bold = len(items) > 0
        if items:
            for a in items[:20]:
                doc.add_paragraph(
                    f"    · {a.get('cod', '?')} — {a.get('denumire', '')[:80]}",
                    style="List Bullet"
                )
            if len(items) > 20:
                doc.add_paragraph(f"    ... și {len(items)-20} mai multe")

    _item("articole fără deviz", p0.fara_deviz, "red" if p0.fara_deviz else "green")
    _item("componente orfane (fără parent identificat)", p0.componente_orfane,
          "red" if len(p0.componente_orfane) > 10 else ("yellow" if p0.componente_orfane else "green"))
    _item("articole incomplete (cant=0 și um lipsă)", p0.incomplete,
          "yellow" if p0.incomplete else "green")


def _phase1_section(doc: Document, oferta_idx: int, p1: Phase1Result) -> None:
    _heading(doc, f"Phase 1 — Articole EXTRA — Oferta {oferta_idx} ({p1.total_extra} total)", level=2)

    if p1.total_extra == 0:
        doc.add_paragraph("✅ Niciun articol extra.")
        return

    if p1.total_extra_dollar > 0:
        doc.add_paragraph(
            f"⚠ {p1.total_extra_dollar} din {p1.total_extra} sunt $-coduri (resurse eDevize). "
            f"Volum mare poate indica bug extragere referință — verificați Phase 0 și PDF original.",
            style="Intense Quote"
        )

    for deviz, arts in sorted(p1.by_deviz.items()):
        doc.add_paragraph(f"Deviz {deviz} — {len(arts)} articole extra:", style="List Bullet")
        for a in arts:
            cod = a.get("oferta_cod") or "?"
            den = (a.get("oferta_denumire") or "")[:70]
            cant = a.get("oferta_cantitate")
            um = a.get("oferta_um") or ""
            cant_str = f"  cant: {cant} {um}" if cant else ""
            doc.add_paragraph(f"    · {cod} — {den}{cant_str}", style="List Bullet 2")


def _phase2_section(doc: Document, oferta_idx: int, p2: Phase2Result) -> None:
    total = p2.total_lipsa + p2.total_deviz_mismatch
    _heading(doc,
             f"Phase 2 — Articole LIPSA — Oferta {oferta_idx} "
             f"({p2.total_lipsa} genuine + {p2.total_deviz_mismatch} deviz mismatch)",
             level=2)

    if p2.total_lipsa == 0 and p2.total_deviz_mismatch == 0:
        doc.add_paragraph("✅ Niciun articol lipsă.")
        return

    if p2.by_deviz:
        for deviz, arts in sorted(p2.by_deviz.items()):
            doc.add_paragraph(f"Deviz {deviz} — {len(arts)} articole lipsă:", style="List Bullet")
            for a in arts:
                cod = a.get("ref_cod") or "?"
                den = (a.get("ref_denumire") or "")[:70]
                cant = a.get("ref_cantitate")
                um = a.get("ref_um") or ""
                cant_str = f"  ref: {cant} {um}" if cant else ""
                doc.add_paragraph(f"    · {cod} — {den}{cant_str}", style="List Bullet 2")

    if p2.total_deviz_mismatch > 0:
        doc.add_paragraph(
            f"DEVIZ_MISMATCH ({p2.total_deviz_mismatch}): coduri prezente în ofertă dar în alt deviz. "
            f"Nu sunt erori reale — verificare manuală dacă devizul diferit e acceptabil."
        )


def _global_summary_table(doc: Document, data: dict) -> None:
    _heading(doc, "Sumar Global", level=1)
    sg = data["sumar_global"]
    doc.add_paragraph(f"Clienți analizați: {len(data['clienti'])}")
    doc.add_paragraph(f"Total matched: {sg['total_matched']}")
    doc.add_paragraph(f"Total LIPSA genuine: {sg['total_lipsa']}")
    doc.add_paragraph(f"Total EXTRA: {sg['total_extra']}")
    doc.add_paragraph(f"Total DEVIZ_MISMATCH: {sg['total_deviz_mismatch']}")

    if sg["clienti_cu_alarme_ref"]:
        doc.add_paragraph(
            f"⚠ Clienți cu alarme Phase 0: {', '.join(sg['clienti_cu_alarme_ref'])}"
        )

    headers = ["Client", "Ofertă", "Matched", "LIPSA", "EXTRA", "DEVIZ_MM", "Ref alarm"]
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    hdr_row = table.rows[0]
    for i, h in enumerate(headers):
        hdr_row.cells[i].text = h
        for run in hdr_row.cells[i].paragraphs[0].runs:
            run.bold = True

    for cr in data["_client_reports"]:
        for o in cr["_oferte_full"]:
            s = o["sumar"]
            alarm = cr["ref_quality"]["alarm_level"]
            _add_table_row(table, [
                cr["client"],
                f"Oferta {o['oferta_idx']}",
                str(s["matched"]),
                str(s["lipsa"]),
                str(s["extra"]),
                str(s["deviz_mismatch"]),
                _ALARM_EMOJI[alarm],
            ])


def generate_diagnostics_docx(data: dict, output_path: Path) -> None:
    doc = Document()
    doc.add_heading("Raport Diagnostic — Analizator Oferte", level=0)

    from datetime import datetime
    doc.add_paragraph(f"Generat: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    doc.add_paragraph(f"Clienți: {', '.join(data['meta']['clienti_analizati'])}")
    doc.add_page_break()

    for cr in data["_client_reports"]:
        _heading(doc, f"CLIENT: {cr['client']}", level=1)
        _sumar_oferte_table(doc, cr["_oferte_full"])
        doc.add_paragraph()

        _phase0_section(doc, cr["_phase0"])

        for o in cr["_oferte_full"]:
            _phase1_section(doc, o["oferta_idx"], o["_phase1"])
            _phase2_section(doc, o["oferta_idx"], o["_phase2"])

        doc.add_page_break()

    _global_summary_table(doc, data)
    doc.save(output_path)
```

- [ ] **Step 2: Testează vizual — rulează pe date reale**

```bash
.venv/bin/python -c "
from pathlib import Path
import json
from shared.diagnostics_builder import build_diagnostics_json, discover_clients
from shared.diagnostics_word import generate_diagnostics_docx

clients = discover_clients()
print('Clienți găsiți:', clients)
data = build_diagnostics_json(clients)
generate_diagnostics_docx(data, Path('output_AO/diagnostics_test.docx'))
print('Generat: output_AO/diagnostics_test.docx')
"
```

Expected: fișier creat fără excepție

- [ ] **Step 3: Verificare metrici vs baseline**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
from shared.diagnostics_builder import build_diagnostics_json, discover_clients

data = build_diagnostics_json(discover_clients())
for cr in data['clienti']:
    print(f\"\n{cr['client']}\")
    for o in cr['oferte']:
        s = o['sumar']
        print(f\"  O{o['oferta_idx']}: matched={s['matched']} LIPSA={s['lipsa']} EXTRA={s['extra']} DEVIZ_MM={s['deviz_mismatch']}\")
    alarm = cr['ref_quality']['alarm_level']
    orfane = len(cr['ref_quality']['componente_orfane'])
    print(f\"  Ref: alarm={alarm} orfane={orfane}\")
"
```

Expected vs baseline state.md:
```
Blocuri Racari O1: matched=308 LIPSA=47 EXTRA=0 DEVIZ_MM=20
Camin Maneciu O1: matched=1056 LIPSA=3 EXTRA=36 DEVIZ_MM=0  (sau LIPSA=1 DEVIZ_MM=2)
Scoala Sportiva Racari O1: matched=2153 LIPSA=2 EXTRA=122 DEVIZ_MM=11
Scoala Dragomiresti O1: matched=651 EXTRA=0 DEVIZ_MM=600+
SSR ref: alarm=yellow/red orfane=154
```

- [ ] **Step 4: Commit**

```bash
git add shared/diagnostics_word.py
git commit -m "feat(diagnostics): DOCX generator"
```

---

## Task 4: `run_diagnostics.py` — CLI entry point

**Files:**
- Create: `run_diagnostics.py`

- [ ] **Step 1: Creează `run_diagnostics.py`**

```python
#!/usr/bin/env python3
# run_diagnostics.py
"""Diagnostic runner — citește output_AO/<client>/ și generează diagnostics.json + diagnostics.docx"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

from shared.diagnostics_builder import build_diagnostics_json, discover_clients
from shared.diagnostics_word import generate_diagnostics_docx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generează raport diagnostic pentru toți clienții")
    parser.add_argument("--client", help="Rulează doar pentru un client specific")
    parser.add_argument("--no-docx", action="store_true", help="Generează doar JSON, fără DOCX")
    parser.add_argument("--output-dir", default="output_AO", help="Director output (default: output_AO)")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)

    if args.client:
        client_ref = output_dir / args.client / "referinta.json"
        if not client_ref.exists():
            print(f"EROARE: Nu există output pentru '{args.client}' în {output_dir}", file=sys.stderr)
            return 1
        clients = [args.client]
    else:
        clients = discover_clients(base_dir=output_dir)
        if not clients:
            print(f"EROARE: Niciun client cu output în {output_dir}", file=sys.stderr)
            return 1

    print(f"Clienți analizați: {', '.join(clients)}")

    data = build_diagnostics_json(clients, base_dir=output_dir)

    json_path = output_dir / "diagnostics.json"
    json_path.write_text(json.dumps(
        {k: v for k, v in data.items() if not k.startswith("_")},
        ensure_ascii=False, indent=2
    ))
    print(f"✅ JSON: {json_path}")

    if not args.no_docx:
        docx_path = output_dir / "diagnostics.docx"
        generate_diagnostics_docx(data, docx_path)
        print(f"✅ DOCX: {docx_path}")

    sg = data["sumar_global"]
    print(f"\nSumar global:")
    print(f"  matched={sg['total_matched']} LIPSA={sg['total_lipsa']} "
          f"EXTRA={sg['total_extra']} DEVIZ_MM={sg['total_deviz_mismatch']}")
    if sg["clienti_cu_alarme_ref"]:
        print(f"  ⚠ Alarme Phase 0: {', '.join(sg['clienti_cu_alarme_ref'])}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Rulează pe toți clienții**

```bash
.venv/bin/python run_diagnostics.py
```

Expected output:
```
Clienți analizați: Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari
✅ JSON: output_AO/diagnostics.json
✅ DOCX: output_AO/diagnostics.docx

Sumar global:
  matched=... LIPSA=... EXTRA=... DEVIZ_MM=...
  ⚠ Alarme Phase 0: Scoala Sportiva Racari
```

- [ ] **Step 3: Rulează cu `--client`**

```bash
.venv/bin/python run_diagnostics.py --client "Blocuri Racari"
```

Expected: rulează doar BR, același format output

- [ ] **Step 4: Rulează cu `--no-docx`**

```bash
.venv/bin/python run_diagnostics.py --no-docx
```

Expected: doar `diagnostics.json` creat, nicio linie DOCX

- [ ] **Step 5: Verifică JSON structura**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
data = json.loads(Path('output_AO/diagnostics.json').read_text())
print('Top keys:', list(data.keys()))
print('Clienți:', [c['client'] for c in data['clienti']])
ssr = next(c for c in data['clienti'] if 'Sportiva' in c['client'])
print('SSR ref alarm:', ssr['ref_quality']['alarm_level'])
print('SSR orfane:', len(ssr['ref_quality']['componente_orfane']))
"
```

Expected: `alarm_level` în `yellow` sau `red`, `componente_orfane` ≈ 154

- [ ] **Step 6: Commit final**

```bash
git add run_diagnostics.py
git commit -m "feat(diagnostics): CLI entry point run_diagnostics.py"
```

---

## Task 5: Rulare completă + validare finală

**Files:** nicio modificare de cod

- [ ] **Step 1: Rulează full suite de teste**

```bash
.venv/bin/python -m pytest tests/test_diagnostics.py -v
```

Expected: 18+ tests PASS, 0 failures

- [ ] **Step 2: Rulează diagnostics pe toți clienții**

```bash
.venv/bin/python run_diagnostics.py
```

Expected: 4 clienți procesați, JSON + DOCX generate

- [ ] **Step 3: Verifică metrici vs baseline complet (state.md)**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
data = json.loads(Path('output_AO/diagnostics.json').read_text())
print('=== VALIDARE vs BASELINE ===')
expected = {
    'Blocuri Racari': {1: (308,47,0,20), 2:(551,2,0,28), 3:(370,25,4,19), 4:(311,49,1,9)},
    'Camin Maneciu':  {1: (1056,3,36,0), 2:(1066,130,41,0)},
    'Scoala Sportiva Racari': {1:(2153,2,122,11)},
    'Scoala Dragomiresti': {1:(651,6,0,624)},
}
for cr in data['clienti']:
    cn = cr['client']
    if cn not in expected:
        continue
    for o in cr['oferte']:
        idx = o['oferta_idx']
        if idx not in expected.get(cn, {}):
            continue
        exp = expected[cn][idx]
        s = o['sumar']
        got = (s['matched'], s['lipsa'], s['extra'], s['deviz_mismatch'])
        status = '✅' if got == exp else '⚠'
        print(f'{status} {cn} O{idx}: got={got} exp={exp}')
"
```

- [ ] **Step 4: Deschide DOCX în Word și verifică vizual**

Verifică:
- Fiecare client are secțiunea sa
- Phase 0 arată orfanele SSR (154)
- Phase 1 arată cele 36 EXTRA Camin Maneciu O1 grupate pe deviz
- Phase 2 arată Scoala Dragomiresti cu DEVIZ_MM separat de LIPSA genuine (6)
- Sumar global cu tabel cross-client

- [ ] **Step 5: Commit final cu tag**

```bash
git add -A
git commit -m "feat(diagnostics): complete diagnostic runner - JSON + DOCX"
```
