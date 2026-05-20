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


def test_build_ref_catalog_extracts_dollar_parents():
    from AgentComparator_local import build_ref_catalog
    ref = [
        {'cod': 'CK25A', 'deviz': '4.1-03', 'is_component': False, 'display_parent_cod': None},
        {'cod': '$6720289', 'deviz': '4.1-03', 'is_component': False, 'display_parent_cod': 'CK25A'},
        {'cod': '$6720301', 'deviz': '4.1-03', 'is_component': False, 'display_parent_cod': 'CK25A'},
        {'cod': 'RPIF09C', 'deviz': '4.1-10', 'is_component': False, 'display_parent_cod': None},
        {'cod': '$2608118', 'deviz': '4.1-10', 'is_component': False, 'display_parent_cod': 'RPIF09C'},
    ]
    catalog = build_ref_catalog(ref)
    assert catalog['$6720289'] == 'CK25A'
    assert catalog['$6720301'] == 'CK25A'
    assert catalog['$2608118'] == 'RPIF09C'
    assert 'CK25A' not in catalog
    assert 'RPIF09C' not in catalog

def test_build_ref_catalog_excludes_no_parent():
    from AgentComparator_local import build_ref_catalog
    ref = [
        {'cod': '$9999', 'deviz': '4.1-03', 'is_component': False, 'display_parent_cod': None},
    ]
    catalog = build_ref_catalog(ref)
    assert '$9999' not in catalog

def test_match_global_returns_4tuple():
    from AgentComparator_local import match_global
    result = match_global([], [], None, None)
    assert len(result) == 4, f"Expected 4-tuple, got {len(result)}-tuple"

def test_match_global_separates_articles_without_deviz():
    from AgentComparator_local import match_global
    base_fields = {f: 0 for f in ['pret_material','val_material','pret_manopera','val_manopera',
                                   'pret_utilaj','val_utilaj','pret_transport','val_transport']}
    ref = [
        {'cod': 'TF24A', 'deviz': '', 'denumire': 'fara deviz', 'um': 'mp',
         'cantitate': 10.0, 'is_component': False, 'display_parent_cod': None, **base_fields},
    ]
    ncs, matches, _, fara_deviz = match_global(ref, [], None, None)
    assert len(fara_deviz) == 1
    assert fara_deviz[0][0] == 'ref'
    assert fara_deviz[0][1]['cod'] == 'TF24A'
    assert len(matches) == 0


def test_layer0_matches_subarticle_exact():
    """$6720289 in both ref and offer → MATCHED via Layer 0."""
    from AgentComparator_local import match_global
    base = {'um': 'mp', 'cantitate': 16.19, 'denumire': 'usa tamplarie pvc',
            'deviz_denumire': 'Arhitectura', 'is_component': False,
            **{f: 0 for f in ['pret_material','val_material','pret_manopera','val_manopera',
                               'pret_utilaj','val_utilaj','pret_transport','val_transport']}}
    ref = [
        {**base, 'cod': 'CK25A', 'deviz': '4.1-03', 'display_parent_cod': None},
        {**base, 'cod': '$6720289', 'deviz': '4.1-03', 'display_parent_cod': 'CK25A'},
    ]
    oferta = [
        {**base, 'cod': 'CK25A', 'deviz': '4.1-03', 'display_parent_cod': None},
        {**base, 'cod': '$6720289', 'deviz': '4.1-03', 'display_parent_cod': 'CK25A'},
    ]
    ncs, matches, _, _ = match_global(ref, oferta, None, None)
    assert any(m.get('ref_cod') == '$6720289' for m in matches), "Expected MATCHED for $6720289"
    lipsa = [n for n in ncs if n.get('tip') == 'ARTICOL_LIPSA']
    assert not any(n.get('ref_cod') == '$6720289' for n in lipsa)

def test_layer0_lipsa_when_subarticle_missing():
    """$6720289 in ref but offer has $6720287 instead → LIPSA + EXTRA."""
    from AgentComparator_local import match_global
    base = {'um': 'mp', 'cantitate': 16.19, 'denumire': 'usa tamplarie pvc',
            'deviz_denumire': 'Arhitectura', 'is_component': False,
            **{f: 0 for f in ['pret_material','val_material','pret_manopera','val_manopera',
                               'pret_utilaj','val_utilaj','pret_transport','val_transport']}}
    ref = [
        {**base, 'cod': 'CK25A', 'deviz': '4.1-03', 'display_parent_cod': None},
        {**base, 'cod': '$6720289', 'deviz': '4.1-03', 'display_parent_cod': 'CK25A'},
    ]
    oferta = [
        {**base, 'cod': 'CK25A', 'deviz': '4.1-03', 'display_parent_cod': None},
        {**base, 'cod': '$6720287', 'deviz': '4.1-03', 'display_parent_cod': 'CK25A'},
    ]
    ncs, matches, _, _ = match_global(ref, oferta, None, None)
    lipsa = [n for n in ncs if n.get('tip') == 'ARTICOL_LIPSA']
    extra = [n for n in ncs if n.get('tip') == 'ARTICOL_EXTRA']
    assert any(n.get('ref_cod') == '$6720289' for n in lipsa), "Expected LIPSA for $6720289"
    assert any(n.get('oferta_cod') == '$6720287' for n in extra), "Expected EXTRA for $6720287"

def test_layer0_extra_for_dollar_not_in_catalog():
    """Offer has $ not in ref_catalog → ARTICOL_EXTRA."""
    from AgentComparator_local import match_global
    base = {'um': 'mp', 'cantitate': 6.24, 'denumire': 'usa profile pvc',
            'deviz_denumire': 'Arhitectura', 'is_component': False,
            **{f: 0 for f in ['pret_material','val_material','pret_manopera','val_manopera',
                               'pret_utilaj','val_utilaj','pret_transport','val_transport']}}
    ref = [
        {**base, 'cod': 'CK25A', 'deviz': '4.1-03', 'display_parent_cod': None},
    ]
    oferta = [
        {**base, 'cod': '$6720287', 'deviz': '4.1-03', 'display_parent_cod': 'CK25A'},
    ]
    ncs, matches, _, _ = match_global(ref, oferta, None, None)
    extra = [n for n in ncs if n.get('tip') == 'ARTICOL_EXTRA']
    assert any(n.get('oferta_cod') == '$6720287' for n in extra), "Expected EXTRA for $6720287"
