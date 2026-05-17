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
