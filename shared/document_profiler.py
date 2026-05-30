from __future__ import annotations
import hashlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

_F3_HEADER_KWS = {"nr.", "denumire", "cantitate", "u.m.", "um", "pret", "cantit"}
_MIN_COLS = 3
_MIN_ROWS = 5


@dataclass
class DocumentProfile:
    mode: Literal["TABLE", "LINES"]
    table_count: int
    has_header_row: bool
    estimated_article_rows: int
    profiler_version: str = "1.0"


def profile_document(di_json: dict) -> DocumentProfile:
    """Inspectează di_json['tables']; returnează TABLE dacă găsește tabel F3 valid."""
    tables = di_json.get("tables") or []
    valid_tables = 0
    has_header = False
    total_data_rows = 0

    for table in tables:
        cells = table.get("cells") or []
        if not cells:
            continue
        row_count = max((c.get("rowIndex", 0) for c in cells), default=0) + 1
        col_count = max((c.get("columnIndex", 0) for c in cells), default=0) + 1
        if col_count < _MIN_COLS or row_count < _MIN_ROWS:
            continue
        header_cells = [c for c in cells if c.get("rowIndex", -1) == 0]
        header_text = " ".join(c.get("content", "") for c in header_cells).lower()
        if any(kw in header_text for kw in _F3_HEADER_KWS):
            valid_tables += 1
            has_header = True
            total_data_rows += row_count - 1

    mode: Literal["TABLE", "LINES"] = "TABLE" if valid_tables > 0 else "LINES"
    return DocumentProfile(
        mode=mode,
        table_count=valid_tables,
        has_header_row=has_header,
        estimated_article_rows=total_data_rows,
    )


def profile_document_cached(di_json: dict, checkpoint_dir: Path) -> DocumentProfile:
    """profile_document cu cache pe disc. Hash = MD5 primii 1000 bytes."""
    raw = json.dumps(di_json, ensure_ascii=False)[:1000].encode()
    h = hashlib.md5(raw).hexdigest()[:12]
    cache_file = checkpoint_dir / f"profile_{h}.json"
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            return DocumentProfile(**data)
        except Exception:
            pass
    profile = profile_document(di_json)
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps(profile.__dict__, ensure_ascii=False), encoding="utf-8"
    )
    return profile
