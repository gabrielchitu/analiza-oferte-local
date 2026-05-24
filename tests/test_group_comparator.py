import pytest
from shared.group_comparator import compare_by_groups, HolisticComparison


def _make_article(cod, deviz, deviz_header=None, cantitate=1.0, um="mp", denumire="test"):
    art = {
        "cod": cod, "deviz": deviz, "cantitate": cantitate, "um": um,
        "denumire": denumire, "is_component": False, "parent_cod": "",
        "deviz_key": f"key_{deviz}", "source_pages": [],
    }
    art["deviz_header"] = deviz_header or {
        "obiectivul": "Proiect A", "obiectul": f"Obiect {deviz}", "categoria": f"Cat {deviz}"
    }
    return art


def _make_header(obj1, obj2, cat, deviz_cod=""):
    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key
    key, valid = _make_deviz_key(obj1, obj2, cat)
    return DevizHeader(obj1, obj2, cat, key, valid, "test", deviz_cod)


def test_matched_groups_basic():
    ref_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    oferta_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    ref_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    oferta_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert isinstance(result, HolisticComparison)
    assert len(result.matched_groups) == 1
    assert len(result.ref_only_groups) == 0
    assert len(result.oferta_only_groups) == 0
    mg = result.matched_groups[0]
    assert mg["ref_deviz_cod"] == "D1"
    assert mg["oferta_deviz_cod"] == "D1"


def test_ref_only_group_all_lipsa():
    ref_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    oferta_arts = []
    ref_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    oferta_dh = {}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert len(result.ref_only_groups) == 1
    rg = result.ref_only_groups[0]
    assert rg["ref_deviz_cod"] == "D1"
    assert len(rg["neconformitati"]) == 2
    assert all(n["tip"] == "ARTICOL_LIPSA" for n in rg["neconformitati"])


def test_oferta_only_group_all_extra():
    ref_arts = []
    oferta_arts = [_make_article("EA02A1", "D2"), _make_article("CA01A", "D2")]
    ref_dh = {}
    oferta_dh = {"D2": _make_header("Proiect B", "Obiect D2", "Cat D2", "D2")}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert len(result.oferta_only_groups) == 1
    og = result.oferta_only_groups[0]
    assert og["oferta_deviz_cod"] == "D2"
    assert len(og["neconformitati"]) == 2
    assert all(n["tip"] == "ARTICOL_EXTRA" for n in og["neconformitati"])


def test_ungrouped_articles():
    art_no_deviz = {"cod": "XX01A", "deviz": "", "cantitate": 1.0, "is_component": False,
                    "denumire": "test", "um": "mp"}
    result = compare_by_groups([art_no_deviz], [], {}, {})
    assert len(result.ungrouped) > 0
    assert any(a.get("cod") == "XX01A" for a in result.ungrouped)


def test_group_match_different_codes_same_content():
    ref_arts = [_make_article("EA02A1", "D1")]
    oferta_arts = [_make_article("EA02A1", "D2")]
    # Both are for "Proiect A" / "Organizare Santier" / "BLC1 Organizare"
    # but with slightly different formatting (numbers, spacing, etc.)
    ref_dh = {"D1": _make_header("Proiect A", "Organizare Santier", "BLC1 Organizare", "D1")}
    oferta_dh = {"D2": _make_header("Proiect A", "03 Organizare Santier", "BLC1 Organizare", "D2")}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert len(result.matched_groups) == 1
    mg = result.matched_groups[0]
    assert mg["ref_deviz_cod"] == "D1"
    assert mg["oferta_deviz_cod"] == "D2"
