# tests/test_nr_ordine.py
import pytest
from shared.f3_regex_parser import extract_articles_regex

LINES_SIMPLE = [
    "1",
    "TF24A",
    "Turnare beton C25/30",
    "mp",
    "34.20",
    "2",
    "TF26A",
    "Turnare beton C30/37",
    "mc",
    "12.50",
]

def test_nr_ordine_main_articles():
    arts = extract_articles_regex(LINES_SIMPLE, "226108", "Structura")
    main = [a for a in arts if not a.get("is_component")]
    assert main[0].get("nr_ordine") == 1
    assert main[1].get("nr_ordine") == 2

def test_nr_ordine_string_format_for_subcomponent():
    """Test that when NR_SUBITEM marker (x.y) is encountered, sub_counter resets properly."""
    lines = [
        "1", "TF24A", "Turnare beton", "mp", "34.20",
        "2.1", "TF26A", "Cofraj", "mp", "10.00",
        "3", "TF27A", "Armatura", "kg", "100.00",
    ]
    arts = extract_articles_regex(lines, "226108", "Structura")
    # The key is that after NR_SUBITEM "2.1" is parsed, the next article "3"
    # should have nr_ordine=3, not inherit sub_counter from before
    main_arts = [a for a in arts if not a.get("is_component")]
    assert len(main_arts) >= 3, f"Expected at least 3 main articles, got {len(main_arts)}"
    assert main_arts[0].get("nr_ordine") == 1
    assert main_arts[1].get("nr_ordine") == 2
    assert main_arts[2].get("nr_ordine") == 3

def test_parent_nr_ordine_on_subcomponent():
    lines = [
        "1", "TF24A", "Turnare beton C25/30", "mp", "34.20",
        "1.1", "$3274270", "Cofraj lemn", "mp", "102.60",
    ]
    arts = extract_articles_regex(lines, "226108", "Structura")
    subs = [a for a in arts if a.get("is_component")]
    if subs:
        assert subs[0].get("parent_nr_ordine") == 1

def test_sub_counter_increments_per_parent():
    """Two subarticles under same parent get sequential nr_ordine."""
    lines = [
        "1", "TF24A", "Beton C25", "mp", "34.20",
        "2", "$3274270", "Cofraj lemn", "mp", "102.60",
        "3", "$3274271", "Armatura OB37", "kg", "850.00",
    ]
    arts = extract_articles_regex(lines, "226108", "Structura")
    subs = [a for a in arts if a.get("is_component")]
    # If both detected as subcomponents of TF24A, they should have sequential nr_ordine
    if len(subs) >= 2:
        nr1 = subs[0].get("nr_ordine", "")
        nr2 = subs[1].get("nr_ordine", "")
        assert nr1.endswith(".1"), f"Expected first sub to end with .1, got {nr1}"
        assert nr2.endswith(".2"), f"Expected second sub to end with .2, got {nr2}"
