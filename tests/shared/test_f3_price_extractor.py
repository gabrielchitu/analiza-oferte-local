import pytest
from shared.f3_price_extractor import _parse_number, _is_capitol_header, _is_cod_name, _is_um, _is_breakdown_key

def test_parse_number_simple():
    assert _parse_number("33.22") == pytest.approx(33.22)

def test_parse_number_with_thousands():
    assert _parse_number("7,473.71") == pytest.approx(7473.71)

def test_parse_number_zero():
    assert _parse_number("0.00") == pytest.approx(0.0)

def test_parse_number_invalid():
    assert _parse_number("material:") is None
    assert _parse_number("INFRASTRUCTURA") is None
    assert _parse_number("") is None

def test_is_capitol_header_yes():
    assert _is_capitol_header("INFRASTRUCTURA") is True
    assert _is_capitol_header("COMPARTIMENTARI") is True
    assert _is_capitol_header("FINISAJE EXTERIOARE") is True

def test_is_capitol_header_no():
    assert _is_capitol_header("TOTAL INFRASTRUCTURA") is False
    assert _is_capitol_header("1") is False
    assert _is_capitol_header("CF38A* - Tencuiala") is False
    assert _is_capitol_header("Nr.") is False

def test_is_cod_name_standard():
    assert _is_cod_name("CF38A* - Tencuiala pe baza de ciment") is True
    assert _is_cod_name("RPCE27A+ - Mastic bituminos") is True

def test_is_cod_name_numeric():
    assert _is_cod_name("2101121 - Mortar de zidarie M 10 nisip S1030") is True

def test_is_cod_name_no():
    assert _is_cod_name("mp") is False
    assert _is_cod_name("225.000") is False
    assert _is_cod_name("armatura din poliester") is False  # continuation line

def test_is_um():
    assert _is_um("mp") is True
    assert _is_um("MP") is True
    assert _is_um("mc") is True
    assert _is_um("buc") is True
    assert _is_um("ml") is True
    assert _is_um("kg") is True
    assert _is_um("33.22") is False
    assert _is_um("CF38A*") is False

def test_is_breakdown_key():
    assert _is_breakdown_key("material:") is True
    assert _is_breakdown_key("manopera:") is True
    assert _is_breakdown_key("utilaj:") is True
    assert _is_breakdown_key("transport:") is True
    assert _is_breakdown_key("material") is False
    assert _is_breakdown_key("TOTAL") is False
