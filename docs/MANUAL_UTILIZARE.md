# Manual de Utilizare — Pipeline Analiza Oferte
**Versiune:** v3.3 | **Actualizat:** 2026-06-16

Ghid complet pentru utilizatorul final: ce produce fiecare pipeline, cum se rulează, ce fișiere generează.

---

## Cuprins

1. [Privire de ansamblu](#1-privire-de-ansamblu)
2. [Configurare (.env)](#2-configurare-env)
3. [Clienți disponibili](#3-clienți-disponibili)
4. [Pipeline 1 — Analiză oferte (principal)](#4-pipeline-1--analiză-oferte-principal)
5. [Pipeline 2 — Liste de articole](#5-pipeline-2--liste-de-articole)
6. [Pipeline 3 — Comparație completă](#6-pipeline-3--comparație-completă)
7. [Pipeline 4 — Sursă de încărcare](#7-pipeline-4--sursă-de-încărcare)
8. [Verificare structurală (verify_agent)](#8-verificare-structurală-verify_agent)
9. [Verificare completitudine extracție (verify_gaps)](#9-verificare-completitudine-extracție-verify_gaps)
10. [Skilluri Claude Code](#10-skilluri-claude-code)
11. [Fișiere generate — referință rapidă](#11-fișiere-generate--referință-rapidă)
12. [Troubleshooting rapid](#12-troubleshooting-rapid)

---

## 1. Privire de ansamblu

```
di_referinta.json  ─┐
di_oferta_1.json   ─┤──▶ [Pipeline 1] ──▶ Raport_Oferta_N.docx
di_oferta_2.json   ─┘                      holistic_oferta_N.json
                                            referinta.json

holistic_oferta_N.json ──▶ [Pipeline 2] ──▶ Lista_Oferta_N.docx
                                             Lista_Referinta.docx

holistic_oferta_N.json ──▶ [Pipeline 3] ──▶ Comparatie_Lista_Oferta_N.docx

di_referinta.json ─────▶ [Pipeline 4] ──▶ Lista-proiect-{ACRONIM}.docx/xlsx/pdf
```

**Fișierele de intrare** (`di_*.json`) sunt extrase din PDF prin instrument extern și depuse în `input_AO/<Client>/`.

**Toate fișierele de ieșire** se salvează în `output_AO/<Client>/`.

---

## 2. Configurare (.env)

Un singur fișier `.env` la rădăcina proiectului controlează toate pipeline-urile:

```
# Obligatoriu
ANTHROPIC_API_KEY=sk-ant-...

# Opțional — LLM local via LiteLLM proxy (fără modificări cod)
ANTHROPIC_BASE_URL=http://localhost:4000
ANTHROPIC_MODEL=ollama/llama3          # default: claude-sonnet-4-6
```

**Mod Anthropic direct (implicit):** lasă `ANTHROPIC_BASE_URL` și `ANTHROPIC_MODEL` nesetate.

**Mod LLM local:** setează `ANTHROPIC_BASE_URL` și `ANTHROPIC_MODEL` conform proxy-ului tău LiteLLM. `ANTHROPIC_API_KEY` poate fi `dummy` dacă proxy-ul nu o cere.

La pornire, fiecare pipeline afișează:
```
LLM: claude-sonnet-4-6 @ Anthropic direct
# sau
LLM: ollama/llama3 @ http://localhost:4000
```

Toate entry point-urile (`local_run.py`, `gen_sursa_incarcare.py`, `shared/v2_orchestrator.py`) apelează `load_dotenv()` automat — `.env` e citit indiferent de cum pornești pipeline-ul.

---

## 3. Clienți disponibili

| Client | Director input | Oferte |
|--------|----------------|--------|
| DT2 | `input_AO/DT2/` | di_oferta_1.json, di_oferta_2.json |
| EuroProject | `input_AO/EuroProject/` | di_referinta.json (sursa incarcare) |

> **Detectare automată:** Orice folder din `input_AO/` care conține `di_referinta.json` este recunoscut automat. Nu e nevoie de configurare suplimentară.

---

## 4. Pipeline 1 — Analiză oferte (principal)

**Ce face:** Extrage articolele din PDF-urile de referință și ofertă, le compară grup cu grup, și generează raportul de neconformități (NC).

**Script:** `multi_client_run.py`

### Rulare

```bash
# Meniu interactiv (alegi clientul)
python3 multi_client_run.py

# Direct, fără meniu
python3 multi_client_run.py --client "DT2"
```

### Ce generează

| Fișier | Conținut |
|--------|---------|
| `output_AO/<Client>/referinta.json` | Articolele extrase din DI referință (structurat: grupuri → articole) |
| `output_AO/<Client>/oferta_N.json` | Articolele extrase din DI ofertă N |
| `output_AO/<Client>/holistic_oferta_N.json` | Comparație completă: grupuri matched + ref-only + ofertă-only + NC per articol |
| `output_AO/<Client>/Raport_Oferta_N.docx` | Raport Word cu NC-urile (LIPSA/EXTRA/COD_SIMILAR/SPECIFICATIE_DIFERITA) |
| `output_AO/<Client>/matching_debug_oferta_N.json` | Debug matching grupuri (util dacă apar grupuri nematchate) |

### Raportul de NC (`Raport_Oferta_N.docx`)

Raportul este structurat pe grupuri (devize). Pentru fiecare grup apare:
- **Antet:** Obiectivul / Obiectul / Categoria de lucrări
- **Tabel articole:** Cod | Denumire | UM | Cant. Referință | Cant. Ofertă | Tip NC
- **Rând TOTAL GRUP:** număr articole main per categorie (matched/lipsa/extra)

Tipuri NC:
| Tip | Semnificație |
|-----|-------------|
| `ARTICOL_LIPSA` | Articol din referință absent din ofertă |
| `ARTICOL_EXTRA` | Articol din ofertă absent din referință |
| `COD_SIMILAR` | Cod diferit dar similar (OCR: I↔1, O↔0) |
| `DIFERENTA_CANT` | Cantitate diferită |
| `DIFERENTA_CAMP(um)` | Unitate de măsură diferită |
| `COD_NORMATIV_DIFERIT` | Articole la același număr de ordine cu coduri diferite |
| `SPECIFICATIE_DIFERITA` | Articole matched dar cu specificații diferite în denumire |

### Checkpoints (cache LLM)

Clasificarea paginilor (costisitoare — Claude API) se salvează automat:
```
output_AO/<Client>/checkpoints/di_referinta_page_classes_*.json
output_AO/<Client>/checkpoints/di_oferta_N_page_classes_*.json
```

La re-rulare, checkpoint-ul este reutilizat — nu se mai fac apeluri LLM.

---

## 5. Pipeline 2 — Liste de articole

**Ce face:** Generează liste de articole în format tabel (15 coloane) din fișierele holistic existente. Util pentru revizuire rapidă sau trimitere către beneficiar.

**Script:** `gen_lista_oferta.py`

**Cerință prealabilă:** Pipeline 1 rulat (are nevoie de `holistic_oferta_N.json` și `referinta.json`).

### Rulare

```bash
# Referință + toate ofertele
python3 gen_lista_oferta.py --client "DT2"

# Doar referința
python3 gen_lista_oferta.py --client "DT2" --referinta

# Doar oferta N
python3 gen_lista_oferta.py --client "DT2" --oferta 1
```

### Ce generează

| Fișier | Conținut |
|--------|---------|
| `output_AO/<Client>/Lista_Referinta.docx` | Toate articolele din referință (cu prețuri, grupate pe devize) |
| `output_AO/<Client>/Lista_Oferta_N.docx` | Toate articolele din oferta N (cu prețuri, grupate pe devize) |

**Format tabel:** Nr. ordine | Cod | Denumire | UM | Cantitate | Preț unitar | Total | … (15 coloane)

Prețurile sunt formatate în localizare română (`1.234,56 lei`).

---

## 6. Pipeline 3 — Comparație completă

**Ce face:** Generează un document side-by-side cu toate articolele din referință și ofertă, coloană cu coloană, pentru fiecare grup. Util pentru auditori sau comisii de evaluare.

**Script:** `gen_comparatie_lista.py`

**Cerință prealabilă:** Pipeline 1 rulat.

### Rulare

```bash
# Toate ofertele
python3 gen_comparatie_lista.py --client "DT2"

# Doar oferta N
python3 gen_comparatie_lista.py --client "DT2" --oferta 1
```

### Ce generează

| Fișier | Conținut |
|--------|---------|
| `output_AO/<Client>/Comparatie_Lista_Oferta_N.docx` | Tabel comparativ: referință vs. ofertă, articol cu articol |

**Format:** Două coloane paralele (Referință | Ofertă) cu toate articolele, evidențiate NC-urile.

---

## 7. Pipeline 4 — Sursă de încărcare

**Ce face:** Pipeline **independent** față de celelalte. Extrage prețurile din documentul de referință eDevize (format F3 cu breakdown material/manopera/utilaj/transport) și generează Lista-proiect în format DOCX, XLSX și PDF.

**Script:** `gen_sursa_incarcare.py`

**Format suportat:** Devize în format eDevize (câmpuri: nr_crt | cod | denumire | UM | cantitate | preț unitar | total | breakdown M+Mo+U+Tr).

### Rulare

```bash
# Interactiv (alegi clientul și fișierul JSON)
python3 gen_sursa_incarcare.py

# Direct
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta

# Fără PDF (dacă LibreOffice/reportlab nu e disponibil)
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --no-pdf

# Forțează re-extracție (ignoră cache)
python3 gen_sursa_incarcare.py --client "EuroProject" --json di_referinta --force
```

### Ce generează

| Fișier | Conținut |
|--------|---------|
| `output_AO/<Client>/Lista-proiect-{ACRONIM}-{stem}.docx` | Lista-proiect formatat (devize, capitole, articole, breakdown) |
| `output_AO/<Client>/Lista-proiect-{ACRONIM}-{stem}.xlsx` | Același conținut în Excel |
| `output_AO/<Client>/Lista-proiect-{ACRONIM}-{stem}.pdf` | PDF searchable (via reportlab nativ sau LibreOffice) |
| `output_AO/<Client>/sursa_extracted_{stem}.json` | Date extrase brut (checkpoint) |
| `output_AO/<Client>/sursa_verified_{stem}.json` | Rezultatul verificării (status: OK/WARN/RED) |

**`{ACRONIM}`** = acronim auto-generat din denumirea obiectivului (ex: `EP` din `EuroProject`).

### Statusuri verificare

| Status | Semnificație |
|--------|-------------|
| `OK` | Toate totalurile corecte, niciun gap nr_crt |
| `WARN` | Totale ok, dar ≥1 articol cu breakdown suspect (sum material+man+utl+tra ≠ preț unitar) |
| `RED` | Gap nr_crt sau total deviz incorect după 5 iterații |

---

## 8. Verificare structurală (`verify_agent`)

**Ce face:** Rulează 6 verificări structurale pe `holistic_oferta_N.json` și generează un raport de severitate.

**Script:** `verify_agent.py`

**Cerință prealabilă:** Pipeline 1 rulat.

### Rulare

```bash
# Verificare fără re-rulare pipeline
python3 verify_agent.py --client "DT2" --verify-only

# Verificare + re-rulare automată dacă găsește probleme (max 3 iterații)
python3 verify_agent.py --client "DT2"

# Controlul numărului de iterații
python3 verify_agent.py --client "DT2" --max-iter 5
```

### Ce verifică

| Check | Nivel | Semnificație |
|-------|-------|-------------|
| `SILENT_VIOLATION` | CRITICAL | `ref_main_count ≠ off_main_count` într-un grup matched (bug comparator) |
| `OFERTA_ONLY_GROUP` | HIGH | Grup din ofertă fără corespondent în referință |
| `REF_ONLY_GROUP` | HIGH | Grup din referință fără corespondent în ofertă |
| `EMPTY_MATCHED_GROUP` | HIGH | Grup matched dar fără articole |
| `HIGH_EXTRA` | MEDIUM | >30% articole EXTRA în grup (posibil bug extracție referință) |
| `HIGH_LIPSA` | MEDIUM | >30% articole LIPSA în grup (posibil bug extracție ofertă) |
| `COD_SIMILAR_CLUSTER` | LOW | ≥3 COD_SIMILAR în același grup (posibil pattern OCR sistematic) |

### Ce generează

```
output_AO/<Client>/verify_report_{timestamp}.md
```

Raportul listează fiecare finding cu detalii (grup, cod articol, counts).

---

## 9. Verificare completitudine extracție (`verify_gaps`)

**Ce face:** Verifică per-deviz că extracția articolelor din DI raw este completă — atât gap-uri interne în secvența de nr_crt, cât și articole la final de deviz care există în raw dar nu au fost extrase.

**Script:** `verify_gaps.py`

**Cerință prealabilă:** Pipeline 1 rulat (are nevoie de checkpoints page_classes pentru scope exact).

### Rulare

```bash
# Referință + toate ofertele
python3 verify_gaps.py --client "DT2"

# Doar referința
python3 verify_gaps.py --client "DT2" --referinta

# Doar oferta N
python3 verify_gaps.py --client "DT2" --oferta 1

# Lookahead mai mare pentru documente dense
python3 verify_gaps.py --client "DT2" --tail-lookahead 20
```

### Tipuri de findings

| Finding | Semnificație | Acțiune |
|---------|-------------|---------|
| `BUG EXTRACTOR` | Nr_crt găsit în raw DI dar absent din extras | Fix obligatoriu în parser |
| `DEVIZ GREȘIT` | Nr_crt găsit în alt deviz (cross-deviz) | Skip — nu e bug parser |
| `SALT NUMEROTARE` | Nr_crt absent din raw DI | Skip — PDF-ul are salt intenționat |
| `MISSING_TAIL` | Articole după ultimul extras există în raw | Fix obligatoriu în parser |

### Exemplu output

```
[DT2] di_referinta — VS0002 Prefabricate:
  Gaps interne: [53] → BUG EXTRACTOR (gasit pag 106, linia 43)
  ⚠ MISSING_TAIL: articolele [53] există în raw DI
    Tail nr=53 — pagina 106, linia 43: '53'
      [42]    'S8877'
      [43]>>> '53'
      [44]    '01003D'
      [45]    '02 MP'
```

---

## 10. Skilluri Claude Code

Skillurile se invocă direct în conversația cu Claude Code ca comenzi `/skill`. Ele orchestrează autonom mai mulți pași, inclusiv fixuri și re-rulări.

| Skill | Invocare | Ce face |
|-------|---------|---------|
| `/extraction-completeness DT2` | `extraction-completeness` | Verifică completitudinea extracției per-deviz. Rulează `verify_gaps`, clasifică fiecare finding, propune și aplică fix-uri în parser, re-rulează pipeline, commit per fix. |
| `/pipeline-qa DT2` | `pipeline-qa` | Orchestrare completă QA: pipeline V1 → autoverify structural → gaps → EXTRA → LIPSA → rapoarte finale. Loop convergență max 3 iterații. |

### Skill `/extraction-completeness`

**Când se folosește:** Când suspectezi că parser-ul a pierdut articole (după fix în parser, sau client nou).

**Ce face autonom:**
1. Rulează `verify_gaps.py --client "<client>"`
2. Clasifică fiecare finding (BUG EXTRACTOR / DEVIZ GREȘIT / SALT NUMEROTARE)
3. Pentru BUG EXTRACTOR → identifică root cause, aplică fix minimal în `f3_regex_parser.py`, testează izolat, commit
4. Re-rulează pipeline după fix-uri
5. Re-verifică (loop convergență)
6. Raport final cu toate fix-urile aplicate

**Raport final:**
```
=== EXTRACTION COMPLETENESS — DT2 ===
REFERINTA:
  Gap-uri interne: 42 grupuri (0 bug extractor, 40 deviz greșit, 2 salt)
  MISSING_TAIL: 6 grupuri → 2 fixate
OFERTA 1:
  Gap-uri: 0 bug extractor
  MISSING_TAIL: 0
Total fix-uri: 2
Commit-uri: b4a184a 880e97e
```

### Skill `/pipeline-qa`

**Când se folosește:** Verificare completă după adăugare client nou sau după modificări majore în parser/comparator.

**Ce face autonom (max 3 iterații):**
1. Pipeline V1 complet
2. Pipeline V2 (rapoarte comparație)
3. `verify_agent --verify-only` → CRITICAL/HIGH → STOP dacă SILENT_VIOLATION
4. `verify_gaps` → fix-uri BUG EXTRACTOR
5. Verificare ARTICOL_EXTRA (caută în di_referinta → fix parser dacă găsit)
6. Verificare ARTICOL_LIPSA (caută în di_oferta → fix parser dacă găsit)
7. Teste de regresie
8. Generare rapoarte finale (comparatie_lista, lista_oferta)

---

## 11. Fișiere generate — referință rapidă

### Per pipeline

| Pipeline | Script | Fișiere generate |
|----------|--------|-----------------|
| 1. Analiză oferte | `multi_client_run.py` | `referinta.json`, `oferta_N.json`, `holistic_oferta_N.json`, `Raport_Oferta_N.docx`, `matching_debug_oferta_N.json` |
| 2. Liste articole | `gen_lista_oferta.py` | `Lista_Referinta.docx`, `Lista_Oferta_N.docx` |
| 3. Comparație | `gen_comparatie_lista.py` | `Comparatie_Lista_Oferta_N.docx` |
| 4. Sursă încărcare | `gen_sursa_incarcare.py` | `Lista-proiect-{ACRONIM}-{stem}.docx/xlsx/pdf`, `sursa_extracted_{stem}.json`, `sursa_verified_{stem}.json` |
| Verificare | `verify_agent.py` | `verify_report_{timestamp}.md` |

### Toate fișierele posibile per client

```
output_AO/<Client>/
├── referinta.json                          ← extrase referință
├── oferta_1.json                           ← extrase ofertă 1
├── oferta_2.json
├── holistic_oferta_1.json                  ← comparație completă ofertă 1
├── holistic_oferta_2.json
├── matching_debug_oferta_1.json            ← debug grup matching
├── Raport_Oferta_1.docx                    ← raport NC ofertă 1
├── Raport_Oferta_2.docx
├── Lista_Referinta.docx                    ← lista articole referință
├── Lista_Oferta_1.docx                     ← lista articole ofertă 1
├── Lista_Oferta_2.docx
├── Comparatie_Lista_Oferta_1.docx          ← comparație completă side-by-side
├── Comparatie_Lista_Oferta_2.docx
├── Lista-proiect-{ACR}-di_referinta.docx  ← sursă încărcare
├── Lista-proiect-{ACR}-di_referinta.xlsx
├── Lista-proiect-{ACR}-di_referinta.pdf
├── sursa_extracted_di_referinta.json
├── sursa_verified_di_referinta.json
├── verify_report_{timestamp}.md            ← raport verificare structurală
└── checkpoints/
    ├── di_referinta_page_classes_*.json    ← cache LLM clasificare pagini
    ├── di_oferta_1_page_classes_*.json
    └── di_oferta_1_deviz_mapping_*.json
```

---

## 12. Troubleshooting rapid

### Grupuri nematchate (ref_only / oferta_only)

1. Deschide `matching_debug_oferta_N.json`
2. Caută grupul cu `"status": "unmatched"`
3. Verifică `group_match_knowledge.json` — poate lipsi o mapare manuală

Fix: adaugă în `shared/group_match_knowledge.json`:
```json
{
  "Denumire grup LLM": "COD_DEVIZ_DIN_REFERINTA"
}
```

### Articole LIPSA sau EXTRA neașteptate

1. Rulează `python3 verify_agent.py --client "<client>" --verify-only`
2. Dacă `HIGH_EXTRA` sau `HIGH_LIPSA` → rulează `python3 verify_gaps.py --client "<client>"`
3. Sau invocă `/pipeline-qa <client>` — face totul automat

### Extracție zero articole (0 devize)

Cauze tipice:
- Checkpoints page_classes corupte → șterge `output_AO/<client>/checkpoints/` și re-rulează
- Format header deviz nerecunoscut → adaugă pattern în `shared/deviz_header_extractor.py`

### Re-rulare fără LLM (cache)

Dacă checkpoints există, pipeline-ul nu face apeluri API. Dacă vrei să forțezi re-clasificare:
```bash
rm output_AO/<client>/checkpoints/di_*.json
python3 multi_client_run.py --client "<client>"
```

### Adăugare client nou

Pașii minimali:
1. Creează `input_AO/<NumeClient>/` cu `di_referinta.json` și `di_oferta_N.json`
2. Rulează `python3 multi_client_run.py --client "<NumeClient>"`
3. Dacă extracția e slabă → verifică cu `/extraction-completeness <NumeClient>`
4. Dacă grupuri nematchate → adaugă în `group_match_knowledge.json`

Detalii complete: secțiunea "Adding a Client" din `CLAUDE.md`.
