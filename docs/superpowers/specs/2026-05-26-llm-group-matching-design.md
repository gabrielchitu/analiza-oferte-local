# Design: LLM Group Matching + Diagnostic Trace

**Data:** 2026-05-26  
**Scope:** Matching LLM-asistat pentru grupuri deviz nematched + JSON diagnostic trace  
**Abordare:** B — LLM integrat în `compare_by_groups` cu knowledge-first caching  

---

## Context

Pipeline-ul holistic matchuiește grupuri deviz pe baza `deviz_key` (MD5 al `obiectivul + obiectul + categoria`). Când textul e ușor diferit între ref și ofertă (abrevieri, prefixe numerice, variante), hash-urile diferă → grupuri rămân nematched → generate ca `ref_only` (LIPSA) sau `oferta_only` (EXTRA) incorect.

**Exemplu CM O1:** 0 ref_only, 16 oferta_only — toate 16 grupuri au aceeași obiectivul, dar categoria diferă textual față de ref (e.g., ref: `"17 Echipam apa calda"` vs oferta: `"17 Echipam apa calda tip I"`).

**Soluție:** după matching 3-layer, dacă rămân grupuri nematched pe ambele laturi, apelăm LLM pentru reconciliere semantică. Matchurile confirmate se persistă în `group_match_knowledge.json` per-client pentru rulări viitoare.

---

## Secțiunea 1 — Diagnostic JSON (`matching_debug_oferta_N.json`)

### Fișier produs
`output_AO/<Client>/matching_debug_oferta_N.json` — scris de `local_run.py` după fiecare rulare.

### Format
```json
{
  "ref_groups": [
    {"deviz_key": "06185a3a...", "den": "01 CRESTERE... | 4.1 Cladire camin | 05 Instalatii camin apometru", "n_articles": 12}
  ],
  "oferta_groups": [
    {"deviz_key": "00a57055...", "den": "01 CRESTERE... | 4.1 Cladire camin | 17 Echipam apa calda tip I", "n_articles": 3}
  ],
  "matched": [
    {"ref_key": "06185a3a", "oferta_key": "06185a3a", "match_type": "same_code",    "ref_den": "...", "oferta_den": "..."},
    {"ref_key": "e2a32864", "oferta_key": "45b5c768", "match_type": "cross_3layer", "ref_den": "...", "oferta_den": "..."},
    {"ref_key": "...",      "oferta_key": "...",      "match_type": "knowledge",    "ref_den": "...", "oferta_den": "..."},
    {"ref_key": "...",      "oferta_key": "...",      "match_type": "llm",          "ref_den": "...", "oferta_den": "..."}
  ],
  "ref_only": [{"deviz_key": "...", "den": "...", "n_articles": 5}],
  "oferta_only": [{"deviz_key": "...", "den": "...", "n_articles": 3}]
}
```

### Unde se construiește
`HolisticComparison` primește câmp nou `match_trace: dict = field(default_factory=dict)`.  
`compare_by_groups` populează `result.match_trace` cu datele de mai sus înainte de return.  
`local_run.py` scrie fișierul după ce primește `HolisticComparison`.

---

## Secțiunea 2 — LLM Group Matching în `group_comparator.py`

### Poziție în flux
```
ref_by_deviz, oferta_by_deviz ← _articles_by_deviz()
↓
group_mapping ← match_devize_by_3layer()        ← existent
full_mapping ← same-code + cross-3layer         ← existent
↓                                                (NOU din acest punct)
remaining_ref   = ref_cods - matched_ref_cods
remaining_oferta = oferta_cods - matched_oferta_cods
↓
knowledge_matches ← _apply_knowledge(remaining_ref, remaining_oferta, client_name)
↓
llm_matches ← _llm_match_groups(remaining_ref, remaining_oferta, llm_client)
            (doar dacă knowledge nu acoperă tot și llm_client is not None)
↓
_save_knowledge(client_name, llm_matches)
↓
Adaugă knowledge_matches + llm_matches în full_mapping
```

### Funcție nouă: `_llm_match_groups`

```python
def _llm_match_groups(
    ref_remaining: dict[str, list],      # deviz_key → articles
    oferta_remaining: dict[str, list],   # deviz_key → articles
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client,
    llm_model: str,
) -> list[tuple[str, str]]:             # [(ref_key, oferta_key), ...]
```

**Prompt trimis LLM:**
```
Ești expert în devize de construcții românești.
Mai jos sunt grupuri din REFERINȚĂ și OFERTĂ care nu s-au potrivit automat.
Textele pot fi abreviate diferit pentru aceeași categorie.

Returnează EXCLUSIV JSON valid, fără text suplimentar:
[{"ref": "<ref_den_exact>", "oferta": "<oferta_den_exact>"}]

Omite perechile nesigure. Dacă nu există nicio potrivire clară, returnează [].

REFERINȚĂ (grupuri nematched):
1. "01 CRESTERE... | 4.1 Cladire camin | 17 Echipam apa calda"
2. ...

OFERTĂ (grupuri nematched):
1. "01 CRESTERE... | 4.1 Cladire camin | 17 Echipam apa calda tip I"
2. ...
```

**Validare răspuns LLM:**
- JSON parseable (try/except → log warning, return [])
- `ref` trebuie să existe exact în lista ref_remaining (den match)
- `oferta` trebuie să existe exact în lista oferta_remaining
- Perechi invalide se ignoră (log warning per pereche)

### Funcție nouă: `_apply_knowledge`

```python
def _apply_knowledge(
    remaining_ref: dict[str, list],
    remaining_oferta: dict[str, list],
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    client_name: str,
) -> list[tuple[str, str]]:   # [(ref_key, oferta_key)]
```

- Citește `shared/group_match_knowledge.json`
- Filtrează intrările pentru `client_name`
- Lookup: pentru fiecare `{"ref_den": "...", "oferta_den": "..."}` din knowledge:
  - Caută ref group cu `_den_string(ref_hdr) == ref_den`
  - Caută oferta group cu `_den_string(oferta_hdr) == oferta_den`
  - Dacă ambele găsite în remaining → adaugă pereche

### Funcție nouă: `_save_knowledge`

```python
def _save_knowledge(client_name: str, new_pairs: list[dict]) -> None:
    # new_pairs = [{"ref_den": str, "oferta_den": str}]
```

- Load knowledge (sau `{}` dacă nu există)
- Append perechi noi la `knowledge[client_name]`
- Dedup pe `(ref_den, oferta_den)`
- Write back

### Signatura actualizată `compare_by_groups`

```python
def compare_by_groups(
    ref_articles: list,
    oferta_articles: list,
    ref_deviz_headers: dict,
    oferta_deviz_headers: dict,
    llm_client=None,
    llm_model: str = "",
    client_name: str = "",          # NOU — pentru knowledge lookup
) -> HolisticComparison:
```

---

## Secțiunea 3 — Knowledge File

### Locație
`shared/group_match_knowledge.json` — fișier nou, committed în repo, creat gol la prima rulare.

### Format
```json
{
  "Camin Maneciu": [
    {
      "ref_den": "01 \" CRESTERE EFICIENTEI... | 4.1 Cladire camin | 17 Echipam apa calda",
      "oferta_den": "01 \" CRESTERE EFICIENTEI... | 4.1 Cladire camin | 17 Echipam apa calda tip I"
    }
  ],
  "Blocuri Racari": []
}
```

### Den string canonical
`_den_string(hdr)` = `" | ".join([hdr.obiectivul, hdr.obiectul, hdr.categoria])` — exact cum apare în `deviz_denumire` din raport.

---

## Implementare note

### `_den_string` — funcție helper la nivel de modul
`_header_to_string` deja există local în `compare_by_groups` (linii ~247-251). Se extrage la nivel de modul ca `_den_string(hdr) -> str` și se refolosește în toate funcțiile noi (`_llm_match_groups`, `_apply_knowledge`, `_save_knowledge`).

### Reverse map în `_llm_match_groups` și `_apply_knowledge`
Validarea răspunsului LLM și lookup-ul din knowledge necesită `den_string → deviz_key`. Se construiește:
```python
ref_den_to_key = {_den_string(ref_deviz_headers.get(k)): k for k in remaining_ref if ref_deviz_headers.get(k)}
oferta_den_to_key = {_den_string(oferta_deviz_headers.get(k)): k for k in remaining_oferta if oferta_deviz_headers.get(k)}
```
Aceste două maps se folosesc atât în `_apply_knowledge` cât și în `_llm_match_groups`.

---

## Fișiere modificate

| Fișier | Tip modificare |
|---|---|
| `shared/group_comparator.py` | `match_trace` în `HolisticComparison`; extrage `_den_string`; `_llm_match_groups`, `_apply_knowledge`, `_save_knowledge`; actualizare `compare_by_groups` |
| `local_run.py` | Transmite `client_name` la `compare_by_groups`; scrie `matching_debug_oferta_N.json` |
| `shared/group_match_knowledge.json` | Creat nou (gol `{}`) |

## Fișiere neatinse
- `shared/deviz_matcher.py` — 3-layer matching existent, nemodificat
- `shared/report_builder.py` — `build_raport_holistic` nu primește match_trace
- `shared/report_word.py` — DOCX nemodificat

---

## Testing

1. Rulare CM O1: `python3 multi_client_run.py --client "Camin Maneciu"` → fișier `matching_debug_oferta_1.json` creat
2. Log arată `[GC] LLM matched N grupuri suplimentare`
3. `group_match_knowledge.json` conține intrări pentru "Camin Maneciu"
4. A doua rulare: `[GC] Knowledge: N perechi aplicate` (fără apel LLM)
5. CM O1 matched_groups crește de la 19 → 19 + N_llm (N_llm = grupuri reconciliate)
