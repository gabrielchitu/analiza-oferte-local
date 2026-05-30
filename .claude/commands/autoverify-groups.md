# Autoverificare Group Matching — Loop autonom

Executa loop autonom de convergenta group matching pentru un client.

**Invariant hard: oferta_only == 0.** Orice oferta_only > 0 = retry obligatoriu.
**Invariant soft: ref_only ≤ 2.** Mai mult → întreabă operatorul.

**Nu decide singur ce e "acceptabil". Nu te opri fără a verifica invariantele.**

## Input

Argumentul optional: numele clientului (ex: `Drum Tatarani`). Daca lipseste, intreaba o singura data.

## Algoritmul

### Pas 1 — Citeste starea curenta

Citeste `output_AO/<client>/holistic_oferta_1.json` (si oferta_2, N etc.).
Extrage:
- `oferta_only_count = len(data["oferta_only_groups"])`
- `ref_only_count = len(data["ref_only_groups"])`
- `matched_count = len(data["matched_groups"])`

Daca `oferta_only_count == 0` si `ref_only_count <= 2` → STOP cu mesaj SUCCESS.

### Pas 2 — Diagnostica oferta_only (invariant hard)

Daca `oferta_only_count > 0`:
1. Listeaza grupurile din `oferta_only_groups`:
   - `group["oferta_deviz_cod"]`
   - `group.get("deviz_denumire", "")` sau `group.get("oferta_header", {})`
2. Cauta aceste denumiri in `input_AO/<client>/di_referinta.json`:
   - In `pages[N].lines[M].content` (fuzzy search, prag 60%)
   - In `tables[N].cells[M].content` daca exista
3. Daca gasit in referinta → grupul nu a fost extras din ref → extraction bug
4. Daca negasit → grupul e genuinely absent din ref (atipic, semnaleaza)

### Pas 3 — Determina strategia de retry

Daca `oferta_only > 0` si grupul e in referinta (Pas 2 pct 3):
- Verifica `output_AO/<client>/checkpoints/profile_*.json`: mode = TABLE sau LINES?
- Daca LINES si referinta are `tables[]` structurate → sterge checkpoint profile → rerun va incerca TABLE
- Daca TABLE si extragere e gola → verifica `_find_header_row` pe tabelul din di_referinta
- Altfel → adauga manual in `shared/group_match_knowledge.json` perechea ref↔oferta

### Pas 4 — Rerun pipeline

```bash
python3 multi_client_run.py --client "<client>"
```

Reciteste holistic_oferta_N.json. Compara oferta_only_count cu iteratia anterioara.

### Pas 5 — Convergence check

- `oferta_only == 0` → SUCCESS invariant hard
- `oferta_only` scade → continua loop (max 3 iteratii)
- `oferta_only` stabil (±0) dupa 2 iteratii → **INTREABA OPERATORUL**:
  "Nu pot reduce oferta_only automat. Grupurile neresolvate: [lista]. Ce actiune doresti?"

### Pas 6 — Verifica ref_only (invariant soft)

Daca `ref_only > 2`:
- Cauta fiecare grup ref_only in di_oferta_N.json (fuzzy, prag 65%)
- Daca gasit → propune adaugare in group_match_knowledge.json si rerun
- Daca negasit → diferenta reala (ofertant a omis lucrari) → raporteaza, nu modifica
- Daca `ref_only > 2` stabil dupa 1 retry → **INTREABA OPERATORUL**

### Pas 7 — Commit daca s-a modificat knowledge

```bash
git add shared/group_match_knowledge.json
git commit -m "fix(groups): autonomous group match <client> — reduce oferta_only N→M"
```

### Pas 8 — Raport final

Afiseaza:
- Iteratii executate
- oferta_only: initial → final
- ref_only: initial → final
- matched: initial → final
- Daca a fost nevoie de interventie operator: DA/NU

## Stop conditions

- `oferta_only == 0` si `ref_only <= 2` → SUCCES complet
- `oferta_only > 0` stabil dupa 2 iteratii → ESCALADARE operator obligatorie
- `ref_only > 2` stabil dupa 1 retry → ESCALADARE operator

## Note

- holistic_oferta_N.json: chei `matched_groups`, `ref_only_groups`, `oferta_only_groups`
- group_match_knowledge.json: structura `{client_name: [{ref_den, oferta_den}]}`
- _den_string(header) = "obiectivul | obiectul | categoria" (format canonical)
- Sterge checkpoint profile pentru a forta re-profilare: `rm output_AO/<client>/checkpoints/profile_*.json`
- MAX_REF_ONLY default = 2, configurabil per-client in shared/agent_knowledge.json
