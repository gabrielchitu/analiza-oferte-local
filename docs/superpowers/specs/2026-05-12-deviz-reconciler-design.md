# Design: Deviz Reconciler Post-Extracție

**Data:** 2026-05-12  
**Status:** Aprobat  

## Problema

Pipeline-ul actual extrage devizele din referință și din fiecare ofertă independent. Când numărul de devize diferă între cele două documente, eroarea este doar logată ca WARNING — fără nicio acțiune de corecție. Cazuri posibile:

- **devize_extra**: oferta conține un deviz absent din referință → imposibil în practică (orice deviz din ofertă trebuie să existe în referință) → înseamnă că referința a fost extrasă incomplet
- **devize_lipsa**: referința conține un deviz absent din ofertă → oferta a fost extrasă incomplet

Ambele cazuri sunt semnale că extracția a eșuat și trebuie auto-corectată înainte de comparație.

## Soluție: Reconciler Post-Extracție (Abordarea A)

Un nou pas în pipeline, după extracția F3 și înainte de comparație, care:
1. Identifică diferențele de devize între referință și ofertă
2. Re-scanează documentul afectat cu un parser țintit pe codul lipsă
3. Actualizează checkpoint-ul cu paginile nou găsite
4. Raportează codurile negăsite ca erori de OCR/parsare

### De ce nu alte abordări

- **Buclă iterativă (B)**: lentă, greu de debugat, risc buclă infinită
- **Re-scan declanșat din comparator (C)**: coupling strâns comparator↔extractor, greu de menținut

## Arhitectura

```
extract_document(ref)    → ref_articles
extract_document(offer)  → oferta_articles
         ↓
   DEVIZ DIFF CHECK
   devize_extra  = oferta_deviz_codes - ref_deviz_codes   → re-scanăm referința
   devize_lipsa  = ref_deviz_codes - oferta_deviz_codes   → re-scanăm oferta
         ↓
   RECONCILER (doar dacă există diferențe)
         ↓
   compare_and_report(ref_articles_updated, oferta_articles_updated)
```

**Referința se actualizează global**: devizele găsite la procesarea ofertei 1 sunt disponibile și la oferta 2.

## Modul nou: `shared/deviz_reconciler.py`

### API public

```python
def reconcile_missing_devize(
    di_path: Path,
    missing_codes: set[str],
    checkpoint_path: Path,
    existing_articles: list,
) -> tuple[list, set[str]]:
    """
    Caută fiecare cod din missing_codes în toate paginile documentului di_path.
    Actualizează checkpoint-ul cu paginile nou clasificate F3.
    Returns: (updated_articles, still_missing_codes)
    - updated_articles: existing_articles + articolele nou extrase
    - still_missing_codes: coduri negăsite nicăieri (eroare OCR/parsare)
    """
```

### Flow intern per cod lipsă

1. **Încarcă** DI JSON (`di_path`) + page_classes din `checkpoint_path`
2. **Caută codul** în `page["lines"]` pentru toate paginile — scan complet, ignoră `is_f3` curent
3. **Detectează intervalul de pagini**: de la prima pagină cu codul, continuă pagini consecutive până când apare un cod de deviz diferit în header (refolosește regex-ul din `f3_page_classifier.DEVIZ_COD_RE`)
4. **Actualizează page_classes**: paginile găsite → `is_f3=True`, `deviz_cod=<target>`
5. **Extrage articolele**: apelează `extract_articles_v3(pages_subset)` pe paginile găsite; paginile deja marcate `is_f3=True` cu `deviz_cod` corect sunt sărite (articolele lor sunt deja în `existing_articles`)
6. **Salvează checkpoint** actualizat — paginile rămân marcate F3 în run-uri viitoare
7. Dacă codul **nu e găsit nicăieri** → adaugă în `still_missing_codes`

### Fără LLM

Reconcilerul este pur determinist: text search + regex + `extract_articles_v3`. LLM-ul rămâne exclusiv în clasificatorul inițial de pagini (`classify_pages`).

## Modificări în `local_run.py`

### Helper nou

```python
def _checkpoint_path(di_path: Path) -> Path:
    """Returnează calea checkpoint-ului pentru un document DI."""
    # extrage logica duplicată din extract_document
```

### Integrare în `main()` (după liniile 591-599 existente)

```python
# Reconcile devize_extra: în ofertă dar absente din referință → re-scanăm ref
if devize_extra:
    ref_articles, unresolved_extra = reconcile_missing_devize(
        ref_path, devize_extra, _checkpoint_path(ref_path), ref_articles
    )
    ref_deviz_codes = {a.get("deviz") for a in ref_articles if a.get("deviz")}
    for code in unresolved_extra:
        logger.error(f"  [RECONCILE] Deviz {code} NEGASIT in referinta — eroare OCR/parsare")

# Reconcile devize_lipsa: în referință dar absente din ofertă → re-scanăm oferta
if devize_lipsa_din_oferta:
    oferta_articles, unresolved_lipsa = reconcile_missing_devize(
        oferta_path, devize_lipsa_din_oferta, _checkpoint_path(oferta_path), oferta_articles
    )
    for code in unresolved_lipsa:
        logger.error(f"  [RECONCILE] Deviz {code} NEGASIT in oferta {oferta_nr} — eroare OCR/parsare")
```

## Raportare erori

- **Coduri rezolvate de reconciler**: logate ca `[RECONCILE] Găsit deviz X pe paginile Y-Z`
- **Coduri nerezolvate**: logate ca `[RECONCILE] NEGASIT` + raportate în DOCX ca tip nou `EROARE_EXTRACTIE` — distinct de `ARTICOL_LIPSA` (devizul există, articolul lipsește)

## Fișiere afectate

| Fișier | Modificare |
|--------|-----------|
| `shared/deviz_reconciler.py` | **Nou** — logica completă de reconciliere |
| `local_run.py` | Adăugare `_checkpoint_path()` + apel reconciler în `main()` |
| `shared/report_word.py` | Opțional: secțiune nouă `EROARE_EXTRACTIE` în DOCX |

## Criterii de succes

- Dacă un deviz există fizic în document (text OCR corect), reconcilerul îl găsește
- Checkpoint-ul actualizat face ca run-urile ulterioare să sară peste re-scanare
- Dacă codul e cu adevărat absent (eroare OCR sau lipsă fizică), eroarea e raportată clar
- Zero apeluri LLM în reconciler
