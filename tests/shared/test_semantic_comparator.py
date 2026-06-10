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


from shared.semantic_comparator import semantic_spec_check


def _match(ref_cod, ref_den, oferta_cod=None, oferta_den=None):
    return {
        "ref_cod": ref_cod,
        "ref_denumire": ref_den,
        "oferta_cod": oferta_cod or ref_cod,
        "oferta_denumire": oferta_den or ref_den,
    }


def _ref_art(cod, den, um="buc", cant=1.0, is_component=False, nr=1, deviz="D1", deviz_den="ctx"):
    return {
        "cod": cod,
        "denumire": den,
        "um": um,
        "cantitate": cant,
        "is_component": is_component,
        "nr_ordine": nr,
        "deviz": deviz,
        "deviz_denumire": deviz_den,
    }


def _oferta_art(cod, den, um="buc", cant=1.0, nr=1):
    return {"cod": cod, "denumire": den, "um": um, "cantitate": cant, "nr_ordine": nr}


LLM_SPEC_SIG = {"diferenta_semnificativa": True, "nota_specialist": "Înălțime diferită: 8m vs 5m"}
LLM_SPEC_NOT = {"diferenta_semnificativa": False, "nota_specialist": ""}


def test_pass2_significant_diff_produces_specificatie_diferita():
    matches = [_match("W2A16A", "stalp pentru iluminat 8m", oferta_den="stalp pentru iluminat 5m")]
    ref_arts = [_ref_art("W2A16A", "stalp pentru iluminat 8m")]
    oferta_arts = [_oferta_art("W2A16A", "stalp pentru iluminat 5m")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value=LLM_SPEC_SIG):
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    assert len(result) == 1
    assert result[0]["tip"] == "SPECIFICATIE_DIFERITA"
    assert result[0]["ref_cod"] == "W2A16A"
    assert result[0]["nota_specialist"] == LLM_SPEC_SIG["nota_specialist"]


def test_pass2_no_significant_diff_returns_empty():
    matches = [_match("W2A16A", "stalp pentru iluminat 8m", oferta_den="stalp pentru iluminat 5m")]
    ref_arts = [_ref_art("W2A16A", "stalp pentru iluminat 8m")]
    oferta_arts = [_oferta_art("W2A16A", "stalp pentru iluminat 5m")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value=LLM_SPEC_NOT):
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    assert result == []


def test_pass2_prefilter_identical_denominations_no_llm_call():
    matches = [_match("W2A16A", "stalp pentru iluminat 8m")]  # same ref+oferta_den
    ref_arts = [_ref_art("W2A16A", "stalp pentru iluminat 8m")]
    oferta_arts = [_oferta_art("W2A16A", "stalp pentru iluminat 8m")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert result == []


def test_pass2_prefilter_high_jaccard_same_numerics_no_llm_call():
    # "stalp pentru iluminat public 8m" vs "stalp pt iluminat public 8m" — high jaccard, same "8"
    matches = [_match("W2A16A", "stalp pentru iluminat public 8m",
                      oferta_den="stalp pt iluminat public 8m")]
    ref_arts = [_ref_art("W2A16A", "stalp pentru iluminat public 8m")]
    oferta_arts = [_oferta_art("W2A16A", "stalp pt iluminat public 8m")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert result == []


def test_pass2_component_articles_excluded():
    matches = [_match("$12345", "subcomponent DVR")]
    ref_arts = [_ref_art("$12345", "subcomponent DVR", is_component=True)]
    oferta_arts = [_oferta_art("$12345", "subcomponent DVR diferit")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert result == []


def test_pass2_cod_similar_pairs_excluded():
    # ref_cod != oferta_cod → not in scope for Pass 2
    matches = [_match("SA131", "Sapatura", oferta_cod="SA13I", oferta_den="Sapatura")]
    ref_arts = [_ref_art("SA131", "Sapatura")]
    oferta_arts = [_oferta_art("SA13I", "Sapatura")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json") as mock_llm:
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    mock_llm.assert_not_called()
    assert result == []


def test_pass2_llm_parse_failure_skips_pair():
    matches = [_match("W2A16A", "stalp 8m", oferta_den="stalp 5m")]
    ref_arts = [_ref_art("W2A16A", "stalp 8m")]
    oferta_arts = [_oferta_art("W2A16A", "stalp 5m")]
    mock_client = MagicMock()
    with patch("shared.semantic_comparator._llm_json", return_value={}):
        result = semantic_spec_check(matches, ref_arts, oferta_arts, "ctx", mock_client, "model")
    assert result == []
