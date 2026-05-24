import json
import pytest
from pathlib import Path


def test_extract_from_lines_all_3():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "OBIECTIVUL: Reabilitare sediu scoala",
        "Obiectul: Corp A scoala",
        "Categoria de lucrari: 2.6 Instalatii Termice",
        "1 EA02A1 buc 1.0",
    ]
    obj1, obj2, cat = _extract_from_lines(lines)
    assert obj1 == "Reabilitare sediu scoala"
    assert obj2 == "Corp A scoala"
    assert cat == "2.6 Instalatii Termice"


def test_extract_from_lines_stadiu_fizic():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "OBIECTIVUL: Sediu primarie",
        "Obiectul: Cladire administrativa",
        "Stadiul fizic: 226108 STRUCTURA DE REZISTENTA",
    ]
    _, _, cat = _extract_from_lines(lines)
    assert cat is not None
    assert "226108" in cat


def test_extract_from_lines_missing_layer():
    from shared.deviz_header_extractor import _extract_from_lines
    lines = [
        "Obiectul: Corp B",
        "Categoria de lucrari: 3.1 Finisaje",
    ]
    obj1, obj2, cat = _extract_from_lines(lines)
    assert obj1 is None
    assert obj2 == "Corp B"
    assert cat == "3.1 Finisaje"


def test_make_deviz_key_stable():
    from shared.deviz_header_extractor import _make_deviz_key
    k1, v1 = _make_deviz_key("A", "B", "C")
    k2, v2 = _make_deviz_key("A", "B", "C")
    assert k1 == k2
    assert v1 is True
    assert not k1.startswith("__INCOMPLETE__")


def test_make_deviz_key_incomplete():
    from shared.deviz_header_extractor import _make_deviz_key
    k, v = _make_deviz_key("A", None, "C")
    assert v is False
    assert k.startswith("__INCOMPLETE__")


def test_cache_roundtrip(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / "cache.json")
    cache.put("key1", "Obiectiv", "Obiect", "Cat")
    result = cache.get("key1")
    assert result == ("Obiectiv", "Obiect", "Cat")


def test_cache_miss(tmp_path):
    from shared.deviz_header_extractor import DevizHeaderCache
    cache = DevizHeaderCache(path=tmp_path / "cache.json")
    assert cache.get("missing") is None


def test_extract_deviz_headers_full(tmp_path):
    from shared.deviz_header_extractor import extract_deviz_headers, DevizHeaderCache
    page_classes = [
        {
            "is_f3": True, "deviz_cod": "1-01", "header_only": False,
            "lines": [
                "OBIECTIVUL: Reabilitare scoala",
                "Obiectul: Corp A",
                "Categoria de lucrari: 2.1 Structuri",
                "1 EA02A1 buc 1.0",
            ],
        }
    ]
    # Use a temporary cache to ensure regex source, not cached
    import unittest.mock
    with unittest.mock.patch('shared.deviz_header_extractor.DevizHeaderCache') as MockCache:
        # Create a mock cache instance that always returns None (cache miss)
        mock_instance = MockCache.return_value
        mock_instance.get.return_value = None
        mock_instance.put.return_value = None
        headers = extract_deviz_headers(page_classes)
    assert "1-01" in headers
    h = headers["1-01"]
    assert h.obiectivul == "Reabilitare scoala"
    assert h.obiectul == "Corp A"
    assert h.categoria == "2.1 Structuri"
    assert h.is_valid is True
    assert h.source == "regex"
    assert not h.deviz_key.startswith("__INCOMPLETE__")


def test_extract_deviz_headers_incomplete():
    from shared.deviz_header_extractor import extract_deviz_headers
    page_classes = [
        {
            "is_f3": True, "deviz_cod": "2-01", "header_only": False,
            "lines": ["Obiectul: Corp B", "1 CA01A mp 5.0"],
        }
    ]
    headers = extract_deviz_headers(page_classes)
    h = headers["2-01"]
    assert h.is_valid is False
    assert h.deviz_key.startswith("__INCOMPLETE__")
