import pytest
from shared.document_profiler import profile_document, DocumentProfile


def _make_table(rows, cols, header_kws=None):
    """Helper: construiește un tables[] entry cu rows×cols celule."""
    cells = []
    for r in range(rows):
        for c in range(cols):
            if r == 0 and header_kws and c < len(header_kws):
                content = header_kws[c]
            else:
                content = f"val_{r}_{c}"
            cells.append({"rowIndex": r, "columnIndex": c, "content": content})
    return {"cells": cells}


def test_profile_table_mode_detected():
    """DI JSON cu tabel F3 valid → mode=TABLE."""
    di_json = {
        "tables": [_make_table(10, 5, ["Nr.", "Denumire", "Cantitate", "U.M.", "Pret"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "TABLE"
    assert profile.has_header_row is True
    assert profile.table_count >= 1


def test_profile_lines_mode_no_tables():
    """DI JSON fără tables[] → mode=LINES."""
    di_json = {"pages": [{"lines": [{"content": "text"}]}]}
    profile = profile_document(di_json)
    assert profile.mode == "LINES"
    assert profile.table_count == 0


def test_profile_lines_mode_small_table():
    """Tabel cu <5 rânduri → ignorat → mode=LINES."""
    di_json = {
        "tables": [_make_table(3, 4, ["Nr.", "Denumire", "Cantitate", "U.M."])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_lines_mode_no_f3_header():
    """Tabel mare dar fără keywords F3 în header → mode=LINES."""
    di_json = {
        "tables": [_make_table(10, 4, ["Col1", "Col2", "Col3", "Col4"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_lines_mode_too_few_columns():
    """Tabel cu <3 coloane → ignorat → mode=LINES."""
    di_json = {
        "tables": [_make_table(10, 2, ["Nr.", "Denumire"])]
    }
    profile = profile_document(di_json)
    assert profile.mode == "LINES"


def test_profile_empty_di_json():
    """DI JSON gol → mode=LINES."""
    profile = profile_document({})
    assert profile.mode == "LINES"
    assert profile.table_count == 0
