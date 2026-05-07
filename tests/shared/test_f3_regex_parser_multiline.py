"""
Test suite for multi-line article extraction in f3_regex_parser.

This test suite demonstrates the bug where multi-line article descriptions
are not fully extracted. When an article's description spans 2-4 lines,
only the first line is captured.
"""
import sys
from pathlib import Path

# Add parent directory to path so we can import shared module
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.f3_regex_parser import extract_articles_regex


def test_two_line_article_description():
    """
    Test extraction of an article whose denomination spans two lines.

    Expected behavior: The denomination should include both lines,
    concatenated with a space.
    """
    lines = [
        "1",
        "VA02B08 - Prelucrare date si documentatie legata de",
        "relocare sarcini - intocmire si depunere documentatie la OJSC",
        "BUC",
        "1.0"
    ]

    articles = extract_articles_regex(lines, "OB1", "TEST_SECTION")

    assert len(articles) == 1, f"Expected 1 article, got {len(articles)}"
    article = articles[0]

    assert article['cod'] == "VA02B08", f"Expected code VA02B08, got {article['cod']}"

    # The full denomination should include both lines
    expected_denomination = (
        "Prelucrare date si documentatie legata de "
        "relocare sarcini - intocmire si depunere documentatie la OJSC"
    )
    assert article['denumire'] == expected_denomination, (
        f"Expected full denomination:\n'{expected_denomination}'\n"
        f"Got:\n'{article['denumire']}'"
    )

    assert article['um'] == "buc", f"Expected unit BUC, got {article['um']}"
    assert article['cantitate'] == 1.0, f"Expected quantity 1.0, got {article['cantitate']}"


def test_three_line_article_description():
    """
    Test extraction of an article whose denomination spans three lines.

    Expected behavior: The denomination should include all three lines,
    concatenated with spaces.
    """
    lines = [
        "1",
        "VA03K02 - Intocmire cu parere de especialist in domeniu privind",
        "evaluarea impactului asupra mediului - consultare publica -",
        "desfasurare procedura de informatii si consiliere",
        "BUC",
        "1.0"
    ]

    articles = extract_articles_regex(lines, "OB1", "TEST_SECTION")

    assert len(articles) == 1, f"Expected 1 article, got {len(articles)}"
    article = articles[0]

    assert article['cod'] == "VA03K02", f"Expected code VA03K02, got {article['cod']}"

    # The full denomination should include all three lines
    expected_denomination = (
        "Intocmire cu parere de especialist in domeniu privind "
        "evaluarea impactului asupra mediului - consultare publica - "
        "desfasurare procedura de informatii si consiliere"
    )
    assert article['denumire'] == expected_denomination, (
        f"Expected full denomination:\n'{expected_denomination}'\n"
        f"Got:\n'{article['denumire']}'"
    )

    assert article['um'] == "buc", f"Expected unit BUC, got {article['um']}"
    assert article['cantitate'] == 1.0, f"Expected quantity 1.0, got {article['cantitate']}"


def test_single_line_article_no_regression():
    """
    Regression test to ensure that single-line articles are still
    extracted correctly after fixing the multi-line bug.

    This test demonstrates that the fix should not break existing
    functionality for single-line articles.
    """
    lines = [
        "1",
        "VA01A01 - Servicii generale de consultanta",
        "BUC",
        "2.0",
        "2",
        "VA01A02 - Analiza situatiei existente",
        "BUC",
        "1.0"
    ]

    articles = extract_articles_regex(lines, "OB1", "TEST_SECTION")

    assert len(articles) == 2, f"Expected 2 articles, got {len(articles)}"

    # First article
    article1 = articles[0]
    assert article1['cod'] == "VA01A01", f"Expected code VA01A01, got {article1['cod']}"
    assert article1['denumire'] == "Servicii generale de consultanta", (
        f"Expected denomination 'Servicii generale de consultanta', "
        f"got '{article1['denumire']}'"
    )
    assert article1['um'] == "buc", f"Expected unit BUC, got {article1['um']}"
    assert article1['cantitate'] == 2.0, f"Expected quantity 2.0, got {article1['cantitate']}"

    # Second article
    article2 = articles[1]
    assert article2['cod'] == "VA01A02", f"Expected code VA01A02, got {article2['cod']}"
    assert article2['denumire'] == "Analiza situatiei existente", (
        f"Expected denomination 'Analiza situatiei existente', "
        f"got '{article2['denumire']}'"
    )
    assert article2['um'] == "buc", f"Expected unit BUC, got {article2['um']}"
    assert article2['cantitate'] == 1.0, f"Expected quantity 1.0, got {article2['cantitate']}"
