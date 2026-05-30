import pytest
from shared.group_comparator import _match_by_rapidfuzz
from shared.deviz_header_extractor import DevizHeader


def _hdr(obj2, cat, obj1=None):
    from shared.deviz_header_extractor import _make_deviz_key
    dkey, _ = _make_deviz_key(obj1, obj2, cat)
    return DevizHeader(
        obiectivul=obj1, obiectul=obj2, categoria=cat,
        deviz_key=dkey, is_valid=True, source="test", deviz_cod=""
    )


def test_exact_match_returns_pair():
    """Texte identice → score 100 → matched."""
    ref = {"k1": _hdr("Structura de rezistenta", "TERASAMENTE")}
    oferta = {"k2": _hdr("Structura de rezistenta", "TERASAMENTE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1
    assert pairs[0][0] == "k1"
    assert pairs[0][1] == "k2"


def test_high_similarity_matches():
    """Texte similare (abrevieri) → score ≥85 → matched."""
    ref = {"k1": _hdr("Corp B Bloc 2", "Instalatii sanitare")}
    oferta = {"k2": _hdr("Corp B - Bloc 2", "INSTALATII SANITARE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1


def test_low_similarity_no_match():
    """Texte complet diferite → score <85 → nicio pereche."""
    ref = {"k1": _hdr("Structura", "TERASAMENTE")}
    oferta = {"k2": _hdr("Instalatii", "ELECTRICE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 0


def test_no_double_match():
    """Un grup ofertă nu poate fi matched la 2 grupuri ref."""
    ref = {
        "k1": _hdr("Structura A", "TERASAMENTE"),
        "k2": _hdr("Structura A", "TERASAMENTE"),
    }
    oferta = {"k3": _hdr("Structura A", "TERASAMENTE")}
    pairs = _match_by_rapidfuzz(ref, oferta, threshold=85)
    assert len(pairs) == 1


def test_empty_inputs():
    """Ref sau ofertă goale → listă goală."""
    assert _match_by_rapidfuzz({}, {}, 85) == []
    ref = {"k1": _hdr("Structura", "TERASAMENTE")}
    assert _match_by_rapidfuzz(ref, {}, 85) == []
