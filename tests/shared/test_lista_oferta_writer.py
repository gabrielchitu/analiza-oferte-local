import pytest
from shared.lista_oferta_writer import extract_entity_name, _iter_source_groups
import json
import tempfile
import os


def _make_di(pages_lines):
    """Helper: write temp di_*.json and return path."""
    data = {
        "pages": [
            {"page_number": i + 1, "lines": lines}
            for i, lines in enumerate(pages_lines)
        ],
        "tables": [],
    }
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, f)
    f.close()
    return f.name


def test_extract_ofertant_found():
    path = _make_di(
        [
            [
                {"content": "Formularul F3"},
                {"content": "CONTRACTANT (OFERTANT)"},
                {"content": "SC. KATO SERVICE SRL"},
            ]
        ]
    )
    try:
        assert extract_entity_name(path, is_referinta=False) == "SC. KATO SERVICE SRL"
    finally:
        os.unlink(path)


def test_extract_ofertant_skips_bare_srl():
    path = _make_di(
        [
            [
                {"content": "CONTRACTANT (OFERTANT)"},
                {"content": "SRL"},
                {"content": "SC. REAL COMPANY SRL"},
            ]
        ]
    )
    try:
        assert extract_entity_name(path, is_referinta=False) == "SC. REAL COMPANY SRL"
    finally:
        os.unlink(path)


def test_extract_proiectant_found():
    path = _make_di(
        [
            [
                {"content": "PROIECTANT"},
                {"content": "SC. ARHI DESIGN SRL"},
            ]
        ]
    )
    try:
        assert extract_entity_name(path, is_referinta=True) == "SC. ARHI DESIGN SRL"
    finally:
        os.unlink(path)


def test_extract_fallback_when_not_found():
    path = _make_di([[{"content": "Random text"}]])
    try:
        assert extract_entity_name(path, is_referinta=False) == "Necunoscut"
    finally:
        os.unlink(path)


def test_extract_searches_only_first_5_pages():
    # Marker on page 6 — should not be found
    pages = [[{"content": "nothing"}]] * 5 + [
        [
            {"content": "CONTRACTANT (OFERTANT)"},
            {"content": "SC. LATE SRL"},
        ]
    ]
    path = _make_di(pages)
    try:
        assert extract_entity_name(path, is_referinta=False) == "Necunoscut"
    finally:
        os.unlink(path)


# Tests for _iter_source_groups
def _make_article(cod="TST01", nr_ordine=1, is_component=False, parent_code=None, deviz_header=None):
    return {
        "cod": cod, "denumire": "Test article", "um": "mc", "cantitate": 1.0,
        "nr_ordine": nr_ordine, "is_component": is_component, "parent_code": parent_code,
        "pret_material": 0.0, "pret_manopera": 0.0, "pret_utilaj": 0.0, "pret_transport": 0.0,
        "val_material": 0.0, "val_manopera": 0.0, "val_utilaj": 0.0, "val_transport": 0.0,
        "deviz_header": deviz_header or {"obiectivul": "OBJ", "obiectul": "OBL", "categoria": "CAT"},
    }


def test_iter_source_groups_oferta():
    art = _make_article("TST01")
    holistic = {
        "matched_groups": [{"oferta_articles": [art], "ref_articles": [], "deviz_denumire": "A|B|C"}],
        "oferta_only_groups": [],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 1
    header, articles = groups[0]
    assert header["obiectivul"] == "OBJ"
    assert articles[0]["cod"] == "TST01"


def test_iter_source_groups_referinta():
    art = _make_article("REF01", deviz_header={"obiectivul": "R", "obiectul": "RL", "categoria": "RC"})
    holistic = {
        "matched_groups": [{"ref_articles": [art], "oferta_articles": [], "deviz_denumire": "R|RL|RC"}],
        "ref_only_groups": [],
        "oferta_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="referinta"))
    assert len(groups) == 1
    header, articles = groups[0]
    assert header["obiectivul"] == "R"
    assert articles[0]["cod"] == "REF01"


def test_iter_source_groups_includes_only_groups():
    art = _make_article("ONLY01", deviz_header={"obiectivul": "X", "obiectul": "Y", "categoria": "Z"})
    holistic = {
        "matched_groups": [],
        "oferta_only_groups": [{"articles": [art], "deviz_denumire": "X|Y|Z"}],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 1
    _, articles = groups[0]
    assert articles[0]["cod"] == "ONLY01"


def test_iter_source_groups_skips_empty_article_groups():
    holistic = {
        "matched_groups": [{"oferta_articles": [], "ref_articles": [], "deviz_denumire": "A|B|C"}],
        "oferta_only_groups": [],
        "ref_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="oferta"))
    assert len(groups) == 0


def test_iter_source_groups_fallback_header_from_deviz_denumire():
    """When articles list is empty but group exists via only_groups with no deviz_header on art."""
    art = {"cod": "X", "denumire": "D", "um": "mc", "cantitate": 1.0,
           "nr_ordine": 1, "is_component": False, "parent_code": None,
           "pret_material": 0.0, "pret_manopera": 0.0, "pret_utilaj": 0.0, "pret_transport": 0.0,
           "val_material": 0.0, "val_manopera": 0.0, "val_utilaj": 0.0, "val_transport": 0.0,
           "deviz_header": {"obiectivul": "OBJ2", "obiectul": "OBL2", "categoria": "CAT2"}}
    holistic = {
        "matched_groups": [],
        "ref_only_groups": [{"articles": [art], "deviz_denumire": "OBJ2|OBL2|CAT2"}],
        "oferta_only_groups": [],
    }
    groups = list(_iter_source_groups(holistic, source="referinta"))
    assert len(groups) == 1
    header, _ = groups[0]
    assert header["obiectivul"] == "OBJ2"
