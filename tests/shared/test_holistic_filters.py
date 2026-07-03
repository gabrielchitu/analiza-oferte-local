"""Tests for shared/holistic_filters.py — CODELESS suppression in reports."""
from shared.holistic_filters import strip_codeless, strip_codeless_ncs


def _holistic():
    return {
        "sumar": {"total_matched_articles": 5},
        "matched_groups": [{
            "ref_deviz_cod": "D1",
            "neconformitati": [
                {"tip": "ARTICOL_LIPSA", "ref_cod": "CODELESS28", "ref_denumire": "buton"},
                {"tip": "ARTICOL_LIPSA", "ref_cod": "TSA01A1", "ref_denumire": "sapatura"},
                {"tip": "ARTICOL_EXTRA", "oferta_cod": "CODELESS4", "oferta_denumire": "junk"},
            ],
            "ref_articles": [
                {"cod": "CODELESS28", "denumire": "buton"},
                {"cod": "TSA01A1", "denumire": "sapatura"},
            ],
            "oferta_articles": [{"cod": "CODELESS4", "denumire": "junk"}],
        }],
        "ref_only_groups": [{
            "articles": [{"cod": "CODELESS2", "denumire": "strat uzura"}],
            "neconformitati": [
                {"tip": "ARTICOL_LIPSA", "ref_cod": "CODELESS2", "ref_denumire": "strat uzura"},
            ],
        }],
    }


def test_strip_codeless_removes_ncs_and_articles():
    result = strip_codeless(_holistic())
    mg = result["matched_groups"][0]
    assert [nc["ref_cod"] for nc in mg["neconformitati"]] == ["TSA01A1"]
    assert [a["cod"] for a in mg["ref_articles"]] == ["TSA01A1"]
    assert mg["oferta_articles"] == []
    rg = result["ref_only_groups"][0]
    assert rg["articles"] == []
    assert rg["neconformitati"] == []


def test_strip_codeless_does_not_mutate_input():
    original = _holistic()
    strip_codeless(original)
    assert len(original["matched_groups"][0]["neconformitati"]) == 3
    assert len(original["matched_groups"][0]["ref_articles"]) == 2


def test_strip_codeless_handles_empty():
    assert strip_codeless({}) == {}
    assert strip_codeless(None) is None
    assert strip_codeless_ncs(None) == []
    assert strip_codeless_ncs([{"tip": "X", "ref_cod": "AB1"}]) == [{"tip": "X", "ref_cod": "AB1"}]
