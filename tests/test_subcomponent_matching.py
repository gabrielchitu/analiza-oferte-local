import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from AgentComparator_local import _should_match_cant_um


def test_strict_mode_requires_cant_um():
    """In strict mode, _should_match_cant_um always returns True."""
    ref_article = {
        'cod': '$3274532',
        'cantitate': 34.5,
        'um': 'kg',
        'is_component': True
    }

    # In strict mode, should always validate cant+UM
    assert _should_match_cant_um(ref_article, comp_mode='strict') == True


def test_lenient_mode_skips_cant_um_for_incomplete_subcomponent():
    """In lenient mode, incomplete subcomponents return False for _should_match_cant_um."""
    ref_article = {
        'cod': '$3274532',
        'cantitate': 0,  # Missing quantity
        'um': '',  # Missing UM
        'is_component': True
    }

    # In lenient mode, incomplete subcomponents skip cant+UM validation
    assert _should_match_cant_um(ref_article, comp_mode='lenient') == False


def test_lenient_mode_validates_complete_articles():
    """In lenient mode, complete articles still validate cant+UM."""
    article = {
        'cod': 'ACD04C1',
        'cantitate': 7.0,
        'um': 'bucata',
        'is_component': False
    }

    # Regular articles always validate cant+UM
    assert _should_match_cant_um(article, comp_mode='lenient') == True


def test_lenient_mode_handles_subcomponent_with_partial_data():
    """In lenient mode, subcomponent with partial data (has UM but no cant) skips validation."""
    article = {
        'cod': '17.L',
        'cantitate': 0,  # Missing
        'um': 'mp',  # Has UM
        'is_component': True
    }

    # Subcomponent with missing cant should return False (skip validation)
    assert _should_match_cant_um(article, comp_mode='lenient') == False


if __name__ == "__main__":
    test_strict_mode_requires_cant_um()
    test_lenient_mode_skips_cant_um_for_incomplete_subcomponent()
    test_lenient_mode_validates_complete_articles()
    test_lenient_mode_handles_subcomponent_with_partial_data()
    print("All tests passed!")
