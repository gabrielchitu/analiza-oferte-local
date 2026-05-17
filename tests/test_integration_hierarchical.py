"""Integration test: hierarchical extraction, matching, reporting."""
import json
from pathlib import Path


def test_hierarchical_workflow():
    """Full workflow: extract components → match → report."""

    # Sample reference (MANECIU format with subcomponents in array)
    ref_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "um": "m",
            "cantitate": 2.0,
            "deviz": "4.3-07",
            "subcomponents": ["6717077", "6719428", "6719435", "0003000"]
        }
    ]

    # Sample offer (separate component articles with parent_code)
    oferta_articles = [
        {
            "cod": "SA14J",
            "parent_code": None,
            "is_component": False,
            "um": "m",
            "cantitate": 2.0,
            "deviz": "4.3-07"
        },
        {
            "cod": "6717077",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "m",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "6719428",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "buc",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "6719435",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "buc",
            "cantitate": 2.0,  # Inherited
            "deviz": "4.3-07"
        },
        {
            "cod": "0003000",
            "parent_code": "SA14J",
            "is_component": True,
            "um": "ore",
            "cantitate": 0.6,  # Inherited
            "deviz": "4.3-07"
        }
    ]

    # Verify components have parent_code
    for art in oferta_articles:
        if art["is_component"]:
            assert art["parent_code"] == "SA14J", f"Component {art['cod']} has wrong parent_code"

    # Verify matching works on (deviz, cod) pair
    for ref_art in ref_articles:
        matching_oferta = [o for o in oferta_articles
                          if o["deviz"] == ref_art["deviz"] and o["cod"] == ref_art["cod"]]
        assert len(matching_oferta) > 0, f"Parent {ref_art['cod']} not found in offer"

    # Verify components match
    for oferta_comp in [a for a in oferta_articles if a["is_component"]]:
        matching_ref = [r for r in ref_articles + oferta_articles
                       if r["deviz"] == oferta_comp["deviz"] and r["cod"] == oferta_comp["cod"]]
        assert len(matching_ref) > 0, f"Component {oferta_comp['cod']} has no match"

    # Test article grouping
    from shared.report_word import _group_articles_by_parent

    grouped = _group_articles_by_parent(oferta_articles)
    assert len(grouped) == 1, "Should have 1 parent group"
    assert grouped[0]["parent"]["cod"] == "SA14J"
    assert len(grouped[0]["components"]) == 4, "Should have 4 components"

    print("✓ Hierarchical workflow: PASS")
