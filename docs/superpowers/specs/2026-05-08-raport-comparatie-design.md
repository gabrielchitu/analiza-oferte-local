# Design Spec: Raport Comparație Oferte

**Data**: 2026-05-08  
**Status**: Draft pentru aprobare  
**Cerință**: Raport DOCX robust, deviz cu deviz, în care clientul poate verifica cu încredere că fiecare rând din proiect (referință F3) a fost ofertat corect.

---

## Context și principii fundamentale

### Cheia de potrivire
Fiecare **rând** dintr-un F3 este identificat prin tripletul `(deviz, cod, UM)`, cu cantitatea ca câmp de comparat. Același cod poate apărea:
- în devize diferite (lucrare diferită, aceeași normă) → articole distincte
- de mai multe ori în același deviz (cantități diferite) → articole distincte

### Caracterele speciale în coduri
Codurile valide conțin **exclusiv** litere mari și cifre arabe `[A-Z0-9]`. Caracterele speciale (`#`, `@`, `[7]`, `$`) sunt artefacte software/OCR și se normalizează (strip) înainte de matching.

### Calitatea extracției = baza de încredere
Dacă din referință lipsesc rânduri (extracție ratată), acestea vor genera automat LIPSA false și EXTRA false în comparație. **Eroarea de extracție se propagă și se amplifică.**

Indicatori de calitate extracție:
- Articole cu `deviz_cod = ""` → F3 pagina fără deviz identificat → problemă
- Devize în ofertă absente complet din referință → F3 din referință neextras

---

## Arhitectura comparației (3 niveluri)

### Nivel 1 — Pre-verificare calitate extracție

**Se execută înainte de orice comparație, per document.**

```
Pentru fiecare document (referință + fiecare ofertă):
  a) Articole cu deviz_cod="" → ALERTĂ: pagini F3 fără deviz identificat
  b) Devize din ofertă absente din referință → ALERTĂ CRITICĂ (explicată mai jos)
```

### Nivel 2 — Verificare cantitativă per deviz

**Pentru fiecare deviz din referință:**
```
ref_count   = număr de articole (deviz, cod) din referință
offer_count = număr de articole (deviz, cod) din ofertă (pentru același deviz)
delta       = offer_count - ref_count
```

Scopul: indicator rapid de completitudine. Delta ≈ 0 = bine. Delta negativă = articole lipsă.

### Nivel 3 — Matching rând cu rând per deviz

**Pentru fiecare (deviz, cod) din referință:**

| Caz | Tip | Detaliu |
|-----|-----|---------|
| Match exact (deviz, cod) | — | Compară cantitate și UM |
| Cantitate diferă | `DIFERENTA_CANT` | ref_cant vs offer_cant, diferența absolută și % |
| UM diferă | `UM_DIFERIT` | ref_um vs offer_um |
| Absent din ofertă | `ARTICOL_LIPSA` | neofertată |
| Prezent în ofertă, absent din ref | `ARTICOL_EXTRA` | cu hint de verificare manuală |

Matching fallback (Layer 2): cod normalizat (OCR: l→1, O→0, strip caractere speciale) — dacă match-ul e prin normalizare → raportăm ca `COD_SIMILAR` cu ambele forme.

---

## Structura raportului DOCX

### Structura per deviz

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
DEVIZ 226108 — STRUCTURA DE REZISTENTA CUPOLA
Referință: 44 articole | Oferta 1: 44 articole | Delta: 0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Tabel diferențe — dacă există]
Tip          | Cod REF   | Denumire (trunchiată)    | REF cant/UM | Oferta cant/UM | Diferență
LIPSA        | CC03C     | MONTARE ARMATURI...      | 4900 KG     | —              | −4900 KG
DIFERENTA    | CB01A1    | COFRAJE IN CUZINETI...   | 200 MP      | 185 MP         | −15 MP
UM_DIFERIT   | TRA06A10  | TRANSPORT RUTIER...      | 10.5 TONA   | 10.5 KG        | —

[Dacă delta = 0 și fără diferențe]
✓ Deviz complet ofertat, fără diferențe de cantitate.

[Dacă există EXTRA — secțiune separată la final deviz]
Articole extra în ofertă (verificare manuală recomandată):
  • $3276069 — TUB PROTECTIE — 650 ML
    (Cod absent din referință pentru acest deviz)
  • $7302051 — CORP ILUMINAT — 1 BUC
    (Cod absent din referință pentru acest deviz)
```

### Alerte finale per ofertă (după toate devizele)

**Secțiunea apare doar dacă există probleme:**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠  ALERTE DE CALITATE — VERIFICARE MANUALĂ NECESARĂ
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALERTĂ CRITICĂ — Devize în ofertă absente din referință:
  • 226668 — 12 articole ofertate
    Aceste articole NU au putut fi comparate cu referința.
    Cauze posibile:
      (a) F3 pentru devizul 226668 nu a fost extras din documentul de referință
      (b) Ofertantul a propus lucrări suplimentare față de proiect
    → Recomandare: verificați manual formularul F3 deviz 226668 din proiect.

Articole cu deviz neidentificat (extracție incompletă):
  • 3 articole din ofertă fără deviz asociat → nu au putut fi comparate
```

---

## Logica pentru "deviz în ofertă, absent din referință"

**Nu filtrăm aceste devize la extracție.** Le extragem, nu le comparăm automat, le raportăm ca alertă.

**De ce nu filtrăm**: filtrul actual (`ref_deviz_codes`) aruncă articolele din devize extra ale ofertei ÎNAINTE de extracție. Dacă referința a ratat un întreg F3, acele articole dispar complet din comparație fără nicio alertă. Clientul nu știe că există o problemă.

**Comportament nou**:
- Extragem TOATE articolele din ofertă (fără filtru de deviz)
- Comparăm numai devizele comune ref ∩ ofertă (matching normal)
- Devizele în ofertă dar nu în ref → Secțiunea ALERTĂ, nu LIPSA sau EXTRA obișnuit

---

## Normalizare coduri articole

### Regula
`canonical_cod([A-Z0-9]+)`:
1. Uppercase tot
2. OCR: `l` → `1`, `L` → `1`, `O` → `0`
3. Strip toate caracterele non-`[A-Z0-9]` (inclusiv `#`, `@`, `[`, `]`, `-`, `$` la matching)
4. Pentru coduri numeric pure (breviar propriu): adaugă prefix `$` intern

### Exemple
| Raw | Canonical (matching) |
|-----|----------------------|
| `IC31A1#` | `IC31A1` |
| `RPCE29A#` | `RPCE29A` |
| `CA02Al` | `CA02A1` (l→1) |
| `$3276069` | `3276069` (intern `$3276069`) |
| `CL08B1[7]` | `CL08B17` |

---

## Indicatori de calitate în raport (sumar)

La finalul raportului, o pagina de sumar:

```
SUMAR COMPARAȚIE OFERTA X vs REFERINȚĂ

Extracție referință:     1279 articole | 41 devize | 0 fără deviz
Extracție ofertă X:      1176 articole | 20 devize (din 41 ref) | 0 fără deviz

Per deviz (din 41 referință):
  • 35 devize complet ofertate (delta=0 sau diferențe minore)
  •  6 devize cu articole lipsă
  •  0 devize complet lipsă din ofertă ← IMPORTANT

Neconformități:
  • ARTICOL_LIPSA:   127 (rânduri din ref complet absente din ofertă)
  • DIFERENTA_CANT:   47 (cantitate diferită)
  • UM_DIFERIT:       22 (unitate de măsură diferită)
  • ARTICOL_EXTRA:    15 (în ofertă, absent din ref — verificare manuală)
  • COD_SIMILAR:      12 (cod potrivit după normalizare OCR)

Alerte calitate:
  •  0 devize în ofertă absente complet din ref
  •  0 articole fără deviz identificat
```

---

## Ce NU se schimbă

- Matching-ul rămâne strict per `(deviz, cod)` — nu facem matching cross-deviz
- ORPHAN (deviz greșit) rămâne ca informație suplimentară, nu ca neconformitate principală
- Priortiatea raportului: ceea ce clientul TREBUIE să vadă clar sunt LIPSA + DIFERENTE

---

## Fișiere afectate de implementare

| Fișier | Modificare |
|--------|-----------|
| `local_run.py` | Scoate filtrul `ref_deviz_codes` din extracție oferte; tracking devize extra |
| `AgentComparator_local.py` | `match_global` lucrează pe devize comune, separă devizele extra |
| `shared/orphan_detector.py` | Deja refăcut (post-matching, fără produs cartezian) |
| `AgentComparator_local.py` | `_normalize_cod` — strip `#` în loc de `#→1` |
| `shared/report_word.py` | Restructurare majoră: deviz-cu-deviz, alerte calitate |
| `shared/comparator.py` | Verificat: suportă noua structură? |

---

## Criterii de succes

1. **Zero false LIPSA din referință** — orice LIPSA raportat = articol genuinely neofertate
2. **Zero devize pierdute** — fiecare F3 din referință și ofertă e acoperit sau alertat
3. **Raportul e acționabil** — clientul știe exact ce să verifice manual
4. **Articole cu deviz_cod="" = vizibile** — nu ascunse, nu silentios ignorate
