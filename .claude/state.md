# Session State — 2026-05-22 (final complet)

## Baseline FINAL (post toate fix-urile)

| Client | O | matched | LIPSA | EXTRA | DEVIZ_MM | DD |
|--------|---|---------|-------|-------|----------|----|
| Blocuri Racari | 1 | 314 | 47 | 0 | 20 | 0 |
| Blocuri Racari | 2 | 551 | 2 | 0 | 28 | 2 |
| Blocuri Racari | 3 | 414 | 21 | 5 | 14 | 46 |
| Blocuri Racari | 4 | 316 | 49 | 1 | 9 | 3 |
| Camin Maneciu | 1 | 1056 | 1 | 36 | 2 | 57 |
| Camin Maneciu | 2 | 1066 | 84 | 41 | 5 | 121 |
| Scoala Dragomiresti | 1 | 910 | 2 | 0 | 1 | 14 |
| Scoala Dragomiresti | 2 | 910 | 2 | 1 | 1 | 14 |
| Scoala Sportiva Racari | 1 | 2152 | 2 | 122 | 6 | 139 |
| Scoala Sportiva Racari | 2 | 1119 | 4 | 55 | 325 | 28 |
| Scoala Sportiva Racari | 3 | 2404 | 6 | 318 | 299 | 44 |

**DD = DESCRIERE_DIFERITA** — detectie Jaccard < 0.50 pe cuvinte (robust OCR).

## Fix-uri livrate sesiunea 2026-05-22 (ordine)

1. Parser scatter `is_f3_um` single-token → BR O3 +19 matched
2. `_CATEGORIA_OPT_RE` decimal + Strategy 0 numeric → SD DEVIZ_MM 624→1
3. Client name + `_extract_ofertant_name` (Executant: prioritar)
4. COD_SIMILAR mereu + DESCRIERE_DIFERITA tip nou + cant=0 filter
5. Strategy 0 format-aware (padded-int only) → CM regresia prevenita
6. DD false pozitive reduse: Jaccard 0.50, OCR artifacts extinse (l: notatie, financiar)

## Known Issues Active

1. **IZDO3D1 OCR** — acceptat
2. **DD reziduale** (CM O2=121, SSR O1=139, BR O3=46): abrevieri ("pt"/"pentru", "termoizol."). Fix propus: dicționar abrevieri statice.
3. **CM O2 LIPSA=84** — neinvestigat
4. **SSR O2/O3 DEVIZ_MM=300+** — neinvestigat
5. **SSR O3 EXTRA=318** — neinvestigat

## Propunere: Dicționar Abrevieri

Sursa principala de false pozitive reziduale: abrevieri specifice documentelor F3 românești.

**Abrevieri comune detectate:**
```python
ABREVIERI_F3 = {
    "pt": "pentru",
    "pt.": "pentru",
    "supr.": "suprafata",
    "supr": "suprafata",
    "toc": "tocarie",         # "supr toc" = suprafata tocarie
    "termoizol.": "termoizolatii",
    "termoizolat.": "termoizolate",
    "canat": "canat",         # uneori split: "canat uri" → "canaturi"
    "exec.": "executare",
    "mont.": "montare",
    "inc.": "inclusiv",
    "incl.": "inclusiv",
    "dim.": "dimensiune",
    "gr.": "grosime",
    "gros.": "grosime",
    "diam.": "diametru",
    "d.": "diametrul",        # "d. 30mm"
    "dn": "diametru nominal", # tehnic, nu expandat
    "pn": "presiune nominala", # tehnic, nu expandat
    "b.a.": "beton armat",
    "b.c.a.": "beton celular autoclavizat",
}
```

**Implementare propusă:** în `_clean_den()` din `shared/comparator.py`, aplică înlocuiri din dicționar înaintea tokenizarii Jaccard.

**Alternativa LLM:** În loc de dicționar static, trimitere la LLM a perechilor cu DD și sim 0.40-0.60 pentru validare: "Sunt aceste denumiri echivalente? Răspunde DA/NU." Costisitor dar precis pentru cazuri ambigue.

## Ce urmează

Refactorizare. Citește ARCHITECTURE.md. Opțional: implementare dicționar abrevieri.
