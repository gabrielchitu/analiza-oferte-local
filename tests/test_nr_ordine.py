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

def test_nr_ordine_none_for_subcomponent():
    lines = LINES_SIMPLE + [
        "3",
        "$3274270",
        "Cofraj lemn",
        "mp",
        "102.60",
    ]
    arts = extract_articles_regex(lines, "226108", "Structura")
    subs = [a for a in arts if a.get("is_component")]
    if subs:
        assert isinstance(subs[0].get("nr_ordine"), str)

def test_parent_nr_ordine_on_subcomponent():
    lines = [
        "1", "TF24A", "Turnare beton C25/30", "mp", "34.20",
        "1.1", "$3274270", "Cofraj lemn", "mp", "102.60",
    ]
    arts = extract_articles_regex(lines, "226108", "Structura")
    subs = [a for a in arts if a.get("is_component")]
    if subs:
        assert subs[0].get("parent_nr_ordine") == 1
