# tests/test_deviz_reconciler.py
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import local_run


def test_checkpoint_path_format():
    """_checkpoint_path returnează un Path cu sufixul corect."""
    p = local_run._checkpoint_path(Path("input_AO/di_referinta.json"))
    assert p.parent == local_run.CHECKPOINT_DIR
    assert p.name.startswith("di_referinta_page_classes_")
    assert p.suffix == ".json"
    assert len(p.stem.split("_")[-1]) == 12  # hash MD5 de 12 caractere


def test_checkpoint_path_consistent():
    """Apeluri repetate returnează același path."""
    p1 = local_run._checkpoint_path(Path("input_AO/di_oferta_1.json"))
    p2 = local_run._checkpoint_path(Path("input_AO/di_oferta_1.json"))
    assert p1 == p2


def test_checkpoint_path_different_for_different_files():
    """Documente diferite → stem diferit în checkpoint."""
    p1 = local_run._checkpoint_path(Path("input_AO/di_referinta.json"))
    p2 = local_run._checkpoint_path(Path("input_AO/di_oferta_1.json"))
    assert p1 != p2


from shared.deviz_reconciler import _find_deviz_page_range


def _make_di_page(page_number: int, *lines: str) -> dict:
    """Construiește o pagină DI JSON minimală."""
    return {
        "page_number": page_number,
        "lines": [{"content": line} for line in lines],
    }


def test_finds_single_page_deviz():
    """Deviz pe o singură pagină — returnat corect."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "STADIUL FIZIC: oferta 226200 BETON"),
    ]
    result = _find_deviz_page_range(pages, "226100", {})
    assert [pn for pn, _ in result] == [1]


def test_finds_multipage_deviz():
    """Deviz pe mai multe pagini consecutive — toate returnate."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "VA02B08 sapaturi pamant 100 mc"),
        _make_di_page(3, "TSC02D11 sapaturi mecanice 50 mc"),
        _make_di_page(4, "STADIUL FIZIC: oferta 226200 BETON"),
    ]
    result = _find_deviz_page_range(pages, "226100", {})
    assert [pn for pn, _ in result] == [1, 2, 3]


def test_returns_empty_when_code_not_found():
    """Cod absent → listă goală."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "VA02B08 sapaturi 100 mc"),
    ]
    result = _find_deviz_page_range(pages, "226999", {})
    assert result == []


def test_stops_at_different_deviz_header():
    """Se oprește când găsește header cu cod diferit."""
    pages = [
        _make_di_page(1, "STADIU FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "VA02B08 articol 1 buc"),
        _make_di_page(3, "STADIU FIZIC: oferta 226200 BETON"),
        _make_di_page(4, "CZ0101A articol 2 buc"),
    ]
    result = _find_deviz_page_range(pages, "226100", {})
    assert [pn for pn, _ in result] == [1, 2]


def test_skips_pages_already_classified_with_different_deviz():
    """Pagini deja clasificate F3 cu alt cod → oprire."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "VA02B08 articol 100 mc"),
        _make_di_page(3, "CK25A articol 200 mp"),
    ]
    pc_by_pn = {
        3: {"page_number": 3, "is_f3": True, "deviz_cod": "226200"},
    }
    result = _find_deviz_page_range(pages, "226100", pc_by_pn)
    assert [pn for pn, _ in result] == [1, 2]


def test_lines_returned_as_strings():
    """Liniile returnate sunt strings, nu dict-uri."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI", "VA02B08 100 mc"),
    ]
    result = _find_deviz_page_range(pages, "226100", {})
    assert result[0][1] == ["STADIUL FIZIC: oferta 226100 SAPATURI", "VA02B08 100 mc"]
