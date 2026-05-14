"""
F3 extractor — extrage articole din Formularul F3 (Lista cu Cantitatile de Lucrari)
folosind textul brut din Document Intelligence + GPT-4o.

Structura unui articol F3 (5 linii):
  Linia 1: [NR] [SIMBOL_COD]  [UM]  [CANTITATE]  [PU_MAT]  [VAL_MAT]
  Linia 2: [denumire part 1]                      [PU_MAN]  [VAL_MAN]
  Linia 3: [denumire part 2]                      [PU_UTI]  [VAL_UTI]
  Linia 4: [denumire part 3]                      [PU_TRA]  [VAL_TRA]
  Linia 5: [SPOR] [GR/UA] [GR.TOT.]  Total=       [TOTAL]
"""
import re
import json
import logging
from typing import List, Dict, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


def _normalize_deviz_cod(cod: str) -> str:
    """Normalizeaza cod deviz: 226U38 → 226038 (U→0 pentru OCR consistency)."""
    if not cod:
        return cod
    return cod.replace('U', '0')


def _normalize_denom(text: str) -> str:
    """Normalizeaza DENUMIRE pentru matching: lowercase, spații, caractere speciale.

    Rezolvă: "ROBINET 1/2\"" vs "ROBINET 1/2" (quote char variație)
             "PLASA ZN.MONT. LA" vs "PLASA ZN.MONT.LA" (spații)
             "BST500 8 MM" vs "BST500 8 mm" (case)
    """
    if not text:
        return text
    # lowercase
    text = text.lower()
    # normalizează citate: " → ', și alte variații
    text = text.replace('"', "'").replace('"', "'").replace('"', "'")
    # înlaturează puncte după litere (ex: "INOX." → "INOX", "M." → "M")
    text = re.sub(r'([A-Z])\.\s+', r'\1 ', text, flags=re.IGNORECASE)
    # înlaturează spații multiple
    text = re.sub(r'\s+', ' ', text)
    # trim
    return text.strip()


# Pattern 1 (priority): "Deviz oferta XXXX DENUMIRE"
_DEVIZ_OFERTA_RE = re.compile(
    r'Deviz\s+oferta\s+([A-Z0-9]+)\s+(.*)',
    re.IGNORECASE
)

# Pattern 2: "STADIUL FIZIC: DENUMIRE" sau "STADIU FIZIC: DENUMIRE"
_STADIU_FIZIC_RE = re.compile(
    r'STADIU[L]?\s+FIZIC\s*:\s*(.+)',
    re.IGNORECASE
)

# Pattern 3: "Categoria de lucrari: [N] DENUMIRE"
_CATEGORIA_RE = re.compile(
    r'Categoria\s+de\s+lucrari\s*:\s*(?:\d+\s+)?(.+)',
    re.IGNORECASE
)

# Pattern pentru linii ">>> componenta NNN NNN COD UM DENUMIRE"
_COMPONENTA_RE = re.compile(
    r'>>>\s*componenta\s+\S+\s+\S+\s+([A-Z$][A-Z0-9#$]*)\s+([A-Z.]{1,10})\s*(.*)',
    re.IGNORECASE
)

# Linii de ignorat (sumar sfarsit deviz)
_SKIP_RE = re.compile(
    r'(Cheltuieli\s+directe|Total\s+cheltuieli|Cheltuieli\s+indirecte|Profit|TOTAL\s+GENERAL'
    r'|TVA|Alte\s+cheltuieli|contributie\s+asiguratorie)',
    re.IGNORECASE
)

SYSTEM_PROMPT = """Esti expert in documente de devize de constructii romanesti (Formularul F3 - Lista cu Cantitatile de Lucrari).

Ti se da textul brut al unei sectiuni de deviz. Din cauza extragerii OCR, fiecare valoare poate aparea pe linie separata. Formatul logic al unui articol:
  [NR_CRT] [SIMBOL_ARTICOL]
  [UM]
  [CANTITATE]
  [DENUMIRE linia 1]
  [DENUMIRE linia 2] (optional)
  [DENUMIRE linia 3] (optional)
  (optional) valori pret pe linii separate

Exista doua tipuri de coduri valide pentru SIMBOL_ARTICOL:
  1. Coduri normative (catalog): RPCT09H1, CA07A1, EA02A1, SA14B#, CK19A#, TSD01D1, ACA11A1# etc.
  2. Articole de deviz proprii (breviar de calcul): $01063, $11225, $22180, $18601 etc. (incep cu $)
     - Acestea sunt articole PRINCIPALE, la fel de importante ca cele normative.
     - Sunt urmate de un bloc "- DESCRIERE:" cu componente de ignorat (linii ">>> componenta NNN").

Reguli IMPORTANTE:
- Extrage AMBELE tipuri de articole: coduri normative SI coduri cu $ (articole proprii)
- SUB-ARTICOLE CU MARKER DECIMAL: Liniile cu numere precum "23.1", "61.1", "52.1" sunt markeri de SUB-ARTICOLE
  distincte (nu sunt comentarii sau variante). Fiecare marker decimal introduce un ARTICOL NOU cu cod, UM si
  cantitate proprii. Exemplu: "23" (articol IZF13A01 cu cant=175) urmat de "23.1" (articol 4321431 cu cant=176.75)
  sunt DOI articoli separati si trebuie amandoi extrasi.
- ARTICOLE LA LIMITE DE PAGINA: Articolele pot fi urmate direct de footer (Deviz "X.X" - Formular F3, Pagina N din M).
  Ignora footer-ul dar PASTREAZA articolul complet cu codul, UM si cantitate.
  Exemplu: "2100995 - Beton...\nmc\n8.100\nDeviz "2.2" - Formular F3" → extrage 2100995 cu UM=mc, cant=8.100
- Ignora TOATE liniile care incep cu ">>> componenta" - acestea sunt sub-componente, NU articole separate
- Ignora linia "- DESCRIERE:" si tot ce urmeaza pana la urmatorul articol principal
- Ignora randurile de sumar (Cheltuieli directe, Total cheltuieli, Cheltuieli indirecte, Profit, TOTAL GENERAL, TVA)
- Ignora anteturile si subsolurile de pagina (Persoana juridica, Formularul F3, Obiectivul, nr. pagina etc.)
- Concateneaza liniile de denumire pentru a forma denumirea completa a articolului
- Valorile numerice folosesc punct sau virgula ca separator zecimal
- Coduri NUMERICE PURE ca articole principale: daca un cod numeric (ex: 2946088, 3050112) apare ca articol
  principal (cu NR_CRT, UM, cantitate, preturi), este un cod de breviar propriu VALID si trebuie extras.
  Adauga prefix '$' la aceste coduri (ex: 2946088 -> "$2946088").
- Ignora coduri numerice NUMAI daca apar ca resurse materiale in liste de resurse/componente (fara structura
  de articol complet cu UM si cantitate), sau ca numere de catalog in blocuri ">>> componenta".

Returneaza DOAR JSON valid (fara text suplimentar):
{
  "articole": [
    {
      "cod": "SIMBOL_ARTICOL",
      "denumire": "denumire completa a articolului",
      "um": "UM",
      "cantitate": 0.0,
      "pret_material": 0.0,
      "val_material": 0.0,
      "pret_manopera": 0.0,
      "val_manopera": 0.0,
      "pret_utilaj": 0.0,
      "val_utilaj": 0.0,
      "pret_transport": 0.0,
      "val_transport": 0.0
    }
  ]
}"""


def _is_numeric_cod(cod: str) -> bool:
    """True daca codul este pur numeric (resursa materiala, nu articol de lucrari)."""
    return bool(re.match(r'^\d+$', cod.strip()))


def _gen_deviz_cod(prefix: str, denumire: str, index: int) -> str:
    """Generate a short unique deviz code from prefix + denumire slug + index."""
    slug = re.sub(r'[^A-Z0-9]', '', denumire.upper())[:8]
    return f"{prefix}_{slug}_{index:02d}"


def _extract_sections_with_pattern(full_text: str, pattern, cod_prefix: str,
                                    group_cod: int = None, group_den: int = 1
                                    ) -> list:
    """
    Generic section extractor for a given regex pattern.
    group_cod: capture group index for the code (None = auto-generate)
    group_den: capture group index for the denomination
    Returns list of (deviz_cod, deviz_denumire, section_text) or [] if no matches.
    """
    matches = list(pattern.finditer(full_text))
    if not matches:
        return []

    sections = []
    for i, m in enumerate(matches):
        if group_cod is not None:
            deviz_cod = m.group(group_cod).upper()
        else:
            raw_den = m.group(group_den).strip()
            deviz_cod = _gen_deviz_cod(cod_prefix, raw_den, i + 1)

        deviz_den = m.group(group_den).strip()

        # For "Deviz oferta", try to capture multi-line title (existing logic)
        if group_cod is not None:
            after_match = full_text[m.end():]
            next_line_match = re.match(r'\s*\n([^\n]{1,60})\n', after_match)
            if next_line_match:
                next_line = next_line_match.group(1).strip()
                if next_line and not re.match(
                    r'(Categoria|Preturile|Lista cu|FORMULAR|NR\.|Obiectiv|Proiectant)',
                    next_line, re.IGNORECASE
                ):
                    deviz_den = (deviz_den + " " + next_line).strip()

        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)

        # Limitează ultima secțiune (sau orice secțiune) la primul marker de "end-of-deviz":
        # FORMULAR C5/C6 (lista resurse), Recapitulatia, etc. nu fac parte din deviz.
        _END_SECTION_RE = re.compile(
            r'(?:^|\n)(FORMULAR\s+C[0-9]|Lista\s+consumurilor\s+de\s+resurse|'
            r'Recapitulatia\s+cheltuielilor|CENTRALIZATOR)',
            re.IGNORECASE
        )
        end_m = _END_SECTION_RE.search(full_text, start + 1, end)
        if end_m:
            # Tăiem la începutul liniei care a declanșat marcatorul
            trimmed_end = end_m.start() if full_text[end_m.start()] == '\n' else end_m.start()
            logger.info(
                f"[F3] Sectiune {deviz_cod} taiata la marcatorul '{end_m.group().strip()}' "
                f"(de la {end - start} la {trimmed_end - start} chars)"
            )
            end = trimmed_end

        section_text = full_text[start:end]
        sections.append((deviz_cod, deviz_den, section_text))
        logger.info(f"[F3] Sectiune ({cod_prefix}): {deviz_cod} | {deviz_den} ({len(section_text)} chars)")

    return sections


def _split_into_deviz_sections(full_text: str) -> list:
    """
    Split full text into deviz sections using multiple patterns (priority order).
    Returns list of (deviz_cod, deviz_denumire, section_text).
    Returns [] if no pattern matches (caller uses fallback).

    Priority:
    1. "Deviz oferta XXXX DENUMIRE"
    2. "STADIUL FIZIC: DENUMIRE"
    3. "Categoria de lucrari: [N] DENUMIRE"
    """
    # Priority 1: Deviz oferta (existing format)
    sections = _extract_sections_with_pattern(
        full_text, _DEVIZ_OFERTA_RE, "DO",
        group_cod=1, group_den=2
    )
    if sections:
        return sections

    # Priority 2: STADIUL FIZIC
    sections = _extract_sections_with_pattern(
        full_text, _STADIU_FIZIC_RE, "SF",
        group_cod=None, group_den=1
    )
    if sections:
        return sections

    # Priority 3: Categoria de lucrari
    sections = _extract_sections_with_pattern(
        full_text, _CATEGORIA_RE, "CAT",
        group_cod=None, group_den=1
    )
    if sections:
        return sections

    logger.warning("[F3] Nicio sectiune gasita cu niciun pattern cunoscut")
    return []


def _chunk_text(text: str, max_chars: int = 12000) -> List[str]:
    """Imparte textul in chunk-uri, rupand la newline, fara a rupe articole.

    Evita ruperea in mijlocul articolelor care au structura:
      NR_CRT/COD
      UM
      CANTITATE
      [DENUMIRE...]
    """
    if len(text) <= max_chars:
        return [text]

    chunks = []
    lines = text.split('\n')
    current_chunk_lines = []
    current_chunk_size = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        line_size = len(line) + 1  # +1 for newline

        # Daca linia curenta ar depasi limita
        if current_chunk_size + line_size > max_chars and current_chunk_lines:
            # Finalizare chunk anterior (dar nu pe linie de cod/UM/cant incomplete)
            # Incearca sa nu iei pe jumatatile un articol
            chunks.append('\n'.join(current_chunk_lines))
            current_chunk_lines = []
            current_chunk_size = 0
            continue

        current_chunk_lines.append(line)
        current_chunk_size += line_size
        i += 1

    if current_chunk_lines:
        chunks.append('\n'.join(current_chunk_lines))

    return chunks


def _extract_chunk(chunk: str, deviz_cod: str, deviz_den: str,
                   openai_client, deployment: str) -> List[Dict]:
    """Trimite un chunk de text la LLM si returneaza articolele extrase."""
    try:
        resp = openai_client.chat.completions.create(
            model=deployment,
            temperature=0.0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"Deviz: {deviz_cod} {deviz_den}\n\n{chunk}"}
            ],
            max_tokens=8000
        )
        result = json.loads(resp.choices[0].message.content)
        return result.get("articole", [])
    except Exception as e:
        logger.error(f"[F3] LLM error pentru {deviz_cod}: {e}")
        return []


def _make_component(cod: str, denumire: str, um: str,
                    deviz_cod: str, deviz_den: str) -> dict:
    """Construieste un articol component (is_component=True, fara preturi)."""
    return {
        "cod": cod, "denumire": _normalize_denom(denumire), "um": um, "cantitate": 0.0,
        "pret_material": 0.0, "val_material": 0.0,
        "pret_manopera": 0.0, "val_manopera": 0.0,
        "pret_utilaj": 0.0, "val_utilaj": 0.0,
        "pret_transport": 0.0, "val_transport": 0.0,
        "deviz": _normalize_deviz_cod(deviz_cod), "deviz_denumire": deviz_den,
        "is_component": True,
    }


def _parse_component_block(lines: list, anchor_idx: int) -> tuple:
    """
    Pornind de la linia anchor (>>> sau NNN), extrage (cod, um, denumire)
    din urmatoarele linii. Returneaza (cod, um, denumire) sau (None, '', '').

    Formate suportate:
      Format A (>>> componenta):   anchor = '>>> componenta NNN'
                                   lines[+1] = 'NNN COD' sau 'COD'
      Format B (DESCRIERE inline): anchor = 'NNN COD' (cod pe aceeasi linie)
      Format C (DESCRIERE split):  anchor = 'NNN' (numar singur)
                                   lines[+1] = 'COD'
    Dupa cod: linia UM (BUC/MP/ORA/ZI etc.), linia cantitate, linia denumire.
    """
    _ALPHA_COD_RE = re.compile(r'(?:\d+\s+)?([A-Z$][A-Z0-9#$]{2,})', re.IGNORECASE)
    _NUMERIC_COD_RE = re.compile(r'(?:\d{1,3}\s+)?(\d{5,7})\s*$')
    _UM_RE = re.compile(r'^[A-Z]{1,6}\.?$', re.IGNORECASE)
    _CANT_RE = re.compile(r'^\d+[\.,]\d+$')

    def _extract_cod_from_line(line):
        m = _ALPHA_COD_RE.match(line.strip())
        if m:
            c = m.group(1).strip().upper()
            # Cod F3 valid: min 3 chars, nu pur numeric, trebuie sa contina cel putin o cifra
            # Elimina tokeni UM (BUC, MC, MP etc.) care nu au cifre
            return c if not re.match(r'^\d+$', c) and len(c) >= 3 and re.search(r'\d', c) else None
        # Cod numeric pur (ex: "036 6701362") — adauga prefix $
        m2 = _NUMERIC_COD_RE.match(line.strip())
        if m2:
            return '$' + m2.group(1)
        return None

    i = anchor_idx
    line = lines[i].strip()

    # Format A: >>> componenta NNN → cod pe linia i+1
    if re.match(r'>>>\s*componenta', line, re.IGNORECASE):
        if i + 1 >= len(lines):
            return None, '', ''
        cod = _extract_cod_from_line(lines[i + 1])
        cod_line_idx = i + 1

    # Format B/C: linie cu numar
    else:
        # Format B: "NNN COD" pe aceeasi linie
        m = re.match(r'^\d{1,3}\s+([A-Z$][A-Z0-9#$]{2,})', line, re.IGNORECASE)
        if m:
            cod = m.group(1).strip().upper()
            cod_line_idx = i
        else:
            # Format C: "NNN" singur → cod pe linia urmatoare
            if i + 1 >= len(lines):
                return None, '', ''
            cod = _extract_cod_from_line(lines[i + 1])
            cod_line_idx = i + 1

    if not cod:
        return None, '', ''

    # Dupa linia cu cod: UM, cantitate, denumire
    j = cod_line_idx + 1
    um = ''
    if j < len(lines) and _UM_RE.match(lines[j].strip().rstrip('.')):
        um = lines[j].strip().rstrip('.')
        j += 1
    if j < len(lines) and _CANT_RE.match(lines[j].strip()):
        j += 1
    denumire = lines[j].strip() if j < len(lines) else ''

    return cod, um, denumire


def _extract_components_from_section(section_text: str, deviz_cod: str, deviz_den: str) -> List[Dict]:
    """
    Extrage componente din doua tipuri de blocuri din $breviar:

    TIP 1 — '>>> componenta NNN':
      >>> componenta 012
      037 SC27A2 / BUC. / 1.000 / PORTPAHAR DIN FONTA

    TIP 2 — bloc '- DESCRIERE:' (resurse/utilaje din breviar de calcul):
      001 AUT3000 / ORA / 2.000 / APARAT DE SUDURA
      002          ← numar singur
      SA43D1       ← cod pe linia urmatoare

    Returneaza articole cu is_component=True, cantitate=0.
    """
    lines = section_text.splitlines()
    components = []
    seen_cods: set = set()

    _COMP_START_RE = re.compile(r'>>>\s*componenta\s+\d+', re.IGNORECASE)
    # Resurse utilaje: "NNN COD" pe aceeasi linie (ex: "001 AUT3000")
    _INLINE_RESOURCE_RE = re.compile(r'^\d{1,3}\s+([A-Z$][A-Z0-9#$]{2,})', re.IGNORECASE)
    # UM echipament/timp — discrimineaza utilajele de materiale si articole normale
    _EQUIP_UM = {'ORA', 'ORE', 'ZI', 'ZILE', 'SCHIMB', 'LUNA', 'LUNI', 'SAPT'}
    _UM_RE = re.compile(r'^[A-Z]{1,6}\.?$', re.IGNORECASE)

    def _add(cod, um, denumire):
        if cod and cod not in seen_cods:
            seen_cods.add(cod)
            components.append(_make_component(cod, denumire, um, deviz_cod, deviz_den))

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()

        # TIP 1: >>> componenta (format explicit)
        if _COMP_START_RE.match(line):
            cod, um, den = _parse_component_block(lines, i)
            _add(cod, um, den)
            continue

        # TIP 2: "NNN COD" inline — extrage DOAR daca UM e echipament/timp
        # Asta elimina: materiale (UM=M/ML/BUC/KG etc.) si articole normale
        if _INLINE_RESOURCE_RE.match(line):
            # Verifica UM pe linia urmatoare
            if i + 1 < len(lines):
                um_candidate = lines[i + 1].strip().rstrip('.')
                if _UM_RE.match(um_candidate) and um_candidate.upper() in _EQUIP_UM:
                    cod, um, den = _parse_component_block(lines, i)
                    _add(cod, um, den)

    if components:
        logger.info(f"[F3] {deviz_cod}: {len(components)} componente extrase din breviar (>>> + DESCRIERE)")
    return components


def extract_articles_from_text(full_text: str, openai_client, deployment: str,
                               progress_callback=None,
                               checkpoint_callback=None,
                               existing_chunk_results: dict = None) -> List[Dict]:
    """
    Extrage toate articolele F3 din textul complet al documentului.
    Proceseaza chunk-urile in paralel (ThreadPoolExecutor).

    Params:
      progress_callback(done, total)       — apelat la fiecare 10 chunks
      checkpoint_callback(chunk_results)   — apelat la fiecare 10 chunks cu dict complet
      existing_chunk_results               — dict {chunk_key: articles} din checkpoint anterior
                                             chunk_key = "deviz_cod|deviz_den|idx"
    """
    sections = _split_into_deviz_sections(full_text)

    if not sections:
        logger.warning("[F3] Fallback: trimit tot textul la LLM fara sectiuni")
        sections = [("PR0000", "LUCRARI", full_text)]

    # Construieste lista plata de (deviz_cod, deviz_den, chunk_idx, total_chunks, chunk)
    work_items = []
    for deviz_cod, deviz_den, section_text in sections:
        chunks = _chunk_text(section_text)
        for idx, chunk in enumerate(chunks):
            work_items.append((deviz_cod, deviz_den, idx + 1, len(chunks), chunk))

    total_chunks = len(work_items)

    # Incarca rezultatele din checkpoint (daca exista)
    # Checkpoint foloseste string keys "deviz_cod|deviz_den|idx"
    # chunk_results intern foloseste tuple keys (deviz_cod, deviz_den, idx)
    chunk_results: Dict[tuple, List[Dict]] = {}
    if existing_chunk_results:
        for ck, arts in existing_chunk_results.items():
            parts = ck.split("|", 2)
            if len(parts) == 3:
                try:
                    chunk_results[(parts[0], parts[1], int(parts[2]))] = arts
                except ValueError:
                    pass
        logger.info(f"[F3] Checkpoint: {len(chunk_results)}/{total_chunks} chunks deja procesate")

    # Filtreaza work_items — sare peste chunks deja in checkpoint
    work_items_todo = [
        item for item in work_items
        if (item[0], item[1], item[2]) not in chunk_results
    ]

    logger.info(f"[F3] Chunks de procesat: {len(work_items_todo)}/{total_chunks} (paralel, max 8 workers)")

    def _process_item(item):
        deviz_cod, deviz_den, idx, total, chunk = item
        logger.info(f"[F3] {deviz_cod} chunk {idx}/{total} ({len(chunk)} chars)")
        arts = _extract_chunk(chunk, deviz_cod, deviz_den, openai_client, deployment)
        # Nu filtram coduri numerice pure — articolele breviar pot aparea fara $ in oferte
        arts = [a for a in arts if a.get("cod", "").strip()]
        return (deviz_cod, deviz_den, idx), arts

    done_chunks = len(chunk_results)  # chunks deja procesate din checkpoint

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_process_item, item): item for item in work_items_todo}
        for future in as_completed(futures):
            key, arts = future.result()
            chunk_results[key] = arts
            done_chunks += 1
            # Raporteaza progres + checkpoint din 10 in 10 chunks (sau la final)
            if done_chunks % 10 == 0 or done_chunks == total_chunks:
                if progress_callback:
                    try:
                        progress_callback(done_chunks, total_chunks)
                    except Exception as pe:
                        logger.debug(f"[F3] Progress callback error (ignored): {pe}")
                if checkpoint_callback:
                    # Converteste la string keys pentru JSON
                    cp_str = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in chunk_results.items() if v}
                    try:
                        checkpoint_callback(cp_str)
                    except Exception as ce:
                        logger.debug(f"[F3] Checkpoint callback error (ignored): {ce}")

    # Reconstituie ordinea originala per sectiune
    all_articles = []
    for deviz_cod, deviz_den, section_text in sections:
        chunks = _chunk_text(section_text)
        deviz_articles = []
        for idx in range(1, len(chunks) + 1):
            deviz_articles.extend(chunk_results.get((deviz_cod, deviz_den, idx), []))

        logger.info(f"[F3] {deviz_cod} {deviz_den}: {len(deviz_articles)} articole extrase")

        # Normalize deviz code (226U38 → 226038) for consistency across files
        normalized_deviz_cod = _normalize_deviz_cod(deviz_cod)
        for art in deviz_articles:
            art["deviz"] = normalized_deviz_cod
            art["deviz_denumire"] = deviz_den
            art["is_component"] = False

        # Adauga componentele din >>> componenta (pentru referinta cu $breviar)
        components = _extract_components_from_section(section_text, deviz_cod, deviz_den)
        # Evita duplicate: nu adauga componente cu cod deja extras de LLM
        existing_cods = {a.get("cod", "").upper() for a in deviz_articles}
        components = [c for c in components if c["cod"] not in existing_cods]

        all_articles.extend(deviz_articles)
        all_articles.extend(components)

    logger.info(f"[F3] Total articole extrase: {len(all_articles)}")
    return all_articles


def extract_articles_from_text_v2(full_text: str) -> List[Dict]:
    """
    Extrage articole F3 folosind RegexStateParser (fara LLM).

    Înlocuiește extract_articles_from_text() în ArticleExtractor v3.0.
    Funcția veche rămâne intactă pentru rollback.

    Returns:
        Lista completă de articole + componente din toate secțiunile deviz.
    """
    from shared.f3_regex_parser import extract_articles_regex

    # PRE-FILTRU F3: procesam DOAR textul de la primul "Formular[ul] F3" incolo.
    # Referinta: F1+F2 (centralizatoare) ocupa ~491 linii inainte de F3.
    # Oferta_1: cover+F4+F5 ocupa ~7221 linii inainte de F3.
    # ATENTIE: in oferta_1 markerul de sectiune "Stadiul fizic:" apare cu 4 linii
    # inainte de "Formular F3" — trebuie sa includem acele linii in textul taiat.
    # Variante cunoscute de header F3:
    # - "Formular F3" / "Formularul F3" (referinta, oferta_1)
    # - "F3 - LISTA cu cantitati de lucrari..." (oferta_2, format ISDP)
    _F3_HEADER_RE = re.compile(
        r'Formular(?:ul)?\s+F3'
        r'|F3\s*[-–]\s*LISTA\s+cu\s+cantitati',
        re.IGNORECASE
    )
    _SECTION_START_RE = re.compile(
        r'Deviz\s+oferta|STADIU[L]?\s+FIZIC\s*:|Categoria\s+de\s+lucrari',
        re.IGNORECASE
    )
    m = _F3_HEADER_RE.search(full_text)
    if m:
        cut_pos = m.start()
        pre_text = full_text[:cut_pos]
        pre_lines = pre_text.splitlines()
        lookback = min(20, len(pre_lines))
        for i in range(len(pre_lines) - 1, len(pre_lines) - lookback - 1, -1):
            if _SECTION_START_RE.search(pre_lines[i]):
                # Include this section marker line and everything after it
                cut_pos = len('\n'.join(pre_lines[:i]))
                if cut_pos > 0:
                    cut_pos += 1  # skip the newline itself
                break
        full_text = full_text[cut_pos:]
        logger.info(f"[F3v2] Pre-filtru F3: textul taiat la poz {cut_pos} "
                    f"({len(full_text)} chars ramasi)")
    else:
        logger.warning("[F3v2] Niciun marker 'Formular F3' — procesez tot documentul")

    sections = _split_into_deviz_sections(full_text)
    if not sections:
        # Fallback: tot documentul = o singură secțiune
        sections = [('DOC', 'Document', full_text)]
        logger.warning("[F3v2] Nicio secțiune deviz detectată — procesez tot documentul ca o secțiune")

    all_articles: List[Dict] = []
    for deviz_cod, deviz_den, section_text in sections:
        lines = section_text.splitlines()
        articole = extract_articles_regex(lines, deviz_cod, deviz_den)
        componente = _extract_components_from_section(section_text, deviz_cod, deviz_den)
        # No dedup needed: regex parser ignores '>>>' lines, so components and main
        # articles occupy distinct OCR positions and cannot overlap.
        all_articles.extend(articole)
        all_articles.extend(componente)
        logger.info(f"[F3v2] {deviz_cod}: {len(articole)} articole + {len(componente)} componente")

    logger.info(f"[F3v2] Total: {len(all_articles)} articole extrase (regex, fara LLM)")
    return all_articles


def extract_articles_v3(page_classifications: list) -> list:
    """
    Extrage articole F3 din lista de PageClassification produsă de f3_page_classifier.

    Grupează paginile pe deviz ÎNAINTE de extragere, pentru a menține last_nr_crt corect
    pe parcursul tuturor paginilor aceluiași deviz.

    Args:
        page_classifications: output din f3_page_classifier.classify_pages()
            Fiecare element: {is_f3, deviz_cod, deviz_den, lines, header_only, page_number}

    Returns:
        Lista completă de articole + componente din toate paginile F3.
    """
    from shared.f3_regex_parser import extract_articles_regex
    from collections import defaultdict

    all_articles: list = []
    seen: dict = {}  # (cod, deviz_cod) → index în all_articles, pentru deduplicare

    # Inherit missing deviz_cod from previous F3 pages (continuation pages)
    # When a page is marked is_f3=True but has blank deviz_cod, inherit from last F3 page
    last_deviz_cod = ""
    last_deviz_den = ""
    for pc in page_classifications:
        if not pc.get("is_f3"):
            continue
        if pc.get("header_only"):
            continue

        deviz_cod = pc.get("deviz_cod", "")
        if deviz_cod:
            # This page has explicit deviz, update last_deviz
            deviz_cod = _normalize_deviz_cod(deviz_cod)
            last_deviz_cod = deviz_cod
            last_deviz_den = pc.get("deviz_den", "")
        elif last_deviz_cod and not deviz_cod:
            # This page has blank deviz but is F3 — inherit from previous
            pc["deviz_cod"] = last_deviz_cod
            if not pc.get("deviz_den"):
                pc["deviz_den"] = last_deviz_den

    # Grupează paginile F3 pe deviz pentru a menține last_nr_crt corect
    pages_by_deviz = defaultdict(list)
    for pc in page_classifications:
        if not pc.get("is_f3"):
            continue
        if pc.get("header_only"):
            continue  # pagini cover eDevize — nu conțin articole

        deviz_cod = pc.get("deviz_cod", "")
        deviz_cod = _normalize_deviz_cod(deviz_cod)
        if deviz_cod:
            pages_by_deviz[deviz_cod].append(pc)

    # Procesează fiecare deviz cu TOATE paginile sale împreună
    for deviz_cod, pages_in_deviz in pages_by_deviz.items():
        # Combină liniile din toate paginile aceluiași deviz
        all_lines = []
        deviz_den = ""
        for pc in pages_in_deviz:
            lines = pc.get("lines", [])
            if lines:
                all_lines.extend(lines)
            if not deviz_den:
                deviz_den = pc.get("deviz_den", "")

        if not all_lines:
            continue

        # Apelează parser o singură dată pe TOATE paginile devizului
        # Aceasta menține last_nr_crt corect pe tot devizul

        section_articles = extract_articles_regex(all_lines, deviz_cod, deviz_den)

        for art in section_articles:
            art["deviz"] = deviz_cod
            art["deviz_denumire"] = deviz_den
            art["is_component"] = False
            art["denumire"] = _normalize_denom(art.get("denumire", ""))

        # Extrage componente din fiecare pagină (nu le combinăm)
        for pc in pages_in_deviz:
            section_text = "\n".join(pc.get("lines", []))
            components = _extract_components_from_section(section_text, deviz_cod, deviz_den)
            section_articles.extend(components)

        # Deduplicare
        for art in section_articles:
            key = (art.get("cod", "").upper(), art.get("deviz", deviz_cod), art.get("cantitate", 0))
            if key not in seen:
                seen[key] = len(all_articles)
                all_articles.append(art)

        logger.info(f"[F3v3] {deviz_cod}: {len(section_articles)} articole extrase (grouped pages)")

    logger.info(f"[F3v3] Total: {len(all_articles)} articole extrase (deviz-grouped, fara LLM)")
    return all_articles
