# Architecture Schema — Diagrama Completă Flux
**Actualizat:** 2026-05-22 | **Versiune:** v8.0

---

## Flux Principal — Big Picture

```
┌──────────────────────────────────────────────────────────────────────────┐
│  INPUT: DI JSON files per client                                         │
│  input_AO/<ClientName>/                                                  │
│   ├── di_referinta.json   (caiet de sarcini)                             │
│   ├── di_oferta_1.json    (oferta 1)                                     │
│   ├── di_oferta_2.json    ...                                            │
│   └── di_oferta_N.json                                                   │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  ENTRY POINT: multi_client_run.py                                        │
│   ├── detecteaza clienti (shared/client_config.py)                       │
│   ├── meniu interactiv sau --client "NumeClient"                         │
│   └── apeleaza run_pipeline(client_config)  ──→  local_run.py           │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 1 — PAGE CLASSIFICATION                                           ║
║  shared/f3_page_classifier.py                                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Per document (referinta + fiecare oferta):                             ║
║                                                                          ║
║  Prioritate detectie deviz_cod (per pagina):                            ║
║   1. EXPLICIT  — "Deviz Oferta XXXXX" (5-8 alphanum)                    ║
║   2. COMPOUND  — Obiectul numeric + Categoria numerica → "obj-cat"       ║
║   3. REFERENCE_MATCHED — fuzzy match text vs deviz_text_map (≥0.65)     ║
║   4. LLM       — batch Claude API pentru pagini needs_llm=True           ║
║   5. INHERITED — continuare pagina anterioare F3                         ║
║                                                                          ║
║  Detectie F3 vs NON_F3:                                                  ║
║   ✓ "Formular F3" / "SECTIUNEA TEHNICA"                                  ║
║   ✓ "STADIUL FIZIC:" header (ISDP)                                       ║
║   ✓ ">>> componenta" + coduri articol                                    ║
║   ✓ "NNNNNN pag" format (eDevize header)                                 ║
║   ✓ "Stadiul fizic: [COD] DENUMIRE" (eDevize cover)                      ║
║                                                                          ║
║  CHECKPOINT: checkpoints/di_<doc>_page_classes_<hash>.json              ║
║   → Reutilizat automat. Reset: find checkpoints -name "*.json" -delete  ║
║                                                                          ║
║  Output: page_classifications                                            ║
║   [{page_number, is_f3, deviz_cod, deviz_den, lines, header_only}]      ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 2 — ARTICLE EXTRACTION                                            ║
║  shared/f3_extractor.py + shared/f3_regex_parser.py                     ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  extract_articles_v3(page_classifications):                              ║
║                                                                          ║
║  2a. Grupeaza pagini F3 pe deviz_cod                                     ║
║      → combina liniile TUTUROR paginilor aceluiasi deviz                 ║
║      → mentiine nr_crt corect pe tot devizul                             ║
║                                                                          ║
║  2b. Preprocess pipeline (inainte de state machine):                     ║
║      ┌─ _preprocess_scattered_format(lines)                              ║
║      │    Detecteaza: counter(digit) + cod + desc + UM + QTY separate   ║
║      │    Combina in format NR_COD_DESC pentru state machine             ║
║      │    ⚠ is_f3_um TREBUIE single-token (fix 2026-05-22):             ║
║      │      len(_f3_um_tokens)==1 — evita "Art. asimilat" false positive ║
║      │                                                                   ║
║      ├─ _preprocess_compound_um(lines)                                   ║
║      │    Combina "82" + "M" (linii separate) → "82 M"                  ║
║      │                                                                   ║
║      └─ _merge_wrapped_codes(lines)                                      ║
║           Uneste coduri rupte: "TRI1AA01E" + "3" → "TRI1AA01E3"        ║
║                                                                          ║
║  2c. State Machine: IDLE → WAITING → READING                            ║
║      ┌── _IDLE: asteapta NR_CRT sau cod inline                          ║
║      │    Recunoaste: NR_CRT singur, NR+COD inline, NR+COD+DESC inline  ║
║      ├── _WAITING: NR_CRT gasit, asteapta linia cu cod (timeout 3 linii)║
║      └── _READING: cod gasit, colecteaza UM/cant/denumire/preturi        ║
║                                                                          ║
║  Formate coduri recunoscute:                                             ║
║   Normativ:  CA01A, CK26A#, TCB40B1   [A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}  ║
║   Extended:  TRI1AA01C2               [A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d+   ║
║   Single-L:  W2F05C01, H1V06H        [A-Z]\d[A-Z]{1,3}\d{2,4}         ║
║   Digit-L-D: 00106B011               \d{3,5}[A-Z]\d{1,3}              ║
║   Breviar $: $2200012, $16508         \$\d{4,9}                         ║
║   Numeric:   6701362 → $6701362       \d{4,9}                           ║
║                                                                          ║
║  UM Detection (in READING):                                              ║
║   1. Token UM valid singur pe linie (BUCATA, M, MP, MC...)              ║
║   2. Format "82 M" (nr_ordine + UM) via m_um_norm regex                 ║
║   3. Guard NR_ALPHA_INLINE: "cod"=UM valid + articol fara UM            ║
║   UM_KNOWN: BUC, M, MP, MC, ML, KG, T, TON, ORA, ZI, SET, ART...      ║
║   UM_SKIP: ASIM, TSCH, SCH, UM, NR, CRT, TOTAL                         ║
║                                                                          ║
║  2d. Detectie subcomponente                                              ║
║      "L:" prefix, ">>>" marker, ".L" suffix                             ║
║      → is_component=True, parent_cod setat                              ║
║                                                                          ║
║  2e. Deduplicare pe (cod, deviz, cantitate)                              ║
║  2f. Mostenire cantitate/UM pentru componente                            ║
║  2g. _apply_parent_inheritance: parent_cod, parent_nr_ordine            ║
║                                                                          ║
║  Output: lista articole                                                  ║
║   [{cod, deviz, cant, um, denumire, is_component, parent_cod, ...}]     ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 3 — DEVIZ MAPPING                                                 ║
║  shared/deviz_matcher.py                                                 ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  match_devize_by_denomination(ref_arts, oferta_arts):                   ║
║   → construieste mapping: deviz_oferta_cod → deviz_ref_cod              ║
║   → fuzzy match pe denumirile devizelor (SequenceMatcher)               ║
║   → aplica remapping la articolele ofertei                              ║
║                                                                          ║
║  CHECKPOINT: checkpoints/di_<doc>_deviz_mapping_<hash>.json            ║
║                                                                          ║
║  ⚠ Known issue: nu mapeaza text↔numeric (SD DEVIZ_MM=600+)              ║
║    Ref: "4.1-01 STRUCTURA" vs Oferta: cod eDevize numeric               ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 4 — MATCHING                                                      ║
║  AgentComparator_local.py → match_global()                               ║
║  + shared/article_matcher.py (Layer 2/2.1/2.5)                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Cheie matching: (deviz_cod, article_cod)                                ║
║                                                                          ║
║  ┌─ LAYER 1: N:M EXACT pe (deviz, cod) ─────────────────────────────┐  ║
║  │  Grupeaza ref si oferta dupa (deviz, cod)                         │  ║
║  │  Potriveste cantitati in ordine (N ref → M oferta)                │  ║
║  │  ref_dedup → oferta_dedup (cheile exacte)                         │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                             ↓ (articole neacoperite)                     ║
║  ┌─ LAYER 2: NORMALIZED COD (same deviz) ────────────────────────────┐  ║
║  │  _normalize_cod: strip $, AUT6752→$6752, OCR fixes                │  ║
║  │  Potriveste coduri normalizate din same deviz                      │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                             ↓ (articole neacoperite)                     ║
║  ┌─ LAYER 2.1: TRAILING DIGIT ────────────────────────────────────────┐ ║
║  │  IC35D ↔ IC35D1 (ref_cod e prefix al oferta_cod sau viceversa)    │ ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                             ↓ (articole neacoperite)                     ║
║  ┌─ LAYER 2.5: COD SIMILAR OCR (SequenceMatcher ≥ 0.80) ─────────────┐ ║
║  │  Per deviz, candidati cu similaritate ≥ 0.80                      │ ║
║  │  N:M complet: oferta_by_deviz[ok].extend(oferta_by_key[ok])       │ ║
║  │  (fix 2026-05-22: toate instantele per cheie, nu doar prima)      │ ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                             ↓ (articole neacoperite)                     ║
║  ┌─ LAYER 3: LLM FUZZY ───────────────────────────────────────────────┐ ║
║  │  Disabled (skip la "No candidate pairs above threshold")           │ ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                             ↓ (post-matching)                            ║
║  ┌─ POST-PROCESSING: LENIENT UM ($ coduri) ──────────────────────────┐  ║
║  │  ARTICOL_EXTRA cu $ cod + cod exista in ref same deviz cu UM=''  │  ║
║  │  → Convert EXTRA → matched + UM_DIFERIT nonconformitate           │  ║
║  └───────────────────────────────────────────────────────────────────┘  ║
║                                                                          ║
║  Output:                                                                 ║
║   matches[] — perechi (ref_art, oferta_art) potrivite                   ║
║   neconformitati[] — ARTICOL_LIPSA, ARTICOL_EXTRA, DEVIZ_MISMATCH...   ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 5 — NONCONFORMITY CLASSIFICATION                                  ║
║  shared/comparator.py                                                    ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Tipuri neconformitate:                                                  ║
║                                                                          ║
║  ARTICOL_LIPSA   — cod in referinta, absent din oferta (sau deviz gresit)║
║  ARTICOL_EXTRA   — cod in oferta, absent din referinta                   ║
║  DEVIZ_MISMATCH  — cod gasit in oferta dar in alt deviz decat referinta  ║
║                    ⚠ NU e LIPSA reala — articolul exista, deviz gresit  ║
║  UM_DIFERIT      — acelasi cod+deviz, UM diferit                         ║
║  DIFERENTA_CAMP  — acelasi cod+deviz, cantitate/pret diferit             ║
║                                                                          ║
║  compare_articles(ref, oferta): field-level comparison                   ║
║   → UM_DIFERIT daca _normalize_um(ref.um) != _normalize_um(oferta.um)  ║
║   → DIFERENTA_CAMP pe cantitate, preturi (cu toleranta 0.5%)            ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 6 — REPORTING                                                     ║
║  shared/report_builder.py + shared/report_word.py                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  build_raport_ierarhic(ref_articles, neconformitati, matches):          ║
║   → organizeaza pe deviz, ierarhic (principal + subcomponente)           ║
║   → nr_ordine, display_parent_cod pentru subarticole                    ║
║                                                                          ║
║  generate_word(raport_ierarhic):                                         ║
║   → Tabel 11 coloane: tip/cod/denumire/um/cant_ref/cant_of/preturi      ║
║   → Coduri culoare: LIPSA=rosu, EXTRA=galben, DEVIZ_MM=albastru         ║
║   → Grupuri deviz cu headere                                             ║
║                                                                          ║
║  Output per oferta:                                                      ║
║   output_AO/<ClientName>/Raport_Oferta_N.docx                           ║
║   output_AO/<ClientName>/comparatie_oferta_N.json                       ║
║   output_AO/<ClientName>/comparatie_deviz_oferta_N.json                 ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 7 — DIAGNOSTICS (optional, run_diagnostics.py)                   ║
║  shared/diagnostics_builder.py + shared/diagnostics_word.py             ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Citeste output_AO/ existent (NU re-ruleaza pipeline):                  ║
║                                                                          ║
║  Phase 0 — Calitate referinta:                                           ║
║   • articole fara deviz (fara_deviz)                                     ║
║   • componente orfane (parent_cod setat dar parent absent)               ║
║   • articole incomplete (cant=0 sau um='')                               ║
║                                                                          ║
║  Phase 1 — EXTRA analysis per deviz:                                     ║
║   • $-coduri EXTRA (eDevize resurse, astestate)                          ║
║   • principale EXTRA (semnal bug extragere sau adaugare legitima)        ║
║                                                                          ║
║  Phase 2 — LIPSA analysis per deviz:                                     ║
║   • genuine LIPSA (cod absent din oferta)                                ║
║   • DEVIZ_MISMATCH (cod gasit in alt deviz)                              ║
║                                                                          ║
║  Output:                                                                 ║
║   output_AO/diagnostics.json                                             ║
║   output_AO/diagnostics.docx                                             ║
╚══════════════════════════════════════════════════════════════════════════╝
```

---

## Data Structures — Obiecte Cheie

### Article (extras din PDF)

```python
{
    "cod":            str,    # "EA02A1", "$2200012", "CK26A"
    "deviz":          str,    # "BLC2", "1-02", "226208"
    "deviz_denumire": str,    # "BLC2 INSTALATII"
    "denumire":       str,    # descriere articol, multiline
    "um":             str,    # "m", "mp", "buc", "mc", ""
    "cantitate":      float,  # 170.0
    "is_component":   bool,   # True pt subcomponente
    "parent_cod":     str,    # cod parinte pt subcomponente
    "nr_ordine":      int,    # pozitia in deviz
}
```

### Neconformitate (output comparator)

```python
{
    "tip":            str,    # "ARTICOL_LIPSA", "DEVIZ_MISMATCH", etc.
    "ref_cod":        str,    # cod din referinta
    "oferta_cod":     str,    # cod din oferta (pt EXTRA)
    "deviz_ref":      str,    # deviz in referinta
    "ref_cantitate":  float,
    "oferta_cantitate": float,
    "ref_um":         str,
    "oferta_um":      str,
    "nr_ordine_ref":  int,
    "parent_cod_ref": str,
}
```

---

## Import Graph (simplificat)

```
multi_client_run.py
└── local_run.py (orchestration)
    ├── shared/client_config.py
    ├── shared/f3_page_classifier.py
    │   └── [anthropic SDK] (LLM batch)
    ├── shared/f3_extractor.py
    │   └── shared/f3_regex_parser.py
    │       ├── _preprocess_scattered_format()  ← FIX 2026-05-22
    │       ├── _preprocess_compound_um()
    │       └── _merge_wrapped_codes()
    ├── shared/deviz_matcher.py
    ├── AgentComparator_local.py
    │   ├── shared/article_matcher.py (Layer 2/2.1/2.5)
    │   └── shared/comparator.py (field-level diffs)
    ├── shared/report_builder.py
    └── shared/report_word.py

run_diagnostics.py
    ├── shared/client_config.py
    ├── shared/diagnostics_builder.py
    └── shared/diagnostics_word.py
```

---

## Metrici Baseline (2026-05-22, v8.0)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM |
|--------|---|---------|-------|-------|----------|
| Blocuri Racari | 1 | 308 | 47 | 0 | 20 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 |
| Blocuri Racari | 3 | 414 | 21 | 5 | - |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 |
| Scoala Dragomiresti | 1 | 651 | 6 | 0 | 624 |
| Scoala Dragomiresti | 2 | 691 | 6 | 1 | 602 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 11 |
| Scoala Sportiva Racari | 2 | 1142 | 4 | 56 | 328 |
| Scoala Sportiva Racari | 3 | 2260 | 6 | 315 | 325 |

---

## Known Issues Active

| # | Issue | Files | Prioritate |
|---|-------|-------|------------|
| 1 | IZDO3D1 OCR O/0 — Layer 1 consuma cheia gresita | AgentComparator | Low/acceptat |
| 2 | BR O3 EXTRA=5 — de investigat | - | Medium |
| 3 | SD DEVIZ_MM=600+ — text vs numeric cod in deviz_matcher | deviz_matcher.py | High |
| 4 | CM O2 LIPSA=84 — neinvestigat | - | Medium |
| 5 | SSR O3 EXTRA=315 — neinvestigat | - | High |
| 6 | SSR O2/O3 DEVIZ_MM=300+ — neinvestigat | - | High |
