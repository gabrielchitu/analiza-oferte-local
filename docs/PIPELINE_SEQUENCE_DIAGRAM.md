# Pipeline — Diagrama de Secvență
**Actualizat:** 2026-06-16 | **Versiune:** v3.2 (+ verify_gaps MISSING_TAIL, P-2 parser fix)

> **2026-05-25:** Removed Strategy 0-3 (match_devize_by_denomination). Holistic path uses deviz_key hash exclusively.
> **2026-05-28:** CM parser fixed (SKIP_RE, LITRU, L: merge, SUBCOMP dot). CM verificat ✅.
> **2026-06-10:** Scatter counter fix (BAZIN CAV Maneciu nr=4.1→5). Semantic comparator adaugat. CAV Maneciu O1-O5 verificat, 21/21 NC comisie acoperite.
> **2026-06-11:** Comparatie lista layout fixes (tblGrid, cell margins, keep_with_next, repeat headers). DT2 adaugat (189/189 grupuri matchate).
> **2026-06-15:** verify_gaps.py MISSING_TAIL detection (per-deviz exact scope via page_classes checkpoint).
> **2026-06-16:** P-2 letter-dash-digit parser fix (MISSING_TAIL nr=56 DT2 VS0002). scatter NR absorption fix. codeless eDevize labor fix.

---

## Diagrama Completă de Secvență

```
Utilizator          multi_client_run     local_run          f3_page_classifier    f3_extractor / f3_regex_parser     deviz_matcher     AgentComparator        report_builder / report_word
    │                       │                │                       │                          │                          │                   │                         │
    │  --client "BR"        │                │                       │                          │                          │                   │                         │
    │──────────────────────▶│                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                 ClientConfig           │                       │                          │                          │                   │                         │
    │                 detect_clients()       │                       │                          │                          │                   │                         │
    │                 resolve_paths()        │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │ run_pipeline() │                       │                          │                          │                   │                         │
    │                       │───────────────▶│                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │══════════ PENTRU FIECARE DOCUMENT (referinta + oferta_N) ═══════════════════════════════════════════════════════════════╗
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │  load_json(di_*.json) │                          │                          │                   │                         ║
    │                       │                │───────────────────────────────────────────────────────────────────────▶(skip)                 │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │  classify_pages()     │                          │                          │                   │                         ║
    │                       │                │──────────────────────▶│                          │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │ [check checkpoint]        │                          │                   │                         ║
    │                       │                │                       │──▶ if exists: return      │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │ per pagina:               │                          │                   │                         ║
    │                       │                │                       │  EXPLICIT/COMPOUND/REF_MATCH                         │                   │                         ║
    │                       │                │                       │  sau needs_llm=True       │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │ [LLM batch pt needs_llm] │                          │                   │                         ║
    │                       │                │                       │──▶ Claude API             │                          │                   │                         ║
    │                       │                │                       │◀─ is_f3, deviz_cod        │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │ inheritance: deviz_cod    │                          │                   │                         ║
    │                       │                │                       │ propagat pt continuare    │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │ save checkpoint           │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │◀─ page_classifications│                          │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │  extract_articles_v3()│                          │                          │                   │                         ║
    │                       │                │──────────────────────────────────────────────────▶│                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │                       │          per deviz_cod (pagini grupate):            │                   │                         ║
    │                       │                │                       │          combine all_lines                          │                   │                         ║
    │                       │                │                       │          _preprocess_scattered_format()             │                   │                         ║
    │                       │                │                       │            ⚠ is_f3_um: single-token only            │                   │                         ║
    │                       │                │                       │          _preprocess_compound_um()                  │                   │                         ║
    │                       │                │                       │          _merge_wrapped_codes()                     │                   │                         ║
    │                       │                │                       │          extract_articles_regex()                   │                   │                         ║
    │                       │                │                       │            IDLE→WAITING→READING state machine       │                   │                         ║
    │                       │                │                       │            detect cod/UM/cant/denumire              │                   │                         ║
    │                       │                │                       │          seteaza deviz_key + deviz_header per art   │                   │                         ║
    │                       │                │                       │          dedup (deviz_key, cod, um, cantitate)      │                   │                         ║
    │                       │                │                       │            ⚠ deviz_key hash, NU deviz_cod string    │                   │                         ║
    │                       │                │                       │          _apply_parent_inheritance()                │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │◀─ articole[]          │                          │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    ║════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  (per oferta)                                    │                          │                   │                         │
    │                       │                │  extract_deviz_headers(page_classes)             │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────▶│                          │                   │                         │
    │                       │                │                       │          DevizHeader{obj1,obj2,cat,deviz_key}       │                   │                         │
    │                       │                │◀─ ref_dh{}, oferta_dh{}                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  compare_by_groups(ref, oferta, ref_dh, of_dh)   │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────────────────────────────────────────────────▶│                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │  _articles_by_deviz()    │   grup per deviz_key hash               │
    │                       │                │                       │                          │  match_devize_by_3layer()│   potrivire grupuri ref↔oferta          │
    │                       │                │                       │                          │  per grup potrivit:      │                   │                         │
    │                       │                │                       │                          │    art["deviz"]=ref_dkey │   (hash, nu cod)                        │
    │                       │                │                       │                          │    match_global() ───────────────────────▶│                         │
    │                       │                │                       │                          │                          │   Layer 1: exact (hash,cod)             │
    │                       │                │                       │                          │                          │   Layer 2: normalized cod               │
    │                       │                │                       │                          │                          │   Layer 2.1: trailing digit             │
    │                       │                │                       │                          │                          │   Layer 2.5: OCR sim ≥0.80 N:M          │
    │                       │                │                       │                          │                          │   Post: lenient UM ($ coduri)           │
    │                       │                │                       │                          │  ref-only → LIPSA        │                   │                         │
    │                       │                │                       │                          │  oferta-only → EXTRA     │                   │                         │
    │                       │                │◀─ HolisticComparison  │                          │                          │                   │                         │
    │                       │                │   {matched_groups,     │                          │                          │                   │                         │
    │                       │                │    ref_only_groups,    │                          │                          │                   │                         │
    │                       │                │    oferta_only_groups} │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  _generate_word_holistic()                       │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────▶│
    │                       │                │                       │                          │                          │  heading grup: OBJ|OBJ2|CAT             │
    │                       │                │                       │                          │                          │  col1: OBJ2|CAT (2 parti finale)        │
    │                       │                │◀─ Raport_Oferta_N.docx│                          │                          │                   │                         │
    │                       │                │   holistic_oferta_N.json                         │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  semantic_nr_match() + semantic_spec_check()     │                   │                         │
    │                       │                │  (shared/semantic_comparator.py)                 │                   │                         │
    │                       │                │  → reclasifica LIPSA+EXTRA@same_nr → COD_NORM_DIF│                   │                         │
    │                       │                │  → detecteaza SPECIFICATIE_DIFERITA pe matched    │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │◀─ ✓ Pipeline complet  │                │                       │                          │                          │                   │                         │
    │   (optional post-run) │                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │  gen_comparatie_lista.py ──────────────────────────────────────────────────────────────────────────────────────────────────────────────▶│
    │  --client "X"         │                │  shared/comparatie_lista_writer.py               │                   │                         │
    │                       │                │  → Comparatie_Lista_Oferta_N.docx (toate art.)   │                   │                         │
    │◀─ Comparatie_Lista_N.docx             │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │  gen_lista_oferta.py  │                │                       │                          │                          │                   │                         │
    │  --client "X"         │                │                       │                          │                          │                   │                         │
    │  [--referinta]        │                │  shared/lista_oferta_writer.py                   │                          │                   │                         │
    │  [--oferta N]         │                │  → Lista_Oferta_N.docx (15 col, preturi RO)     │                   │                         │
    │                       │                │  → Lista_Referinta.docx                         │                   │                         │
    │◀─ Lista_*.docx        │                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │  verify_agent.py      │                │                       │                          │                          │                   │                         │
    │  --client "X"         │                │  shared/pipeline_verifier.py                     │                          │                   │                         │
    │  --verify-only        │                │  → 6 checks: SILENT_VIOLATION, OFERTA_ONLY_GROUP │                   │                         │
    │                       │                │    REF_ONLY_GROUP, HIGH_EXTRA, HIGH_LIPSA         │                   │                         │
    │                       │                │    EMPTY_MATCHED_GROUP, COD_SIMILAR_CLUSTER       │                   │                         │
    │                       │                │  → verify_report_{timestamp}.md                  │                   │                         │
    │◀─ severitate findings │                │    CRITICAL / HIGH / MEDIUM / LOW                │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │  verify_gaps.py       │                │                       │                          │                          │                   │                         │
    │  --client "X"         │                │  per deviz:                                      │                          │                   │                         │
    │  [--referinta]        │                │    _find_gaps(): nr_crt lipsă din secventa extrasă                    │                         │
    │  [--oferta N]         │                │    _find_tail_missing(): articole dupa max_extracted                  │                         │
    │  [--tail-lookahead N] │                │      ⚠ scope EXACT: page_classes checkpoint pages                     │                         │
    │                       │                │      (no ±3 extension — previne false positives cross-deviz)          │                         │
    │                       │                │    BUG EXTRACTOR / DEVIZ GREȘIT / SALT NUMEROTARE                     │                         │
    │◀─ gaps + MISSING_TAIL │                │    ⚠ MISSING_TAIL: mereu bug extractor → fix obligatoriu              │                         │
```

---

## Secventa Detaliata: Preprocess + State Machine

```
all_lines (combinate din toate paginile aceluiasi deviz)
    │
    ▼
_preprocess_scattered_format(lines)
    ┌─────────────────────────────────────────────────────────────────┐
    │ Pentru fiecare linie ce e bare counter (^\d+$):                │
    │                                                                 │
    │ Branch A: Counter + Cod + UM + QTY (consecutive)               │
    │   lines[i]   = "6"         ← counter                           │
    │   lines[i+1] = "EA02A1"    ← cod valid                         │
    │   lines[i+2] = "BUCATA"    ← UM valid (single-token ✓)         │
    │   lines[i+3] = "170,00000" ← QTY valid                         │
    │   → Combina: "6 EA02A1 - DESCRIPTION"                          │
    │              "BUCATA" (UM)                                      │
    │              "170,00000" (QTY)                                  │
    │                                                                 │
    │ Branch B: Counter + Cod + DESCRIERE... + UM + QTY (F3-order)   │
    │   lines[i]   = "6"         ← counter                           │
    │   lines[i+1] = "EA02A1"    ← cod valid                         │
    │   lines[i+2] = "82 M"      ← NU e UM valid (cifra+litera)      │
    │   Scan ahead k=i+2..i+12:                                      │
    │     "82 M" → desc_part (nu e UM: cifra+litera)                 │
    │     "170,00000" → desc_part (cifre)                             │
    │     "TUB IZOLANT..." → desc_part                               │
    │     "BUCATA" → is_f3_um=True (single-token, in UM_KNOWN) ✓     │
    │              → f3_um="BUCATA", f3_qty=lines[k+1]               │
    │   ⚠ FIX 2026-05-22: is_f3_um TREBUIE len(tokens)==1            │
    │     "Art. asimilat" → 2 tokens → is_f3_um=False ✓ (nu mai fura│
    │                        NR_CRT-ul articolului urmator ca QTY)   │
    │                                                                 │
    │ Fallback: linie nemodificata → state machine o proceseaza direct│
    │                                                                 │
    │ ⚠ FIX 2026-06-10: last_scatter_counter                        │
    │   Daca counter == last_scatter_counter → auto-increment        │
    │   Previne ca pretul unitatii (ex: 4 lei/luna pt WC) sa fie    │
    │   interpretat ca nr_ordine pt articolul urmator (BAZIN)        │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
_preprocess_compound_um(lines)
    ┌─────────────────────────────────────────────────────────────────┐
    │ "82" + "M" (linii consecutive) → "82 M" (o singura linie)     │
    │ "99" + "ZECI MP"               → "99 ZECI MP"                 │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
_merge_wrapped_codes(lines)
    ┌─────────────────────────────────────────────────────────────────┐
    │ "TRI1AA01E" + "3" → "TRI1AA01E3" (cod rupt de OCR)             │
    └─────────────────────────────────────────────────────────────────┘
    │
    ▼
extract_articles_regex(lines, deviz_cod, deviz_den)
    │
    │  ┌─────────────────────────────────────────────────────────────┐
    │  │ STATE: _IDLE                                                │
    │  │  Recunoaste:                                                │
    │  │   NR_ALPHA_INLINE "024 CK26A#"  → direct _READING           │
    │  │   NR_NUMERIC_INLINE "024 2200012" → direct _READING ($)    │
    │  │   NR_COD_DESC "6 CA01J1 - DESC" → direct _READING          │
    │  │   _is_nr_crt(line) → _WAITING + last_nr_crt=N              │
    │  │   altceva → ignora                                          │
    │  └─────────────────────────────────────────────────────────────┘
    │              │ NR_CRT gasit
    │              ▼
    │  ┌─────────────────────────────────────────────────────────────┐
    │  │ STATE: _WAITING (timeout 3 linii → _IDLE)                   │
    │  │  Recunoaste:                                                │
    │  │   _try_parse_cod(line) → cod extras → _READING              │
    │  │   NR_ALPHA_INLINE/NUMERIC_INLINE → cod inline → _READING    │
    │  │   _is_nr_crt → update last_nr_crt, ramai _WAITING           │
    │  │   waiting_lines >= 3 → _IDLE                                │
    │  └─────────────────────────────────────────────────────────────┘
    │              │ cod gasit
    │              ▼
    │  ┌─────────────────────────────────────────────────────────────┐
    │  │ STATE: _READING                                             │
    │  │  Colecteaza (pana la finalizare):                           │
    │  │                                                             │
    │  │  NR_*_INLINE → finalize() + nou articol                     │
    │  │  [guard 82 M]: daca "cod"=UM valid si um='' → seteaza UM    │
    │  │                                                             │
    │  │  _is_model_reference → skip                                 │
    │  │                                                             │
    │  │  NR_CRT bare ("82"):                                        │
    │  │   daca cant==0 → finalize() + _WAITING                      │
    │  │   daca cant>0 si price_count==0 → _is_nr_crt() → finalize  │
    │  │                                                             │
    │  │  UM detection (daca um==''):                                │
    │  │   token UM singur pe linie (BUCATA, M, MP)                  │
    │  │   "ZECI M" → um=m                                           │
    │  │   "82 M" → m_um_norm → um=m (nr_ordine ignorat)            │
    │  │                                                             │
    │  │  CANT_DECIMAL_RE → cantitate=float                          │
    │  │  CANT_INT_RE (daca um setat) → cantitate=int                │
    │  │  PRET_RE → preturi.append                                   │
    │  │                                                             │
    │  │  text → denumire_parts.append                               │
    │  └─────────────────────────────────────────────────────────────┘
    │              │ finalizare
    │              ▼
    │  _finalize() → articole.append({cod, um, cantitate, denumire, preturi})
    │
    ▼
articole[] (per deviz)
```

---

## Secventa Detaliata: Matching (Layer 1-2.5)

```
ref_articole[]                    oferta_articole[] (dupa deviz mapping)
      │                                    │
      ▼                                    ▼
  ref_dedup{}                         oferta_dedup{}
  cheie: (deviz, cod)                 cheie: (deviz, cod)
  valoare: [art1, art2, ...]          valoare: [art1, art2, ...]
      │                                    │
      └──────────────┬─────────────────────┘
                     │
         ╔═══════════▼═══════════╗
         ║  LAYER 1: EXACT       ║
         ║  N ref : M oferta     ║
         ║  per (deviz, cod)     ║
         ╚═══════════╤═══════════╝
                     │ unmatched ref + unmatched oferta
         ╔═══════════▼═══════════╗
         ║  LAYER 2: NORM COD    ║
         ║  AUT6752 ↔ $6752      ║
         ║  strip $ prefix       ║
         ╚═══════════╤═══════════╝
                     │ unmatched
         ╔═══════════▼═══════════╗
         ║  LAYER 2.1: TRAIL DGT ║
         ║  IC35D ↔ IC35D1       ║
         ║  prefix match         ║
         ╚═══════════╤═══════════╝
                     │ unmatched
         ╔═══════════▼═══════════╗
         ║  LAYER 2.5: OCR SIM   ║
         ║  SequenceMatcher≥0.80  ║
         ║  per deviz, N:M complet║
         ║  FIX: oferta_by_deviz  ║
         ║  .extend(all instances)║
         ╚═══════════╤═══════════╝
                     │ unmatched
         ╔═══════════▼═══════════╗
         ║  LAYER 3: LLM FUZZY   ║
         ║  DISABLED              ║
         ║  (no candidate pairs)  ║
         ╚═══════════╤═══════════╝
                     │
         ╔═══════════▼═══════════╗
         ║  POST: LENIENT UM     ║
         ║  $ EXTRA cod in ref   ║
         ║  cu UM='' → MATCHED   ║
         ║  + UM_DIFERIT added   ║
         ╚═══════════╤═══════════╝
                     │
            ┌────────┴────────┐
            ▼                 ▼
        matches[]         neconformitati[]
   (ref+oferta perechi)   LIPSA/EXTRA/DEVIZ_MM
```

---

## Secventa: DEVIZ_MISMATCH Detection

```
ref cod "CF08A03" in deviz BLC6
      │
      ▼ Layer 1 exact: cautare in oferta cu key ("BLC6", "CF08A03")
      │ → NOT FOUND (oferta are CF08A03 in BLC1)
      │
      ▼ Layer 2/2.1/2.5: cautare in same deviz BLC6
      │ → NOT FOUND in BLC6
      │
      ▼ ref "CF08A03" → ARTICOL_LIPSA initial
      │
      ▼ [dar oferta are CF08A03 in BLC1]
      │ → detectat de deviz_mismatches detection
      │ → tip schimbat: LIPSA → DEVIZ_MISMATCH
      │
      └─ Interpretare: articolul EXISTA in oferta, deviz gresit
         NU e LIPSA reala. Ofertantul a structurat devizele diferit.
```

---

## Secventa: Diagnostics (run_diagnostics.py)

```
run_diagnostics.py --client "Blocuri Racari"
      │
      ▼
discover_client_outputs(client_name)
      │ citeste output_AO/<Client>/comparatie_oferta_N.json
      │ citeste output_AO/<Client>/checkpoints/di_referinta_*.json
      │
      ▼
load_comparison_data()
      │
      ├─ Phase 0: calitate_referinta
      │    ref_articole → fara_deviz, orfane, incomplete
      │
      ├─ Phase 1: extra_analysis (per oferta, per deviz)
      │    EXTRA → $ vs principale
      │
      └─ Phase 2: lipsa_analysis (per oferta, per deviz)
           LIPSA → genuine vs DEVIZ_MISMATCH
      │
      ▼
build_diagnostics_json()
      │
      ├─ output_AO/diagnostics.json
      └─ output_AO/diagnostics.docx (daca --no-docx nu e setat)
```

---

## Call Graph — Ierarhie Functii (multi_client_run → output)

```
multi_client_run.main()
├── parse_args()
├── ClientConfig.detect_clients(input_dir)
├── show_client_menu(clients)                          [interactiv, daca nu --client]
└── run_pipeline(client_config)
    ├── client_config.ensure_output_dirs()
    └── _run_analysis_pipeline(client_config, ref_di_json, oferta_di_list)
        ├── _build_client()                            → (anthropic_client, model)
        │
        ├── extract_document(ref_path, client, model)  ← REFERINTA
        │   ├── _checkpoint_path(di_path, client_config)
        │   ├── [no checkpoint] classify_pages(pages, client, model)
        │   │   └── LLM batch Claude API (is_f3, deviz_cod per pagina)
        │   │   └── save checkpoint {page_classes, metadata}
        │   ├── [has __partial__ cod] _resolve_partial_keys_with_llm(page_classes, ref_groups, client, model)
        │   │   └── LLM rezolva "1-???" → "1-04" din context ref
        │   ├── _reclassify_missed_f3_pages(page_classes, pages, checkpoint, client, model)
        │   │   └── LLM tintit pt pagini F3 ratate de classifier
        │   ├── _apply_end_detection(page_classes, F3Knowledge())  [in-memory, nu checkpoint]
        │   ├── extract_deviz_headers(page_classes, client, model)
        │   │   ├── _extract_from_lines(lines[:30])               [regex OBIECTIVUL/Obiectul/Categoria]
        │   │   ├── [if incomplete + llm_client] _extract_via_llm(lines, client, model)
        │   │   └── _make_deviz_key(obj1, obj2, cat)               → md5 hash (16 chars)
        │   ├── extract_articles_v3(page_classes)
        │   │   └── [per deviz_cod group — combine all pages]:
        │   │       ├── _preprocess_scattered_format(lines)        [counter+cod+UM+QTY → inline]
        │   │       ├── _preprocess_compound_um(lines)             ["82"+"M" → "82 M"]
        │   │       ├── _merge_wrapped_codes(lines)                ["TRI1AA01E"+"3" → "TRI1AA01E3"]
        │   │       ├── extract_articles_regex(lines, deviz_cod, deviz_den)
        │   │       │   └── state machine IDLE → WAITING → READING
        │   │       │       ├── _try_parse_cod(line)               [detectie cod articol]
        │   │       │       ├── _is_valid_um(token)                [UM_KNOWN check]
        │   │       │       ├── _is_nr_crt(line)                   [NR_CRT detectie]
        │   │       │       └── _finalize()                        → articles.append(art)
        │   │       └── _apply_parent_inheritance(articles)        [parent_cod, display_parent_cod]
        │   ├── dedup by (deviz_key, cod, um, cantitate)           ← hash, NU deviz_cod string
        │   └── extract_articles_from_tables_smart(tables)         [merge table articles]
        │       └── [prioritate tabel pt UM + cant=0 fix]
        │   → returns (articles, checkpoint_data{deviz_headers, subcomponent_format})
        │
        ├── populate_deviz_denominations(ref_articles)
        │
        ├── [per oferta_path]:
        │   ├── _extract_ofertant_name(oferta_path)
        │   ├── extract_document(oferta_path, client, model, ref_deviz_groups, ref_articles)
        │   │   └── [identic cu referinta, in plus: ref_deviz_groups pt LLM partial key resolution]
        │   ├── populate_deviz_denominations(oferta_articles)
        │   ├── _headers_from_articles(ref_arts)    → ref_dh  {deviz_key → DevizHeader}
        │   ├── _headers_from_articles(oferta_arts) → oferta_dh
        │   └── compare_and_report(ref_arts, oferta_arts, oferta_nr, ...)
        │       ├── match_global(ref_arts, oferta_arts, client, model)
        │       │   ├── Layer 1: N:M exact (deviz_key_hash, cod)
        │       │   ├── Layer 2: normalized cod  [article_matcher.py]
        │       │   │   └── _normalize_cod(): strip $, AUT→$, OCR fixes
        │       │   ├── Layer 2.1: trailing digit  [IC35D ↔ IC35D1]
        │       │   ├── Layer 2.5: OCR similar SequenceMatcher ≥ 0.80 N:M
        │       │   └── Post: lenient UM ($ EXTRA cu ref.um='' → MATCHED + UM_DIFERIT)
        │       │   → returns (neconformitati[], matches[], matched_ref_keys, fara_deviz)
        │       │
        │       ├── [reconstruct DevizHeader obiecte din checkpoint]:
        │       │   ├── _ref_dh{deviz_key → DevizHeader}  din ref_checkpoint_data["deviz_headers"]
        │       │   └── _oferta_dh{deviz_key → DevizHeader} din checkpoint_data["deviz_headers"]
        │       │
        │       ├── compare_by_groups(ref_arts, oferta_norm, _ref_dh, _oferta_dh, client, model)
        │       │   ├── _articles_by_deviz(ref_valid)      → {deviz_key_hash: [arts]}
        │       │   ├── _articles_by_deviz(oferta_valid)   → {deviz_key_hash: [arts]}
        │       │   ├── match_devize_by_3layer(ref_dh, oferta_dh)  → group_mapping
        │       │   ├── _quick_3layer_sim(rh, oh)          [same-code verify: sim ≥ 0.75]
        │       │   ├── [per grup matched]:
        │       │   │   └── _compare_articles_in_group(ref_arts, of_arts, group_key, ...)
        │       │   │       ├── art["deviz"] = ref_dkey    ← hash normalizat pt match_global
        │       │   │       ├── match_global(ref_arts, of_arts, ...)
        │       │   │       └── DEVIZ_MISMATCH → ARTICOL_LIPSA  [imposibil in grup]
        │       │   ├── [ref-only grupuri]: _lipsa_neconf(art, ref_cod, deviz_den)
        │       │   └── [oferta-only grupuri]: _extra_neconf(art, "", deviz_den)
        │       │   → returns HolisticComparison{matched_groups, ref_only, oferta_only, ungrouped}
        │       │
        │       ├── build_raport_holistic(_holistic)       → raport_holistic{sumar, grupuri}
        │       ├── mark_suspicious_extras(neconformitati, ref_di_text, ref_arts)
        │       ├── generate_excel(...)                    → Raport_Oferta_N.xlsx
        │       └── generate_word(holistic_result, ...)
        │           └── _generate_word_holistic()
        │               ├── [per matched_groups]:
        │               │   ├── _add_group_heading(table, ref_hdr, deviz_den)
        │               │   └── _add_neconf_row(table, nc)
        │               │       └── col1 = " | ".join(parts[-2:])  [Obiectul | Categoria]
        │               ├── [per ref_only_groups]:  similar, heading "GRUP ABSENT DIN OFERTA"
        │               └── [per oferta_only_groups]: similar, heading "GRUP EXTRA IN OFERTA"
        │           → Raport_Oferta_N.docx
        │
        └── save holistic_oferta_N.json, comparatie_oferta_N.json
```

### Legende Return Values

| Functie | Return |
|---------|--------|
| `extract_document()` | `(articles[], checkpoint_data{deviz_headers, subcomponent_format})` |
| `extract_deviz_headers()` | `{deviz_key_hash: DevizHeader}` |
| `extract_articles_v3()` | `[{cod, deviz, deviz_key, deviz_header, um, cantitate, ...}]` |
| `match_global()` | `(neconformitati[], matches[], matched_ref_keys, fara_deviz)` |
| `compare_by_groups()` | `HolisticComparison{matched_groups[], ref_only[], oferta_only[], ungrouped[]}` |
| `build_raport_holistic()` | `{sumar{}, grupuri[]}` |
| `match_devize_by_3layer()` | `{oferta_deviz_key: ref_deviz_key}` mapping |

### Checkpoint-uri salvate pe disk

```
output_AO/<Client>/checkpoints/
├── di_referinta_page_classes_<hash>.json     ← classify_pages() output + deviz_headers
├── di_oferta_1_page_classes_<hash>.json      ← idem pt oferta 1
├── di_oferta_2_page_classes_<hash>.json      ← idem pt oferta 2
└── ...
```

Formatul checkpoint:
```json
{
  "page_classes": [{page_number, is_f3, deviz_cod, deviz_den, lines, header_only, ...}],
  "metadata": {
    "deviz_headers": {"<deviz_key_hash>": {obiectivul, obiectul, categoria, is_valid, deviz_cod}},
    "subcomponent_format": {format, name, confidence}
  }
}
```

---

## Imperfectiuni Known

### Rezolvate in sesiunile 2026-05

| Fix | Commit | Impact |
|-----|--------|--------|
| Layer 2.5 N:M complet (oferta_by_key vs oferta_map) | 70e67b9 | +25 matched BR O3 |
| Parser: `82 M` format NR_ALPHA_INLINE guard | 38e0b6f | logic corect |
| Scatter: is_f3_um single-token (Art. asimilat fix) | scatter-fix | +19 matched BR O3 |
| Dedup: deviz_key hash (nu deviz_cod string) | 2026-05-25 | BR O1/O2: 21→35 grupuri matched |
| Col1 raport: Obiectul\|Categoria (nu hash/cod) | 2026-05-25 | display corect |
| group_comparator: eliminat dead deviz_cod lookups | 2026-05-25 | cod mai curat |

### Active

| # | Problema | Impact | Fix propus |
|---|----------|--------|------------|
| 1 | SSR 0 grupuri holistic — ref 2 grupuri/obiect vs oferta 8+ sub-devize; matching bijective 1→many | 0 matched SSR | strategie noua in group_comparator.py |
| 2 | BR O4: 3 ref-only, 12 oferta-only | raport incomplet | investigare structura document |
| 3 | BR O3: 3 oferta-only | minor | investigare |
| 4 | CAV Maneciu O2: 1 ref_only DUPLEX | minor | investigare header deviz |

### Rezolvate in v3 (2026-06-10/11)

| Fix | Impact |
|-----|--------|
| Scatter counter (last_scatter_counter) | BAZIN CAV Maneciu nr=4.1→5, 21/21 NC comisie acoperite |
| Semantic comparator (Pass1+Pass2) | COD_NORMATIV_DIFERIT + SPECIFICATIE_DIFERITA detectate |
| Comparatie lista layout (tblGrid, margins, keep_with_next) | DOCX stabil in orice viewer, header nu se desparte de tabel |

---

## Diagrama Secventa: Sursa de Incarcare (Pipeline Separat)

> Pipeline independent. Entry point: `gen_sursa_incarcare.py`. Zero modificari la pipeline multi-client.

```
Utilizator          gen_sursa_incarcare     f3_page_classifier    deviz_header_extractor    f3_price_extractor    lista_verifier    sursa_incarcare_writer
    │                       │                       │                       │                       │                    │                       │
    │  --client "EP"        │                       │                       │                       │                    │                       │
    │  --json di_referinta  │                       │                       │                       │                    │                       │
    │──────────────────────▶│                       │                       │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                 ClientConfig.detect_clients() │                       │                       │                    │                       │
    │                 _pick_client(), _pick_json()  │                       │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  [1/4] classify_pages │                       │                       │                    │                       │
    │                       │──────────────────────▶│                       │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │                       │ [check ckpt]          │                       │                    │                       │
    │                       │                       │ {json_stem}_page_classes.json                 │                    │                       │
    │                       │                       │  ─▶ if exists: return │                       │                    │                       │
    │                       │                       │  ─▶ else: LLM batch   │                       │                    │                       │
    │                       │                       │       Claude API       │                       │                    │                       │
    │                       │                       │       save checkpoint  │                       │                    │                       │
    │                       │◀─ page_classes        │                       │                       │                    │                       │
    │                       │   (F3 count printed)  │                       │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  [2/4] extract_deviz_headers()                │                       │                    │                       │
    │                       │──────────────────────────────────────────────▶│                       │                    │                       │
    │                       │◀─ deviz_headers[]     │                       │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  [3/4] extract_prices(page_classes, deviz_headers, checkpoint_path)   │                    │                       │
    │                       │──────────────────────────────────────────────────────────────────────▶│                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │                       │                       │    per pagina F3:      │                    │                       │
    │                       │                       │                       │    skip header zone   │                    │                       │
    │                       │                       │                       │    (pana la "5=3x4")  │                    │                       │
    │                       │                       │                       │    state machine:     │                    │                       │
    │                       │                       │                       │      CAPITOL           │                    │                       │
    │                       │                       │                       │      ART_NR            │                    │                       │
    │                       │                       │                       │      COD_NAME          │                    │                       │
    │                       │                       │                       │      UM + 3×NUMBER     │                    │                       │
    │                       │                       │                       │      BREAKDOWN×4       │                    │                       │
    │                       │                       │                       │      SUB_NR            │                    │                       │
    │                       │                       │                       │    _assemble_deviz():  │                    │                       │
    │                       │                       │                       │      control_ok check  │                    │                       │
    │                       │                       │                       │      suspect flag      │                    │                       │
    │                       │                       │                       │    save checkpoint     │                    │                       │
    │                       │◀─ extracted[]         │                       │                       │                    │                       │
    │                       │   (N articole, M breakdown printed)           │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  [4/4] verify(extracted, deviz_headers)       │                       │                    │                       │
    │                       │──────────────────────────────────────────────────────────────────────────────────────────▶│
    │                       │                       │                       │                       │ iter 1..5:         │                       │
    │                       │                       │                       │                       │  NR_CRT_GAPS [HIGH]│                       │
    │                       │                       │                       │                       │  TOTAL_CAPITOL [HIGH]                      │
    │                       │                       │                       │                       │  TOTAL_DEVIZ [HIGH]│                       │
    │                       │                       │                       │                       │  BREAKDOWN_CTRL [W]│                       │
    │                       │                       │                       │                       │  COUNT_DEVIZE [I]  │                       │
    │                       │                       │                       │                       │  no HIGH → OK/WARN │                       │
    │                       │                       │                       │                       │  HIGH×5 → RED      │                       │
    │                       │◀─ verification{status, iterations, checks}    │                       │                    │                       │
    │                       │   save sursa_verified_{stem}.json             │                       │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  inject status: for deviz in extracted: deviz['status'] = status      │                    │                       │
    │                       │                       │                       │                       │                    │                       │
    │                       │  write_docx(extracted, docx_path)             │                       │                    │──────────────────────▶│
    │                       │  write_xlsx(extracted, xlsx_path)             │                       │                    │──────────────────────▶│
    │                       │  write_pdf(docx_path, output_dir) [optional]  │                       │                    │   soffice CLI         │
    │                       │◀─ Lista-proiect-{ACRONIM}-{stem}.docx/xlsx/pdf                        │                    │                       │
    │◀─ output paths printed│                       │                       │                       │                    │                       │
```

---

### Secventa Detaliata: f3_price_extractor State Machine

```
pagini F3 (lines per pagina)
    │
    ▼
Header zone SKIP (pana la "5 = 3 x 4")
    │
    ▼
Article zone — dispatch per linie:

  LINIE                     EVENT           ACTIUNE
  ──────────────────────────────────────────────────────
  all-caps fara cifre   →   CAPITOL         nou capitol (titlu)
  "TOTAL XYZ 1234.56"   →   TOTAL_CAPITOL   capitol.total_capitol = float
  numar intreg singur   →   ART_NR          articol.nr_crt = N
  "COD - denumire"      →   COD_NAME        articol.cod + denumire  ⚠ INAINTE de CAPITOL
  token UM valid        →   UM              articol.um = UM
                                            deschide in_num_window (3 numere)
  numar (in window)     →   NUMBER          cant | pret_unitar | total
  "material:" etc.      →   BREAKDOWN       breakdown key activ
  nr decimal (1.1)      →   SUB_NR          sub_item (DOAR daca NOT in_num_window)
  altceva               →   TEXT            denumire continua

    ⚠ in_num_window se inchide dupa 3 numere
      Previne: "225.000" (pret) clasificat ca SUB_NR
    │
    ▼
_assemble_deviz(events, header):
    ├── construieste articole, capitole, total_deviz
    ├── pentru fiecare articol cu breakdown:
    │     control_ok = |mat+man+utl+tra - pret_unitar| < 0.02
    │     art['suspect'] = not control_ok
    └── returns deviz dict
```

---

### Retry Loop: lista_verifier

```
extracted[]  +  deviz_headers[]  +  raw_nrs/raw_max_nr  +  footer{}
      │
      ▼
iteration 1..5:
      │
      ├── NR_CRT_GAPS:    per deviz, nr_crt int consecutive fara salturi
      │                   gaps = [(deviz_key, nr_a, nr_b)]
      │                   raw_nrs distinge golul real de numerotarea sarita
      │                   dintr-o situatie de lucrari → numbering_skips
      │
      ├── LAST_NR_CRT:    max(nr_crt) extras == max(nr_crt) printat in raw
      │
      ├── TOTAL_CAPITOL:  |sum(art.total) - capitol.total_capitol| ≤ 0.05
      │                   failures = [(deviz_key, capitol, computed, extracted)]
      │                   total_capitol e CITIT din linia 'TOTAL <capitol>'
      │
      ├── TOTAL_DEVIZ:    |sum(capitol.total_capitol) - deviz.total_deviz| ≤ 0.05
      │                   TAUTOLOGIC: total_deviz e calculat ca aceeasi suma
      │                   (f3_price_extractor._assemble_deviz) → nu poate esua
      │
      ├── TOTAL_1_DOC:    |sum(total_deviz) - footer.total_1| ≤ 0.05
      │                   'TOTAL 1 (Cheltuieli directe)' CITIT din recapitulatie
      │                   singurul check care prinde un articol/capitol pierdut
      │                   skipped daca doc nu printeaza TOTAL 1, sau printeaza
      │                   mai multe (o recapitulatie per deviz → nu e total doc)
      │
      ├── FOOTER:         cele 4 randuri de recapitulatie prezente +
      │                   fara_TVA + TVA = cu_TVA (±0.05) +
      │                   fara_TVA × pct = TVA (±1.0, TVA e rotunjit la leu)
      │
      ├── HOLLOW_ARTICLES: articole cu total/cantitate dar fara cod+denumire
      │
      ├── BREAKDOWN_CTRL: articole cu suspect=True → lista nr_crt
      │
      └── COUNT_DEVIZE:   len(extracted) vs len(deviz_headers)
                          ok=None + skipped=True daca headers=None

      ↓
      high_failures = [NR_CRT_GAPS, LAST_NR_CRT, TOTAL_CAPITOL, TOTAL_DEVIZ,
                       TOTAL_1_DOC, FOOTER] care nu ok
      ↓
      if not high_failures:
          status = WARN daca BREAKDOWN_CTRL / HOLLOW_ARTICLES fail, altfel OK
          return {status, iterations, checks}
      else if reextract_fn si iteration < 5:
          current = reextract_fn(current, checks, iteration)
          → urmatoarea iteratie
      else:
          return {status: RED, iterations, checks}
```
