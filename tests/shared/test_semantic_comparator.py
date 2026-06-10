# tests/shared/test_semantic_comparator.py
import pytest
from unittest.mock import patch, MagicMock
from shared.semantic_comparator import semantic_nr_match


def _lipsa(nr, ref_cod, ref_den, ref_um="buc", ref_cant=1.0, is_component=False):
    return {
        "tip": "ARTICOL_LIPSA",
        "is_component": is_component,
        "nr_ordine_ref": nr,
        "ref_cod": ref_cod,
        "ref_denumire": ref_den,
        "ref_um": ref_um,
        "ref_cantitate": ref_cant,
        "deviz_ref": "DEV001",
        "deviz_denumire": "Instalatii electrice",
    }


def _extra(nr, oferta_cod, oferta_den, oferta_um="buc", oferta_cant=1.0, is_component=False):
    return {
        "tip": "ARTICOL_EXTRA",
        "is_component": is_component,
        "nr_ordine_oferta": nr,
        "oferta_cod": oferta_cod,
        "oferta_denumire": oferta_den,
        "oferta_um": oferta_um,
        "oferta_cantitate": oferta_cant,
        "deviz_ref": "DEV001",
        "deviz_denumire": "Instalatii electrice",
    }


LLM_MATCH = {
    "match": True,
    "motiv": "Aceeași lucrare: montare DVR; cod normativ diferit",
    "diferente": [
        {"camp": "cod_normativ", "ref": "ES08A4", "oferta": "TCB30A1"},
        {"camp": "specificatie", "detaliu": "Oferta omite numărul de canale (16)"},
    ],
}
LLM_NO_MATCH = {"match": False, "motiv": "Lucrări diferite", "diferente": []}


def test_pass1_match_found_produces_cod_normativ_diferit():
    ncs = [_lipsa(10, "ES08A4", "Montare DVR 16 canale"), _extra(10, "TCB30A1", "MONTARE DVR")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value=LLM_MATCH):
        result = semantic_nr_match(ncs, "Instalatii electrice", mock_client, "model")
    cod_diff = [nc for nc in result if nc["tip"] == "COD_NORMATIV_DIFERIT"]
    assert len(cod_diff) == 1
    assert cod_diff[0]["ref_cod"] == "ES08A4"
    assert cod_diff[0]["oferta_cod"] == "TCB30A1"
    assert cod_diff[0]["nr_ordine"] == 10
    assert cod_diff[0]["motiv_llm"] == LLM_MATCH["motiv"]
    assert len(cod_diff[0]["diferente"]) == 2
    assert not any(nc["tip"] == "ARTICOL_LIPSA" for nc in result)
    assert not any(nc["tip"] == "ARTICOL_EXTRA" for nc in result)


def test_pass1_no_match_leaves_ncs_unchanged():
    ncs = [_lipsa(10, "ES08A4", "Montare DVR 16 canale"), _extra(10, "TCB30A1", "MONTARE DVR")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value=LLM_NO_MATCH):
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    assert len(result) == 2
    assert result[0]["tip"] == "ARTICOL_LIPSA"
    assert result[1]["tip"] == "ARTICOL_EXTRA"


def test_pass1_no_shared_nrs_makes_no_llm_call():
    ncs = [_lipsa(10, "ES08A4", "Montare DVR"), _extra(20, "TCB30A1", "MONTARE DVR")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert len(result) == 2


def test_pass1_component_articles_excluded():
    ncs = [
        _lipsa(10, "ES08A4", "Montare DVR", is_component=True),
        _extra(10, "TCB30A1", "MONTARE DVR", is_component=True),
    ]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert len(result) == 2


def test_pass1_multiple_shared_nrs_calls_llm_per_pair():
    ncs = [
        _lipsa(10, "ES08A4", "Montare DVR"),
        _extra(10, "TCB30A1", "MONTARE DVR"),
        _lipsa(15, "YC01J01", "Paratrasnet"),
        _extra(15, "PTC03A1", "PARATRASNET"),
    ]
    call_count = 0

    def fake_llm(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return LLM_MATCH

    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", side_effect=fake_llm):
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    assert call_count == 2
    assert len([nc for nc in result if nc["tip"] == "COD_NORMATIV_DIFERIT"]) == 2


def test_pass1_llm_parse_failure_skips_pair():
    ncs = [_lipsa(10, "ES08A4", "Montare DVR"), _extra(10, "TCB30A1", "MONTARE DVR")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value={}):
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    assert len(result) == 2  # no crash, originals preserved


def test_pass1_preserves_other_nc_types():
    ncs = [
        _lipsa(10, "ES08A4", "Montare DVR"),
        _extra(10, "TCB30A1", "MONTARE DVR"),
        {"tip": "DIFERENTA_CAMP", "camp": "cantitate", "ref_cod": "X1", "is_component": False},
        {"tip": "UM_DIFERIT", "ref_cod": "X2", "is_component": False},
    ]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value=LLM_MATCH):
        result = semantic_nr_match(ncs, "ctx", mock_client, "model")
    tips = [nc["tip"] for nc in result]
    assert "DIFERENTA_CAMP" in tips
    assert "UM_DIFERIT" in tips
    assert "COD_NORMATIV_DIFERIT" in tips
