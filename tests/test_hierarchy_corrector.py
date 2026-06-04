"""Tests for hierarchy corrector with group-aware ffill.

This module tests the enhanced fix_hierarchy_ffill function that handles
group boundaries correctly, ensuring components don't inherit parents from
other groups.
"""

import pytest
from shared.hierarchy_analyzer import fix_hierarchy_ffill


def test_fix_hierarchy_ffill_group_aware():
    """Test that ffill resets at group boundaries (new main articles).

    When a new main article (is_component=False, parent_nr=None) is encountered,
    the parent context should reset. Components after it should inherit the new
    main article's NR as parent, not the previous group's parent.
    """
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},  # Should ffill to "1"
        {"nr": "2", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY: reset context
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Should ffill to "2", NOT "1"
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Find articles by nr
    art_1_2 = [a for a in fixed if a["nr"] == "1.2"][0]
    art_2_1 = [a for a in fixed if a["nr"] == "2.1"][0]

    # 1.2 should inherit from group 1
    assert art_1_2["parent_nr"] == "1", "Component 1.2 should inherit parent from group 1"
    assert art_1_2["hierarchy_corrected"] is True

    # 2.1 should inherit from group 2, NOT from group 1
    assert art_2_1["parent_nr"] == "2", "Component 2.1 should inherit parent from group 2, not group 1"
    assert art_2_1["hierarchy_corrected"] is True


def test_fix_hierarchy_ffill_multi_group_complex():
    """Test group-aware ffill with multiple groups and mixed valid/invalid parents."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},  # Missing parent
        {"nr": "1.3", "parent_nr": "1", "is_component": True},   # Valid parent
        {"nr": "2", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Missing parent
        {"nr": "2.2", "parent_nr": None, "is_component": True},  # Missing parent
        {"nr": "3", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY
        {"nr": "3.1", "parent_nr": None, "is_component": True},  # Missing parent
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Group 1
    assert [a for a in fixed if a["nr"] == "1.2"][0]["parent_nr"] == "1"
    assert [a for a in fixed if a["nr"] == "1.3"][0]["parent_nr"] == "1"

    # Group 2
    assert [a for a in fixed if a["nr"] == "2.1"][0]["parent_nr"] == "2"
    assert [a for a in fixed if a["nr"] == "2.2"][0]["parent_nr"] == "2"

    # Group 3
    assert [a for a in fixed if a["nr"] == "3.1"][0]["parent_nr"] == "3"


def test_fix_hierarchy_ffill_component_with_explicit_parent():
    """Test that explicit parent_nr is preserved across group boundaries."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY
        {"nr": "2.1", "parent_nr": "1", "is_component": True},  # Explicit parent to previous group
    ]
    fixed = fix_hierarchy_ffill(articles)

    # 2.1 has explicit parent_nr="1", should NOT be changed
    art_2_1 = [a for a in fixed if a["nr"] == "2.1"][0]
    assert art_2_1["parent_nr"] == "1"
    assert art_2_1["hierarchy_corrected"] is False


def test_fix_hierarchy_ffill_consecutive_components_same_group():
    """Test that consecutive components in same group all inherit correct parent."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},
        {"nr": "1.3", "parent_nr": None, "is_component": True},
        {"nr": "1.4", "parent_nr": None, "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    # All components should inherit from parent "1"
    for nr in ["1.2", "1.3", "1.4"]:
        art = [a for a in fixed if a["nr"] == nr][0]
        assert art["parent_nr"] == "1", f"Component {nr} should inherit parent from group 1"
        assert art["hierarchy_corrected"] is True


def test_fix_hierarchy_ffill_single_component_per_group():
    """Test single missing-parent component in each group."""
    articles = [
        {"nr": "A", "parent_nr": None, "is_component": False},
        {"nr": "A.1", "parent_nr": None, "is_component": True},  # Missing parent
        {"nr": "B", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY
        {"nr": "B.1", "parent_nr": None, "is_component": True},  # Missing parent
        {"nr": "C", "parent_nr": None, "is_component": False},   # GROUP BOUNDARY
        {"nr": "C.1", "parent_nr": None, "is_component": True},  # Missing parent
    ]
    fixed = fix_hierarchy_ffill(articles)

    assert [a for a in fixed if a["nr"] == "A.1"][0]["parent_nr"] == "A"
    assert [a for a in fixed if a["nr"] == "B.1"][0]["parent_nr"] == "B"
    assert [a for a in fixed if a["nr"] == "C.1"][0]["parent_nr"] == "C"


def test_fix_hierarchy_ffill_main_with_explicit_parent():
    """Test main article with explicit parent_nr sets correct context.

    When a main article (is_component=False) has an explicit parent_nr,
    it should become the context for following components.
    """
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "X", "parent_nr": "PARENT_X", "is_component": False},  # Main with explicit parent
        {"nr": "X.1", "parent_nr": None, "is_component": True},  # Should inherit from PARENT_X
    ]
    fixed = fix_hierarchy_ffill(articles)

    # X keeps explicit parent
    art_x = [a for a in fixed if a["nr"] == "X"][0]
    assert art_x["parent_nr"] == "PARENT_X"
    assert art_x["hierarchy_corrected"] is False

    # X.1 should inherit PARENT_X (the explicit parent of its main article)
    art_x_1 = [a for a in fixed if a["nr"] == "X.1"][0]
    assert art_x_1["parent_nr"] == "PARENT_X"
    assert art_x_1["hierarchy_corrected"] is True
