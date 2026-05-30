from __future__ import annotations
import re
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shared.document_profiler import DocumentProfile

logger = logging.getLogger(__name__)


def extract_groups_as_headers(
    di_json: dict,
    page_classes: list,
    profile: "DocumentProfile",
) -> dict:
    """
    Returnează dict[deviz_key, DevizHeader] — identic cu extract_deviz_headers().
    TABLE mode: parsează di_json['tables'] direct (Azure native).
    LINES mode: delegă la extract_deviz_headers(page_classes).
    Dacă TABLE mode returnează gol → apelantul trebuie să facă fallback la LINES.
    """
    if profile.mode == "TABLE":
        result = _extract_from_tables(di_json)
        if result:
            return result
        logger.info("[GEv2] TABLE mode: niciun grup extras, apelantul va face fallback")
        return {}
    return _extract_from_lines(page_classes)


def _extract_from_lines(page_classes: list) -> dict:
    from shared.deviz_header_extractor import extract_deviz_headers
    return extract_deviz_headers(page_classes)


def _extract_from_tables(di_json: dict) -> dict:
    """Extrage DevizHeader din tables[].cells folosind pandas pentru reconstrucție matrice."""
    try:
        import pandas as pd
    except ImportError:
        logger.warning("[GEv2] pandas nedisponibil — fallback la LINES")
        return {}

    from shared.deviz_header_extractor import DevizHeader, _make_deviz_key

    result = {}
    for table in (di_json.get("tables") or []):
        cells = table.get("cells") or []
        if not cells:
            continue
        max_row = max(c.get("rowIndex", 0) for c in cells) + 1
        max_col = max(c.get("columnIndex", 0) for c in cells) + 1
        matrix = [[""] * max_col for _ in range(max_row)]
        for cell in cells:
            r, c = cell.get("rowIndex", 0), cell.get("columnIndex", 0)
            matrix[r][c] = (cell.get("content") or "").strip()

        df = pd.DataFrame(matrix)
        header_idx = _find_header_row(df)
        if header_idx is None or header_idx == 0:
            continue
        meta_df = df.iloc[:header_idx]
        group_data = _parse_meta_rows(meta_df)
        if not group_data:
            continue
        obj1 = group_data.get("obiectivul")
        obj2 = group_data.get("obiectul")
        cat = group_data.get("categoria")
        deviz_cod = group_data.get("deviz_cod", "")
        if not (obj2 or cat):
            continue
        dkey, _ = _make_deviz_key(obj1, obj2, cat)
        if dkey and dkey not in result:
            result[dkey] = DevizHeader(
                obiectivul=obj1,
                obiectul=obj2,
                categoria=cat,
                deviz_key=dkey,
                is_valid=bool(obj2 or cat),
                source="table",
                deviz_cod=deviz_cod,
            )
    return result


def _find_header_row(df) -> int | None:
    """Returnează indexul primului rând cu keywords F3."""
    _KWS = {"nr.", "denumire", "cantitate", "u.m.", "um"}
    for idx, row in df.iterrows():
        row_text = " ".join(str(v) for v in row.values if v).lower()
        if sum(1 for kw in _KWS if kw in row_text) >= 2:
            return int(idx)
    return None


def _parse_meta_rows(meta_df) -> dict:
    """Extrage obiectivul/obiectul/categoria/deviz_cod din rândurile de deasupra header-ului."""
    result: dict = {}
    for _, row in meta_df.iterrows():
        text = " ".join(str(v) for v in row.values if v).strip()
        if not text:
            continue
        tl = text.lower()
        if "obiectivul" in tl or "obiectiv:" in tl:
            result.setdefault("obiectivul", _after_colon(text))
        elif "obiectul" in tl or "obiect:" in tl:
            result.setdefault("obiectul", _after_colon(text))
        elif "categoria" in tl:
            result.setdefault("categoria", _after_colon(text))
        else:
            m = re.search(r"deviz\s+oferta?\s+([A-Z0-9]{3,8})", text, re.IGNORECASE)
            if m:
                result.setdefault("deviz_cod", m.group(1))
                result.setdefault("categoria", text.strip())
    return result


def _after_colon(text: str) -> str | None:
    """Returnează textul după primul ':' sau None."""
    if ":" in text:
        val = text.split(":", 1)[1].strip()
        return val if val else None
    return text.strip() or None
