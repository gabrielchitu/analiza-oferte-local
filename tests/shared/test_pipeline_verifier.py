import pytest
from shared.pipeline_verifier import verify_holistic, Finding, DEFAULT_THRESHOLDS


def _make_group(ref_arts=None, oferta_arts=None, ncs=None,
                ref_cod="DEV1", oferta_cod="DEV1", den="Test deviz"):
    return {
        "ref_deviz_cod": ref_cod,
        "oferta_deviz_cod": oferta_cod,
        "deviz_denumire": den,
        "ref_articles": ref_arts or [],
        "oferta_articles": oferta_arts or [],
        "neconformitati": ncs or [],
    }


def _art(is_component=False, cant=1.0):
    return {"is_component": is_component, "cantitate": cant, "cod": "A01"}


def _nc(tip):
    return {"tip": tip}


def _holistic(matched=None, ref_only=None, oferta_only=None):
    return {
        "matched_groups": matched or [],
        "ref_only_groups": ref_only or [],
        "oferta_only_groups": oferta_only or [],
    }


# --- SILENT_VIOLATION ---

def test_silent_violation_detected():
    g = _make_group(ref_arts=[_art(), _art()], oferta_arts=[_art()], ncs=[])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    silent = [f for f in findings if f.check == "SILENT_VIOLATION"]
    assert len(silent) == 1
    assert silent[0].severity == "CRITICAL"


def test_no_silent_violation_when_nc_present():
    g = _make_group(ref_arts=[_art(), _art()], oferta_arts=[_art()],
                    ncs=[_nc("ARTICOL_LIPSA")])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    silent = [f for f in findings if f.check == "SILENT_VIOLATION"]
    assert len(silent) == 0


# --- OFERTA_ONLY_GROUP ---

def test_oferta_only_group_detected():
    g = {"oferta_deviz_cod": "OFF1", "deviz_denumire": "Extra group",
         "articles": [_art()], "neconformitati": []}
    data = _holistic(oferta_only=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "OFERTA_ONLY_GROUP"]
    assert len(found) == 1
    assert found[0].severity == "HIGH"


# --- REF_ONLY_GROUP ---

def test_ref_only_group_detected():
    g = {"ref_deviz_cod": "REF1", "deviz_denumire": "Missing group",
         "articles": [_art()], "neconformitati": []}
    data = _holistic(ref_only=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "REF_ONLY_GROUP"]
    assert len(found) == 1


# --- HIGH_EXTRA ---

def test_high_extra_detected_above_threshold():
    ncs = [_nc("ARTICOL_EXTRA")] * 5
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"extra": 3})
    found = [f for f in findings if f.check == "HIGH_EXTRA"]
    assert len(found) == 1
    assert found[0].value == 5
    assert found[0].threshold == 3


def test_high_extra_not_triggered_at_threshold():
    ncs = [_nc("ARTICOL_EXTRA")] * 3
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"extra": 3})
    found = [f for f in findings if f.check == "HIGH_EXTRA"]
    assert len(found) == 0


# --- HIGH_LIPSA ---

def test_high_lipsa_detected():
    ncs = [_nc("ARTICOL_LIPSA")] * 4
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"lipsa": 3})
    found = [f for f in findings if f.check == "HIGH_LIPSA"]
    assert len(found) == 1


# --- COD_SIMILAR_CLUSTER ---

def test_cod_similar_cluster_detected():
    ncs = [_nc("COD_SIMILAR")] * 6
    g = _make_group(ref_arts=[_art()], oferta_arts=[_art()], ncs=ncs)
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {"cod_sim": 5})
    found = [f for f in findings if f.check == "COD_SIMILAR_CLUSTER"]
    assert len(found) == 1


# --- EMPTY_MATCHED_GROUP ---

def test_empty_matched_group_detected():
    g = _make_group(ref_arts=[], oferta_arts=[_art()])
    data = _holistic(matched=[g])
    findings = verify_holistic(data, 1, {})
    found = [f for f in findings if f.check == "EMPTY_MATCHED_GROUP"]
    assert len(found) == 1
    assert found[0].severity == "HIGH"
