import json
import pytest
from pathlib import Path
from shared.f3_knowledge import F3Knowledge


@pytest.fixture
def tmp_knowledge(tmp_path):
    data = {
        "version": 1,
        "start_markers": [
            {"pattern": "Formular F3", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "STADIUL FIZIC:", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
        "end_markers": [
            {"pattern": "TOTAL CHELT. DIRECTE", "type": "exact", "format": "isdp", "source": "manual", "seen_count": 0},
            {"pattern": "TOTAL GENERAL pe categorie", "type": "prefix", "format": "isdp", "source": "manual", "seen_count": 0},
        ],
    }
    p = tmp_path / "knowledge.json"
    p.write_text(json.dumps(data))
    return F3Knowledge(path=p)


def test_find_start_marker_exact(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["col1 col2 col3", "Formular F3", "1 EA02A1 buc"])
    assert result == "Formular F3"


def test_find_start_marker_prefix(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["STADIUL FIZIC: oferta 226108 STRUCTURA"])
    assert result is not None


def test_find_start_marker_none(tmp_knowledge):
    result = tmp_knowledge.find_start_marker(["linie normala", "alt text"])
    assert result is None


def test_find_end_marker_returns_index(tmp_knowledge):
    lines = ["1 EA02A1 buc 1.0", "TOTAL CHELT. DIRECTE", "Cheltuieli indirecte"]
    result = tmp_knowledge.find_end_marker(lines)
    assert result == (1, "TOTAL CHELT. DIRECTE")


def test_find_end_marker_prefix(tmp_knowledge):
    lines = ["art1", "TOTAL GENERAL pe categorie Vo=To+Io+Po"]
    result = tmp_knowledge.find_end_marker(lines)
    assert result is not None
    assert result[0] == 1


def test_find_end_marker_none(tmp_knowledge):
    result = tmp_knowledge.find_end_marker(["1 EA02A1 buc", "2 CA01A mp"])
    assert result is None


def test_learn_adds_new_start_marker(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Lista cu cantitati", "exact", source_type="start")
    result = k.find_start_marker(["Lista cu cantitati de lucrari pe categorii"])
    assert result is not None


def test_learn_no_duplicate(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Formular F3", "exact", source_type="start")
    k.learn("Formular F3", "exact", source_type="start")
    count = sum(1 for m in k._data["start_markers"] if m["pattern"] == "Formular F3")
    assert count == 1


def test_learn_increments_seen_count(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("Formular F3", "exact", source_type="start")
    k.learn("Formular F3", "exact", source_type="start")
    entry = next(m for m in k._data["start_markers"] if m["pattern"] == "Formular F3")
    assert entry["seen_count"] == 2


def test_learn_rejects_short_pattern(tmp_path):
    k = F3Knowledge(path=tmp_path / "k.json")
    k.learn("F3", "exact", source_type="start")
    assert not any(m["pattern"] == "F3" for m in k._data["start_markers"])


def test_learn_saves_to_file(tmp_path):
    p = tmp_path / "k.json"
    k = F3Knowledge(path=p)
    k.learn("Lista lucrari", "exact", source_type="start")
    k2 = F3Knowledge(path=p)
    assert k2.find_start_marker(["Lista lucrari"]) is not None
