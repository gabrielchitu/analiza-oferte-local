# Pipeline — Diagrama de Secvență și Inventar Imperfectiuni

**Data**: 2026-05-08  
**Rulare de referință**: Haiku (`claude-haiku-4-5`) pe 3 oferte  
**Stare checkpointuri**: existente (clasificarea LLM nu s-a re-rulat)

---

## Rezultate Rulare Curentă

| Document      | Articole extrase | Devize |
|---------------|-----------------|--------|
| Referința     | 1 279           | 41     |
| Oferta 1      | 1 510           | ~30    |
| Oferta 2      | 428             | 20     |
| Oferta 3      | 210             | 25     |

| Oferta   | Matched | LIPSA | EXTRA | ORPHAN | DIFERENTA | UM_DIFERIT | COD_SIMILAR | TOTAL |
|----------|---------|-------|-------|--------|-----------|------------|-------------|-------|
| Oferta 1 | 1 164   | 99    | 163   | 364    | 84        | 45         | 16          | 771   |
| Oferta 2 | 424     | 839   | 4     | 88     | 15        | 22         | 6           | 974   |
| Oferta 3 | 210     | 1 053 | 0     | 60     | 1         | 0          | 2           | 1 116 |

**Nota Oferta 2 — descompunere LIPSA:**
- 198 LIPSA din devize **absente** în oferta (oferta nu acoperă acel scope) — corecte
- 641 LIPSA din devize **comune** ref+oferta — problematice (ref are 1 081 articole, oferta are 428)

---

## Diagrama de Secvență Completă

```
DI JSON (di_referinta.json / di_oferta_N.json)
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 1 — PAGE CLASSIFICATION                                ║
║  fișier: shared/f3_page_classifier.py                         ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  build_page_classifications(pages):                           ║
║    pentru fiecare pagina din DI JSON:                         ║
║      1. NON_F3 check (FORMULAR C/F, CENTRALIZATOR, etc.)      ║
║         → if match: label=NON_F3, RESET deviz context         ║
║      2. RECAPITULATIA check → NON_F3                          ║
║      3. STADIUL FIZIC regex (ISDP format, primele 3 linii)    ║
║         → F3, cod deviz extras din linie                      ║
║      4. Stadiul fizic eDevize (full_content search)           ║
║         → F3, is_header = True dacă NU are coduri articole    ║
║      5. Formular F3 regex                                     ║
║         → F3, cod din "NNNNNN pag N Formular" sau fallback    ║
║      6. SECTIUNEA TEHNICA regex                               ║
║         → F3, cod = "" (se propagă din context)               ║
║      7. >>> componenta + coduri → F3                          ║
║      8. "NNNNNN pag" în primele 150 chars + coduri → F3       ║
║      9. altfel → AMBIGUOUS (needs_llm = True)                 ║
║                                                               ║
║  Propagare deviz:                                             ║
║    F3 cu cod → setează current_deviz_cod                      ║
║    F3 fără cod → folosește current_deviz_cod propagat         ║
║    NON_F3 → RESETEAZĂ current_deviz_cod = ""  ← [!]          ║
║    AMBIGUOUS → RESETEAZĂ current_deviz_cod = ""  ← [!]       ║
║                                                               ║
║  classify_pages() — LLM batch:                                ║
║    pagini cu needs_llm=True → batch LLM                       ║
║    LLM → is_f3, deviz_cod per pagina                          ║
║    fallback: dacă LLM fail → pagina rămâne NON_F3             ║
║                                                               ║
║  CHECKPOINT: salvat în output_AO/checkpoints/                 ║
║    dacă există → SKIP TOTAL al clasificării LLM               ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!] BUG POTENTIAL: NON_F3 între pagini F3 rupe propagarea    ║
║  [!] AMBIGUOUS fără răspuns LLM = pierdut definitiv           ║
║  [!] CHECKPOINT fără versioning → stale după bug-fix          ║
║  [!] Formate noi (noi soft devize) → AMBIGUOUS → LLM sau pierd║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 2 — ARTICLE EXTRACTION                                 ║
║  fișiere: shared/f3_extractor.py, shared/f3_regex_parser.py   ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  extract_articles_v3(page_classifications):                   ║
║    pentru fiecare pagina cu is_f3=True, header_only=False:    ║
║      deviz_cod = normalize_deviz_cod(cod)  [U→0]              ║
║      extract_articles_regex(lines, deviz_cod, deviz_den)      ║
║        → RegexStateParser: state machine pe linii             ║
║        → detectează cod articol, UM, cantitate, denumire      ║
║        → suportă multi-line denumiri                          ║
║      _extract_components_from_section(text)                   ║
║        → extrage componente din $breviar (>>> componenta)      ║
║      dedup per pagina by (cod.upper(), deviz_cod)             ║
║        → ține articolul cu cantitate maximă                   ║
║                                                               ║
║  extract_articles_from_tables_smart(di.tables):               ║
║    Pass 1: identifică tabelele metadata (Stadiul fizic:)      ║
║    Pass 2: identifică tabelele F3 data (SECTIUNEA TEHNICA)    ║
║    → linkează table data cu deviz din metadata precedent      ║
║    merge: dedup cu articole din pagini (4-tuple key)          ║
║                                                               ║
║  Dedup final în local_run.py:                                 ║
║    by (deviz, cod, um, cantitate) 4-tuple                     ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!] Coduri cu sufixe speciale (#, [7]) → neextrase           ║
║  [!] Pagini cu deviz_cod="" → namespace coliziune în dedup    ║
║  [!] OCR: coduri cu litere confuzabile (O/0, l/1) → partial  ║
║  [!] Articole în devize neidentificate = pierdute             ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼  [doar pentru oferte, nu referință]
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 2.5 — FILTRARE DEVIZE OFERTĂ (local_run.py)           ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  ref_deviz_codes = set(deviz din referință)                   ║
║  page_classes filtrate: păstrează doar pagini cu              ║
║    deviz_cod ∈ ref_deviz_codes                                ║
║                                                               ║
║  Rezultat:                                                    ║
║    Oferta 2: 98 → 75 pagini F3 active                         ║
║    Oferta 3: 117 → 25 pagini F3 active  ← AGRESIV            ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!] Filtrare preventivă elimină devize extra din ofertă      ║
║  [!] Nu vedem CE oferă oferta în plus față de referință       ║
║  [!] Oferta 3: 92 din 117 pagini = ignorate complet           ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 3 — DEVIZ NORMALIZATION                                ║
║  fișier: shared/deviz_normalizer.py                           ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  normalize_devize(ref_articole, oferta_articole):             ║
║    construiește mapping: oferta_deviz_den → ref_deviz_den     ║
║                                                               ║
║    Tier 1: exact key match (strip prefixe numerice)           ║
║      "001 226108 STRUCTURA" → "STRUCTURA DE REZISTENTA"       ║
║    Tier 2: strip prefix extins + exact key                    ║
║      "oferta 226U08 ALIMENTARE" → strip → match               ║
║    Tier 3: word overlap > 0.6                                 ║
║      "INSTALATII INCALZIRE" ↔ "INSTALATII DE INCALZIRE"       ║
║    Tier 4: LLM fallback                                       ║
║      → trimite toate denumirile nerezolvate la LLM            ║
║      → răspuns: {oferta_den: ref_den} JSON                   ║
║      [!!!] HAIKU WRAP JSON în ```json\n...\n```               ║
║      [!!!] json.loads() crăpă → WARNING + doar mapping local  ║
║                                                               ║
║  Rezultat aplicat: oferta_art["deviz_denumire"] = ref_den     ║
║  ATENȚIE: deviz_cod NU este modificat (doar denumirea)        ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!!!] Haiku JSON bug → LLM step silently skipped             ║
║  [!] deviz_cod rămâne neschimbat → matching pe cod e ok       ║
║  [!] dacă tier 1-3 nu prinde → deviz_den rămâne din ofertă   ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 4 — ORPHAN DETECTION                                   ║
║  fișier: shared/orphan_detector.py                            ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  detect_orphans(ref_articole, oferta_norm):                   ║
║    găsește: articole cu același cod în ambele documente        ║
║             dar în devize DIFERITE                            ║
║    → emit ARTICOL_ORPHAN pentru fiecare                        ║
║                                                               ║
║  Statistici rulare curentă:                                   ║
║    Oferta 1: 364 orphane                                      ║
║    Oferta 2:  88 orphane                                      ║
║    Oferta 3:  60 orphane                                      ║
║    TOTAL:    512 orphane nerezolvate                          ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!!!] Orfanele NU sunt excluse din matching                  ║
║  [!!!] → același articol apare și ca LIPSA (din ref) +        ║
║          și ca EXTRA (din ofertă) = DUBLU NUMĂRAT             ║
║  [!]  NU se încearcă potrivire cross-deviz                    ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 5 — MATCHING (3 straturi)                              ║
║  fișiere: AgentComparator_local.py, shared/article_matcher.py ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  Layer 1 — Exact match pe (deviz_cod, cod):                   ║
║    _deviz_key(art) = normalize(art.deviz) [U→0]               ║
║    _art_key(art)   = (deviz_key, cod)                         ║
║    ref_map[key] vs oferta_map[key] → direct match             ║
║    → diffs via compare_articles() → DIFERENTA_CAMP, UM_DIFERIT║
║                                                               ║
║  Layer 2 — Normalized cod match (same deviz):                 ║
║    _normalize_cod(cod):                                       ║
║      l→1, L→1  (OCR: litera l vs cifra 1)                    ║
║      O→0       (OCR: litera O vs cifra 0)                     ║
║      #→1       (sufixe hash)                                  ║
║      strip non-alfanumerice                                   ║
║    → COD_SIMILAR dacă match găsit                             ║
║                                                               ║
║  Layer 3 — LLM fuzzy match per deviz grup:                    ║
║    pre-filtru: cod_similarity >= 0.75 (SequenceMatcher)        ║
║    dacă niciun candidat → skip LLM ("No candidate pairs")     ║
║    batch: max 50 ref + candidați ofertă per call LLM          ║
║    FUZZY_SYSTEM_PROMPT: "diferă max 1-2 caractere + denumire" ║
║    [!!!] HAIKU WRAP JSON → json.loads crăpă → skip batch      ║
║    [!!!] la fail → return [] → articolele rămân LIPSA         ║
║                                                               ║
║  ARTICOL_LIPSA: ref neacoperit după toate 3 straturi          ║
║  ARTICOL_EXTRA: ofertă neacoperit după toate 3 straturi       ║
║    (excluse componentele din breviar deja cunoscute)          ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!!!] Haiku JSON bug → Layer 3 silently disabled             ║
║  [!] Layer 3 e strict pe ACELAȘI deviz → orfanele nu benefic  ║
║  [!] cod_similarity 0.75 poate fi prea strict sau prea lax    ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
╔═══════════════════════════════════════════════════════════════╗
║  ETAPA 6 — VALIDATION + REPORTS                               ║
║  fișiere: shared/extraction_validator.py, report_word.py      ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  mark_suspicious_extras():                                    ║
║    ARTICOL_EXTRA cu cod prezent în DI ref → posibil_omis      ║
║    (13 marcate în oferta 1)                                   ║
║                                                               ║
║  Adăugare orphane la neconformitati (tip=ARTICOL_ORPHAN)      ║
║                                                               ║
║  generate_word() → Raport_Oferta_N.docx                       ║
║    XLSX comentat (dezactivat)                                  ║
║                                                               ║
╠═══════════════════════════════════════════════════════════════╣
║  [!] ARTICOL_ORPHAN și ARTICOL_LIPSA pot fi același articol   ║
║  [!] Raportul nu distinge LIPSA-scope vs LIPSA-extracție       ║
║  [!] XLSX dezactivat — raportul Excel lipsește                 ║
╚═══════════════════════════════════════════════════════════════╝
   │
   ▼
output_AO/Raport_Oferta_N.docx
output_AO/comparatie_oferta_N.json
```

---

## Inventar Complet Imperfectiuni

### 🔴 CRITICE (produc rezultate greșite sigur)

| # | Problema | Locație | Impact |
|---|----------|---------|--------|
| C1 | **Haiku returnează ```json → json.loads() crăpă** | anthropic_adapter.py | Layer 3 fuzzy + deviz norm LLM = disabled silentios |
| C2 | **ARTICOL_ORPHAN dublu numărare** | orphan_detector + matcher | 512 articole apar și LIPSA și EXTRA simultan |

### 🟠 IMPORTANTE (produc zgomot semnificativ în raport)

| # | Problema | Locație | Impact |
|---|----------|---------|--------|
| I1 | **NON_F3 resetează deviz context** | f3_page_classifier.py:224 | Pagini F3 ulterioare = deviz_cod="" → dedup coliziune |
| I2 | **Filtrare agresivă oferta 3 (117→25 pagini)** | local_run.py:95-101 | 92 pagini ignorate, 1 053 LIPSA "artificiale" |
| I3 | **Raportul nu distinge LIPSA-scope vs LIPSA-extracție** | report_word.py | Toate LIPSA arată la fel, nu știm ce e real vs bug |
| I4 | **Checkpoint fără versioning** | local_run.py:74-89 | Bug-fix la clasificare = invizibil la re-rulare |

### 🟡 MINORE (edge cases, impact limitat)

| # | Problema | Locație | Impact |
|---|----------|---------|--------|
| M1 | Coduri cu `[7]`, `[]` sufixe → neextrase | f3_regex_parser.py | ~6 articole din 1279 referință |
| M2 | Pagini AMBIGUOUS fără răspuns LLM → pierdute | f3_page_classifier.py:261 | Nedeterminat, probabil mic |
| M3 | deviz_cod="" pe pagini orfane → namespace coliziune dedup | f3_extractor.py:657 | Posibil pierdere articole |
| M4 | XLSX dezactivat | local_run.py:229-236 | Raportul Excel lipsește |

---

## Root Causes pentru ARTICOL_LIPSA în cifre

```
Oferta 1 — 99 LIPSA:
  • ~16 COD_SIMILAR găsiți (Layer 2) = rămân ~83 reale
  • din care: OCR coduri nedetectate de Layer 3 (Haiku bug) = necunoscut
  • din care: pagini F3 neclasificate = necunoscut
  • din care: genuine (bidder nu oferă) = necunoscut

Oferta 2 — 839 LIPSA:
  • 198 = LIPSA-scope (devize absente din ofertă) — CORECTE
  • 641 = LIPSA în devize comune ref+ofertă — PROBLEMATICE
    → oferta 2 are 428 articole vs 1081 în ref, în aceleași 20 devize
    → 37% coverage = posibil extracție ratată SAU ofertă cu mai puțin scope

Oferta 3 — 1053 LIPSA:
  • ~majority = LIPSA-scope (oferta 3 acoperă alt scope)
  • 210 articole extrase (ref 1279) → ratio mic dar devize diferite
```

---

## Fluxul Ideal (după remedieri)

```
DI JSON
  ↓
[1] PAGE CLASSIFICATION (cu checkpoint versionat)
    regex → LLM batch (cu JSON fix) → checkpoint
  ↓
[2] ARTICLE EXTRACTION
    regex parser → tables → merge
  ↓
[2.5] FILTRARE DEVIZE (cu raportare explicită scope gaps)
  ↓
[3] DEVIZ NORMALIZATION (cu JSON fix Haiku)
  ↓
[4] ORPHAN RESOLUTION (cross-deviz match cu confirmare denumire)
    → orfanele rezolvate = excluse din LIPSA + EXTRA
    → orfanele nerezolvate → ARTICOL_ORPHAN (genuine deviz mismatch)
  ↓
[5] MATCHING (cu Layer 3 funcțional)
    L1: exact (deviz, cod)
    L2: normalized cod
    L3: LLM fuzzy (Haiku fix)
  ↓
[6] CLASIFICARE LIPSA
    LIPSA-SCOPE:    articol din deviz absent în ofertă
    LIPSA-EXTRAS:   articol din deviz comun, neextras
    LIPSA-GENUINE:  articol care chiar lipsește din ofertă
  ↓
[7] RAPORT cu categorii clare
```
