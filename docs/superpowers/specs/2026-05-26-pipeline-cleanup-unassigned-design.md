# Design: Pipeline Cleanup + Articole Neasignate

**Data:** 2026-05-26  
**Scope:** Eliminare pipeline vechi (match_global pe deviz_cod), adăugare secțiune "articole neasignate" în raport  
**Abordare:** B — cleanup complet pipeline + unassigned_articles în holistic

---

## Context

Pipeline-ul are două ramuri paralele care produc rezultate contradictorii:

- **Pipeline holistic** (canonical): `compare_by_groups` pe `deviz_key` (hash obiectivul+obiectul+categoria) → alimentează DOCX
- **Pipeline vechi** (cod mort): `match_global` pe `deviz_cod` string → generează 144–181 DEVIZ_MISMATCH false în loguri, scrie fișiere JSON neutilizate

Arhitectura corectă: matching exclusiv pe `deviz_key`. DEVIZ_MISMATCH nu trebuie să existe.

---

## Secțiunea 1 — Cleanup `local_run.py`

### De șters
- `detect_deviz_mismatches` call + `_deviz_remap` logic (~liniile 1068–1090)
- `match_global` call (~linia 1093) + toate variabilele rezultate (`neconformitati`, `matches`, `matched_ref_keys`, `articole_fara_deviz`)
- `mark_suspicious_extras` call (~linia 1164)
- `build_raport_ierarhic` call + import (~liniile 1240–1242)
- Scriere `comparatie_oferta_{N}.json` (~liniile 1222–1233)
- Scriere `comparatie_deviz_oferta_{N}.json` (~liniile 407–415)
- Log-uri din pipeline vechi: `Neconformitati: {dict(tipuri)}`, `Matched: N articole` (~liniile 1235–1237)
- Import `generate_json_by_deviz` (~linia 32)
- Import `detect_deviz_mismatches` (~linia 986)

### Rămâne
Doar holistic pipeline:
```
extract ref + offer articles
↓
compare_by_groups(ref, offer, ref_dh, oferta_dh) → HolisticComparison
↓
build_raport_holistic(HolisticComparison) → raport_holistic
↓
generate_word(comp) → DOCX
holistic_oferta_N.json (deja scris)
```

### Log-uri noi (înlocuiesc cele vechi)
```
[HOLISTIC] N grupuri matchate, N ref-only, N oferta-only
[HOLISTIC] Neconformitati: {dict(tipuri_holistic)} (total: N)
[HOLISTIC] Matched: N articole
[HOLISTIC] Neasignate: N articole ref, N articole oferta
```
Tipurile holistic se extrag din `raport_holistic["sumar"]["neconformitati_by_tip"]`.

---

## Secțiunea 2 — `group_comparator.py`: `unassigned_articles`

### `HolisticComparison` dataclass
Câmp nou:
```python
unassigned_articles: list = field(default_factory=list)
# Format per articol: {source: "ref"|"oferta", cod, denumire, deviz_cod, source_pages}
```

### `_articles_by_deviz` — comportament nou
Articolele cu `deviz_key` INCOMPLETE sau null au două cazuri:
- `deviz` (cod string) prezent → merg în `unassigned_articles` (nu în `result[f"__cod__{cod}"]`)
- `deviz` absent → merg în `ungrouped` (comportament existent)

```python
def _articles_by_deviz(articles, unassigned_out=None):
    for a in articles:
        key = (a.get("deviz_key") or "").strip()
        if key and not key.startswith("__INCOMPLETE__"):
            result[key].append(a)
        else:
            deviz_cod = (a.get("deviz") or "").strip()
            if deviz_cod:
                if unassigned_out is not None:
                    unassigned_out.append(a)
                # NU mai adăugat în result → nu mai apare ca ref-only/oferta-only
            # dacă nici deviz_cod → ungrouped (existent)
```

### `compare_by_groups`
Colectează `unassigned_ref` și `unassigned_oferta` separat, le pune în:
```python
result.unassigned_articles = (
    [{"source": "ref",    **a} for a in unassigned_ref] +
    [{"source": "oferta", **a} for a in unassigned_oferta]
)
```

---

## Secțiunea 3 — `report_word.py`: secțiune DOCX

### Locație în document
La final, după grupurile `oferta_only_groups`. Apare **doar dacă există articole neasignate**.

### Format
**Heading:** "Articole neasignate — deviz neidentificat"  
**Intro (italic):** "Articolele de mai jos nu au putut fi atribuite unui grup deviz (Obiectiv + Obiect + Categorie). Verificați manual pagina sursă din document."

**Tabel** cu coloane: Sursă | Cod | Denumire | Deviz detectat | Pagini

- Fundal galben deschis (#FFFACD) pe rânduri
- "Sursă" = "REF" sau "OFERTĂ"
- "Deviz detectat" = `art.get("deviz")` — codul extras din PDF
- "Pagini" = `", ".join(str(p) for p in art.get("source_pages", []))`

### `build_raport_holistic` — extinde sumar
```python
"unassigned_articles": holistic_comparison.unassigned_articles,
"sumar": {
    ...existing...,
    "total_unassigned_ref": len([a for a in unassigned if a["source"]=="ref"]),
    "total_unassigned_oferta": len([a for a in unassigned if a["source"]=="oferta"]),
}
```

---

## Secțiunea 4 — `abbreviation_learner.py`

### Schimbare
Citește `holistic_oferta_{N}.json` în loc de `comparatie_oferta_{N}.json`.

```python
# Înainte:
f = cfg.output_dir / f"comparatie_oferta_{i}.json"
comp = json.loads(f.read_text())
for nc in comp.get("neconformitati", []):
    if nc.get("tip") != "DESCRIERE_DIFERITA": continue

# După:
f = cfg.output_dir / f"holistic_oferta_{i}.json"
holistic = json.loads(f.read_text())
for mg in holistic.get("matched_groups", []):
    for nc in mg.get("neconformitati", []):
        if nc.get("tip") != "DESCRIERE_DIFERITA": continue
```

Câmpurile `tip`, `similaritate`, `ref`, `oferta`, `ref_cod` sunt identice în holistic NCs — restul logicii neschimbat.

---

## Fișiere modificate

| Fișier | Tip modificare |
|---|---|
| `local_run.py` | Ștergere pipeline vechi (~80 linii), log-uri noi holistic |
| `shared/group_comparator.py` | `unassigned_articles` în `HolisticComparison` + `_articles_by_deviz` |
| `shared/report_builder.py` | `build_raport_holistic` extinde sumar cu unassigned |
| `shared/report_word.py` | Secțiune "Articole neasignate" la final DOCX |
| `shared/abbreviation_learner.py` | Citește din `holistic_oferta_N.json` |

## Fișiere de șters (generate, neutilizate)
- `output_AO/*/comparatie_oferta_*.json` (generate din pipeline vechi)
- `output_AO/*/comparatie_deviz_oferta_*.json` (generate din pipeline vechi)
- `shared/report_json.py` (dacă `generate_json_by_deviz` e singurul export)

## Fișiere lăsate neatinse
- `shared/diagnostics_builder.py` / `shared/diagnostics_word.py` — tool offline, nu e în pipeline
- `shared/deviz_mismatch_detector.py` — poate rămâne ca utilitar (nu e apelat din pipeline după cleanup)

---

## Testing
1. Rulare BR: `python3 multi_client_run.py --client "Blocuri Racari"` — 0 DEVIZ_MISMATCH în loguri
2. Log-ul nou arată `[HOLISTIC] Neconformitati: {...}` (fără DEVIZ_MISMATCH)
3. DOCX O1/O3: secțiunea "Articole neasignate" apare (sau lipsește dacă toate au deviz_key valid)
4. `abbreviation_learner` rulează fără erori pe holistic JSON
