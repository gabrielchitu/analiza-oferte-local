import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.f3_page_classifier import _extract_compound_deviz


def test_extract_explicit_deviz_oferta():
    """Test extraction of explicit 'Deviz Oferta' code (highest priority)."""
    lines = [
        "Formular F3",
        "Deviz oferta 226238 MONTAT BOILER",
        "Obiectul: 4.1",
        "Categoria de lucrari: 03"
    ]

    cod, meta = _extract_compound_deviz(lines)

    assert cod == "226238", f"Expected '226238', got '{cod}'"
    assert meta["extraction_method"] == "explicit"
    assert meta["source"] == "Deviz Oferta"


def test_extract_compound_deviz():
    """Test extraction of compound Obiectul-Categoria code."""
    lines = [
        "Formular F3",
        "OBIECTIV: 01 CRESTERE EFICIENTEI",
        "Obiectul: 4.1 Cladire camin",
        "Categoria de lucrari: 03 Arhitectura - eligibile tip I"
    ]

    cod, meta = _extract_compound_deviz(lines)

    assert cod == "4.1-03", f"Expected '4.1-03', got '{cod}'"
    assert meta["extraction_method"] == "compound"
    assert meta["obiectul"]["number"] == "4.1"
    assert meta["categoria"]["number"] == "03"


def test_extract_compound_with_stadiul_fizic():
    """Test compound extraction using Stadiul fizic instead of Categoria."""
    lines = [
        "Formular F3",
        "Obiectul: 0002",
        "Stadiul fizic: 0120 VESTIAR TEREN"
    ]

    cod, meta = _extract_compound_deviz(lines)

    assert cod == "0002-0120", f"Expected '0002-0120', got '{cod}'"
    assert meta["extraction_method"] == "compound"


def test_no_deviz_found():
    """Test graceful fallback when no deviz code found."""
    lines = [
        "Some random text",
        "No deviz codes here",
        "Just article descriptions"
    ]

    cod, meta = _extract_compound_deviz(lines)

    assert cod == "", f"Expected empty string, got '{cod}'"
    assert meta["extraction_method"] == "none"


def test_partial_compound_no_category():
    """Test that partial compound (only Obiectul) returns empty."""
    lines = [
        "Obiectul: 4.1 Cladire camin",
        "Some text without Categoria"
    ]

    cod, meta = _extract_compound_deviz(lines)

    # Should return empty since both components required
    assert cod == "", f"Expected empty, got '{cod}'"


def test_deviz_oferta_priority_over_compound():
    """Test that explicit Deviz Oferta takes priority over compound."""
    lines = [
        "Deviz oferta 226238 BOILER",
        "Obiectul: 4.1",
        "Categoria: 03"
    ]

    cod, meta = _extract_compound_deviz(lines)

    # Should use explicit code, not compound
    assert cod == "226238"
    assert meta["extraction_method"] == "explicit"


if __name__ == "__main__":
    test_extract_explicit_deviz_oferta()
    test_extract_compound_deviz()
    test_extract_compound_with_stadiul_fizic()
    test_no_deviz_found()
    test_partial_compound_no_category()
    test_deviz_oferta_priority_over_compound()
    print("All tests passed!")
