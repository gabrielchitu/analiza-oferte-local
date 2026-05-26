import pytest
import json
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
    assert mg["ref_deviz_cod"] == "key_D1"
    assert mg["oferta_deviz_cod"] == "key_D1"


def test_ref_only_group_all_lipsa():
    ref_arts = [_make_article("EA02A1", "D1"), _make_article("CA01A", "D1")]
    oferta_arts = []
    ref_dh = {"D1": _make_header("Proiect A", "Obiect D1", "Cat D1", "D1")}
    oferta_dh = {}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert len(result.ref_only_groups) == 1
    rg = result.ref_only_groups[0]
    assert "D1" in rg["ref_deviz_cod"]
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
    assert "D2" in og["oferta_deviz_cod"]
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
    # Headers keyed by deviz_key (as _headers_from_articles does in production)
    ref_dh = {"key_D1": _make_header("Proiect A", "Organizare Santier", "BLC1 Organizare", "D1")}
    oferta_dh = {"key_D2": _make_header("Proiect A", "03 Organizare Santier", "BLC1 Organizare", "D2")}
    result = compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh)
    assert len(result.matched_groups) == 1
    mg = result.matched_groups[0]
    assert "key_D1" in mg["ref_deviz_cod"]
    assert "key_D2" in mg["oferta_deviz_cod"]


def test_build_raport_holistic_structure():
    from shared.group_comparator import HolisticComparison
    from shared.report_builder import build_raport_holistic

    hc = HolisticComparison(
        matched_groups=[{
            "ref_deviz_cod": "D1", "oferta_deviz_cod": "D1",
            "ref_header": None, "oferta_header": None,
            "ref_articles": [{"cod": "EA02A1", "deviz": "D1", "cantitate": 1.0,
                               "denumire": "test", "um": "mp", "is_component": False,
                               "nr_ordine": 1, "parent_cod": ""}],
            "oferta_articles": [],
            "neconformitati": [{"tip": "ARTICOL_LIPSA", "ref_cod": "EA02A1",
                                "deviz_ref": "D1", "deviz_denumire": ""}],
            "matches": [],
        }],
        ref_only_groups=[],
        oferta_only_groups=[{
            "oferta_deviz_cod": "D2", "oferta_header": None,
            "articles": [{"cod": "CB01A", "deviz": "D2", "cantitate": 5.0,
                          "denumire": "extra", "um": "mc", "is_component": False,
                          "nr_ordine": 1, "parent_cod": ""}],
            "neconformitati": [{"tip": "ARTICOL_EXTRA", "oferta_cod": "CB01A",
                                "deviz_ref": "", "deviz_denumire": ""}],
        }],
        ungrouped=[{"source": "ref", "cod": "??", "deviz": ""}],
    )

    raport = build_raport_holistic(hc)

    assert "matched_groups" in raport
    assert "ref_only_groups" in raport
    assert "oferta_only_groups" in raport
    assert "ungrouped" in raport
    assert "sumar" in raport
    assert raport["sumar"]["total_matched_groups"] == 1
    assert raport["sumar"]["total_ref_only_groups"] == 0
    assert raport["sumar"]["total_oferta_only_groups"] == 1
    assert raport["sumar"]["total_ungrouped_articles"] == 1


def test_holistic_comparison_has_match_trace():
    from shared.group_comparator import HolisticComparison
    hc = HolisticComparison()
    assert hasattr(hc, "match_trace")
    assert isinstance(hc.match_trace, dict)


def test_apply_knowledge_returns_pairs(tmp_path, monkeypatch):
    """_apply_knowledge matches known ref_den/oferta_den pairs to deviz keys."""
    from shared import group_comparator as gc
    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key

    def _make_hdr(obj1, obj2, cat, cod="X"):
        key, valid = _make_deviz_key(obj1, obj2, cat)
        return DevizHeader(obj1, obj2, cat, key, valid, "test", cod)

    ref_hdr = _make_hdr("Proj", "Obj1", "Cat1")
    oferta_hdr = _make_hdr("Proj", "Obj1", "Cat1 tip I")
    rkey = ref_hdr.deviz_key
    okey = oferta_hdr.deviz_key

    kf = tmp_path / "group_match_knowledge.json"
    kf.write_text(json.dumps({
        "TestClient": [
            {"ref_den": "Proj | Obj1 | Cat1", "oferta_den": "Proj | Obj1 | Cat1 tip I"}
        ]
    }))
    monkeypatch.setattr(gc, "_KNOWLEDGE_PATH", kf)

    result = gc._apply_knowledge(
        remaining_ref={rkey},
        remaining_oferta={okey},
        ref_deviz_headers={rkey: ref_hdr},
        oferta_deviz_headers={okey: oferta_hdr},
        client_name="TestClient",
    )
    assert (rkey, okey) in result


def test_save_knowledge_deduplicates(tmp_path, monkeypatch):
    """_save_knowledge deduplicates on (ref_den, oferta_den)."""
    from shared import group_comparator as gc

    kf = tmp_path / "group_match_knowledge.json"
    kf.write_text("{}")
    monkeypatch.setattr(gc, "_KNOWLEDGE_PATH", kf)

    pair = {"ref_den": "A | B | C", "oferta_den": "A | B | C tip I"}
    gc._save_knowledge("MyClient", [pair])
    gc._save_knowledge("MyClient", [pair])  # second call — same pair

    data = json.loads(kf.read_text())
    assert len(data["MyClient"]) == 1
    assert data["MyClient"][0]["ref_den"] == "A | B | C"
