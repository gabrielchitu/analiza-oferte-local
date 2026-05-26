# Pipeline Cleanup + Articole Neasignate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Elimină pipeline-ul vechi bazat pe `deviz_cod` din `local_run.py` și adaugă secțiunea "Articole neasignate" în raportul holistic DOCX.

**Architecture:** Matching exclusiv pe `deviz_key` (hash obiectivul+obiectul+categoria). Articolele cu `deviz_key` INCOMPLETE/null → secțiune separată `unassigned_articles` în `HolisticComparison`, vizibilă în DOCX ca semnal de alarmă. Pipeline-ul vechi (`match_global` pe deviz_cod, `detect_deviz_mismatches`, `build_raport_ierarhic`) se șterge complet.

**Tech Stack:** Python 3.12+, python-docx, dataclasses, pathlib

---

## File Map

| Fișier | Modificare |
|---|---|
| `shared/group_comparator.py` | Add `unassigned_articles` field + update `_articles_by_deviz` |
| `shared/report_builder.py` | Extend `build_raport_holistic` sumar cu unassigned counts |
| `shared/report_word.py` | Add `_add_unassigned_section` + call din `_generate_word_holistic` |
| `shared/abbreviation_learner.py` | Read din `holistic_oferta_N.json` în loc de `comparatie_oferta_N.json` |
| `local_run.py` | Șterge pipeline vechi (~90 linii), adaugă log-uri holistic |

---

## Task 1: `group_comparator.py` — unassigned_articles

**Files:**
- Modify: `shared/group_comparator.py`

- [ ] **Step 1.1: Adaugă câmp `unassigned_articles` în `HolisticComparison`**

Înlocuiește blocul `@dataclass` existent (liniile 14-19):

```python
@dataclass
class HolisticComparison:
    matched_groups: list = field(default_factory=list)
    ref_only_groups: list = field(default_factory=list)
    oferta_only_groups: list = field(default_factory=list)
    ungrouped: list = field(default_factory=list)
    unassigned_articles: list = field(default_factory=list)
```

- [ ] **Step 1.2: Actualizează `_articles_by_deviz` să accepte `unassigned_out`**

Înlocuiește funcția `_articles_by_deviz` (liniile 22-37):

```python
def _articles_by_deviz(articles: list, unassigned_out: list | None = None) -> dict:
    """Grupeaza articolele dupa deviz_key (hash OBIECTIVUL+OBIECTUL+CATEGORIA).

    Articolele cu deviz_key INCOMPLETE dar cu deviz_cod prezent → unassigned_out.
    Articolele fara deviz deloc → ramân în grupul returnat cu cheie __fallback.
    """
    result = defaultdict(list)
    for a in articles:
        key = (a.get("deviz_key") or "").strip()
        if key and not key.startswith("__INCOMPLETE__"):
            result[key].append(a)
        else:
            cod = (a.get("deviz") or "").strip()
            if cod:
                if unassigned_out is not None:
                    unassigned_out.append(a)
                # NU adăugat în result → nu apare ca ref-only/oferta-only cu cheie ciudată
    return dict(result)
```

- [ ] **Step 1.3: Actualizează `compare_by_groups` să colecteze unassigned**

În `compare_by_groups`, găsește secțiunea unde se apelează `_articles_by_deviz` (liniile ~154-155):

```python
    ref_by_deviz = _articles_by_deviz(ref_valid)
    oferta_by_deviz = _articles_by_deviz(oferta_valid)
```

Înlocuiește cu:

```python
    unassigned_ref: list = []
    unassigned_oferta: list = []
    ref_by_deviz = _articles_by_deviz(ref_valid, unassigned_out=unassigned_ref)
    oferta_by_deviz = _articles_by_deviz(oferta_valid, unassigned_out=unassigned_oferta)
    result.unassigned_articles = (
        [{"source": "ref", **a} for a in unassigned_ref] +
        [{"source": "oferta", **a} for a in unassigned_oferta]
    )
```

Adaugă aceste linii ÎNAINTE de `ref_cods = set(ref_by_deviz.keys())`.

- [ ] **Step 1.4: Verificare manuală**

```bash
python3 -c "
from shared.group_comparator import HolisticComparison, _articles_by_deviz
h = HolisticComparison()
print('unassigned_articles field:', h.unassigned_articles)

arts = [
    {'deviz_key': 'abc123', 'deviz': 'BLC1', 'cod': 'IZF71C'},
    {'deviz_key': '__INCOMPLETE__xyz', 'deviz': 'BLC2', 'cod': 'CF08A'},
    {'deviz_key': '', 'deviz': 'BLC3', 'cod': 'TRA01'},
    {'deviz_key': None, 'deviz': '', 'cod': 'NO_DEVIZ'},
]
unassigned = []
result = _articles_by_deviz(arts, unassigned_out=unassigned)
print('result keys:', list(result.keys()))
print('unassigned:', [a['cod'] for a in unassigned])
# Expected: result keys: ['abc123'], unassigned: ['CF08A', 'TRA01']
"
```

Expected output:
```
unassigned_articles field: []
result keys: ['abc123']
unassigned: ['CF08A', 'TRA01']
```

- [ ] **Step 1.5: Commit**

```bash
git add shared/group_comparator.py
git commit -m "feat(group_comparator): add unassigned_articles for INCOMPLETE deviz_key articles"
```

---

## Task 2: `report_builder.py` — extinde sumar holistic

**Files:**
- Modify: `shared/report_builder.py`

- [ ] **Step 2.1: Extinde `build_raport_holistic` cu unassigned**

Găsește blocul `return {` din `build_raport_holistic` (liniile ~198-211). Înlocuiește:

```python
    return {
        "matched_groups": holistic_comparison.matched_groups,
        "ref_only_groups": holistic_comparison.ref_only_groups,
        "oferta_only_groups": holistic_comparison.oferta_only_groups,
        "ungrouped": holistic_comparison.ungrouped,
        "sumar": {
            "total_matched_groups": len(holistic_comparison.matched_groups),
            "total_ref_only_groups": len(holistic_comparison.ref_only_groups),
            "total_oferta_only_groups": len(holistic_comparison.oferta_only_groups),
            "total_ungrouped_articles": len(holistic_comparison.ungrouped),
            "total_matched_articles": total_matched_arts,
            "neconformitati_by_tip": dict(tips),
        },
    }
```

Cu:

```python
    unassigned = holistic_comparison.unassigned_articles
    return {
        "matched_groups": holistic_comparison.matched_groups,
        "ref_only_groups": holistic_comparison.ref_only_groups,
        "oferta_only_groups": holistic_comparison.oferta_only_groups,
        "ungrouped": holistic_comparison.ungrouped,
        "unassigned_articles": unassigned,
        "sumar": {
            "total_matched_groups": len(holistic_comparison.matched_groups),
            "total_ref_only_groups": len(holistic_comparison.ref_only_groups),
            "total_oferta_only_groups": len(holistic_comparison.oferta_only_groups),
            "total_ungrouped_articles": len(holistic_comparison.ungrouped),
            "total_matched_articles": total_matched_arts,
            "neconformitati_by_tip": dict(tips),
            "total_unassigned_ref": sum(1 for a in unassigned if a.get("source") == "ref"),
            "total_unassigned_oferta": sum(1 for a in unassigned if a.get("source") == "oferta"),
        },
    }
```

- [ ] **Step 2.2: Verificare manuală**

```bash
python3 -c "
from shared.group_comparator import HolisticComparison
from shared.report_builder import build_raport_holistic
h = HolisticComparison()
h.unassigned_articles = [
    {'source': 'ref', 'cod': 'IZF71C', 'deviz': 'BLC1'},
    {'source': 'oferta', 'cod': 'CF08A', 'deviz': '1-01'},
]
r = build_raport_holistic(h)
print('unassigned_articles in output:', len(r['unassigned_articles']))
print('sumar unassigned_ref:', r['sumar']['total_unassigned_ref'])
print('sumar unassigned_oferta:', r['sumar']['total_unassigned_oferta'])
# Expected: 2, 1, 1
"
```

- [ ] **Step 2.3: Commit**

```bash
git add shared/report_builder.py
git commit -m "feat(report_builder): include unassigned_articles in holistic sumar"
```

---

## Task 3: `report_word.py` — secțiune "Articole neasignate" în DOCX

**Files:**
- Modify: `shared/report_word.py`

- [ ] **Step 3.1: Adaugă funcția `_add_unassigned_section`**

Adaugă funcția ÎNAINTE de `def _generate_word_holistic` (linia ~1019):

```python
def _add_unassigned_section(doc, unassigned_articles: list) -> None:
    """Adaugă secțiunea 'Articole neasignate' la finalul documentului."""
    if not unassigned_articles:
        return

    doc.add_heading("Articole neasignate — deviz neidentificat", level=2)
    intro = doc.add_paragraph(
        "Articolele de mai jos nu au putut fi atribuite unui grup deviz "
        "(Obiectiv + Obiect + Categorie). Verificați manual pagina sursă din document."
    )
    intro.runs[0].italic = True

    tbl = doc.add_table(rows=1, cols=5)
    tbl.style = "Table Grid"
    hdr = tbl.rows[0].cells
    for i, text in enumerate(["Sursă", "Cod", "Denumire", "Deviz detectat", "Pagini"]):
        hdr[i].paragraphs[0].add_run(text).bold = True
        _set_cell_shading(hdr[i], "D3D3D3")

    for art in unassigned_articles:
        row = tbl.add_row().cells
        row[0].text = "REF" if art.get("source") == "ref" else "OFERTĂ"
        row[1].text = art.get("cod", "")
        row[2].text = (art.get("denumire") or "")[:80]
        row[3].text = art.get("deviz", "")
        pages = art.get("source_pages", [])
        row[4].text = ", ".join(str(p) for p in pages) if pages else "—"
        for cell in row:
            _set_cell_shading(cell, "FFFACD")
```

- [ ] **Step 3.2: Apelează `_add_unassigned_section` din `_generate_word_holistic`**

La finalul funcției `_generate_word_holistic`, după blocul `ungrouped` (după linia ~1087), adaugă:

```python
    # --- Articole neasignate (deviz_key INCOMPLETE) ---
    unassigned = raport_holistic.get("unassigned_articles", [])
    if unassigned:
        _add_unassigned_section(doc, unassigned)
```

- [ ] **Step 3.3: Verificare manuală DOCX**

```bash
python3 -c "
from shared.group_comparator import HolisticComparison
from shared.report_builder import build_raport_holistic
from shared.report_word import generate_word

h = HolisticComparison()
h.unassigned_articles = [
    {'source': 'ref', 'cod': 'IZF71C', 'denumire': 'Sistem termoizolant', 'deviz': 'BLC1', 'source_pages': [42]},
    {'source': 'oferta', 'cod': 'CF08A', 'denumire': 'Cofraj stalpi', 'deviz': '1-01', 'source_pages': [31, 32]},
]
raport = build_raport_holistic(h)
comp = {
    'oferta_nr': 99,
    'source_file': 'test.pdf',
    'ofertant': 'Test',
    'raport_holistic': raport,
    'ref_art_count': 10,
    'oferta_art_count': 10,
}
session = {'client_name': 'Test Client'}
docx_bytes = generate_word(session, comp)
open('/tmp/test_unassigned.docx', 'wb').write(docx_bytes)
print('DOCX scris la /tmp/test_unassigned.docx — verifică manual secțiunea Articole neasignate')
"
```

Deschide `/tmp/test_unassigned.docx` și verifică că secțiunea "Articole neasignate" apare cu 2 rânduri galbene.

- [ ] **Step 3.4: Commit**

```bash
git add shared/report_word.py
git commit -m "feat(report_word): add 'Articole neasignate' section to holistic DOCX"
```

---

## Task 4: `abbreviation_learner.py` — citire din holistic JSON

**Files:**
- Modify: `shared/abbreviation_learner.py`

- [ ] **Step 4.1: Înlocuiește bucla de citire**

Găsește funcția `_collect_borderline_pairs` (în jurul liniei 50). Înlocuiește bucla de citire:

```python
    # ÎNAINTE (de înlocuit):
    pairs = []
    for i in range(1, 10):
        f = cfg.output_dir / f"comparatie_oferta_{i}.json"
        if not f.exists():
            continue
        comp = json.loads(f.read_text(encoding="utf-8"))
        for nc in comp.get("neconformitati", []):
            if nc.get("tip") != "DESCRIERE_DIFERITA":
                continue
            sim = nc.get("similaritate", 0)
            if BORDERLINE_LOW <= sim <= BORDERLINE_HIGH:
                pairs.append({
                    "ref": nc.get("ref", ""),
                    "oferta": nc.get("oferta", ""),
                    "sim": sim,
                    "oferta_nr": i,
                    "ref_cod": nc.get("ref_cod", ""),
                })
```

Cu:

```python
    # DUPĂ (citește din holistic_oferta_N.json):
    pairs = []
    for i in range(1, 10):
        f = cfg.output_dir / f"holistic_oferta_{i}.json"
        if not f.exists():
            continue
        holistic = json.loads(f.read_text(encoding="utf-8"))
        for mg in holistic.get("matched_groups", []):
            for nc in mg.get("neconformitati", []):
                if nc.get("tip") != "DESCRIERE_DIFERITA":
                    continue
                sim = nc.get("similaritate", 0)
                if BORDERLINE_LOW <= sim <= BORDERLINE_HIGH:
                    pairs.append({
                        "ref": nc.get("ref", ""),
                        "oferta": nc.get("oferta", ""),
                        "sim": sim,
                        "oferta_nr": i,
                        "ref_cod": nc.get("ref_cod", ""),
                    })
```

- [ ] **Step 4.2: Verificare manuală**

```bash
python3 -c "
from shared.abbreviation_learner import _collect_borderline_pairs
# Verificare că funcția nu crașează (va returna [] dacă nu există holistic JSONs)
# sau perechi reale dacă există
try:
    pairs = _collect_borderline_pairs('Blocuri Racari')
    print(f'Perechi borderline: {len(pairs)}')
except Exception as e:
    print(f'ERROR: {e}')
"
```

Expected: fie `Perechi borderline: N` (N ≥ 0), fie nicio eroare.

- [ ] **Step 4.3: Commit**

```bash
git add shared/abbreviation_learner.py
git commit -m "fix(abbreviation_learner): read DESCRIERE_DIFERITA from holistic_oferta_N.json"
```

---

## Task 5: `local_run.py` — eliminare pipeline vechi

**Files:**
- Modify: `local_run.py`

- [ ] **Step 5.1: Șterge import-urile pipeline-ului vechi**

Găsește linia (~32):
```python
from shared.report_json import generate_json_by_deviz
```
Șterge această linie complet.

Găsește în interiorul funcției `compare_oferta` (~linia 986):
```python
from shared.deviz_mismatch_detector import detect_deviz_mismatches
```
Șterge această linie complet.

- [ ] **Step 5.2: Șterge blocul `detect_deviz_mismatches` + `_deviz_remap`**

Șterge integral blocul (~liniile 1068-1090):

```python
    # Detectare deviz mismatch (devize din oferta cu cod diferit dar articole similare)
    deviz_mismatches = detect_deviz_mismatches(ref_articles, oferta_norm)
    _deviz_remap: dict = {}  # oferta_deviz → ref_deviz pentru mismatch-uri cu overlap inalt
    if deviz_mismatches:
        for m in deviz_mismatches:
            logger.warning(
                f"  [DEVIZ_MISMATCH] Deviz {m['oferta_deviz']} din oferta (~{m['overlap_score']:.0%} overlap) "
                f"pare echivalentul lui {m['ref_deviz']} din referinta "
                f"({m['oferta_art_count']} vs {m['ref_art_count']} articole)"
            )
            # Remap automat cand overlap e foarte inalt (≥90%): redenumeste codul deviz
            # in articolele ofertei astfel incat Layer 1 sa le potriveasca cu referinta.
            # Ofertantul a numerotata devizele diferit (226113 vs 226118) — acelasi continut.
            if m['overlap_score'] >= 0.9:
                _deviz_remap[m['oferta_deviz']] = m['ref_deviz']

    if _deviz_remap:
        for art in oferta_norm:
            old = art.get('deviz', '')
            if old in _deviz_remap:
                art['deviz'] = _deviz_remap[old]
                art['_deviz_original'] = old  # pastram originalul pt raport
        logger.info(f"  Remap devize oferta: {_deviz_remap}")
```

- [ ] **Step 5.3: Șterge apelul `match_global`**

Șterge blocul (~liniile 1092-1095):

```python
    # Matching 3 straturi — returneaza si cheile REF match-uite
    neconformitati, matches, matched_ref_keys, articole_fara_deviz = match_global(
        ref_articles, oferta_norm, client, model, include_prices=include_prices
    )
```

- [ ] **Step 5.4: Șterge `mark_suspicious_extras` și `subcomp_anomalies` append**

Șterge blocul (~liniile 1160-1183):

```python
    # Build ref DI text from JSON if provided, otherwise use empty string
    ref_di_text = ""
    if ref_di_json:
        ref_di_text = json.dumps(ref_di_json, ensure_ascii=False)
    neconformitati = mark_suspicious_extras(neconformitati, ref_di_text, ref_articole=ref_articles)

    # Adauga anomalii subcomponente la neconformitati (Phase 2)
    for anom in subcomp_anomalies:
        neconformitati.append({
            'tip': 'SUBCOMP_EXTRA',
            'deviz_ref': anom['deviz'],
            'deviz_denumire': f'Subcomponent anomaly',
            'is_component': True,
            'ref_cod': f"SUBCOMP:{anom['subcomp_code']}",
            'ref_denumire': f"Unknown subcomponent code {anom['subcomp_code']}",
            'ref_um': '',
            'ref_cantitate': 0,
            'oferta_cod': anom['cod'],
            'oferta_denom': anom['subcomp_code'],
            'oferta_denumire': f"Subcomponent code {anom['subcomp_code']}",
            'oferta_um': '',
            'oferta_cantitate': 0,
            'motiv': f'Articol {anom["cod"]}: contains subcomponent code {anom["subcomp_code"]} not found in reference',
        })
```

Șterge și `import mark_suspicious_extras` dacă există ca import de modul (caută cu `grep -n mark_suspicious_extras local_run.py`).

- [ ] **Step 5.5: Șterge calculul `_devize_extra` / `_devize_lipsa`**

Șterge blocul (~liniile 1185-1218):

```python
    # Colecteaza devize_extra si devize_lipsa pentru raport
    from collections import defaultdict as _defaultdict
    ref_devize_set = {a.get('deviz', '') for a in ref_articles if a.get('deviz')}
    oferta_devize_set = {a.get('deviz', '') for a in oferta_norm if a.get('deviz')}

    oferta_devize_art_count = _defaultdict(int)
    for a in oferta_norm:
        oferta_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_art_count = _defaultdict(int)
    for a in ref_articles:
        ref_devize_art_count[a.get('deviz', '')] += 1
    ref_devize_den = {}
    for a in ref_articles:
        d = a.get('deviz', ''); n = a.get('deviz_denumire', '')
        if d and n:
            ref_devize_den[d] = n

    _devize_extra = [
        {
            'deviz': d,
            'denumire': next((a.get('deviz_denumire', '') for a in oferta_norm
                              if a.get('deviz') == d), ''),
            'art_count': oferta_devize_art_count[d],
        }
        for d in sorted(oferta_devize_set - ref_devize_set - {''})
    ]
    _devize_lipsa = [
        {
            'deviz': d,
            'denumire': ref_devize_den.get(d, ''),
            'art_count': ref_devize_art_count[d],
        }
        for d in sorted(ref_devize_set - oferta_devize_set - {''})
    ]
```

- [ ] **Step 5.6: Șterge scrierile JSON vechi**

Șterge blocul `comparatie_oferta_N.json` (~liniile 1220-1233):

```python
    # Salveaza JSON comparatie
    output_dir = client_config.output_dir if client_config else OUTPUT_DIR
    comparatie_path = output_dir / f"comparatie_oferta_{oferta_nr}.json"
    logger.debug(f"DEBUG: Before JSON save, neconformitati has {len(neconformitati)} items")
    comparatie_path.write_text(
        json.dumps({
            "oferta_nr": oferta_nr,
            "neconformitati": neconformitati,
            "total_neconformitati": len(neconformitati),
            "matches": len(matches),
            "deviz_mismatches": deviz_mismatches,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
```

Adaugă în loc (după holistic JSON write, linia ~1286):
```python
    output_dir = client_config.output_dir if client_config else OUTPUT_DIR
```
(dacă `output_dir` nu mai e definit în altă parte — verifică că rămâne definit pentru `holistic_path`).

Șterge blocul `comparatie_deviz_oferta_N.json` (~liniile 407-415 din funcția `run_client`):

```python
        # Generate JSON report grouped by deviz
        if comp and comp.get('neconformitati'):
            session = {"client_name": client_config.name if client_config else "", "obiect_investitii": ""}
            json_report = generate_json_by_deviz(session, comp)

            json_file = client_config.output_dir / f"comparatie_deviz_oferta_{oferta_nr}.json"
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(json_report, f, ensure_ascii=False, indent=2)

            logger.info(f"  JSON by deviz: {json_file.name}")
```

- [ ] **Step 5.7: Șterge log-urile vechi, adaugă log-uri holistic**

Șterge (~liniile 1235-1237):

```python
    tipuri = Counter(n["tip"] for n in neconformitati)
    logger.info(f"  Neconformitati: {dict(tipuri)} (total: {len(neconformitati)})")
    logger.info(f"  Matched: {len(matches)} articole")
```

Adaugă DUPĂ linia `logger.info(f"  [HOLISTIC] ...")` existentă (~linia 1151):

```python
    _h_sumar = raport_holistic.get("sumar", {})
    logger.info(
        f"  [HOLISTIC] Neconformitati: {_h_sumar.get('neconformitati_by_tip', {})} "
        f"(total: {sum(_h_sumar.get('neconformitati_by_tip', {}).values())})"
    )
    logger.info(f"  [HOLISTIC] Matched: {_h_sumar.get('total_matched_articles', 0)} articole")
    _n_unassigned = _h_sumar.get('total_unassigned_ref', 0) + _h_sumar.get('total_unassigned_oferta', 0)
    if _n_unassigned:
        logger.warning(f"  [HOLISTIC] Neasignate: {_n_unassigned} articole fara deviz_key valid")
```

- [ ] **Step 5.8: Șterge `build_raport_ierarhic` și actualizează `comp`**

Șterge (~liniile 1240-1242):

```python
    from shared.report_builder import build_raport_ierarhic
    raport_ierarhic = build_raport_ierarhic(ref_articles, neconformitati, matches,
                                            articole_fara_deviz=articole_fara_deviz)
```

Actualizează dict-ul `comp` (~liniile 1245-1256) — șterge cheile `neconformitati`, `raport_ierarhic`, `deviz_mismatches` care nu mai există:

```python
    comp = {
        "oferta_nr": oferta_nr,
        "source_file": oferta_path.name,
        "ofertant": ofertant_name or f"Oferta {oferta_nr}",
        "ref_art_count": len(ref_articles),
        "oferta_art_count": len(oferta_norm),
        "ref_articles": ref_articles,
        "oferta_articles": oferta_norm,
        "raport_holistic": raport_holistic,
    }
```

- [ ] **Step 5.9: Actualizează apelul `generate_word` — șterge `devize_extra`/`devize_lipsa`**

Înlocuiește (~liniile 1272-1278):

```python
    docx_bytes = generate_word(
        session, comp,
        comparison_mode=comparison_mode,
        devize_extra=_devize_extra,
        devize_lipsa=_devize_lipsa,
        subcomponent_mode=subcomponent_mode,
    )
```

Cu:

```python
    docx_bytes = generate_word(
        session, comp,
        comparison_mode=comparison_mode,
        subcomponent_mode=subcomponent_mode,
    )
```

- [ ] **Step 5.10: Actualizează `return`**

Găsește (~linia 1295):
```python
    return neconformitati, comp
```

Înlocuiește cu:
```python
    return comp
```

Actualizează și toate call-site-urile lui `compare_oferta` care despachetează returul ca `neconformitati, comp = compare_oferta(...)`:

```bash
grep -n "compare_oferta\|neconformitati, comp" local_run.py
```

Schimbă `neconformitati, comp = compare_oferta(...)` în `comp = compare_oferta(...)` și șterge orice referință la `neconformitati` din `run_client`.

- [ ] **Step 5.11: Verificare sintaxă**

```bash
python3 -m py_compile local_run.py && echo "OK — fara erori de sintaxa"
```

- [ ] **Step 5.12: Commit**

```bash
git add local_run.py
git commit -m "refactor(local_run): remove old match_global pipeline, use holistic exclusively"
```

---

## Task 6: Verificare integrare

- [ ] **Step 6.1: Rulează pipeline BR complet**

```bash
.venv/bin/python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log
```

Verifică în output:
- NU apare `[DEVIZ_MISMATCH]` (WARNING cu overlap %)
- NU apare `Neconformitati: {'DEVIZ_MISMATCH': ...}`
- APARE `[HOLISTIC] Neconformitati: {...}` (fără DEVIZ_MISMATCH)
- APARE `[HOLISTIC] Matched: N articole`
- Dacă există articole neasignate: `[HOLISTIC] Neasignate: N articole`

- [ ] **Step 6.2: Verifică DOCX O1 și O3**

Deschide `output_AO/Blocuri Racari/Raport_Oferta_1.docx` și `Raport_Oferta_3.docx`:
- Raportul se generează fără erori
- La final, dacă există articole neasignate, apare secțiunea "Articole neasignate" cu fundal galben
- Fără secțiune dacă toate articolele au deviz_key valid

- [ ] **Step 6.3: Verifică `abbreviation_learner` nu crașează**

```bash
python3 -c "from shared.abbreviation_learner import _collect_borderline_pairs; print(_collect_borderline_pairs('Blocuri Racari')[:2])"
```

Expected: listă (posibil goală), fără erori.

- [ ] **Step 6.4: Șterge fișierele JSON vechi din output**

```bash
find output_AO -name "comparatie_oferta_*.json" -o -name "comparatie_deviz_oferta_*.json" | xargs rm -f
```

- [ ] **Step 6.5: Commit final**

```bash
git add -A
git commit -m "chore: remove stale comparatie_oferta_*.json output files"
git tag v11.1.3
```

---

## Note importante

- `shared/deviz_mismatch_detector.py` — lasă neatins (tool independent, nu e apelat din pipeline după cleanup)
- `shared/diagnostics_builder.py` / `shared/diagnostics_word.py` — lasă neatinse (tool offline)
- `shared/report_json.py` — lasă neatins dacă `generate_json_by_deviz` e singurul export; șterge dacă vrei cleanup total (verifică cu `grep -rn "report_json" . --include="*.py"`)
- Import `match_global` din `AgentComparator_local` rămâne în `group_comparator.py` (folosit în `_compare_articles_in_group` pentru matching within-group — acesta NU se șterge)
