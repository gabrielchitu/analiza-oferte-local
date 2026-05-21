# Raport Diagnostic Automat — Design Spec

**Data:** 2026-05-21  
**Branch:** main  
**Prerequisit:** Pipeline multi-client funcțional (v8.0), output-uri JSON existente în `output_AO/<client>/`

---

## Obiectiv

Script standalone `run_diagnostics.py` care citește output-urile JSON existente ale pipeline-ului pentru toți clienții și generează un raport de diagnostic structurat în două formate:
- `output_AO/diagnostics.json` — date structurate pentru procesare ulterioară
- `output_AO/diagnostics.docx` — raport detaliat lizibil

Scopul principal: identificarea semnalelor de alarmă care indică bug-uri de extragere în referință sau probleme sistematice de matching, înainte ca rapoartele de neconformitate să fie livrate clientului.

---

## Input / Output

**Input (citit, nu modificat):**
- `output_AO/<client>/referinta.json` — articolele extrase din documentul de referință
- `output_AO/<client>/comparatie_oferta_N.json` — rezultatele comparației per ofertă (N=1,2,...)

**Output (generat):**
- `output_AO/diagnostics.json` — toate datele de diagnostic în format JSON
- `output_AO/diagnostics.docx` — raport detaliat formatat

**Nu re-rulează pipeline-ul.** Dacă output-urile lipsesc, scriptul raportează client-ul ca lipsă și continuă.

---

## Arhitectură

```
run_diagnostics.py
├── discover_clients()                     → lista clienți cu output-uri disponibile
├── load_client_data(client_name)          → (referinta_dict, [comparatie_dict, ...])
├── analyze_ref_quality(ref_articole)      → Phase0Result
├── analyze_extra(comp, ref_articole)      → Phase1Result
├── analyze_lipsa(comp)                    → Phase2Result
├── build_client_report(client_name, ...)  → ClientReport
├── build_diagnostics_json(all_reports)    → scrie diagnostics.json
└── build_diagnostics_docx(all_reports)   → scrie diagnostics.docx
```

**Fișiere noi:**
- `run_diagnostics.py` — entry point + orchestrare
- `shared/diagnostics_builder.py` — logică analiză (Phase 0/1/2) + build JSON
- `shared/diagnostics_word.py` — generare DOCX diagnostic

**Fișiere existente folosite (read-only):**
- `shared/client_config.py` — `ClientConfig.detect_clients()`, path resolution
- `shared/report_word.py` — stiluri Word reutilizabile (opțional)

---

## Descoperire clienți

```python
def discover_clients() -> list[str]:
    """Returnează clienții care au output_AO/<client>/referinta.json."""
    base = Path("output_AO")
    return [
        d.name for d in base.iterdir()
        if d.is_dir() and (d / "referinta.json").exists()
    ]
```

Clienți așteptați (baseline): `Blocuri Racari`, `Camin Maneciu`, `Scoala Dragomiresti`, `Scoala Sportiva Racari`.

---

## Phase 0 — Calitate Referință

**Sursă:** `referinta.json["articole"]`

**Semnale detectate:**

| Semnal | Condiție | Severitate |
|--------|----------|-----------|
| Deviz negăsit | `deviz = ""` sau `None` | 🔴 Critică |
| Articol incomplet | `cantitate = 0` ȘI `um = ""` | 🟡 Avertisment |
| Componentă orfană | `is_component=True` ȘI `display_parent_cod=None` | 🟡 Avertisment |

**Output Phase0Result:**
```python
@dataclass
class Phase0Result:
    fara_deviz: list[dict]          # articole cu deviz="" sau None
    incomplete: list[dict]          # cantitate=0 și um=""
    componente_orfane: list[dict]   # is_component=True, fără parent
    total_ref: int                  # total articole în referință
```

Dacă orice lista non-goală → semnal de alarmă în raport.

---

## Phase 1 — Analiza Articolelor EXTRA

**Sursă:** `comparatie_oferta_N.json["neconformitati"]` filtrat pe `tip="ARTICOL_EXTRA"`

**Grupare:** per deviz (câmpul `deviz_ref` sau `deviz`)

**Separare:**
- EXTRA `$`-coduri (`cod` începe cu `$`) — posibil resurse eDevize neextrase din referință
- EXTRA principale (`cod` nu începe cu `$`) — articole adăugate de ofertant

**Output Phase1Result:**
```python
@dataclass
class Phase1Result:
    oferta_idx: int
    extra_principale: list[dict]    # EXTRA non-$ per articol
    extra_dollar: list[dict]        # EXTRA $-coduri per articol
    by_deviz: dict[str, list[dict]] # {deviz_cod → [articole EXTRA]}
    total_extra: int
    total_extra_dollar: int
```

**Câmpuri afișate per articol EXTRA:** `cod`, `denumire`, `cantitate` (ofertă), `um`.

---

## Phase 2 — Analiza Articolelor LIPSA

**Sursă:** `comparatie_oferta_N.json["neconformitati"]` filtrat pe `tip` în `{"ARTICOL_LIPSA", "DEVIZ_MISMATCH"}`

**Separare:**
- `ARTICOL_LIPSA` genuine — absent complet din ofertă
- `DEVIZ_MISMATCH` — cod găsit în alt deviz din ofertă

**Grupare:** per deviz (câmpul `deviz_ref`)

**Output Phase2Result:**
```python
@dataclass
class Phase2Result:
    oferta_idx: int
    lipsa_genuine: list[dict]       # ARTICOL_LIPSA per articol
    deviz_mismatch: list[dict]      # DEVIZ_MISMATCH per articol
    by_deviz: dict[str, list[dict]] # {deviz_cod → [articole LIPSA]}
    total_lipsa: int
    total_deviz_mismatch: int
```

**Câmpuri afișate per articol LIPSA:** `ref_cod`, `ref_denumire`, `cantitate_ref`, `um_ref`.

---

## Structura diagnostics.json

```json
{
  "meta": {
    "data_generare": "2026-05-21T...",
    "versiune_pipeline": "8.0",
    "clienti_analizati": ["Blocuri Racari", "Camin Maneciu", ...]
  },
  "clienti": [
    {
      "client": "Blocuri Racari",
      "ref_quality": {
        "total_ref": 530,
        "fara_deviz": [],
        "incomplete": [...],
        "componente_orfane": [...]
      },
      "oferte": [
        {
          "oferta_idx": 1,
          "sumar": {"matched": 308, "lipsa": 47, "extra": 0, "deviz_mismatch": 20},
          "extra": {"total": 0, "dollar": 0, "principale": 0, "by_deviz": {}},
          "lipsa": {"total": 47, "genuine": 27, "deviz_mismatch": 20, "by_deviz": {...}}
        }
      ]
    }
  ],
  "sumar_global": {
    "total_matched": 12549,
    "total_lipsa": ...,
    "total_extra": ...,
    "total_deviz_mismatch": ...,
    "clienti_cu_alarme_ref": ["Camin Maneciu"]
  }
}
```

---

## Structura DOCX

### Secțiune per client

```
═══ CLIENT: Blocuri Racari ═══════════════════════════

  [Sumar oferte]
  ┌─────────────┬─────────┬───────┬───────┬──────────┐
  │ Ofertă      │ Matched │ LIPSA │ EXTRA │ DEV_MM   │
  ├─────────────┼─────────┼───────┼───────┼──────────┤
  │ Oferta 1    │ 308     │ 47    │ 0     │ 20       │
  │ Oferta 2    │ 551     │ 2     │ 0     │ 28       │
  └─────────────┴─────────┴───────┴───────┴──────────┘

  [Phase 0] Calitate referință
    ✅ 0 articole fără deviz
    🟡 12 componente fără parent identificat: [lista cod + denumire]
    ✅ 0 articole incomplete

  [Phase 1] Articole EXTRA — Oferta 1 (0 total)
    ✅ Niciun articol extra

  [Phase 1] Articole EXTRA — Oferta 2 (0 total)
    ✅ Niciun articol extra

  [Phase 2] Articole LIPSA — Oferta 1 (47 total: 27 genuine + 20 deviz mismatch)
    Deviz 4.1-03 — 5 articole lipsă:
      · CK25A — Hidroizolatie...    ref: 120 mp
      · ...
    DEVIZ_MISMATCH (20): cod prezent în alt deviz din ofertă — nu sunt erori reale
```

### Notă contextuală pentru EXTRA (afișată dacă EXTRA > 0)

> *"Număr mare de articole EXTRA poate indica bug-uri de extragere în referință (F3 neprocesat, deviz neidentificat, componente ignorate). Verificați Phase 0 și comparați cu documentul PDF original."*

### Sumar global (ultima secțiune)

Tabel cross-client cu toate metricile. Celule roșii dacă: Phase 0 alarme critice, EXTRA > 5% din matched, LIPSA genuine > 10% din matched.

---

## Praguri semafoare (sumar global)

| Metrică | 🟢 Verde | 🟡 Galben | 🔴 Roșu |
|---------|---------|---------|--------|
| Phase 0 fara_deviz | 0 | 1-5 | > 5 |
| EXTRA / matched | < 2% | 2-10% | > 10% |
| LIPSA genuine / matched | < 5% | 5-15% | > 15% |
| DEVIZ_MISMATCH / matched | < 5% | 5-20% | > 20% |

---

## CLI

```bash
# Toți clienții (default)
python3 run_diagnostics.py

# Client specific
python3 run_diagnostics.py --client "Blocuri Racari"

# Doar JSON (fără DOCX)
python3 run_diagnostics.py --no-docx

# Output dir custom
python3 run_diagnostics.py --output-dir /path/to/output
```

---

## Criterii de succes

1. Script rulează fără erori pe toți 4 clienții
2. `diagnostics.json` conține date corecte (validate manual vs `state.md` baseline)
3. DOCX generabil și lizibil în Word
4. Phase 0 detectează corect componentele orfane din `Camin Maneciu` (EXTRA mare = semnal)
5. Phase 1 listează cele 36 EXTRA din Camin Maneciu O1 grupate pe deviz
6. Phase 2 listează cele 624 DEVIZ_MISMATCH din Scoala Dragomiresti separate de LIPSA genuine (6)

---

## Fișiere modificate / create

| Fișier | Acțiune |
|--------|---------|
| `run_diagnostics.py` | NOU — entry point |
| `shared/diagnostics_builder.py` | NOU — Phase 0/1/2 + JSON builder |
| `shared/diagnostics_word.py` | NOU — DOCX generator |
| `tests/test_diagnostics.py` | NOU — teste unitare faze |
