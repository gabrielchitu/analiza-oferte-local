# Rulare pipeline — comenzi rapide

## 1. Pipeline complet (extragere + comparare + generare DOCX)

Genereaza `referinta.json`, `holistic_oferta_N.json` si `Raport_Oferta_N.docx` in `output_AO/<client>/`.

**Meniu interactiv (alegi clientul):**
```bash
python3 multi_client_run.py
```

**Direct, fara meniu:**
```bash
python3 multi_client_run.py --client "Camin Maneciu"
python3 multi_client_run.py --client "Scoala Dragomiresti"
python3 multi_client_run.py --client "Scoala Sportiva Racari"
python3 multi_client_run.py --client "Blocuri Racari"
```

Output relevant:
- `output_AO/<client>/referinta.json` — articole extrase din DI referinta
- `output_AO/<client>/holistic_oferta_N.json` — comparatie completa per oferta
- `output_AO/<client>/Raport_Oferta_N.docx` — raport Word per oferta

---

## 2. Verificare output (fara re-rulare pipeline)

Ruleaza 6 checks structurale pe holistic JSON si genereaza raport Markdown.

```bash
python3 verify_agent.py --client "Camin Maneciu" --verify-only
```

Raportul se salveaza in `output_AO/<client>/verify_report_<timestamp>.md`.

Severitati raport:
| Nivel | Semnificatie |
|-------|-------------|
| CRITICAL | Violare invariant silentioasa — necesita interventie manuala |
| HIGH | Grupuri lipsa / extra / goale |
| MEDIUM | HIGH_EXTRA / HIGH_LIPSA in grupuri matched (eroare extractie probabila) |
| LOW | COD_SIMILAR clusters |

---

## 3. Generare DOCX (inclusa in pipeline)

`Raport_Oferta_N.docx` se genereaza **automat** la finalul `multi_client_run.py`.
Nu exista un pas separat.

Daca vrei sa regenerezi doar DOCX-ul fara re-extractie:
```bash
# Nu exista comanda separata — re-ruleaza pipeline-ul complet
python3 multi_client_run.py --client "<client>"
```

---

## 4. Skill autoverificare ARTICOL_EXTRA

Loop autonom: citeste EXTRA din raport → cauta in di_referinta → identifica root cause → fixeaza parser → re-ruleaza → commit → urmatorul.

**In conversatia cu Claude Code:**
```
/autoverify-extra Camin Maneciu
```

Skill-ul se opreste cand:
- Toate EXTRA-urile sunt fixate sau sunt genuine (absent din di_referinta)
- Sau dupa 5 iteratii fara progres

---

## Clienti disponibili

| Client | Director input |
|--------|---------------|
| Camin Maneciu | `input_AO/Camin Maneciu/` |
| Scoala Dragomiresti | `input_AO/Scoala Dragomiresti/` |
| Scoala Sportiva Racari | `input_AO/Scoala Sportiva Racari/` |
| Blocuri Racari | `input_AO/Blocuri Racari/` |
| BR BLOC A / A2 / A3 / A4 / B / C | `input_AO/BR BLOC A/` etc. |

---

## Debugging rapid

```bash
# Verifica articole extrase din referinta
python3 -c "
import json
with open('output_AO/<client>/referinta.json') as f:
    arts = json.load(f)
arts = arts if isinstance(arts, list) else arts.get('articole', [])
print(f'Total: {len(arts)}')
"

# Cauta un cod specific in di_referinta
python3 -c "
import json
with open('input_AO/<client>/di_referinta.json') as f:
    data = json.load(f)
pages = data if isinstance(data, list) else data.get('pages', [])
for i, p in enumerate(pages):
    lines = p if isinstance(p, list) else p.get('lines', [])
    for j, l in enumerate(lines):
        c = l.get('content', l) if isinstance(l, dict) else l
        if 'COD_CAUTAT' in str(c):
            print(f'Page {i}, line {j}: {c}')
"

# Testeaza extractia unui set de linii
python3 -c "
import sys; sys.path.insert(0, '.')
from shared.f3_regex_parser import extract_articles_regex, SKIP_RE
lines = ['...', '...']
print('SKIP check:', [(l, bool(SKIP_RE.search(l))) for l in lines])
arts = extract_articles_regex(lines, deviz_cod='4.1-03', deviz_den='Test')
print('Articles:', [(a['cod'], a['um'], a['cantitate']) for a in arts])
"
```
