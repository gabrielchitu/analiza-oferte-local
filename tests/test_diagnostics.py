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


# Phase 1 tests
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


# Phase 2 tests
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
    assert "4.1-02" in result.by_deviz           # DEVIZ_MISMATCH also grouped
    assert len(result.by_deviz["4.1-02"]) == 1   # RPC01 DEVIZ_MISMATCH

def test_phase2_ignora_extra():
    result = analyze_lipsa(NC_LIPSA)
    all_arts = result.lipsa_genuine + result.deviz_mismatch
    for art in all_arts:
        assert art["tip"] in ("ARTICOL_LIPSA", "DEVIZ_MISMATCH")
