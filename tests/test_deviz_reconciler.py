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
