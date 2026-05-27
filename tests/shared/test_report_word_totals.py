import pytest
from shared.report_word import _count_main_articles


def test_count_main_articles_empty():
    assert _count_main_articles([]) == 0


def test_count_main_articles_all_main():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A02"},  # missing key → not a component
        {"cod": "A03", "is_component": False},
    ]
    assert _count_main_articles(articles) == 3


def test_count_main_articles_filters_components():
    articles = [
        {"cod": "A01", "is_component": False},
        {"cod": "A01-sub1", "is_component": True},
        {"cod": "A01-sub2", "is_component": True},
        {"cod": "A02", "is_component": False},
    ]
    assert _count_main_articles(articles) == 2


def test_count_main_articles_all_components():
    articles = [
        {"cod": "X01", "is_component": True},
        {"cod": "X02", "is_component": True},
    ]
    assert _count_main_articles(articles) == 0
