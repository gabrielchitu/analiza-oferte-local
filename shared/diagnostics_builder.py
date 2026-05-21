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
    return Phase2Result(lipsa_genuine=genuine, deviz_mismatch=mismatch, by_deviz=by_deviz)
