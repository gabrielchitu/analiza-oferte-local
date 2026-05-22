# Pipeline — Diagrama de Secvență
**Actualizat:** 2026-05-22 | **Versiune:** v8.0

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
    │                       │                │                       │          dedup (cod, deviz, cantitate)              │                   │                         ║
    │                       │                │                       │          _apply_parent_inheritance()                │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    │                       │                │◀─ articole[]          │                          │                          │                   │                         ║
    │                       │                │                       │                          │                          │                   │                         ║
    ║════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════╝
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  (per oferta)         │                          │                          │                   │                         │
    │                       │                │  match_devize_by_denomination()                  │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────────────────────────────▶│                   │                         │
    │                       │                │                       │                          │          check checkpoint │                   │                         │
    │                       │                │                       │                          │          fuzzy match      │                   │                         │
    │                       │                │                       │                          │          deviz_den→ref    │                   │                         │
    │                       │                │◀─ deviz_mapping{}     │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  match_global(ref, oferta_norm)                  │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────────────────────────────────────────────────▶│                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │          Layer 1: exact (deviz,cod)          │                         │
    │                       │                │                       │                          │          Layer 2: normalized cod              │                         │
    │                       │                │                       │                          │          Layer 2.1: trailing digit            │                         │
    │                       │                │                       │                          │          Layer 2.5: OCR similar ≥0.80 N:M     │                         │
    │                       │                │                       │                          │          Layer 3: LLM fuzzy (disabled)        │                         │
    │                       │                │                       │                          │          Post: lenient UM ($ coduri)          │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │◀─ matches[], neconf[] │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │  build_raport_ierarhic()                         │                          │                   │                         │
    │                       │                │──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────▶│
    │                       │                │                       │                          │                          │                   │                         │
    │                       │                │                       │                          │                          │      organizeaza ierarhic pe deviz          │
    │                       │                │                       │                          │                          │                   │  generate_word()         │
    │                       │                │                       │                          │                          │                   │  tabel 11 col            │
    │                       │                │◀─ Raport_Oferta_N.docx│                          │                          │                   │                         │
    │                       │                │   comparatie_oferta_N.json                       │                          │                   │                         │
    │                       │                │                       │                          │                          │                   │                         │
    │◀─ ✓ Pipeline complet  │                │                       │                          │                          │                   │                         │
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

## Imperfectiuni Known (2026-05-22)

### Rezolvate in sesiunile 2026-05

| Fix | Commit | Impact |
|-----|--------|--------|
| Layer 2.5 N:M complet (oferta_by_key vs oferta_map) | 70e67b9 | +25 matched BR O3 |
| Parser: `82 M` format NR_ALPHA_INLINE guard | 38e0b6f | logic corect |
| Scatter: is_f3_um single-token (Art. asimilat fix) | HEAD | +19 matched BR O3 |

### Active

| # | Problema | Impact | Fix propus |
|---|----------|--------|------------|
| 1 | IZDO3D1 OCR: Layer 1 consuma IZD03D1, IZDO3D1 ramane LIPSA | 1 LIPSA per oferta | Normalizare O↔0 global sau Layer 2 re-consume excess |
| 2 | SD deviz_matcher: text cod vs numeric eDevize | 600+ DEVIZ_MM | deviz_matcher: matching pe cod articol, nu doar denumire |
| 3 | SSR O3 EXTRA=315 | raport zgomotos | Investigare root cause (deviz_mismatch?) |
| 4 | SSR DEVIZ_MM=300+ | raport zgomotos | Investigare deviz mapping |
| 5 | CM O2 LIPSA=84 | neclar | Breakdown $-coduri vs principale |
