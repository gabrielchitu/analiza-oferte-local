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


from shared.deviz_reconciler import reconcile_missing_devize


def _make_checkpoint(tmp_path: Path, page_classes: list) -> Path:
    cp = tmp_path / "checkpoints" / "di_test_page_classes_abc123456789.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(page_classes, ensure_ascii=False), encoding="utf-8")
    return cp


def _make_di_json(tmp_path: Path, pages: list) -> Path:
    di_path = tmp_path / "di_test.json"
    di_path.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    return di_path


def test_reconcile_finds_missing_deviz_and_extracts(tmp_path):
    """Deviz lipsă găsit în DI → articole extrase și returnate."""
    di_pages = [
        _make_di_page(5, "STADIUL FIZIC: oferta 226400 FINISAJE", "1 VA02B08", "finisaje", "mp", "100"),
    ]
    di_path = _make_di_json(tmp_path, di_pages)

    page_classes = [
        {
            "page_number": 5, "is_f3": False, "deviz_cod": "", "deviz_den": "",
            "lines": ["STADIUL FIZIC: oferta 226400 FINISAJE", "1 VA02B08", "finisaje", "mp", "100"],
            "needs_llm": False, "header_only": False,
        }
    ]
    cp = _make_checkpoint(tmp_path, page_classes)

    updated_arts, still_missing = reconcile_missing_devize(
        di_path=di_path,
        missing_codes={"226400"},
        checkpoint_path=cp,
        existing_articles=[],
    )

    assert "226400" not in still_missing
    assert any(a.get("deviz") == "226400" for a in updated_arts)

    saved = json.loads(cp.read_text(encoding="utf-8"))
    pn5 = next(p for p in saved if p["page_number"] == 5)
    assert pn5["is_f3"] is True
    assert pn5["deviz_cod"] == "226400"


def test_reconcile_returns_still_missing_when_not_found(tmp_path):
    """Cod absent din document → apare în still_missing_codes."""
    di_pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI", "VA02B08 100 mc"),
    ]
    di_path = _make_di_json(tmp_path, di_pages)

    page_classes = [
        {
            "page_number": 1, "is_f3": True, "deviz_cod": "226100", "deviz_den": "",
            "lines": ["STADIUL FIZIC: oferta 226100 SAPATURI", "VA02B08 100 mc"],
            "needs_llm": False, "header_only": False,
        }
    ]
    cp = _make_checkpoint(tmp_path, page_classes)

    updated_arts, still_missing = reconcile_missing_devize(
        di_path=di_path,
        missing_codes={"226999"},
        checkpoint_path=cp,
        existing_articles=[],
    )

    assert "226999" in still_missing
    assert updated_arts == []


def test_reconcile_preserves_existing_articles(tmp_path):
    """Articolele deja extrase sunt păstrate în lista returnată."""
    existing = [{"deviz": "226100", "cod": "VA02B08", "cantitate": 100.0, "um": "mc"}]

    di_pages = [_make_di_page(2, "STADIUL FIZIC: oferta 226400 FINISAJE", "CK25A finisaje 50 mp")]
    di_path = _make_di_json(tmp_path, di_pages)

    page_classes = [
        {
            "page_number": 2, "is_f3": False, "deviz_cod": "", "deviz_den": "",
            "lines": ["STADIUL FIZIC: oferta 226400 FINISAJE", "CK25A finisaje 50 mp"],
            "needs_llm": False, "header_only": False,
        }
    ]
    cp = _make_checkpoint(tmp_path, page_classes)

    updated_arts, still_missing = reconcile_missing_devize(
        di_path=di_path,
        missing_codes={"226400"},
        checkpoint_path=cp,
        existing_articles=existing,
    )

    assert any(a.get("deviz") == "226100" for a in updated_arts)


def test_reconcile_skips_already_extracted_pages(tmp_path):
    """Pagini deja clasificate corect → nu re-extrage articolele."""
    existing = [{"deviz": "226400", "cod": "VA02B08", "cantitate": 100.0, "um": "mc"}]

    di_pages = [_make_di_page(3, "STADIUL FIZIC: oferta 226400 FINISAJE", "VA02B08 100 mc")]
    di_path = _make_di_json(tmp_path, di_pages)

    page_classes = [
        {
            "page_number": 3, "is_f3": True, "deviz_cod": "226400", "deviz_den": "",
            "lines": ["STADIUL FIZIC: oferta 226400 FINISAJE", "VA02B08 100 mc"],
            "needs_llm": False, "header_only": False,
        }
    ]
    cp = _make_checkpoint(tmp_path, page_classes)

    updated_arts, still_missing = reconcile_missing_devize(
        di_path=di_path,
        missing_codes={"226400"},
        checkpoint_path=cp,
        existing_articles=existing,
    )

    count_226400 = sum(1 for a in updated_arts if a.get("deviz") == "226400")
    assert count_226400 == 1  # doar cel din existing
