"""Tests for f3_regex_parser with hierarchical component support."""
from shared import f3_regex_parser


def test_extract_components_from_denomination():
    """Extract subcomponent codes from parent denomination."""
    denom = "teava din material plastic pe, d=110mm l: sl05 -0020:6717077 -teava polietilena"

    codes = f3_regex_parser._extract_subcomponent_codes(denom)
    assert "6717077" in codes


def test_make_article_with_parent_code():
    """Article can have parent_code for component tracking."""
    art = f3_regex_parser._make_article(
        cod="6717077",
        denumire="teava polietilena",
        um="m",
        cantitate=2.0,
        preturi=[0, 0, 0, 0],
        deviz_cod="4.3-07",
        deviz_den="Conducte",
        is_component=True,
        parent_code="SA14J"
    )
    assert art["cod"] == "6717077"
    assert art["parent_code"] == "SA14J"
    assert art["is_component"] is True


def test_make_article_parent():
    """Parent article has parent_code=null."""
    art = f3_regex_parser._make_article(
        cod="SA14J",
        denumire="teava din material plastic",
        um="m",
        cantitate=2.0,
        preturi=[0, 0, 0, 0],
        deviz_cod="4.3-07",
        deviz_den="Conducte",
        is_component=False,
        parent_code=None,
        subcomponents=["6717077", "6719428"]
    )
    assert art["parent_code"] is None
    assert art["is_component"] is False
    assert art["subcomponents"] == ["6717077", "6719428"]
