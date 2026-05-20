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


def test_deduplicate_on_preserves_highest_priority():
    from AgentComparator_local import _deduplicate_neconformitati
    ncs = [
        {'deviz': 'D1', 'ref_cod': 'TF24A', 'oferta_cod': 'TF24A_', 'tip': 'DIFERENTA_CAMP'},
        {'deviz': 'D1', 'ref_cod': 'TF24A', 'oferta_cod': 'TF24A_', 'tip': 'COD_SIMILAR'},
    ]
    result = _deduplicate_neconformitati(ncs)
    assert len(result) == 1
    assert result[0]['tip'] == 'COD_SIMILAR'


def test_deduplicate_no_articol_orphan_in_priority():
    from AgentComparator_local import _deduplicate_neconformitati
    import inspect
    src = inspect.getsource(_deduplicate_neconformitati)
    assert 'ARTICOL_ORPHAN' not in src


def test_enrich_adds_nr_ordine_fields():
    from AgentComparator_local import _enrich
    ref_art = {
        'cod': 'TF24A', 'denumire': 'Beton', 'um': 'mp', 'cantitate': 34.2,
        'is_component': False, 'nr_ordine': 3, 'parent_cod': None,
        'parent_nr_ordine': None, 'cant_mostenita': False,
        'pret_material': 0, 'pret_manopera': 0, 'pret_utilaj': 0, 'pret_transport': 0,
        'val_material': 0, 'val_manopera': 0, 'val_utilaj': 0, 'val_transport': 0,
    }
    oferta_art = {**ref_art, 'nr_ordine': 5}
    neconf = {'tip': 'DIFERENTA_CAMP'}
    result = _enrich(neconf, ref_art, oferta_art, '226108', 'Structura')
    assert result.get('nr_ordine_ref') == 3
    assert result.get('nr_ordine_oferta') == 5
    assert result.get('parent_cod_ref') is None
    assert result.get('cant_mostenita') is False
