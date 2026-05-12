# Deviz Reconciler Post-Extracție — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adaugă un reconciler post-extracție care detectează devize lipsă prin cross-verificarea numărului de devize referință vs ofertă, le caută țintit în documentul DI, actualizează checkpoint-ul și raportează codurile negăsite ca erori.

**Architecture:** Modul nou `shared/deviz_reconciler.py` cu două funcții interne (`_find_deviz_page_range`, `_reconcile_one_code`) și un punct public (`reconcile_missing_devize`). Se apelează din `local_run.py::main()` imediat după calculul `devize_extra`/`devize_lipsa`, înainte de comparație. Zero apeluri LLM — căutare text + regex + `extract_articles_v3`.

**Tech Stack:** Python 3.11, `pathlib.Path`, `re`, `json`, `shared.f3_extractor.extract_articles_v3`

---

## File Map

| Fișier | Acțiune | Responsabilitate |
|--------|---------|-----------------|
| `shared/deviz_reconciler.py` | **Create** | Toată logica de reconciliere |
| `tests/test_deviz_reconciler.py` | **Create** | Teste unitare + integrare |
| `local_run.py` | **Modify** | Helper `_checkpoint_path` + apel reconciler în `main()` |

---

## Task 1: Helper `_checkpoint_path` în `local_run.py`

**Files:**
- Modify: `local_run.py:262-266` (extrage logica existentă din `extract_document`)
- Test: `tests/test_deviz_reconciler.py`

- [ ] **Step 1: Scrie testul**

```python
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
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
cd /Users/gabriel.chitu/Proiecte/analiza-oferte-EP/analiza-oferte-local
python -m pytest tests/test_deviz_reconciler.py -v
```

Expected: `AttributeError: module 'local_run' has no attribute '_checkpoint_path'`

- [ ] **Step 3: Adaugă `_checkpoint_path` în `local_run.py`**

Inserează după linia 66 (după `_normalize_deviz_for_filter`):

```python
def _checkpoint_path(di_path: Path) -> Path:
    """Returnează calea checkpoint-ului pentru un document DI."""
    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    return CHECKPOINT_DIR / f"{di_path.stem}_page_classes_{_clf_hash}.json"
```

Apoi în `extract_document` (linia 262-266), înlocuiește:
```python
    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    checkpoint = CHECKPOINT_DIR / f"{di_path.stem}_page_classes_{_clf_hash}.json"
```
cu:
```python
    checkpoint = _checkpoint_path(di_path)
```

- [ ] **Step 4: Rulează testele — verifică că trec**

```bash
python -m pytest tests/test_deviz_reconciler.py::test_checkpoint_path_format tests/test_deviz_reconciler.py::test_checkpoint_path_consistent tests/test_deviz_reconciler.py::test_checkpoint_path_different_for_different_files -v
```

Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add local_run.py tests/test_deviz_reconciler.py
git commit -m "refactor: extract _checkpoint_path helper from extract_document"
```

---

## Task 2: `_find_deviz_page_range` în `deviz_reconciler.py`

Caută un cod de deviz în paginile brute DI JSON și returnează intervalul de pagini consecutive.

**Files:**
- Create: `shared/deviz_reconciler.py`
- Modify: `tests/test_deviz_reconciler.py`

- [ ] **Step 1: Scrie testele**

Adaugă în `tests/test_deviz_reconciler.py`:

```python
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
        _make_di_page(3, "STADIU FIZIC: oferta 226200 BETON"),  # alt deviz
        _make_di_page(4, "CZ0101A articol 2 buc"),
    ]
    result = _find_deviz_page_range(pages, "226100", {})
    assert [pn for pn, _ in result] == [1, 2]


def test_skips_pages_already_classified_with_different_deviz():
    """Pagini deja clasificate F3 cu alt cod → oprire."""
    pages = [
        _make_di_page(1, "STADIUL FIZIC: oferta 226100 SAPATURI"),
        _make_di_page(2, "VA02B08 articol 100 mc"),
        _make_di_page(3, "CK25A articol 200 mp"),  # fara header nou, dar clasificat cu alt deviz
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
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
python -m pytest tests/test_deviz_reconciler.py -k "find_deviz" -v
```

Expected: `ImportError: cannot import name '_find_deviz_page_range'`

- [ ] **Step 3: Creează `shared/deviz_reconciler.py` cu `_find_deviz_page_range`**

```python
"""
deviz_reconciler.py — Reconciliere post-extracție pentru devize lipsă.

Detectează devize absente prin cross-verificare referință vs ofertă,
le caută țintit în documentul DI, actualizează checkpoint-ul.
Zero apeluri LLM.
"""
import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# Detectează header de deviz nou: "STADIUL FIZIC:" / "STADIU FIZIC:"
_STADIUL_FIZIC_RE = re.compile(r'STADIU[L]?\s+FIZIC\s*:', re.IGNORECASE)

# Extrage codul devizului dintr-o linie cu STADIUL FIZIC
# Acceptă: "oferta 226100", "001 226100", "226100" direct
_DEVIZ_COD_RE = re.compile(
    r'(?:oferta\s+)?(?:\d{1,3}\s+)?((?=[A-Z0-9]*\d{3})[A-Z0-9]{5,8})',
    re.IGNORECASE,
)


def _find_deviz_page_range(
    di_pages: list[dict],
    target_code: str,
    pc_by_pn: dict,
) -> list[tuple[int, list[str]]]:
    """
    Caută target_code în toate paginile DI JSON.

    Returnează lista de (page_number, lines_as_strings) pentru paginile
    aparținând devizului target_code, în ordine consecutivă.

    Se oprește când:
    - apare un header "STADIUL FIZIC:" cu un cod diferit
    - pagina e deja clasificată F3 cu un alt deviz_cod

    Args:
        di_pages: paginile brute din DI JSON ({"page_number": N, "lines": [{"content": "..."}]})
        target_code: codul devizului căutat (ex: "226400"), uppercase
        pc_by_pn: page_classes indexate după page_number (pentru verificare clasificare existentă)
    """
    target = target_code.strip().upper()
    _target_re = re.compile(r'\b' + re.escape(target) + r'\b', re.IGNORECASE)

    result: list[tuple[int, list[str]]] = []
    in_target = False

    for page in sorted(di_pages, key=lambda p: p.get("page_number", 0)):
        pn = page.get("page_number", 0)
        lines = [ln.get("content", "") for ln in page.get("lines", [])]
        full_text = " ".join(lines)

        if not in_target:
            if _target_re.search(full_text):
                in_target = True
                result.append((pn, lines))
        else:
            # Verifică dacă această pagină deschide un deviz NOU
            if _STADIUL_FIZIC_RE.search(full_text):
                m = _DEVIZ_COD_RE.search(full_text)
                if m:
                    found_code = m.group(1).upper()
                    if found_code != target:
                        break  # header cu alt deviz — oprim

            # Verifică clasificarea existentă în checkpoint
            existing = pc_by_pn.get(pn, {})
            if existing.get("is_f3") and existing.get("deviz_cod") and existing.get("deviz_cod").upper() != target:
                break  # pagină deja atribuită altui deviz — oprim

            result.append((pn, lines))

    return result
```

- [ ] **Step 4: Rulează testele — verifică că trec**

```bash
python -m pytest tests/test_deviz_reconciler.py -k "find_deviz" -v
```

Expected: 6 PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/deviz_reconciler.py tests/test_deviz_reconciler.py
git commit -m "feat: _find_deviz_page_range — page range detection for missing deviz"
```

---

## Task 3: `reconcile_missing_devize` — funcția publică

**Files:**
- Modify: `shared/deviz_reconciler.py`
- Modify: `tests/test_deviz_reconciler.py`

- [ ] **Step 1: Scrie testele**

Adaugă în `tests/test_deviz_reconciler.py`:

```python
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
    import json

    # Pagina 5 conține devizul 226400 (neclasificată F3)
    di_pages = [
        _make_di_page(5, "STADIUL FIZIC: oferta 226400 FINISAJE", "VA02B08 finisaje 100 mp"),
    ]
    di_path = _make_di_json(tmp_path, di_pages)

    page_classes = [
        {
            "page_number": 5, "is_f3": False, "deviz_cod": "", "deviz_den": "",
            "lines": ["STADIUL FIZIC: oferta 226400 FINISAJE", "VA02B08 finisaje 100 mp"],
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

    # Checkpoint actualizat: pagina 5 marcată F3
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

    assert any(a.get("deviz") == "226100" for a in updated_arts)  # original păstrat


def test_reconcile_skips_already_extracted_pages(tmp_path):
    """Pagini deja clasificate corect → nu re-extrage articolele."""
    existing = [{"deviz": "226400", "cod": "VA02B08", "cantitate": 100.0, "um": "mc"}]

    di_pages = [_make_di_page(3, "STADIUL FIZIC: oferta 226400 FINISAJE", "VA02B08 100 mc")]
    di_path = _make_di_json(tmp_path, di_pages)

    # Pagina deja clasificată corect
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

    # Niciun articol duplicat adăugat
    count_226400 = sum(1 for a in updated_arts if a.get("deviz") == "226400")
    assert count_226400 == 1  # doar cel din existing
```

- [ ] **Step 2: Rulează testele — verifică că eșuează**

```bash
python -m pytest tests/test_deviz_reconciler.py -k "reconcile" -v
```

Expected: `ImportError: cannot import name 'reconcile_missing_devize'`

- [ ] **Step 3: Implementează `reconcile_missing_devize` în `shared/deviz_reconciler.py`**

Adaugă după `_find_deviz_page_range`:

```python
def reconcile_missing_devize(
    di_path: Path,
    missing_codes: set[str],
    checkpoint_path: Path,
    existing_articles: list,
) -> tuple[list, set[str]]:
    """
    Pentru fiecare cod din missing_codes, caută devizul în toate paginile di_path.
    Actualizează checkpoint-ul cu paginile nou clasificate F3.

    Returns:
        (updated_articles, still_missing_codes)
        - updated_articles: existing_articles + articolele nou extrase
        - still_missing_codes: coduri negăsite nicăieri (eroare OCR/parsare)
    """
    from shared.f3_extractor import extract_articles_v3

    if not missing_codes:
        return existing_articles, set()

    if not checkpoint_path.exists():
        logger.warning(f"  [RECONCILE] Checkpoint lipsă: {checkpoint_path} — skip reconciliere")
        return existing_articles, set(missing_codes)

    di = json.loads(di_path.read_text(encoding="utf-8"))
    di_pages = di.get("pages", [])
    page_classes: list[dict] = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    pc_by_pn: dict[int, dict] = {pc["page_number"]: pc for pc in page_classes}

    all_articles = list(existing_articles)
    still_missing: set[str] = set()
    checkpoint_dirty = False

    for code in sorted(missing_codes):
        target = code.strip().upper()
        page_range = _find_deviz_page_range(di_pages, target, pc_by_pn)

        if not page_range:
            logger.warning(f"  [RECONCILE] Deviz {target} NEGASIT in {di_path.stem}")
            still_missing.add(code)
            continue

        pages_to_extract: list[dict] = []
        for pn, lines in page_range:
            pc = pc_by_pn.get(pn)
            if pc is None:
                # Pagină neînregistrată în checkpoint (caz rar)
                pc = {
                    "page_number": pn, "is_f3": True,
                    "deviz_cod": target, "deviz_den": "",
                    "lines": lines, "needs_llm": False, "header_only": False,
                }
                page_classes.append(pc)
                pc_by_pn[pn] = pc
                checkpoint_dirty = True
                pages_to_extract.append(pc)
            elif pc.get("is_f3") and pc.get("deviz_cod", "").upper() == target:
                pass  # deja clasificat corect — articolele sunt în existing_articles
            else:
                pc["is_f3"] = True
                pc["deviz_cod"] = target
                pc["header_only"] = False
                checkpoint_dirty = True
                pages_to_extract.append(pc)

        if pages_to_extract:
            new_arts = extract_articles_v3(pages_to_extract)
            logger.info(
                f"  [RECONCILE] Deviz {target}: {len(new_arts)} articole gasite"
                f" pe {len(pages_to_extract)} pagini (din {len(page_range)} total)"
            )
            all_articles.extend(new_arts)
        else:
            logger.info(f"  [RECONCILE] Deviz {target}: pagini deja extrase — skip")

    if checkpoint_dirty:
        checkpoint_path.write_text(
            json.dumps(page_classes, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        logger.info(f"  [RECONCILE] Checkpoint actualizat: {checkpoint_path.name}")

    return all_articles, still_missing
```

- [ ] **Step 4: Rulează toate testele reconciler**

```bash
python -m pytest tests/test_deviz_reconciler.py -v
```

Expected: toate PASSED

- [ ] **Step 5: Commit**

```bash
git add shared/deviz_reconciler.py tests/test_deviz_reconciler.py
git commit -m "feat: reconcile_missing_devize — targeted re-scan for missing deviz codes"
```

---

## Task 4: Integrare în `local_run.py::main()`

**Files:**
- Modify: `local_run.py:591-599`

- [ ] **Step 1: Adaugă importul `reconcile_missing_devize` în `main()`**

În `local_run.py`, la începutul funcției `main()` (linia 532), adaugă după `from shared.deviz_namer import populate_deviz_denominations`:

```python
    from shared.deviz_reconciler import reconcile_missing_devize
```

- [ ] **Step 2: Înlocuiește blocul `devize_extra`/`devize_lipsa` (liniile 591-599)**

Găsește secțiunea:
```python
        oferta_deviz_codes = set(a.get("deviz", "") for a in oferta_articles if a.get("deviz"))
        devize_extra = oferta_deviz_codes - ref_deviz_codes - {""}
        devize_lipsa_din_oferta = ref_deviz_codes - oferta_deviz_codes
        if devize_extra:
            logger.warning(f"  ALERTA: {len(devize_extra)} devize in oferta ABSENTE din referinta: {sorted(devize_extra)}")
            logger.warning(f"  → Posibil F3 neextras din referinta SAU lucrari suplimentare propuse de ofertant")
        if devize_lipsa_din_oferta:
            logger.info(f"  {len(devize_lipsa_din_oferta)} devize din referinta NEACOPERITE de oferta: {sorted(devize_lipsa_din_oferta)}")
```

Înlocuiește cu:
```python
        oferta_deviz_codes = set(a.get("deviz", "") for a in oferta_articles if a.get("deviz"))
        devize_extra = oferta_deviz_codes - ref_deviz_codes - {""}
        devize_lipsa_din_oferta = ref_deviz_codes - oferta_deviz_codes

        # Reconciliere devize_extra: în ofertă dar absente din referință → re-scanăm ref
        if devize_extra:
            logger.warning(f"  ALERTA: {len(devize_extra)} devize in oferta ABSENTE din referinta: {sorted(devize_extra)}")
            logger.info(f"  → Reconciliere: re-scanam referinta pentru {sorted(devize_extra)}")
            ref_articles, unresolved_extra = reconcile_missing_devize(
                di_path=ref_path,
                missing_codes=devize_extra,
                checkpoint_path=_checkpoint_path(ref_path),
                existing_articles=ref_articles,
            )
            ref_deviz_codes = {a.get("deviz") for a in ref_articles if a.get("deviz")}
            for code in unresolved_extra:
                logger.error(f"  [RECONCILE] Deviz {code} NEGASIT in referinta — posibila eroare OCR/parsare")

        # Reconciliere devize_lipsa: în referință dar absente din ofertă → re-scanăm oferta
        if devize_lipsa_din_oferta:
            logger.info(f"  {len(devize_lipsa_din_oferta)} devize din referinta NEACOPERITE de oferta: {sorted(devize_lipsa_din_oferta)}")
            logger.info(f"  → Reconciliere: re-scanam oferta {oferta_nr} pentru {sorted(devize_lipsa_din_oferta)}")
            oferta_articles, unresolved_lipsa = reconcile_missing_devize(
                di_path=oferta_path,
                missing_codes=devize_lipsa_din_oferta,
                checkpoint_path=_checkpoint_path(oferta_path),
                existing_articles=oferta_articles,
            )
            for code in unresolved_lipsa:
                logger.error(f"  [RECONCILE] Deviz {code} NEGASIT in oferta {oferta_nr} — posibila eroare OCR/parsare")
```

- [ ] **Step 3: Verifică că pipeline-ul pornește fără erori de import**

```bash
python -c "import local_run; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Rulează toate testele**

```bash
python -m pytest tests/ -v
```

Expected: toate PASSED (niciun test existent stricat)

- [ ] **Step 5: Commit**

```bash
git add local_run.py
git commit -m "feat: integrate deviz reconciler in main() pipeline"
```

---

## Task 5: Verificare end-to-end

- [ ] **Step 1: Șterge checkpoint-urile existente pentru a forța re-clasificare**

```bash
# Nu șterge — reconcilerul funcționează și cu checkpoint-uri existente.
# Dacă vrei să testezi cu devize_extra simulate, modifică temporar un oferta_X.json.
```

- [ ] **Step 2: Rulează pipeline-ul real**

```bash
python local_run.py 2>&1 | tee new_run.log
```

- [ ] **Step 3: Verifică log-ul pentru mesaje `[RECONCILE]`**

```bash
grep "\[RECONCILE\]" new_run.log
```

Expected output (dacă există devize lipsă detectate):
```
[RECONCILE] Deviz 226400: 12 articole gasite pe 3 pagini (din 3 total)
[RECONCILE] Checkpoint actualizat: di_oferta_3_page_classes_XXXXXXXX.json
```

Sau dacă totul era deja extras corect:
```
(niciun output — nu existau diferențe de devize)
```

- [ ] **Step 4: Verifică că totalul `matched` a crescut sau a rămas stabil**

```bash
grep -E "\[COMP\]|Neconformitati|Matched" new_run.log
```

- [ ] **Step 5: Commit final**

```bash
git add new_run.log
git commit -m "test: end-to-end run with deviz reconciler active"
```
