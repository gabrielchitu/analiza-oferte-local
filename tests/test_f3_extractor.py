"""Integration tests for f3_extractor with hierarchical component support."""
from shared import f3_extractor


def test_component_inherits_quantity_from_parent():
    """Component article inherits quantity from parent when not explicit."""
    ref_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "cantitate": 2.0
        },
        {
            "cod": "6717077",
            "parent_code": "SA14J",
            "is_component": True,
            "cantitate": 0.0  # No explicit quantity
        }
    ]

    # Apply inheritance
    result = f3_extractor.inherit_component_quantities(ref_articles)

    # Component should now have parent's quantity
    component = [a for a in result if a["cod"] == "6717077"][0]
    assert component["cantitate"] == 2.0


def test_component_inherits_unit_from_parent():
    """Component inherits unit from parent if not explicit."""
    articles = [
        {"cod": "SA14J", "parent_code": None, "is_component": False, "um": "m"},
        {"cod": "6717077", "parent_code": "SA14J", "is_component": True, "um": ""}
    ]

    result = f3_extractor.inherit_component_units(articles)
    component = [a for a in result if a["cod"] == "6717077"][0]
    assert component["um"] == "m"


def test_source_pages_propagated():
    """Articolele extrase dintr-un deviz au source_pages din paginile fizice."""
    from shared.f3_extractor import extract_articles_v3

    # Use realistic multi-line format matching the F3 structure
    page_classifications = [
        {
            "is_f3": True, "deviz_cod": "1-01", "deviz_den": "STRUCTURA",
            "lines": [
                "Nr.",
                "1", "EA02A1", "buc", "1.0", "10.0", "10.0",
                "MONTAJ STRUCTURA", "", "", "2.0", "2.0",
                "", "", "", "", "15.0",
            ],
            "page_number": 12, "header_only": False,
        },
        {
            "is_f3": True, "deviz_cod": "1-01", "deviz_den": "STRUCTURA",
            "lines": [
                "Nr.",
                "2", "CA01A", "mp", "10.0", "5.0", "50.0",
                "TENCUIALA", "", "", "1.0", "10.0",
                "", "", "", "", "65.0",
            ],
            "page_number": 13, "header_only": False,
        },
    ]
    articles = extract_articles_v3(page_classifications)
    assert len(articles) > 0, "Should extract articles"
    for art in articles:
        assert "source_pages" in art, f"Article {art.get('cod')} missing source_pages"
        assert 12 in art["source_pages"] or 13 in art["source_pages"], \
            f"Article {art.get('cod')} source_pages {art['source_pages']} should contain page 12 or 13"


def test_f3_line_end_limits_extraction():
    """Daca pagina are f3_line_end, extragerea respecta limita."""
    from shared.f3_extractor import extract_articles_v3

    page_classifications = [
        {
            "is_f3": True, "deviz_cod": "2-01", "deviz_den": "TEST",
            "lines": [
                "Nr.",
                "1", "EA02A1", "buc", "1.0", "10.0", "10.0",
                "MONTAJ TEST", "", "", "2.0", "2.0",
                "", "", "", "", "15.0",
                "TOTAL CHELT. DIRECTE",
                "Cheltuieli indirecte",
            ],
            "page_number": 5, "header_only": False,
            "f3_line_end": 14,  # opreste la linia 14 (exclusiv)
        },
    ]
    articles = extract_articles_v3(page_classifications)
    # Articolul EA02A1 trebuie extras (e inainte de f3_line_end=14)
    # Liniile dupa f3_line_end (TOTAL CHELT. DIRECTE, Cheltuieli indirecte) NU sunt procesate
    cods = [a.get("cod", "") for a in articles]
    assert any("EA02A1" in c for c in cods), f"EA02A1 not found in {cods}"
    # Verify source_pages is set
    for art in articles:
        assert "source_pages" in art, f"Article {art.get('cod')} missing source_pages"
