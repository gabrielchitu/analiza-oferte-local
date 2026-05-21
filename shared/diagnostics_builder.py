from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import json
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
            by_deviz.setdefault(deviz, []).append(nc)
    return Phase2Result(lipsa_genuine=genuine, deviz_mismatch=mismatch, by_deviz=by_deviz)


def discover_clients(base_dir: Path | None = None) -> list[str]:
    base = Path(base_dir) if base_dir else Path("output_AO")
    if not base.exists():
        return []
    return sorted(
        d.name for d in base.iterdir()
        if d.is_dir() and (d / "referinta.json").exists()
    )


def load_client_data(client_name: str, base_dir: Path | None = None) -> tuple[list[dict], list[dict]]:
    base = Path(base_dir) if base_dir else Path("output_AO")
    client_dir = base / client_name
    ref_path = client_dir / "referinta.json"
    if not ref_path.exists():
        raise FileNotFoundError(f"referinta.json not found for client '{client_name}': {ref_path}")
    ref_articole = json.loads(ref_path.read_text())["articole"]
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
