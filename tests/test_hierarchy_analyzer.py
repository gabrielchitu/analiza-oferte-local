"""Tests for hierarchy_analyzer - detect and fix broken parent-child relationships."""
import pytest
from shared.hierarchy_analyzer import detect_broken_hierarchy, fix_hierarchy_ffill


def test_detect_broken_hierarchy_missing_parent():
    """Detect component articles with no parent_nr."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # BROKEN: no parent_nr
    ]
    issues = detect_broken_hierarchy(articles)

    assert len(issues) == 1
    assert issues[0]["nr"] == "2.1"
    assert issues[0]["issue"] == "MISSING_PARENT"


def test_detect_broken_hierarchy_nonexistent_parent():
    """Detect articles whose parent_nr references a non-existent parent."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "3", "parent_nr": "NONEXISTENT", "is_component": False},  # BROKEN
    ]
    issues = detect_broken_hierarchy(articles)

    assert len(issues) == 1
    assert issues[0]["nr"] == "3"
    assert issues[0]["issue"] == "NONEXISTENT_PARENT"
    assert issues[0]["parent_nr"] == "NONEXISTENT"


def test_detect_broken_hierarchy_multiple_issues():
    """Detect multiple issues in same article list."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Issue 1: MISSING_PARENT
        {"nr": "3", "parent_nr": "NONEXISTENT", "is_component": False},  # Issue 2: NONEXISTENT_PARENT
    ]
    issues = detect_broken_hierarchy(articles)

    assert len(issues) == 2
    issue_types = {issue["issue"] for issue in issues}
    assert issue_types == {"MISSING_PARENT", "NONEXISTENT_PARENT"}


def test_detect_broken_hierarchy_no_issues():
    """Return empty list when hierarchy is valid."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": "2", "is_component": True},
    ]
    issues = detect_broken_hierarchy(articles)

    assert len(issues) == 0


def test_detect_broken_hierarchy_empty_list():
    """Handle empty article list gracefully."""
    issues = detect_broken_hierarchy([])
    assert len(issues) == 0


def test_fix_hierarchy_ffill_basic():
    """Fix missing parent_nr using forward fill."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},  # Inherit parent from 1.1
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Inherit parent from 2
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Check that 1.2 got parent_nr=1
    art_1_2 = [a for a in fixed if a["nr"] == "1.2"][0]
    assert art_1_2["parent_nr"] == "1"
    assert art_1_2["hierarchy_corrected"] is True

    # Check that 2.1 got parent_nr=2
    art_2_1 = [a for a in fixed if a["nr"] == "2.1"][0]
    assert art_2_1["parent_nr"] == "2"
    assert art_2_1["hierarchy_corrected"] is True


def test_fix_hierarchy_ffill_marks_corrected():
    """Mark articles that were fixed with hierarchy_corrected flag."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    # 1 and 1.1 should not be marked corrected
    art_1 = [a for a in fixed if a["nr"] == "1"][0]
    assert art_1["hierarchy_corrected"] is False

    art_1_1 = [a for a in fixed if a["nr"] == "1.1"][0]
    assert art_1_1["hierarchy_corrected"] is False

    # 1.2 should be marked corrected
    art_1_2 = [a for a in fixed if a["nr"] == "1.2"][0]
    assert art_1_2["hierarchy_corrected"] is True


def test_fix_hierarchy_ffill_preserves_valid_parents():
    """Don't change valid parent references."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    for article in fixed:
        # All should have hierarchy_corrected=False
        assert article["hierarchy_corrected"] is False


def test_fix_hierarchy_ffill_handles_gaps():
    """Handle gaps in component sequences correctly."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.2", "parent_nr": None, "is_component": True},  # Gap in numbering
        {"nr": "2.3", "parent_nr": None, "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Check 2.2 and 2.3 got parent_nr=2
    art_2_2 = [a for a in fixed if a["nr"] == "2.2"][0]
    assert art_2_2["parent_nr"] == "2"

    art_2_3 = [a for a in fixed if a["nr"] == "2.3"][0]
    assert art_2_3["parent_nr"] == "2"


def test_fix_hierarchy_ffill_no_changes_needed():
    """When no changes needed, still add hierarchy_corrected flag."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Both should have hierarchy_corrected flag
    for article in fixed:
        assert "hierarchy_corrected" in article


def test_fix_hierarchy_ffill_empty_list():
    """Handle empty article list gracefully."""
    fixed = fix_hierarchy_ffill([])
    assert len(fixed) == 0


def test_fix_hierarchy_ffill_complex_scenario():
    """Test complex multi-level scenario."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": None, "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": None, "is_component": True},
        {"nr": "2.2", "parent_nr": "2", "is_component": True},
        {"nr": "2.3", "parent_nr": None, "is_component": True},
    ]
    fixed = fix_hierarchy_ffill(articles)

    # Check results
    art_1_2 = [a for a in fixed if a["nr"] == "1.2"][0]
    assert art_1_2["parent_nr"] == "1"
    assert art_1_2["hierarchy_corrected"] is True

    art_2_1 = [a for a in fixed if a["nr"] == "2.1"][0]
    assert art_2_1["parent_nr"] == "2"
    assert art_2_1["hierarchy_corrected"] is True

    art_2_3 = [a for a in fixed if a["nr"] == "2.3"][0]
    assert art_2_3["parent_nr"] == "2"
    assert art_2_3["hierarchy_corrected"] is True

    # 2.2 should keep original parent
    art_2_2 = [a for a in fixed if a["nr"] == "2.2"][0]
    assert art_2_2["parent_nr"] == "2"
    assert art_2_2["hierarchy_corrected"] is False
