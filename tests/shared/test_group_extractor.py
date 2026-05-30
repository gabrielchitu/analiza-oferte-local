import pytest
from shared.document_profiler import DocumentProfile
from shared.group_extractor import extract_groups_as_headers
from shared.deviz_header_extractor import DevizHeader


def _profile(mode):
    return DocumentProfile(
        mode=mode, table_count=1 if mode == "TABLE" else 0,
        has_header_row=mode == "TABLE", estimated_article_rows=10
    )


def _make_di_with_table():
    """DI JSON cu un tabel F3 minimal și rând de metadate."""
    cells = []
    # Rând 0: meta Obiectivul
    cells.append({"rowIndex": 0, "columnIndex": 0, "content": "Obiectivul: TEST OBIECTIV"})
    cells.append({"rowIndex": 0, "columnIndex": 1, "content": ""})
    # Rând 1: meta Obiectul
    cells.append({"rowIndex": 1, "columnIndex": 0, "content": "Obiectul: 001 Structura"})
    cells.append({"rowIndex": 1, "columnIndex": 1, "content": ""})
    # Rând 2: meta Categoria
    cells.append({"rowIndex": 2, "columnIndex": 0, "content": "Categoria de lucrari: TERASAMENTE"})
    cells.append({"rowIndex": 2, "columnIndex": 1, "content": ""})
    # Rând 3: header tabel
    cells.append({"rowIndex": 3, "columnIndex": 0, "content": "Nr."})
    cells.append({"rowIndex": 3, "columnIndex": 1, "content": "Denumire"})
    cells.append({"rowIndex": 3, "columnIndex": 2, "content": "Cantitate"})
    # Rânduri date (5 minim pentru TABLE mode)
    for r in range(4, 9):
        cells.append({"rowIndex": r, "columnIndex": 0, "content": str(r)})
        cells.append({"rowIndex": r, "columnIndex": 1, "content": f"articol_{r}"})
        cells.append({"rowIndex": r, "columnIndex": 2, "content": "1.0"})
    return {"tables": [{"cells": cells}]}


def test_table_mode_returns_deviz_headers():
    """TABLE mode extrage DevizHeader din tables[].cells."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    assert isinstance(result, dict)
    assert len(result) >= 1
    hdr = next(iter(result.values()))
    assert isinstance(hdr, DevizHeader)


def test_table_mode_extracts_obiectul():
    """TABLE mode: obiectul extras corect din rândul meta."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    hdr = next(iter(result.values()))
    assert hdr.obiectul is not None
    assert "Structura" in hdr.obiectul or "001" in hdr.obiectul


def test_table_mode_empty_tables_falls_back_to_lines():
    """TABLE mode fără celule → returnează dict gol (caller face fallback)."""
    di_json = {"tables": [{"cells": []}]}
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    assert isinstance(result, dict)


def test_lines_mode_delegates_to_existing_extractor():
    """LINES mode → delegă la extract_deviz_headers(page_classes)."""
    page_classes = []  # fără pagini → dict gol
    result = extract_groups_as_headers({}, page_classes=page_classes, profile=_profile("LINES"))
    assert isinstance(result, dict)


def test_output_keys_are_deviz_key_hashes():
    """Cheile din dict sunt hash-uri hexadecimale (16 chars, MD5[:16]), nu deviz_cod strings."""
    di_json = _make_di_with_table()
    result = extract_groups_as_headers(di_json, page_classes=[], profile=_profile("TABLE"))
    for key in result.keys():
        # _make_deviz_key returnează hexdigest()[:16] — 16 chars hex
        assert len(key) == 16 and all(c in "0123456789abcdef" for c in key), \
            f"Key {key!r} nu e hash MD5[:16]"
