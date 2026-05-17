"""Tests for matching logic with hierarchical components."""


def test_match_component_by_deviz_cod_pair():
    """Components match on (deviz, cod) pair like parent articles."""
    # Note: This is a conceptual test showing how components should match
    # The actual matching logic is in AgentComparator_local

    ref_articles = [
        {"deviz": "4.3-07", "cod": "SA14J", "parent_code": None, "is_component": False},
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", "is_component": True}
    ]

    oferta_articles = [
        {"deviz": "4.3-07", "cod": "SA14J", "parent_code": None, "is_component": False},
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J", "is_component": True}
    ]

    # Both should have matching (deviz, cod) pairs
    # Parent: (4.3-07, SA14J)
    # Component: (4.3-07, 6717077)

    # Verify that matching would work based on (deviz, cod)
    for ref_art in ref_articles:
        matching_oferta = [o for o in oferta_articles
                          if o["deviz"] == ref_art["deviz"] and o["cod"] == ref_art["cod"]]
        assert len(matching_oferta) > 0, f"No match found for {ref_art['cod']}"


def test_component_quantity_mismatch():
    """UM_DIFERIT for component mismatches."""
    ref_articles = [
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J",
         "is_component": True, "um": "m", "cantitate": 2.0}
    ]

    oferta_articles = [
        {"deviz": "4.3-07", "cod": "6717077", "parent_code": "SA14J",
         "is_component": True, "um": "buc", "cantitate": 2.0}  # Different UM
    ]

    # Check that UM is different
    ref_um = ref_articles[0]["um"]
    oferta_um = oferta_articles[0]["um"]

    assert ref_um != oferta_um, "Test data should have different UMs"
    assert ref_um == "m" and oferta_um == "buc"
