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


def test_regex_extraction_includes_confidence():
    """Regex extraction should include confidence score"""
    # Use a realistic article format: "1 CF41B01 - ARTICLE DESCRIPTION"
    lines = [
        "1",
        "CF41B01 - ARTICLE DESCRIPTION",
        "BUC",
        "10"
    ]

    result = f3_regex_parser.extract_articles_regex(lines, deviz_cod="0001", deviz_den="TEST")

    assert len(result) > 0, "Should extract article"
    article = result[0]

    assert "confidence" in article, "Article should have confidence field"
    assert 0.0 <= article["confidence"] <= 1.0, f"Confidence out of range: {article['confidence']}"
    assert article["confidence"] >= 0.60, "Regex confidence should be at least MEDIUM (0.60)"

    # Check metadata fields
    assert "extraction_source" in article, "Article should have extraction_source field"
    assert article["extraction_source"] == "REGEX", "extraction_source should be 'REGEX'"
    assert "descriere_normalized" in article, "Article should have descriere_normalized"
    assert "um_normalized" in article, "Article should have um_normalized"
    assert "cant_numeric" in article, "Article should have cant_numeric"
    assert "comparison_key" in article, "Article should have comparison_key"
    assert "parent_nr" in article, "Article should have parent_nr"
    assert "is_component" in article, "Article should have is_component"
