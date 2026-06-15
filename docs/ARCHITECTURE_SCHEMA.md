# Architecture Schema — Diagrama Completă Flux
**Actualizat:** 2026-06-11 | **Versiune:** v3.1 (+ Sursa de Incarcare pipeline)

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
║      │    ⚠ is_f3_um TREBUIE single-token (fix 2026-05-22)              ║
║      │    ⚠ last_scatter_counter (fix 2026-06-10): auto-increment cand  ║
║      │      counter == last_used — evita ca pretul unitatii sa devina    ║
║      │      nr_ordine al articolului urmator (BAZIN CAV Maneciu OS)      ║
║      │                                                                   ║
║      ├─ _preprocess_compound_um(lines)                                   ║
║      │    Combina "82" + "M" (linii separate) → "82 M"                  ║
║      │                                                                   ║
║      └─ _merge_wrapped_codes(lines)                                      ║
║           Uneste coduri rupte: "TRI1AA01E" + "3" → "TRI1AA01E3"        ║
║                                                                          ║
║  2b.5. _merge_split_l_lines(lines) — inainte de state machine           ║
║      Uneste L: split pe 2-3 linii: ['L:SL13A', '-M', ':1100670'] →     ║
║        ['L:SL13A -M:1100670']                                           ║
║      ⚠ SKIP_RE ruleaza via re.search() (NU re.match()):                ║
║        pattern-uri fara ancore matchuiesc ORIUNDE in linie              ║
║        7 cifre = catalog; 4-6 cifre = capitol; 8+ cifre = CPV          ║
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
║   UM_KNOWN: BUC, M, MP, MC, ML, KG, T, TON, ORA, ZI, SET, ART, LITRU  ║
║   UM_SKIP: ASIM, TSCH, SCH, UM, NR, CRT, TOTAL                         ║
║                                                                          ║
║  2d. Detectie subcomponente                                              ║
║      "L:" prefix, ">>>" marker, ".L" suffix                             ║
║      → is_component=True, parent_cod setat                              ║
║      SUBCOMP_PREFIXED_RE: L\s*:\s*([A-Z0-9.]+)\s*-\s*([A-Z0-9]*)\s*:\ ║
║        Prefix accepta dot (OCR: "101.73" in loc de "10173")             ║
║                                                                          ║
║  2e. Deduplicare pe (deviz_key, cod, um, cantitate)                      ║
║      ⚠ deviz_key (hash MD5) nu deviz_cod string — mai multe grupuri    ║
║        logice pot imparti acelasi deviz_cod (BLC7 = 2 grupuri distincte)║
║  2f. Mostenire cantitate/UM pentru componente                            ║
║  2g. _apply_parent_inheritance: parent_cod, parent_nr_ordine            ║
║                                                                          ║
║  Output: lista articole                                                  ║
║   [{cod, deviz, deviz_key, deviz_header, cant, um, denumire,            ║
║     is_component, parent_cod, ...}]                                      ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
║  ⚠ ETAPA 3 REMOVED (2026-05-25): deviz_matcher.py dead code              ║
║    Old Strategy 0-3 (match_devize_by_denomination) removed               ║
║    Holistic path (ETAPA 3.5) handles all deviz matching via deviz_key    ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 3.5 — HOLISTIC GROUP COMPARISON (calea principala)                ║
║  shared/group_comparator.py + shared/deviz_header_extractor.py          ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  extract_deviz_headers(page_classifications):                            ║
║   → extrage OBIECTIVUL + Obiectul + Categoria per deviz din pagini F3   ║
║   → genereaza DevizHeader{obiectivul, obiectul, categoria, deviz_key}   ║
║   → dict keyed by deviz_key (hash) — NU deviz_cod                       ║
║                                                                          ║
║  compare_by_groups(ref_arts, oferta_arts, ref_dh, oferta_dh):           ║
║   1. _articles_by_deviz(): grupeaza pe deviz_key hash                   ║
║   2. match_devize_by_3layer(): potriveste grupuri ref↔oferta             ║
║      (similitudine 3-strat: OBIECTIVUL + Obiectul + Categoria)           ║
║      + same-code verify: verifica similitudine inainte de pairing        ║
║   3. Per grup potrivit: _compare_articles_in_group()                    ║
║      → art["deviz"] = ref_dkey (hash) inainte de match_global           ║
║      → DEVIZ_MISMATCH imposibil in grup → reclasificat ca ARTICOL_LIPSA ║
║   4. Grupuri ref-only → ARTICOL_LIPSA                                   ║
║   5. Grupuri oferta-only → ARTICOL_EXTRA                                ║
║                                                                          ║
║  deviz_denumire = "OBIECTIVUL | Obiectul | Categoria" (3 elemente)      ║
║  Col 1 raport afiseaza: Obiectul | Categoria (ultimele 2 parti)         ║
║  OBIECTIVUL e in heading-ul grupului — NU se duplica in col 1           ║
║                                                                          ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 4 — MATCHING (per grup)                                           ║
║  AgentComparator_local.py → match_global()                               ║
║  + shared/article_matcher.py (Layer 2/2.1/2.5)                          ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Cheie matching: (deviz_key_hash, article_cod)                           ║
║  ⚠ art["deviz"] e setat la deviz_key hash de compare_by_groups()       ║
║    inainte de apelul match_global — NU deviz_cod string                 ║
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
║  ARTICOL_LIPSA         — cod in referinta, absent din oferta             ║
║  ARTICOL_EXTRA         — cod in oferta, absent din referinta             ║
║  DEVIZ_MISMATCH        — cod gasit in oferta dar in alt deviz            ║
║  UM_DIFERIT            — acelasi cod+deviz, UM diferit                   ║
║  DIFERENTA_CAMP        — acelasi cod+deviz, cantitate/camp diferit       ║
║  COD_SIMILAR           — cod similar OCR (I↔1, O↔0) — Layer 2.5        ║
║  COD_NORMATIV_DIFERIT  — LIPSA+EXTRA la acelasi nr → alt cod normativ   ║
║                          (ex: TSD08B01↔CG32B1) — generat de semantic    ║
║  SPECIFICATIE_DIFERITA — spec numerica diferita in descriere             ║
║                          (ex: 8m→5m, DN50→DN110) — generat de semantic  ║
║                                                                          ║
║  compare_articles(ref, oferta): field-level comparison                   ║
║   → UM_DIFERIT daca _normalize_um(ref.um) != _normalize_um(oferta.um)  ║
║   → DIFERENTA_CAMP pe cantitate, preturi (cu toleranta 0.5%)            ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 5b — SEMANTIC COMPARATOR (post-holistic)                          ║
║  shared/semantic_comparator.py                                           ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Pass 1 — semantic_nr_match(ncs, deviz_context, llm):                   ║
║   Gaseste perechi LIPSA+EXTRA cu acelasi nr_ordine in acelasi grup       ║
║   → reclasifica ca COD_NORMATIV_DIFERIT (ofertant a folosit alt cod)    ║
║   Motiv LLM: descriere diferenta sau matching context                    ║
║                                                                          ║
║  Pass 2 — semantic_spec_check(matches, ref_arts, oferta_arts, llm):     ║
║   Pe perechi matched cu acelasi cod dar descriere diferita               ║
║   Filtru: cel putin o diferenta NUMERICA in descriere (dim, param)      ║
║   → genereaza SPECIFICATIE_DIFERITA cu nota_specialist                  ║
║                                                                          ║
║  Culori raport comparatie:                                               ║
║   COD_NORMATIV_DIFERIT  → FFD966 (galben portocaliu)                    ║
║   SPECIFICATIE_DIFERITA → FFC000 (amber)                                ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 6 — REPORTING                                                     ║
║  shared/report_builder.py + shared/report_word.py                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  _generate_word_holistic(holistic_result):                               ║
║   → Sectiuni: matched_groups / ref_only_groups / oferta_only_groups     ║
║   → Heading grup: OBIECTIVUL | Obiectul | Categoria                     ║
║   → Col 1 "Categoria de lucrari": Obiectul | Categoria (2 parti finale) ║
║   → OBIECTIVUL NU repetat in col 1 — e deja in heading                  ║
║   → Nr.crt: pag.ref/pag.of + (nr_ordine_ref/nr_ordine_of)              ║
║   → display_parent_cod: afisat pt is_component=True + $-coduri          ║
║                                                                          ║
║  Output per oferta:                                                      ║
║   output_AO/<ClientName>/Raport_Oferta_N.docx      (NC-only)            ║
║   output_AO/<ClientName>/holistic_oferta_N.json                         ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 6b — COMPARATIE LISTA DOCX (optional, gen_comparatie_lista.py)   ║
║  shared/comparatie_lista_writer.py                                       ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  build_comparatie_docx(holistic, client, oferta_nr, output_path):       ║
║   → Landscape A4, 11 coloane (5 ref | 5 oferta | 1 NC)                 ║
║   → TOATE articolele (nu doar NC) — verde=OK, colorat=NC                ║
║   → tblGrid cu latimi exacte in twips (stabil in orice viewer)          ║
║   → Margini celule: top/bottom 0.5mm, stanga/dreapta 1mm               ║
║   → keep_with_next pe header grup                                        ║
║   → Repeat header rows pe fiecare pagina                                ║
║   → Fuzzy suggest: pt LIPSA/EXTRA arata potential match din cealalta    ║
║     parte ("POSIBIL ACELASI MATERIAL (N%): COD — den")                  ║
║                                                                          ║
║  Culori:                                                                 ║
║   ARTICOL_EXTRA        → FFE0CC (portocaliu pal)                        ║
║   ARTICOL_LIPSA        → CCE5FF (albastru pal)                          ║
║   NC generic           → FFFACD (galben pal)                            ║
║   COD_NORMATIV_DIFERIT → FFD966 (galben portocaliu)                     ║
║   SPECIFICATIE_DIFERITA→ FFC000 (amber)                                 ║
║                                                                          ║
║  Output:                                                                 ║
║   output_AO/<ClientName>/Comparatie_Lista_Oferta_N.docx                 ║
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
    "deviz":          str,    # "BLC2", "1-02", "226208"  — cod string (display only)
    "deviz_key":      str,    # md5 hash "4d91083264aeebaa" — IDENTIFICATOR CANONIC
    "deviz_header":   dict,   # {"obiectivul": ..., "obiectul": ..., "categoria": ...}
    "denumire":       str,    # descriere articol, multiline
    "um":             str,    # "m", "mp", "buc", "mc", ""
    "cantitate":      float,  # 170.0
    "is_component":   bool,   # True pt subcomponente
    "parent_cod":     str,    # cod parinte pt subcomponente
    "nr_ordine":      int,    # pozitia in deviz
    "source_pages":   list,   # pagini PDF sursa
}
```

### DevizHeader (output deviz_header_extractor)

```python
DevizHeader(
    obiectivul = "EFICIENTIZARE ENERGETICA ...",
    obiectul   = "ORGANIZARE DE SANTIER",
    categoria  = "BLC7 ORGANIZARE SANTIER",
    deviz_key  = "4d91083264aeebaa",    # md5(normalized 3 elemente)
    is_valid   = True,
    source     = "regex",               # "regex" | "llm" | "cache"
    deviz_cod  = "BLC7",                # cod PDF (display only, nu e unic)
)
```

### Neconformitate (output group_comparator + comparator)

```python
{
    "tip":              str,    # "ARTICOL_LIPSA", "ARTICOL_EXTRA", "UM_DIFERIT", etc.
    "ref_cod":          str,    # cod din referinta
    "oferta_cod":       str,    # cod din oferta (pt EXTRA)
    "deviz_ref":        str,    # deviz_key hash (identificator grup)
    "deviz_denumire":   str,    # "OBIECTIVUL | Obiectul | Categoria" (3 elemente)
    "ref_cantitate":    float,
    "oferta_cantitate": float,
    "ref_um":           str,
    "oferta_um":        str,
    "nr_ordine_ref":    int,
    "nr_ordine_oferta": int,
    "is_component":     bool,
    "parent_cod_ref":   str,
    "ref_source_pages": list,
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
    ├── shared/deviz_header_extractor.py       ← extrage DevizHeader per grup
    │   └── DevizHeaderCache (JSON persistence)
    ├── shared/deviz_matcher.py
    │   └── match_devize_by_3layer()           ← potrivire grupuri ref↔oferta
    ├── shared/group_comparator.py             ← compare_by_groups() PRINCIPAL
    │   ├── _articles_by_deviz()               ← grupeaza pe deviz_key hash
    │   ├── _compare_articles_in_group()
    │   └── AgentComparator_local.py (import intern)
    ├── AgentComparator_local.py
    │   ├── shared/article_matcher.py (Layer 2/2.1/2.5)
    │   └── shared/comparator.py (field-level diffs)
    ├── shared/semantic_comparator.py          ← Pass1 COD_NORMATIV_DIFERIT + Pass2 SPEC_DIFERITA
    └── shared/report_word.py
        ├── _generate_word_holistic()          ← CALEA PRINCIPALA
        └── _generate_word_hierarchical()      ← legacy

gen_comparatie_lista.py
    └── shared/comparatie_lista_writer.py      ← landscape A4, toate articolele, layout fix v3

run_diagnostics.py
    ├── shared/client_config.py
    ├── shared/diagnostics_builder.py
    └── shared/diagnostics_word.py
```

---

## Metrici Baseline Holistic — Curent (2026-06-11)

| Client | O | matched_groups | ref-only | oferta-only | Note |
|--------|---|----------------|----------|-------------|------|
| Blocuri Racari | 1 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 2 | 35 | 0 | 0 | ✅ perfect |
| Blocuri Racari | 3 | 35 | 0 | 3 | neinvestigat |
| Blocuri Racari | 4 | 32 | 3 | 12 | structura diferita |
| Scoala Dragomiresti | 1 | 22 | 0 | 0 | ✅ perfect |
| Scoala Dragomiresti | 2 | 22 | 0 | 0 | ✅ perfect |
| Scoala Sportiva Racari | 1-3 | 0 | — | — | ❌ header format incompatibil |
| Camin Maneciu | 1 | 35 | 0 | 0 | ✅ 0 CRITICAL/HIGH, 18 MEDIUM genuine |
| Camin Maneciu | 2 | 35 | 0 | 0 | ✅ 0 CRITICAL/HIGH, 18 MEDIUM genuine |
| **CAV Maneciu** | **1** | **11** | **0** | **0** | ✅ **16/16 NC comisie (SOLICI~4)** |
| **CAV Maneciu** | **2** | **10** | **1** | **0** | 1 ref_only neinvestigat |
| **CAV Maneciu** | **3** | **11** | **0** | **1** | off_only=EG02A01 Montaj echip. EXTRA |
| **CAV Maneciu** | **4** | **11** | **0** | **1** | off_only=EG02A01 Montaj echip. EXTRA |
| **CAV Maneciu** | **5** | **11** | **0** | **0** | ✅ **3/3 NC comisie (SO092A~1)** |
| Drum Tatarani | 1 | 189 | 0 | 0 | ✅ 0 CRITICAL/HIGH |
| Drum Tatarani | 2 | 189 | 0 | 0 | ✅ 0 CRITICAL/HIGH |

---

## Known Issues Active

| # | Issue | Files | Prioritate |
|---|-------|-------|------------|
| 1 | SSR 0 holistic grupuri — ref 2 grupuri/obiect vs oferta 8+ sub-devize; matching bijective nu suporta 1→many | deviz_header_extractor.py, group_comparator.py | **HIGH** |
| 2 | BR O3: 3 oferta-only neinvestigate | group_comparator.py | Low |
| 3 | BR O4: 3 ref-only, 12 oferta-only — structura diferita | — | Low |
| 4 | CAV Maneciu O2: 1 ref_only — DUPLEX grup absent sau alt header | group_comparator.py | Low |

---

## Pipeline Sursa de Incarcare (v3.1 — PIPELINE SEPARAT)

**Entry point:** `gen_sursa_incarcare.py` — independent, ZERO modificari la pipeline multi-client.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  INPUT: un singur di_*.json din input_AO/<ClientName>/                   │
│  (ex: di_referinta.json — document eDevize cu preturi)                   │
└────────────────────────────┬─────────────────────────────────────────────┘
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 1 — PAGE CLASSIFICATION (existent, reutilizat)                    ║
║  shared/f3_page_classifier.py                                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║  CHECKPOINT: output_AO/<client>/{json_stem}_page_classes.json            ║
║  Output: page_classes [{page_nr, is_f3, lines, ...}]                    ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 2 — DEVIZ HEADER EXTRACTION (existent, reutilizat)                ║
║  shared/deviz_header_extractor.py                                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║  Output: deviz_headers — lista DevizHeader(obj1, obj2, cat, deviz_key)   ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 3 — PRICE EXTRACTION (NOU)                                        ║
║  shared/f3_price_extractor.py                                            ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Structura eDevize (state machine per pagina F3):                        ║
║   - Header zone SKIP → pana la sentinela "5 = 3 x 4"                    ║
║   - CAPITOL: linie all-caps fara cifre                                   ║
║   - ART_NR: numar intreg singur pe linie                                 ║
║   - COD_NAME: "COD - denumire" (verificat INAINTE de CAPITOL)            ║
║   - UM, NUMBER (3 numere per articol: cant, pret, total)                 ║
║   - BREAKDOWN: "material:" + pret + total (4 keys)                       ║
║   - SUB_NR: numar decimal (1.1, 1.2) — NU din in_num_window             ║
║                                                                          ║
║  control_ok = |material+manopera+utilaj+transport - pret_unitar| < 0.02  ║
║  suspect = not control_ok (setat pe articol)                             ║
║                                                                          ║
║  _parse_number: rightmost-separator-wins                                 ║
║   "7,473.71" → 7473.71 (US)  |  "1.234,56" → 1234.56 (EU)             ║
║                                                                          ║
║  CHECKPOINT: output_AO/<client>/sursa_extracted_{json_stem}.json         ║
║  Output: [deviz{deviz_key, obj1, obj2, cat, capitole[{titlu, articole,   ║
║           total_capitol}], total_deviz}]                                 ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 4 — VERIFICATION (NOU)                                            ║
║  shared/lista_verifier.py                                                ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  5 checks (max 5 iteratii, retry daca HIGH failures):                    ║
║   NR_CRT_GAPS    — nr_crt intreg consecutiv, fara goluri  [HIGH]         ║
║   TOTAL_CAPITOL  — sum(art.total) ≈ total_capitol (±0.05 Lei) [HIGH]    ║
║   TOTAL_DEVIZ    — sum(capitol.total) ≈ total_deviz (±0.05 Lei) [HIGH]  ║
║   BREAKDOWN_CONTROL — articole cu suspect=True [WARN]                   ║
║   COUNT_DEVIZE   — len(extracted) vs len(deviz_headers) [INFO]          ║
║                                                                          ║
║  Status: OK | WARN | RED (dupa 5 iteratii HIGH nerezolvate)             ║
║  CHECKPOINT: output_AO/<client>/sursa_verified_{json_stem}.json          ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
╔══════════════════════════════════════════════════════════════════════════╗
║  ETAPA 5 — OUTPUT GENERATION (NOU)                                       ║
║  shared/sursa_incarcare_writer.py                                        ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  Naming: Lista-proiect-{ACRONIM}-{json_stem}.docx/xlsx/pdf               ║
║  ACRONIM: strip prefix numeric, filtreaza stopwords, max 6 litere        ║
║   "CONSTRUIRE UNITATE DE CAZARE TARGOVISTE" → "CUCT"                    ║
║   "0232 000000232 DRUMURI TATARANI" → "DT"                              ║
║                                                                          ║
║  DOCX: landscape A4, 6 coloane, tblGrid fixed [1.2,9.0,1.5,2.5,2.8,3.0]║
║   Randuri: HEADER_DEVIZ | ANTET_TABEL (gray D9D9D9) | CAPITOL (EEEEEE)  ║
║           ARTICOL | BREAKDOWN (italic 7pt) | SUB_ITEM | TOTAL_CAPITOL   ║
║           TOTAL_DEVIZ (FFF2CC) | RED_FLAG (FF0000, daca status=RED)     ║
║                                                                          ║
║  XLSX: aceeasi structura, un sheet per deviz, fara merge-uri            ║
║  PDF: LibreOffice CLI (--no-pdf sau indisponibil → skip silentios)      ║
║                                                                          ║
║  ⚠ CRITIC: deviz['status'] = verification['status']                     ║
║    TREBUIE injectat INAINTE de write_docx/write_xlsx                    ║
╚══════════════════════════════════════════════════════════════════════════╝
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  OUTPUT: output_AO/<ClientName>/                                          │
│   Lista-proiect-{ACRONIM}-{json_stem}.docx                               │
│   Lista-proiect-{ACRONIM}-{json_stem}.xlsx                               │
│   Lista-proiect-{ACRONIM}-{json_stem}.pdf  (daca LibreOffice disponibil) │
└──────────────────────────────────────────────────────────────────────────┘
```

### Import Graph — Sursa de Incarcare

```
gen_sursa_incarcare.py
├── shared/client_config.py          ← existent, neatins
├── shared/f3_page_classifier.py     ← existent, neatins
├── shared/deviz_header_extractor.py ← existent, neatins
├── shared/f3_price_extractor.py     ← NOU
│   ├── _parse_number()              (rightmost-separator-wins)
│   ├── _parse_f3_page_lines()       (state machine events)
│   ├── _assemble_deviz()            (events → deviz dict + suspect flag)
│   └── extract_prices()             (public API + checkpoint)
├── shared/lista_verifier.py         ← NOU
│   ├── _check_nr_crt_gaps()
│   ├── _check_total_capitol()
│   ├── _check_total_deviz()
│   ├── _check_breakdown_control()
│   └── verify()                     (retry loop + status)
└── shared/sursa_incarcare_writer.py ← NOU
    ├── make_acronym()
    ├── write_docx()
    ├── write_xlsx()
    └── write_pdf()
```

### Structura Output Deviz (extract_prices)

```python
{
  'deviz_key': str,         # md5(obiectivul|obiectul|categoria)
  'obiectivul': str,
  'obiectul': str,
  'categoria': str,
  'status': 'OK'|'WARN'|'RED',  # injectat de CLI
  'total_deviz': float,
  'capitole': [
    {
      'titlu': str, 'total_capitol': float|None,
      'articole': [
        {
          'nr_crt': str, 'cod': str, 'denumire': str, 'um': str,
          'cantitate': float, 'pret_unitar': float, 'total': float,
          'suspect': bool,
          'breakdown': None | {
            'material': {'pret': float, 'total': float},
            'manopera': {'pret': float, 'total': float},
            'utilaj':   {'pret': float, 'total': float},
            'transport':{'pret': float, 'total': float},
            'control_ok': bool
          },
          'sub_items': [...]
        }
      ]
    }
  ]
}
```

### Teste Sursa de Incarcare

| Fisier | Teste |
|--------|-------|
| `tests/shared/test_f3_price_extractor.py` | 26 teste (state machine, assembler, checkpoint) |
| `tests/shared/test_lista_verifier.py` | 10 teste (checks, retry loop, status) |
| `tests/shared/test_sursa_incarcare_writer.py` | 13 teste (acronim, DOCX, XLSX, PDF) |

**Baseline teste:** 702 passing (din 718 total; 16 pre-existing failures neschimbate).
