import pytest
from shared.lista_oferta_writer import extract_entity_name
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
