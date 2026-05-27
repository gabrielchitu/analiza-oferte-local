# Session Handoff — Analizator Oferte Constructii

> Citeste acest fisier la inceputul unei sesiuni noi. Contine starea actuala a proiectului.
> **Ultima actualizare:** 2026-05-27 | **Versiune:** v12.1

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. Azure Document Intelligence JSON (di_referinta.json + di_oferta_N.json) per client
2. Extrage articolele din F3 (Lista cu cantitati de lucrari) folosind regex state machine
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Genereaza rapoarte DOCX cu neconformitati per grup

**Repo:** `main` branch | **Entry point:** `python3 multi_client_run.py --client "NumeClient"`

---

## Stare Clienti (v12.1)

| Client | Status | Oferte | Observatii |
|--------|--------|--------|------------|
| Blocuri Racari | ✅ OK | 1-4 | 35 grupuri matched, 0 violari invariant |
| BR BLOC A | ✅ OK | 1-4 | 0 violari invariant |
| BR BLOC A2 | ✅ OK | 1-4 | 0 violari invariant |
| BR BLOC A3 | ✅ OK | 1-4 | 0 violari invariant |
| BR BLOC A4 | ✅ OK | 1-4 | 0 violari invariant |
| BR BLOC B  | ✅ OK | 1-4 | 0 violari invariant |
| BR BLOC C  | ✅ OK | 1-4 | 0 violari invariant |
| Scoala Dragomiresti | ✅ OK | 1-2 | 22 grupuri matched, 0 violari |
| Scoala Sportiva Racari | ⚠️ PARTIAL | — | Structural mismatch — vezi Known Issues |
| Camin Maneciu | ⚠️ HIGH_EXTRA | 1-2 | 0 CRITICAL/HIGH, 37 MEDIUM (HIGH_EXTRA extractie), 733 NC total |

---

## Invariantul de Baza

**"0-NC matched group → ref_main_count == off_main_count"**

Ecuatia echivalenta: `ref_main - LIPSA = off_main - EXTRA`

- `ref_main` / `off_main` = articole cu `is_component=False AND cantitate > 0`
- Violare SILENTIOASA (fara NC) = BUG in pipeline
- Violare cu NC = ASTEPTAT (ex. `DIFERENTA_CAMP(tip_articol)`)

**Verificat: 0 violari silentioase pe 7 clienti × 4 oferte = 28 rulari (v12.0)**

---

## Fix-uri Majore v12.0 (commits d1d8bc0, 1814cd2, c295137)

### Parser (c295137)
- `NR_SUBITEM` (`x.y` decimal): seteaza `explicit_component_marker=True` numai cand `base_nr == last_nr_crt`
- Same-nr inline: seteaza `explicit_component_marker` cand nr == `current_parent_nr`
- Linked markers (`NR_LINKED`, `BARE_L`, `DOT_L`): seteaza `explicit_component_marker=True`

### Comparator (d1d8bc0)
- **Layer 2 COD_SIMILAR:** eliminat `and (diffs or arith)` guard — perechi OCR (SA131↔SA13I, IZLO5XF↔IZL05XF) genereaza COD_SIMILAR. Cauza: `_normalize_cod` mapeaza I→1/O→0, deci normalizeaza identic → match Layer 2, NU Layer 2.5
- **is_component mismatch Layer 1:** genereaza `DIFERENTA_CAMP(tip_articol)` cand articolul e `is_component=True` in ref dar `False` in oferta (fix `$4202729` SD)
- **Eliminat fuzzy denomination matching** (45% threshold absorba silentios ARTICOL_EXTRA NCs)
- **`_dedup_articles`** in `group_comparator.py` — fix BLC7 grup duplicat (BR O3)

### Comparator (1814cd2)
- **EXTRA loop:** cand `norm_cod in ref_component_cods` dar `oferta_art.is_component=False` → genereaza `DIFERENTA_CAMP(tip_articol)` in loc de `continue` silentios. Fix CK25A/IZK03C1 (BR BLOC A)

### Report (f6cd0ad → 61879bc)
- **`_count_main_articles`:** filtru `cantitate > 0` — aliniat cu `match_global`
- **`_add_group_totals_row`:** rand gri TOTAL GRUP dupa fiecare grup in DOCX holistic
- **Eliminat** `oferta_N.json` garbage output din `local_run.py`

---

## Arhitectura Cheie

### deviz_key = md5(OBIECTIVUL|OBIECTUL|CATEGORIA)
- **NICIODATA** `deviz_cod` string (ex "BLC7") ca lookup key — instabil, duplicat
- Mai multe grupuri logice pot imparti acelasi deviz_cod (BLC5 = A, A2, A3, A4, B, C)

### Group Matching (shared/group_comparator.py)
```
Phase 1   — deviz_key exact (same hash ref si oferta)
Phase 1.5 — deviz_cod prefix al offer.CATEGORIA (ISDP/eDevize compat)
Phase 2a  — group_match_knowledge.json (per-client cache LLM)
Phase 2b  — LLM fallback Claude API (chunk=15, max_tokens=2000)
```

### Matching Engine (AgentComparator_local.py)
```
Layer 1   — N:M exact (deviz, cod)
Layer 2   — _normalize_cod: I→1, O→0, strip $
Layer 2.1 — trailing digit: IC35D ↔ IC35D1
Layer 2.5 — SequenceMatcher ≥ 0.80 (OCR)
Layer 3   — LLM fuzzy (DISABLED)
```

### IMPORTANT: f3_markers_knowledge.json
**MANUAL ONLY.** ALL LLM marker learning DISABLED in `f3_page_classifier.py`.
Motivatie: auto-invatate "Pag N" ca end-markers → 0 articole extrase.
Nu adauga `"source": "llm"` in acest fisier.

---

## Fisiere Cheie

| Fisier | Responsabilitate |
|--------|-----------------|
| `multi_client_run.py` | Entry point — meniu sau `--client` |
| `local_run.py` | Pipeline orchestration (extract + compare + report) |
| `AgentComparator_local.py` | Matching engine Layer 1-2.5 |
| `shared/group_comparator.py` | Holistic group matching, Phase 1/1.5/2 |
| `shared/f3_page_classifier.py` | Clasificare pagini F3, deviz_cod extraction |
| `shared/f3_extractor.py` | Extragere articole per grup pagini |
| `shared/f3_regex_parser.py` | Regex state machine (1600+ linii) |
| `shared/report_word.py` | DOCX generation, holistic + flat |
| `shared/group_match_knowledge.json` | Cache LLM per client — nu sterge |
| `shared/f3_markers_knowledge.json` | Markeri F3 — MANUAL ONLY |
| `shared/pattern_library.json` | Pattern detection |
| `verify_agent.py` | Verification agent CLI — 6 checks, loop, MD report |
| `shared/pipeline_verifier.py` | 6 structural checks pe holistic_oferta_N.json |
| `shared/agent_knowledge.json` | Jurnal runs + thresholds per client |
| `shared/ocr_patterns_knowledge.json` | OCR patterns aditionale (additive, MANUAL ONLY) |

---

## Known Issues (pentru sesiunea urmatoare)

### SSR — Structural Mismatch (Scoala Sportiva Racari)
- Ref: 1-2 grupuri per obiect (OBIECTIVUL|OBIECTUL|CATEGORIA)
- Oferta: 8-12 sub-devize per obiect
- Phase 1.5 rezolva partial (deviz_cod prefix matching)
- Restul ramane `oferta_only` — matching bijective nu suporta 1→many
- **Fix ar necesita:** strategie noua unde un ref grup poate acoperi mai multi offer sub-devize

### Camin Maneciu — HIGH_EXTRA (v12.1)
- Rulat v12.1: 0 CRITICAL, 0 HIGH, 37 MEDIUM (HIGH_EXTRA/LIPSA), 733 NC total
- Pattern: EXTRA mari in fiecare grup de instalatii = fragmentare articole in oferta vs referinta
- Causa probabila: subcomponente ofertate ca articole principale, sau devize cu granularitate diferita
- Nu sunt grupuri inventate (0 oferta_only_groups) — toate matched, problema la nivel articol

---

## Comenzi Utile

```bash
# Rulare client
rtk proxy python3 multi_client_run.py --client "Blocuri Racari" 2>&1 | rtk log

# Sumar holistic rapid
rtk proxy python3 -c "
import json; from pathlib import Path
for f in sorted(Path('output_AO/Blocuri Racari').glob('holistic_oferta_*.json')):
    h = json.loads(f.read_text())
    mg = len(h.get('matched_groups',[])); ro = len(h.get('ref_only_groups',[])); oo = len(h.get('oferta_only_groups',[]))
    print(f.name, f'matched={mg} ref_only={ro} oferta_only={oo}')
"

# Verificare invariant rapid
rtk proxy python3 -c "
import json
def get_main(arts): return [a for a in arts if not a.get('is_component') and (a.get('cantitate') or 0) > 0]
data = json.load(open('output_AO/Blocuri Racari/holistic_oferta_1.json'))
silent = sum(1 for g in data.get('matched_groups',[])
    if not g.get('neconformitati') and
    len(get_main(g.get('ref_articles',[]))) != len(get_main(g.get('oferta_articles',[]))))
print(f'Silent violations: {silent}')
"

# Teste
rtk proxy python3 -m pytest tests/ -q \
  --ignore=tests/test_compound_deviz_extraction.py \
  --ignore=tests/test_subcomponent_matching.py

# Reset checkpoints client
find "output_AO/Scoala Dragomiresti/checkpoints" -name "*.json" -delete

# Verification agent
python3 verify_agent.py --client "Camin Maneciu" --verify-only
python3 verify_agent.py --client "Camin Maneciu" --max-iter 2
```

---

## Cross-Check Blocuri Racari vs Suma Blocuri Individuale

Documentat in `output_AO/Raport_Verificare_Blocuri_Racari.docx`.

**Concluzie:** BR consolidat (601 articole) ≠ suma blocuri (628). Diferenta de 27 = 9 coduri × 3 aparitii (3 obiecte in PDF consolidat vs 6 blocuri individuale). NU eroare pipeline.

Coduri afectate: AUT6752, CE23A1, CO06B, RPCP16C, SE03A01, TRA01A20, TSD16B1, TSE01D1, VC03A01.

---

## Git State (v12.0, 2026-05-27)

```
tag: 12.0 → commit eb04c83
```

Commits principale din aceasta versiune:
- `eb04c83` chore(v12.0): knowledge updates, 6 BR bloc clients, verification report
- `1814cd2` fix(comparator): surface ref-component/offer-main reclassification as NC
- `d372876` docs(local_run): update output docstring
- `8a21695` docs(claude): update invariant fix summary
- `d1d8bc0` fix(comparator): fix COD_SIMILAR suppression + is_component mismatch
- `c295137` fix(parser): correct subcomponent detection
