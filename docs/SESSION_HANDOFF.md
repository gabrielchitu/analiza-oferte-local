# Session Handoff — Analizator Oferte Constructii

> Citeste acest fisier la inceputul unei sesiuni noi. Contine starea actuala a proiectului.
> **Ultima actualizare:** 2026-06-11 | **Versiune:** v3

---

## Ce este acest proiect

Pipeline Python care analizeaza oferte de constructii romanesti:
1. Azure Document Intelligence JSON (di_referinta.json + di_oferta_N.json) per client
2. Extrage articolele din F3 (Lista cu cantitati de lucrari) folosind regex state machine
3. Compara oferta cu referinta pe baza de GRUPURI (OBIECTIVUL + Obiectul + Categoria)
4. Semantic comparator: detecteaza COD_NORMATIV_DIFERIT si SPECIFICATIE_DIFERITA
5. Genereaza Raport_Oferta_N.docx (NC-only) si Comparatie_Lista_Oferta_N.docx (toate articolele, landscape)

**Repo:** `main` branch, tag `v3` | **Entry point:** `python3 multi_client_run.py --client "NumeClient"`

---

## Stare Clienti (v3)

| Client | Status | Oferte | Observatii |
|--------|--------|--------|------------|
| Blocuri Racari | ✅ OK | 1-4 | 35 grupuri matched, 0 violari invariant |
| BR BLOC A/A2/A3/A4/B/C | ✅ OK | 1-4 | 0 violari invariant per bloc |
| Scoala Dragomiresti | ✅ OK | 1-2 | 22 grupuri matched, 0 violari |
| Scoala Sportiva Racari | ⚠️ PARTIAL | — | Structural mismatch — vezi Known Issues |
| Camin Maneciu | ✅ OK | 1-2 | 35 grupuri matched, 0 violari, 18 MEDIUM genuine |
| Drum Tatarani | ✅ OK | 1-2 | 189/189 grupuri matched O1+O2, 0 CRITICAL/HIGH |
| **CAV Maneciu** | ✅ **VERIFICAT** | **1-5** | 11/11 O1/O3-O5, 10/11 O2; 0 violari; **21/21 NC comisie acoperite** |

---

## Baseline Verificare CAV Maneciu (v3) — Ground Truth ✅

Documente comisie in `input_AO/CAV Maneciu/`:

| Doc | Ofertant | Oferta | NC F3 | Acoperire |
|-----|----------|--------|--------|-----------|
| `SOLICI~4.DOC` | DARTIM OVY CONSTRUCT / TOP DESIGN | O1 | 16 | **16/16** ✅ |
| `SOLICI~2.DOC` | DUPLEX DISTRIBUTION / IMPA&I | O3 | 1 | **1/1** ✅ |
| `SOLICI~3.DOC` | TROIA PREMIUM CONSTRUCT | O4 | 1 | **1/1** ✅ |
| `SO092A~1.DOC` | ZEB CITY / ROBSAN ALEXINSTAL | O5 | 3 | **3/3** ✅ |

**Total: 21/21 NC din documentele comisiei acoperite de pipeline.**

---

## Invariantul de Baza

**"0-NC matched group → ref_main_count == off_main_count"**

Ecuatia: `ref_main - LIPSA = off_main - EXTRA`
- `ref_main` / `off_main` = articole cu `is_component=False AND cantitate > 0`
- Violare SILENTIOASA = BUG. Violare cu NC = asteptat.

**Verificat: 0 violari silentioase pe toti clientii activi.**

---

## Fix-uri Majore v3

### Comparatie Lista Layout (shared/comparatie_lista_writer.py)
- `tblGrid` cu latimi exacte in twips → coloane stabile
- Margini celule: 1.9mm → top/bottom 0.5mm, stanga/dreapta 1mm
- `keep_with_next=True` pe header grup
- Repeat header rows pe fiecare pagina
- Coloana Cod scoasa din noWrap (coduri lungi nu mai debordeza)
- Eliminat duplicate `_shade` calls

### Semantic Comparator (shared/semantic_comparator.py)
**Pass 1 — `semantic_nr_match`:** LIPSA+EXTRA la acelasi nr_ordine → `COD_NORMATIV_DIFERIT`
**Pass 2 — `semantic_spec_check`:** perechi matched cu spec numerica diferita → `SPECIFICATIE_DIFERITA`

### Scatter Counter Fix (shared/f3_regex_parser.py)
`last_scatter_counter` in `_preprocess_scattered_format`: previne ca pretul unitatii
(ex: `4` lei/luna pt WC) sa fie citit ca nr_ordine al articolului urmator (BAZIN).
Rezultat: BAZIN CAV Maneciu extras corect ca nr=5, nu nr=4.1.

---

## Metrici CAV Maneciu (v3)

| Oferta | Matched | Ref-only | Off-only | Total NC |
|--------|---------|----------|----------|----------|
| O1 | 11/11 | 0 | 0 | 134 |
| O2 | 10/11 | 1 | 0 | 19 |
| O3 | 11/11 | 0 | 1 | 8 |
| O4 | 11/11 | 0 | 1 | 16 |
| O5 | 11/11 | 0 | 0 | 95 (83 EXTRA = subcomp materiale) |

---

## Arhitectura Cheie

### deviz_key = md5(OBIECTIVUL|OBIECTUL|CATEGORIA)
**NICIODATA** `deviz_cod` string ca lookup key — instabil, duplicat.

### Group Matching
```
Phase 1   — deviz_key exact hash
Phase 1.5 — deviz_cod prefix al offer.CATEGORIA (ISDP/eDevize compat)
Phase 2a  — group_match_knowledge.json (cache LLM)
Phase 2b  — LLM fallback Claude API
```

### Article Matching
```
Layer 1   — N:M exact (deviz, cod)
Layer 2   — _normalize_cod: I→1, O→0, strip $
Layer 2.1 — trailing digit: IC35D ↔ IC35D1
Layer 2.5 — SequenceMatcher ≥ 0.80 (OCR)
```

### IMPORTANT: f3_markers_knowledge.json = MANUAL ONLY
ALL LLM marker learning DISABLED. Auto-learning a generat false positives ("Pag N" ca end-marker → 0 articole extrase).

---

## Fisiere Cheie

| Fisier | Responsabilitate |
|--------|-----------------|
| `multi_client_run.py` | Entry point |
| `local_run.py` | Pipeline orchestration |
| `AgentComparator_local.py` | Matching engine Layer 1-2.5 |
| `shared/group_comparator.py` | Group matching Phase 1-2 |
| `shared/f3_regex_parser.py` | Regex state machine + scatter fix |
| `shared/deviz_header_extractor.py` | DevizHeader per grup, client-specific patterns |
| `shared/semantic_comparator.py` | Pass1 COD_NORMATIV_DIFERIT + Pass2 SPECIFICATIE_DIFERITA |
| `shared/comparatie_lista_writer.py` | DOCX comparatie landscape (toate articolele) |
| `shared/report_word.py` | DOCX raport NC-only |
| `gen_comparatie_lista.py` | CLI generator Comparatie_Lista_Oferta_N.docx |
| `shared/group_match_knowledge.json` | Cache LLM per client — nu sterge |
| `shared/f3_markers_knowledge.json` | Markeri F3 — MANUAL ONLY |
| `shared/ocr_patterns_knowledge.json` | OCR patterns — MANUAL ONLY |
| `verify_agent.py` | Verification agent (6 checks, loop, MD report) |

---

## Known Issues

### SSR — Structural Mismatch (Scoala Sportiva Racari)
- Ref: 1-2 grupuri per obiect | Oferta: 8-12 sub-devize per obiect
- Matching bijective nu suporta 1→many → 0 matched
- Fix: strategie noua in group_comparator (low priority)

### CAV Maneciu O2 — 1 ref_only
Grup absent din oferta O2 (DUPLEX). Legitim sau alt header — neinvestigat.

---

## Comenzi Utile

```bash
# Rulare client
rtk proxy python3 multi_client_run.py --client "CAV Maneciu" 2>&1 | rtk log

# Genereaza comparatie cu TOATE articolele
python3 gen_comparatie_lista.py --client "CAV Maneciu"
python3 gen_comparatie_lista.py --client "CAV Maneciu" --oferta 1

# Sumar holistic rapid
python3 -c "
import json, os; os.chdir('/Users/gabrielchitu/analiza-oferte-local')
from collections import Counter
for i in range(1,6):
    d = json.load(open(f'output_AO/CAV Maneciu/holistic_oferta_{i}.json'))
    mg=len(d.get('matched_groups',[])); ro=len(d.get('ref_only_groups',[])); oo=len(d.get('oferta_only_groups',[]))
    cnt=Counter(nc.get('tip') for g in d.get('matched_groups',[]) for nc in g.get('neconformitati',[]))
    print(f'O{i}: matched={mg} ref={ro} off={oo} nc={sum(cnt.values())}')
"

# Verification agent
python3 verify_agent.py --client "CAV Maneciu" --verify-only

# Teste
pytest tests/ -q --ignore=tests/test_compound_deviz_extraction.py --ignore=tests/test_subcomponent_matching.py

# Reset checkpoints
find "output_AO/CAV Maneciu/checkpoints" -name "*.json" -delete
```

---

## Cross-Check Blocuri Racari vs Suma Blocuri Individuale

`output_AO/Raport_Verificare_Blocuri_Racari.docx`: BR consolidat 601 articole vs suma blocuri 628.
Diferenta de 27 = 9 coduri × 3 aparitii (3 obiecte in PDF consolidat vs 6 blocuri). NU eroare pipeline.

---

## Git State (v3, 2026-06-11)

```
tag: v3 → HEAD main (2026-06-11)
tag: 12.0 → commit eb04c83 (baza stabila)
```

Commits recente (→ v3):
- `v3 tag`  fix(report): comparatie layout — tblGrid, cell margins, keep_with_next, repeat headers + baseline docs
- `52811c7` fix(report): COD_NORMATIV_DIFERIT + SPECIFICATIE_DIFERITA in comparatie_lista_writer
- `b30d256` fix(semantic): pre-filter SPECIFICATIE_DIFERITA numeric-diff-only
- `fd5c0c7` feat(report): render COD_NORMATIV_DIFERIT + SPECIFICATIE_DIFERITA in DOCX
- `3049246` fix(parser): scatter counter auto-increment — BAZIN nr=4.1→5 (CAV Maneciu OS)
- `930965c` fix(parser): exclude material-spec codes (BCR4/5, C20/25) from scatter preprocessor
- `38a0d01` fix(knowledge): DT Padurii match corectat PA0005 Marcaje
