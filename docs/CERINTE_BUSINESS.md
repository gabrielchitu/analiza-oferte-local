# Cerințe de Business — Sistem Analiză Oferte Construcții

**Versiune:** 1.0 DRAFT — pentru certificare operator  
**Data:** 2026-06-01  
**Status:** ⬜ NECERTIFICAT — requires review and sign-off  

---

## 1. CONTEXT ȘI SCOP

Sistemul primește devize de lucrări de construcții în format PDF (procesate prin Azure Document Intelligence → JSON) și compară o **ofertă** față de o **referință** (caiet de sarcini/deviz bază).

**Scopul:** Identificarea diferențelor dintre ceea ce s-a cerut (referință) și ceea ce a ofertat un contractor (ofertă), la nivel de articole de deviz, organizate pe grupuri (devize).

---

## 2. CONCEPTE FUNDAMENTALE

### 2.1 Structura Documentului

Un deviz de construcții are o structură ierarhică cu 3 niveluri de identificare:

| Nivel | Câmp | Exemplu |
|-------|------|---------|
| Proiect | OBIECTIVUL | `0232 000000232 DRUMURI TATARANI` |
| Amplasament | OBIECTUL | `0008 Strada Bisericii` |
| Tip lucrare | CATEGORIA | `BI0006 Acostamente 10cm 60mp` |

Combinația OBIECTIVUL + OBIECTUL + CATEGORIA identifică **unic un grup de lucrări** (deviz).

### 2.2 Articolul de Deviz

Unitate atomică de lucrare. Conține:
- **COD** — cod normativ (ex: `CA01A`, `$6701362`, `AN1`)
- **DENUMIRE** — descriere lucrare
- **UM** — unitate de măsură (buc, mp, mc, m, kg, etc.)
- **CANTITATE** — cantitatea cerută/ofertată
- **TIP** — articol principal sau subcomponentă (is_component)

### 2.3 Deviz Key

Identificatorul unic al unui grup = MD5 hash(OBIECTIVUL | OBIECTUL | CATEGORIA).
Folosit pentru a asocia grupuri din referință cu grupuri din ofertă, indiferent de formatul de cod.

---

## 3. CERINȚE FUNCȚIONALE — PIPELINE V1 (PRODUCȚIE)

### CR-01: Extragere articole din PDF

**Descriere:** Sistemul extrage articolele de deviz din fișierele JSON produse de Azure Document Intelligence.

**Condiții de acceptare:**
- ✅ Fiecare pagină F3 este clasificată și asociată unui deviz (OBIECTIVUL/OBIECTUL/CATEGORIA)
- ✅ Articolele sunt extrase cu câmpurile: COD, DENUMIRE, UM, CANTITATE
- ✅ Subcomponentele sunt identificate (marker L:, prefix >>>)
- ✅ Gruparea se face pe deviz_key (hash unic per combinație obiectivul+obiectul+categoria)
- ✅ Cantitățile și UM sunt moștenite de la articolul parinte pentru subcomponente

**Limitare documentată:**
- OCR poate introduce erori în coduri (ex: `I` vs `1`, `O` vs `0`) — tratate prin normalizare

---

### CR-02: Matching Grupuri (Group Matching)

**Descriere:** Sistemul asociază grupurile din referință cu grupurile corespunzătoare din ofertă.

**Regula de bussiness principală:**
> Un grup din referință și un grup din ofertă reprezintă ACELEAȘI lucrări dacă OBIECTIVUL, OBIECTUL și CATEGORIA lor se referă la același lucru.

**Metoda de determinare:**
1. **Faza 1 — Same key:** deviz_key identic (hash exact) → match sigur
2. **Faza 1.5 — Prefix:** deviz_cod referință este prefix al categoriei ofertă (formate ISDP/eDevize)
3. **Faza 2 — Knowledge cache:** perechi cunoscute din rulări anterioare (group_match_knowledge.json)
4. **Faza 2 — LLM fallback:** Claude API cu text complet OBIECTIVUL|OBIECTUL|CATEGORIA când fazele 1-1.5 eșuează

**Condiții de acceptare:**
- ✅ `oferta_only_groups == 0` (INVARIANT HARD): orice grup din ofertă trebuie să fie asociat unui grup din referință sau să fie o lucrare nouă explicabilă
- ✅ `ref_only_groups ≤ 2` (INVARIANT SOFT): grupuri din referință absente din ofertă = lucrări lipsă; >2 → investigare obligatorie
- ✅ Un grup din ofertă NU poate fi asociat cu mai mult de un grup din referință (1:1 assignment)

---

### CR-03: Matching Articole (Article Matching)

**Descriere:** În interiorul unui grup matched, se asociază articolele din referință cu articolele corespunzătoare din ofertă.

**Regulă de business:**
> Articolele sunt comparate DOAR în interiorul grupului lor. Un articol din grupul A nu se poate potrivi cu un articol din grupul B.

**Metoda de determinare (în ordine de prioritate):**
1. **NR** — numărul de ordine (dacă NR identic în ambele)
2. **COD** — codul de catalog normalizat
3. **Hash** — hash(descriere + UM + cantitate) pentru articole fără cod

**Tipuri de neconformități generate:**
| Tip NC | Semnificație |
|--------|-------------|
| ARTICOL_LIPSA | Articol cerut în referință, absent din ofertă |
| ARTICOL_EXTRA | Articol prezent în ofertă, absent din referință |
| DIFERENTA_CANT | Cantitate diferită față de referință |
| DIFERENTA_CAMP | Alt câmp diferit (UM, tip articol, etc.) |
| COD_SIMILAR | Cod aparent diferit dar similar OCR (I↔1, O↔0) |

---

### CR-04: Raport Word

**Descriere:** Sistemul generează un document Word cu rezultatele comparației.

**Format:**
- Tabel 11 coloane, orientare landscape A4
- Col 0-1: Cod/Nr ordine referință
- Col 2-5: Ceea ce s-a cerut (referință): COD, DENUMIRE, UM, CANTITATE
- Col 6-9: Ceea ce a ofertat: COD, DENUMIRE, UM, CANTITATE
- Col 10: Observații (tip NC)
- Coduri culoare: ROȘU = LIPSA, GALBEN = EXTRA, ALBASTRU = DEVIZ_MISMATCH

**Structură raport:**
- Grupuri matched: tabel cu articolele comparate + rând TOTAL GRUP
- Grupuri ref_only: articolele din referință fără corespondent în ofertă
- Grupuri oferta_only: articolele din ofertă fără corespondent în referință

**Condiții de acceptare:**
- ✅ Fiecare grup are un rând TOTAL GRUP cu numărul de articole principale (stânga=ref, dreapta=ofertă)
- ✅ Articolele subcomponentă (is_component=True) NU sunt numărate în TOTAL GRUP
- ✅ Raportul se salvează ca `Raport_Oferta_N.docx` în `output_AO/<ClientName>/`

---

### CR-05: Invariant de Conservare

**Descriere:** Garantarea că nicio neconformitate nu este pierdută silențios.

**Invariant:**
> Dacă un grup are 0 neconformități (matched perfect), atunci numărul de articole principale din referință TREBUIE să fie egal cu numărul de articole principale din ofertă.

**Verificare automată:** `verify_agent.py` rulează 6 checks pe holistic_oferta_N.json:
- SILENT_VIOLATION: grup cu 0 NC dar count_ref ≠ count_off
- OFERTA_ONLY_GROUP: grup complet absent din referință
- REF_ONLY_GROUP: grup complet absent din ofertă
- HIGH_EXTRA: >10 ARTICOL_EXTRA într-un grup
- HIGH_LIPSA: >10 ARTICOL_LIPSA într-un grup
- COD_SIMILAR_CLUSTER: cod similar detectat fără match explicit

---

## 4. CERINȚE FUNCȚIONALE — PIPELINE V2 (DEVELOPMENT)

Pipeline V2 este o implementare alternativă, independentă de V1, cu aceleași cerințe de business dar cu implementare diferită.

### CR-V2-01: Extragere Tabelară

**Descriere:** V2 încearcă să extragă articolele din structurile tabelă ale Azure DI (mai precis decât regex).

**Condiții de acceptare:**
- ✅ Per pagina, se încearcă extragere din tabelă DI; dacă lipsă/incompletă, fallback regex
- ✅ Ierarchia articolelor este corectată (forward-fill parinte pentru orfani)
- ✅ Grupurile PAGE_N (pagini neclasificate cu articole goale) sunt filtrate din output

---

### CR-V2-02: Group Matching V2

**Descriere:** Matching grupuri prin similaritate text OBIECTIVUL/OBIECTUL/CATEGORIA (deterministic, fără LLM).

**Condiții de acceptare:**
- ✅ Normalizare text: strip prefixe cod numeric (`0001`) sau alfanumeric (`BI0006`, `AN1`, `LC001A`)
- ✅ NU strip cuvinte normale (`Acostamente`, `Terasamente`)
- ✅ Pondere scoring: 70% similaritate CATEGORIA + 30% similaritate OBIECTUL
- ✅ OBIECTUL ignorat în scoring dacă conține cod pur numeric (ex: cod EU `45230000`)
- ✅ Threshold: 0.55 SequenceMatcher (echivalent ~0.80 RapidFuzz partial_token)
- ✅ Fallback: exact deviz_cod match când text header indisponibil
- ✅ Greedy 1:1 assignment (sortare descrescătoare după sim, primul câștigă)

**Performanță actuală (Drum Tatarani):**
- O1: 185/189 grupuri matched (4 ref_only genuine: lucrări absente din ofertă)
- O2: 188/189 grupuri matched (1 ref_only genuine)

**Limitare documentată:**
- Compound deviz_cod: când >1 grup din deviz_mapping partajează același deviz_cod în page_classes (DT, BR, SSR) → V2 creează un singur grup în loc de multiple → ref_only suplimentare

---

### CR-V2-03: Article Matching V2

**Aceleași cerințe ca CR-03 (V1).**

Implementare: set-based (NR → COD → hash) în `shared/set_based_matcher.py`.

---

### CR-V2-04: Raport V2

**Descriere:** Generare raport Word identic ca format cu V1.

**Condiții de acceptare:**
- ✅ Fișier: `Raport_Oferta_N_v2.docx` (nu suprascrie V1)
- ✅ Format identic cu V1 (același report_word.py)
- ✅ V1 și V2 pot coexista în același folder output

---

## 5. CERINȚE NON-FUNCȚIONALE

### CN-01: Independență Pipelines
- V1 și V2 sunt **total independente**: rulează separat, produc fișiere cu nume diferite, nu se suprascriu

### CN-02: Caching
- Page classes (V1) și extrageri (V2) sunt cached în `checkpoints/`
- Re-rulare pe același document reutilizează cache (fără re-clasificare LLM)
- Cache invalidat automat dacă detectată structură stale

### CN-03: Multi-Client
- Sistemul detectează automat toți clienții din `input_AO/` (folder cu `di_referinta.json`)
- Fiecare client are folder separat în `output_AO/`
- Configurare client-specifică: OCR patterns, group match knowledge, F3 context

### CN-04: Testare
- Baseline: 588 teste pass (22 failed pre-existente, neschimbate)
- Orice modificare care scade numărul de teste passing = BLOCKER

---

## 6. CLIENȚI VERIFICAȚI

| Client | V1 Status | V2 Status | Note |
|--------|-----------|-----------|------|
| Blocuri Racari (consolidat) | ✅ 0 violări | N/A | 4 oferte |
| BR BLOC A/A2/A3/A4/B/C | ✅ 0 violări | N/A | 6 blocuri × 4 oferte |
| Scoala Dragomiresti | ✅ 0 violări | N/A | |
| Camin Maneciu | ✅ 0 CRITICAL/HIGH | N/A | 18 MEDIUM genuine |
| Drum Tatarani | ✅ 189/189 | ✅ 185-188/189 | Compound deviz_cod limitare |
| Scoala Sportiva Racari | ⚠️ structural mismatch | N/A | nerezolvat |

---

## 7. CERTIFICARE OPERATOR

Prin semnarea acestui document, operatorul confirmă că:

1. **Logica de matching grupuri** (CR-02) reflectă corect cerința de business pentru identificarea lucrărilor identice din referință și ofertă.

2. **Invariantul de conservare** (CR-05) este acceptat: un grup cu 0 NC implică count_ref == count_off articole principale.

3. **Pragurile de acceptabilitate** pentru verificare automată sunt corecte:
   - `oferta_only == 0` = hard invariant
   - `ref_only ≤ 2` = soft threshold; mai mult necesită investigare

4. **Limitarea V2** (compound deviz_cod) este documentată și acceptată pentru versiunea curentă.

5. **Formatul raportului Word** (CR-04) corespunde nevoilor de prezentare către beneficiar.

---

**Operator:** ___________________________

**Data:** ___________________________

**Observații/Modificări cerute:**

```
[ ] Logica de matching grupuri — modificare: ________________________________
[ ] Tipuri neconformități — adaugare/modificare: ____________________________
[ ] Format raport Word — modificare: _______________________________________
[ ] Praguri verificare — modificare: ________________________________________
[ ] Altele: ________________________________________________________________
```

---

*Document generat automat din conversație Claude Code — 2026-06-01*
