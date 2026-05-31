"""Tests for hierarchy_validator - validate corrected hierarchies against constraints."""
import pytest
from shared.hierarchy_analyzer import validate_hierarchy


def test_validate_hierarchy_valid():
    """Valid hierarchy with all constraints satisfied."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": "2", "is_component": True},
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is True
    assert result["error_count"] == 0
    assert result["errors"] == []


def test_validate_hierarchy_invalid_parent_not_found():
    """Invalid: parent_nr references non-existent parent."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": "NONEXISTENT", "is_component": False},
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is False
    assert result["error_count"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["error"] == "PARENT_NOT_FOUND"
    assert result["errors"][0]["nr"] == "2"


def test_validate_hierarchy_nesting_too_deep():
    """Invalid: nesting depth exceeds maximum (>2 dots)."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},
        {"nr": "1.1.1.1", "parent_nr": "1.1.1", "is_component": True},  # Too deep (3 dots)
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is False
    assert result["error_count"] == 1
    assert result["errors"][0]["error"] == "NESTING_TOO_DEEP"
    assert result["errors"][0]["nr"] == "1.1.1.1"


def test_validate_hierarchy_component_no_parent():
    """Invalid: component has no parent_nr after correction."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Component without parent
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is False
    assert result["error_count"] == 1
    assert result["errors"][0]["error"] == "COMPONENT_NO_PARENT"
    assert result["errors"][0]["nr"] == "2.1"


def test_validate_hierarchy_circular_reference():
    """Invalid: circular reference (A→B→C→A)."""
    articles = [
        {"nr": "1", "parent_nr": "3", "is_component": False},  # 1 → 3
        {"nr": "2", "parent_nr": "1", "is_component": False},  # 2 → 1
        {"nr": "3", "parent_nr": "2", "is_component": False},  # 3 → 2 (circular)
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is False
    assert result["error_count"] >= 1  # At least one circular reference detected
    assert any(e["error"] == "CIRCULAR_REFERENCE" for e in result["errors"])


def test_validate_hierarchy_multiple_errors():
    """Invalid: multiple errors in same hierarchy."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},
        {"nr": "1.1.1.1", "parent_nr": "1.1.1", "is_component": True},  # Error 1: nesting too deep
        {"nr": "2.1", "parent_nr": None, "is_component": True},  # Error 2: component no parent
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is False
    assert result["error_count"] == 2
    assert len(result["errors"]) == 2


def test_validate_hierarchy_empty_list():
    """Empty article list is valid."""
    result = validate_hierarchy([])

    assert result["is_valid"] is True
    assert result["error_count"] == 0
    assert result["errors"] == []


def test_validate_hierarchy_single_main_article():
    """Single main article (no components) is valid."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is True
    assert result["error_count"] == 0


def test_validate_hierarchy_max_nesting_allowed():
    """Max nesting (2 dots) is valid."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},  # Exactly 2 dots (allowed)
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is True
    assert result["error_count"] == 0


def test_validate_hierarchy_error_structure():
    """Error entries have required fields: index, nr, error."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "NONEXISTENT", "is_component": True},
    ]
    result = validate_hierarchy(articles)

    assert result["error_count"] == 1
    error = result["errors"][0]
    assert "index" in error
    assert "nr" in error
    assert "error" in error


def test_validate_hierarchy_complex_valid_structure():
    """Complex but valid structure with multiple groups and subcomponents."""
    articles = [
        {"nr": "1", "parent_nr": None, "is_component": False},
        {"nr": "1.1", "parent_nr": "1", "is_component": True},
        {"nr": "1.1.1", "parent_nr": "1.1", "is_component": True},
        {"nr": "1.2", "parent_nr": "1", "is_component": True},
        {"nr": "2", "parent_nr": None, "is_component": False},
        {"nr": "2.1", "parent_nr": "2", "is_component": True},
        {"nr": "2.1.1", "parent_nr": "2.1", "is_component": True},
        {"nr": "3", "parent_nr": None, "is_component": False},
    ]
    result = validate_hierarchy(articles)

    assert result["is_valid"] is True
    assert result["error_count"] == 0
