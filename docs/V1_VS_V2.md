# V1 vs V2 — Comparație Arhitecturală

**Data:** 2026-06-02  
**Branch V2:** `feature/v2-table-extraction`

---

## Rezumat Executiv

| Dimensiune | V1 (producție) | V2 (development) |
|------------|----------------|------------------|
| Extragere articole | Regex state machine pur | Tabel Azure DI + fallback regex |
| Matching grupuri | LLM + knowledge cache | Deterministic (SequenceMatcher) |
| Matching articole | Multi-layer fuzzy (OCR-aware) | Set-based (NR→COD→hash) |
| Dependențe LLM runtime | Page classifier + Group comparator | Page classifier only (shared checkpoint) |
| Configurare per-client | Da (SKIP_RE, knowledge JSON) | Nu (universal, automat) |
| Reproducibilitate | Parțial (LLM non-determinist) | Totală (fără LLM la runtime) |

---

## 1. Extragere Articole

### V1 — Regex State Machine

```
f3_regex_parser.py::extract_articles_regex()

Preprocess:
  _preprocess_scattered_format()   — combina linii scatter (NR + COD + DESC separate)
  _preprocess_compound_um()        — combina "NR" + "UM" separate
  _merge_wrapped_codes()           — uneste coduri rupte pe 2 linii

State machine:
  _IDLE → _WAITING → _READING → _IDLE
           (NR_CRT)   (COD)

Subcomponente detectate inline (în parser):
  L: prefix, >>> marker, .L suffix, SUBCOMP_PREFIXED_RE
```

**Caracteristici:**
- Un singur pas over linii text
- Subcomponentele detectate și marcate în același pas cu extragerea
- Sensibil la OCR artifacts (linii rupte, format scatter)
- Necesită tuning per-client: `SKIP_RE`, `NR_SUBITEM`, `UM_KNOWN`, `SUBCOMP_PREFIXED_RE`

### V2 — Dual-Source cu Fallback

```
extraction_v2.py::ExtractionOrchestrator.extract()

Per pagina:
  TemplateDetector    → fingerprint tip document (DI table vs text)
  TableExtractor      → Azure DI table → articole (coloane COD/UM/CANT)
  RegexExtractor      → f3_regex_parser (fallback dacă tabel absent/incomplet)
  ExtractionComparator → alege sursa mai bună per pagina

Post-extragere:
  HierarchyCorrector  → detectează componente orfane, forward-fill parinte
```

**Caracteristici:**
- Încearcă structura tabelă nativă din Azure DI (mai precisă geometric)
- Fallback transparent la regex dacă tabel absent sau incomplet
- Corectarea ierarhiei ca pas separat (nu inline)
- Nu necesită tuning per-client pentru formatul de bază

**Diferența cheie:** V1 extrage din text brut linie-cu-linie. V2 încearcă mai întâi structura tabelară pe care Azure DI o recunoaște automat (coloane aliniate), mai robustă la variații de format.

---

## 2. Identificarea Grupurilor (Deviz Keys)

### V1 — deviz_key MD5 Hash

```python
deviz_key = md5(f"{obiectivul}|{obiectul}|{categoria}").hexdigest()
```

- Hash calculat din textul complet al header-ului
- Grupuri identificate la group_comparator (după extragere)
- Un deviz_cod poate mapa la mai multe deviz_key-uri (OBIECTUL diferit)
- Calculat de `group_comparator.py` la matching, nu în extragere

### V2 — Compound Key (deviz_cod, obiectul_text)

```python
group_key: Tuple[str, str] = (page_deviz_cod, page_obj)
# ex: ("BLC4", "2 LUCRARI CONEXE BLOC A")
#     ("BLC4", "4 LUCRARI CONEXE BLOC A2")
```

- Key compus construit **în timpul extragerii** (extraction_v2.py)
- `obiectul_text` = valoarea per-pagina din page_classes checkpoint
- Forward-fill în cadrul aceluiași deviz_cod; reset când deviz_cod se schimbă
- Permite split automat: 7 deviz_cods → 35 grupuri logice (Blocuri Racari)
- Grupuri multiple per cod: `BLC4__0`, `BLC4__1`, ..., `BLC4__5`

**Diferența cheie:** V1 calculează identitatea grupului după extragere (hash pe text header). V2 o calculează în timpul extragerii (compound key din metadata pagini), ceea ce permite split-ul automat fără LLM.

---

## 3. Matching Grupuri

### V1 — Multi-Phase cu LLM Fallback

```
Phase 1:   deviz_key identic (exact hash) → match sigur
Phase 1.5: deviz_cod ref = prefix al offer.categoria → compatibilitate ISDP/eDevize
Phase 2a:  group_match_knowledge.json (cache manual + LLM anterior)
Phase 2b:  LLM fallback — Claude API, text complet OBIECTIVUL|OBIECTUL|CATEGORIA
           chunk=15 grupuri, max_tokens=2000
```

**Caracteristici:**
- Dependență LLM la runtime pentru grupuri nerezolvate
- Knowledge cache acumulat (nu pierde între rulări)
- Non-determinist: același input poate da rezultat diferit la re-rulare (LLM)
- Necesită `ANTHROPIC_API_KEY` la runtime pentru grupuri noi
- Produce `matching_debug_oferta_N.json` cu trace complet

### V2 — Deterministic SequenceMatcher

```python
# group_set_matcher.py::_group_score()
ref_cat_norm = _normalize(ref_group["categoria"])    # strip cod prefix
off_cat_norm = _normalize(offer_group["categoria"])
cat_sim = SequenceMatcher(None, ref_cat_norm, off_cat_norm).ratio()

if obiectul_has_letters(both sides):
    obj_sim = SequenceMatcher(None, ref_obj_norm, off_obj_norm).ratio()
    score = 0.7 * cat_sim + 0.3 * obj_sim
else:
    score = cat_sim  # obiectul pur numeric (cod EU) — ignorat

MATCH_THRESHOLD = 0.55
```

**Caracteristici:**
- 100% determinist, 0 API calls la runtime
- `_normalize()` strip coduri reale (`\d+`, `[A-Z]{1,4}\d+[A-Z]?`) — nu cuvinte normale
- Greedy 1:1 assignment (sort descendent sim, primul câștigă)
- Fallback: exact deviz_cod string dacă header text absent
- Nu produce matching_debug — trace implicit în holistic JSON

**Diferența cheie:** V1 cere LLM pentru cazuri ambigue (grup nou, format nou). V2 nu cere niciodată LLM la runtime — orice grup nerezolvat rămâne ref_only/oferta_only.

---

## 4. Matching Articole

### V1 — Multi-Layer Fuzzy (OCR-Aware)

```
Layer 1:   N:M exact pe (deviz_cod, article_cod)
Layer 2:   Normalized cod: _normalize_cod() — I→1, O→0, OCR patterns
           Strip prefix $, trailing normalization
Layer 2.1: Trailing digit: IC35D ↔ IC35D1
Layer 2.5: SequenceMatcher ≥ 0.80 pe cod (fuzzy OCR)
Layer 3:   LLM fuzzy — DISABLED (fallback dezactivat)
```

**OCR Knowledge:** `ocr_patterns_knowledge.json` — substitutions additive, union cu hardcoded.

### V2 — Set-Based (NR → COD → Hash)

```python
# set_based_matcher.py::match_articles_by_key()
Priority:
  1. NR (număr de ordine) — identic în ref și ofertă
  2. COD — codul de catalog normalizat (exact)
  3. hash(descriere + UM + cantitate) — pentru articole fără cod
```

**Caracteristici:**
- Fără fuzzy matching la nivel de cod
- Fără OCR-awareness (nu face I→1/O→0)
- Mai simplu și predictibil dar mai puțin robust la OCR errors în coduri

**Diferența cheie:** V1 are 4+ layers de fallback pentru OCR și format variation. V2 are 3 criterii deterministe. V2 poate rata matches pe care V1 le rezolvă prin fuzzy (Layer 2/2.5).

---

## 5. Corectare Ierarhie Articole

### V1 — Inline în Parser

Subcomponentele detectate în același pas cu extragerea:
- `L:` prefix → `is_component=True`
- `>>> marker` → subcomponentă
- `.L suffix` / `SUBCOMP_PREFIXED_RE` → componentă prefixată
- Cantitate/UM moștenite de la articolul parinte

### V2 — Post-Processing Separat

```python
# hierarchy_corrector.py::HierarchyCorrector.correct()
Input:  articole brute din extragere (table sau regex)
Output: articole cu is_component + parent_code corecte

Pași:
  1. _normalize_article_fields() — standardizare câmpuri
  2. Detectare relații parinte-copil rupte (HierarchyAnalyzer)
  3. Forward-fill parinte pentru articole orfane
  4. _denormalize_article_fields() — refacere format original
```

**Avantaj V2:** Corectarea ierarhiei decuplată de extragere — poate fi aplicată pe orice sursă (table sau regex), mai ușor de testat izolat.

---

## 6. Utilizare LLM

| Etapă | V1 | V2 |
|-------|----|----|
| Page classification | ✅ LLM batch (~10 calls/offer) | ✅ LLM batch (shared checkpoint cu V1) |
| Group matching | ✅ LLM fallback (Phase 2b) | ❌ NICIODATĂ |
| Article matching | ❌ (Layer 3 disabled) | ❌ |
| Marker learning | ❌ DISABLED (false positives) | ❌ N/A |

**V2 reutilizează checkpointul V1** — dacă V1 a rulat deja pe același fișier, V2 nu face niciun API call (page_classes deja cached).

---

## 7. Configurare per-Client

### V1 — Tuning Manual

| Fișier/Loc | Scop |
|------------|------|
| `f3_regex_parser.py::SKIP_RE` | Filtrare coduri catalog de ignorat |
| `f3_regex_parser.py::NR_SUBITEM` | Marker decimal pentru subcomponente |
| `f3_regex_parser.py::SUBCOMP_PREFIXED_RE` | Pattern prefixe componente |
| `shared/f3_knowledge.py` | Context LLM per client (markers, deviz_format) |
| `shared/group_match_knowledge.json` | Cache perechi grup ref↔ofertă |
| `shared/ocr_patterns_knowledge.json` | Substitutii OCR aditionale |
| `shared/deviz_header_extractor.py::_DEVIZ_OFERTA_LETTERED_RE` | Pattern deviz_cod cu prefix litere |

### V2 — Universal

V2 nu necesită configurare per-client pentru cazurile standard:
- `_normalize()` din `group_set_matcher.py` recunoaște automat pattern-uri comune
- Compound split pe (deviz_cod, obiectul_text) funcționează automat
- HierarchyCorrector este generic

**Excepție:** V2 moștenește checkpointul de page_classes de la V1 — dacă V1 nu are configurat clientul corect (SKIP_RE, header patterns), V2 primește date mai puțin curate.

---

## 8. Outputs

| Output | V1 | V2 |
|--------|----|----|
| Raport Word | `Raport_Oferta_N.docx` | `Raport_Oferta_N_v2.docx` |
| Holistic JSON | `holistic_oferta_N.json` | `holistic_oferta_N_v2.json` |
| Match trace | `matching_debug_oferta_N.json` | — |
| Articole extrase | `referinta.json`, `oferta_N.json` | `checkpoints/*_extracted.json` |

Formatul raportului Word este **identic** — ambele folosesc `shared/report_word.py`.

---

## 9. Performanță Comparată (Group Matching)

| Client | V1 | V2 | Delta |
|--------|----|----|-------|
| Drum Tatarani O1/O2 | 189/189 | 189/189 | ═ |
| Blocuri Racari O1 | 35/35 | 34/35 | -1 (ref_only genuine) |
| Blocuri Racari O2 | 35/35 | 35/35 | ═ |
| Blocuri Racari O3 | 35/35 | 34/35 | -1 (ref_only genuine) |
| Blocuri Racari O4 | **0/35** ❌ | 35/35 | **+35** (V2 mai bun) |
| BR BLOC A/A2/A3/A4 | 6/6 | 6/6 | ═ |
| BR BLOC B/C | 7/7 | 7/7 | ═ |
| Camin Maneciu O1/O2 | 35/35 | 35/35 | ═ |
| Scoala Dragomiresti O1/O2 | 22/22 | 22/22 | ═ |
| Scoala Sportiva Racari | ~9-10/41 | ~9-10/41 | ═ (structural) |

**Nota BR O4:** V1 a eșuat total (dedup bug + LLM). V2 corect 35/35 — avantaj real.
**Nota BR O1/O3:** V2 lasă BLC6 ORGANIZARE SANTIER ca ref_only (absent din ofertă). V1 îl potrivea greșit cu LLM. V2 este mai precis.

---

## 10. Trade-offs

### V1 — Avantaje
- OCR-aware la nivel de cod (I→1, O→0, learned patterns)
- LLM fallback rezolvă cazuri ambigue de group matching
- Knowledge cache acumulat (investiție recuperată)
- Matur, testat pe toți clienții

### V1 — Dezavantaje
- Non-determinist (LLM la runtime)
- Necesită `ANTHROPIC_API_KEY` active pentru clienți noi
- Tuning per-client manual (SKIP_RE, etc.)
- V1 O4 BR: bug dedup cauza eșec complet

### V2 — Avantaje
- 100% determinist și reproductibil
- 0 API calls la runtime (dacă checkpoint V1 există)
- Compound split automat (BR: 7 coduri → 35 grupuri)
- HierarchyCorrector decuplat (testabil izolat)
- Nu necesită knowledge cache

### V2 — Dezavantaje
- Set-based article matching fără OCR fuzzy (poate rata coduri cu erori OCR)
- Group matching fără LLM: grup fără header text = nerezolvat
- Dependent de calitatea page_classes checkpoint (moștenită din V1)
- SSR structural mismatch nerezolvat (la fel ca V1)
