# func-analiza-oferte/shared/f3_regex_parser.py
"""
RegexStateParser — extrage articole F3 din lista de linii OCR.

Intrare: linii text (output din DI JSON, una per element)
         deviz_cod, deviz_denumire — identificatorii secțiunii curente
Ieșire:  lista de articole (același format ca LLM extractor v2.x)
"""
import re
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

# ── Regex-uri ────────────────────────────────────────────────────────────────

# Cod normativ: TSC35A22, SA14B#, RPCE26C1, CA02A1 etc. (cu – şi descriere)
# Sufixe acceptate: # > * @ % și [1] [2] ]1 cu optional - trailing
_COD_SUFFIX = r'(?:[#>*@%]|\[\d*\]|[\[\]]\d*)?[-]?'
COD_NORM_RE = re.compile(
    r'^([A-Z]{2,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?' + _COD_SUFFIX + r')\s*[-–]\s*(.+)',
    re.IGNORECASE
)
# Cod normativ extins: TRI1AA01C2, TRI1AA08F1 (prefix 2-5 litere + 1-2 cifre + 1-3 litere + 2-4 cifre + opt suffix)
COD_NORM_EXTENDED_RE = re.compile(
    r'^([A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}[A-Z]?\d?' + _COD_SUFFIX + r')\s*[-–]\s*(.+)',
    re.IGNORECASE
)
# Cod normativ cu prefix single-letter: W1C01A1, H1V06H, W1MM05A
COD_NORM_SINGLE_RE = re.compile(
    r'^([A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}' + _COD_SUFFIX + r')\s*[-–]\s*(.+)',
    re.IGNORECASE
)
# Cod breviar cu $ prefix
COD_BREVIAR_RE = re.compile(r'^(\$[A-Z0-9]{4,})\s*[-–]\s*(.+)', re.IGNORECASE)
# Cod numeric pur 4-8 cifre cu – şi descriere; acceptă @ suffix
# 4 cifre: utilaje breviar (1303, 2506); 8 cifre: materiale extinse (22000561)
COD_NUMERIC_RE = re.compile(r'^(\d{4,8}[@]?)\s*[-–]\s*(.+)')
# Cod normativ SINGUR pe linie, cu optional tip UM (ASIM etc.) pe aceeași linie
# Ex: "TCB40A1" sau "TCB40A1 ASIM" (format referinţă deviz)
COD_NORM_STANDALONE_RE = re.compile(
    r'^([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?' + _COD_SUFFIX + r')(?:\s+([A-Z]{1,8}\.?))?\s*$',
    re.IGNORECASE
)
# Cod numeric cu spaţiu + descriere + optional |UM (format Breviar materiale referinţă)
# Ex: "6701362 @COT RACORD WC ORIENTABIL |BUC."
COD_NUMERIC_PIPE_RE = re.compile(
    r'^(\d{4,8})\s+(@?[^\|]{3,}?)(?:\s*\|([A-Z]{1,6}\.?))?\s*$'
)
# NR_CRT + COD NORMATIV pe aceeaşi linie, cu optional tokeni UM (ASIM, BUC. etc.)
# Ex: "024 CK26A#" sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC."
NR_ALPHA_INLINE_RE = re.compile(
    r'^(\d{1,3})\s+([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,2})\s*$',
    re.IGNORECASE
)
# NR_CRT + COD NUMERIC pe aceeaşi linie (format referinţă deviz: "024 2200012")
NR_NUMERIC_INLINE_RE = re.compile(
    r'^(\d{1,3})\s+(\d{4,8})\s*$'
)
# NR_CRT: integer 1-999 singur pe linie
NR_CRT_RE = re.compile(r'^(\d{1,3})$')
# UM: token scurt alfabetic
UM_RE = re.compile(r'^([A-Z]{1,6})\.?$', re.IGNORECASE)
# Cantitate cu zecimale — include format cu separator mii: 2,000.000 sau 1.234,56
CANT_DECIMAL_RE = re.compile(r'^\d{1,10}(?:[.,]\d{3})*[,.]\d{1,6}$')
# Cantitate întreagă (folosit doar când UM deja setat)
CANT_INT_RE = re.compile(r'^\d{1,6}$')
# Preț/valoare numerică (poate conține separator mii)
PRET_RE = re.compile(r'^[\d.,]+$')
# Linii de ignorat (sumar, total, etc.)
SKIP_RE = re.compile(
    r'(Cheltuieli\s+directe|Total\s+cheltuieli|Cheltuieli\s+indirecte|'
    r'Profit|TOTAL\s+GENERAL|TVA|contributie\s+asiguratorie)',
    re.IGNORECASE
)

UM_KNOWN = {
    # Volum / masa / lungime
    'BUC', 'MC', 'ML', 'MP', 'MPC', 'KG', 'T', 'TO', 'TON', 'TONA', 'G', 'MG',
    'L', 'M', 'H', 'CM', 'DM', 'KM',
    # Electric
    'KW', 'KWH', 'KVA', 'W',
    # Timp
    'ORA', 'ORE', 'ZI', 'ZILE', 'SCHIMB', 'LUNA', 'LUNI', 'SAPT',
    # Misc constructii
    'SET', 'PERECHE', 'ROLA', 'PAG', 'ART', 'ROT',
    # Financiar
    'LEI', 'MII',
}
# NOTA: 'MM' este intentionat ABSENT din UM_KNOWN.
# '8 MM' in OCR este continuare de denumire (ex: 'OB 37 D = 6 - 8 MM'),
# nu o coloana UM. Milimetrii apar extrem de rar ca UM in devize F3.
# Tokeni care par UM (scurți, alfabetici) dar sunt de fapt designatori de tip normativ (nu UM reale)
# ASIM = asimilat, TSCH = tip schemă — apar în devizele referință F3 ÎNAINTEA UM real
UM_SKIP = {'ASIM', 'TSCH', 'SCH', 'UM', 'NR', 'CRT', 'TOTAL', 'PU', 'VAL'}

# Stări
_IDLE = 'IDLE'
_WAITING = 'WAITING_ARTICLE'
_READING = 'READING_ARTICLE'


def _is_price_line(line):
    """
    Check if a line contains price information.
    Price lines typically contain numbers with 2 decimal places or currency symbols.
    """
    # Pattern: optional whitespace, numbers, decimal point, 2 digits (price format)
    # or common price indicators
    price_pattern = r'^\s*\d+[.,]\d{2}\s*$|RON|EUR|USD|lei|\$|€'
    return bool(re.search(price_pattern, line.strip()))


def _parse_number(s: str) -> float:
    """Convertește string număr (cu . sau , ca separator) la float."""
    s = s.strip().replace(' ', '')
    # Dacă are atât . cât și , → separatorul mii e primul
    if '.' in s and ',' in s:
        if s.index('.') < s.index(','):
            s = s.replace('.', '').replace(',', '.')
        else:
            s = s.replace(',', '')
    else:
        s = s.replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _is_valid_um(token: str) -> bool:
    """
    Returnează True dacă token-ul este o unitate de măsură validă.

    Reguli (în ordine):
    1. Normalizează: strip puncte și spații ("M.C." → "MC", "MP ." → "MP")
    2. Respinge dacă token-ul conține cifre — liniile cu cifre+litere sunt
       continuare de denumire (ex: '8 MM', '100 ML batuta') sau prețuri
    3. Acceptă NUMAI dacă token-ul e în UM_KNOWN (whitelist explicit)
       — elimină catch-all-ul anterior (len≤4, isalpha) care accepta
         'tare', 'mata', 'toli', 'cod' etc. din denumiri multi-linie
    """
    t = re.sub(r'[\.\s]', '', token.strip()).upper()
    if not t:
        return False
    if t in UM_SKIP:
        return False
    # Regula anti-digit: o linie cu cifre nu este o coloana UM
    if re.search(r'\d', token):
        return False
    return t in UM_KNOWN


def _make_article(cod: str, denumire: str, um: str, cantitate: float,
                  preturi: list, deviz_cod: str, deviz_den: str) -> Dict:
    """Construiește dict articol în formatul standard."""
    fields = ['pret_material', 'val_material', 'pret_manopera', 'val_manopera',
              'pret_utilaj', 'val_utilaj', 'pret_transport', 'val_transport']
    art = {
        'cod': cod,
        'denumire': denumire.strip(),
        'um': um.lower(),
        'cantitate': cantitate,
        'deviz': deviz_cod,
        'deviz_denumire': deviz_den,
        'is_component': False,
    }
    for i, field in enumerate(fields):
        art[field] = preturi[i] if i < len(preturi) else 0.0
    return art


def extract_articles_regex(lines: List[str], deviz_cod: str,
                           deviz_den: str) -> List[Dict]:
    """
    Extrage articole dintr-o listă de linii OCR pentru o secțiune deviz.

    Args:
        lines: linii text brut (fiecare element = o linie din OCR)
        deviz_cod: codul secțiunii deviz (ex: 'OB1')
        deviz_den: denumirea secțiunii (ex: 'LUCRARI TERASAMENTE')

    Returns:
        Lista de articole în formatul standard (compatibil AgentComparator).
    """
    articole: List[Dict] = []
    state = _IDLE

    # Articolul în curs de construire
    cod = ''
    denumire_parts: List[str] = []
    um = ''
    cantitate = 0.0
    preturi: List[float] = []

    last_nr_crt = 0
    waiting_lines = 0   # contor linii în WAITING_ARTICLE

    def _finalize():
        nonlocal cod, denumire_parts, um, cantitate, preturi
        if cod:
            # Coduri numerice pure → adaugă prefix $
            if re.match(r'^\d+$', cod):
                cod = '$' + cod
            den_joined = ' '.join(denumire_parts)
            # Skip coduri cu / (numere proiect: 424/2018, 424-rev/2024)
            if '/' in cod:
                logger.debug(f"[PARSER] Skip cod cu slash: {cod}")
            # Skip token UM capturat gresit ca cod (BUC, MC, MP etc.)
            elif cod.upper() in UM_KNOWN:
                logger.debug(f"[PARSER] Skip UM capturat ca cod: {cod}")
            # Skip coduri deviz-sumar: numeric $226XXX cu denumire scurta (pag, deviz antet)
            elif re.match(r'^\$\d{4,7}$', cod) and den_joined.lower().startswith('pag'):
                logger.debug(f"[PARSER] Skip deviz-sumar: {cod}")
            else:
                art = _make_article(cod, den_joined, um, cantitate,
                                    preturi, deviz_cod, deviz_den)
                articole.append(art)
                logger.debug(f"[PARSER] Articol finalizat: {cod} ({um}, {cantitate})")
        cod = ''
        denumire_parts = []
        um = ''
        cantitate = 0.0
        preturi = []

    def _is_nr_crt(line: str, current_state: str, price_count: int,
                   current_cantitate: float = 0.0) -> bool:
        """
        Un integer 1-999 este NR_CRT doar dacă:
        1. E în intervalul 1-999
        2. State = IDLE
           SAU (READING_ARTICLE și price_count >= 4)
           SAU (READING_ARTICLE și price_count == 0 și cantitate > 0)
        3. Valoarea >= last_nr_crt sau <= 5 (reset la secțiune nouă)
        """
        m = NR_CRT_RE.match(line.strip())
        if not m:
            return False
        val = int(m.group(1))
        if not (1 <= val <= 999):
            return False
        if current_state == _IDLE:
            return val >= last_nr_crt or val <= 5
        if current_state == _READING:
            if price_count >= 4:
                return val >= last_nr_crt or val <= 5
            # Ofertele cu articole $-cod au doar 2 prețuri (pret_unitar + total)
            # înainte de NR_CRT următor — acceptăm NR_CRT dacă cantitate e setată
            if current_cantitate > 0.0 and price_count >= 2:
                return val >= last_nr_crt or val <= 5
            if price_count == 0 and current_cantitate > 0.0:
                return val >= last_nr_crt or val <= 5
        return False

    def _try_parse_cod(line: str):
        """Încearcă să parseze linia ca cod articol.
        Returnează (cod, den, um_hint) sau (None, None, '').
        um_hint e non-empty doar pentru formatul 'COD DESCRIERE |UM'.
        """
        s = line.strip()
        # Normalizeaza spatiu inainte de sufix bracket: "IA22C1 [1]" → "IA22C1[1]"
        s = re.sub(r'(?<=[A-Z0-9])\s+(\[\d)', r'\1', s, flags=re.IGNORECASE)
        # Formate cu separator –: breviar $COD, normativ (2+ litere), single-letter, numeric
        for pattern in (COD_BREVIAR_RE, COD_NORM_EXTENDED_RE, COD_NORM_RE, COD_NORM_SINGLE_RE, COD_NUMERIC_RE):
            m = pattern.match(s)
            if m:
                cod_raw = m.group(1).strip().upper()
                # Strip trailing artifacts: -, >, *, @, %
                cod_raw = re.sub(r'[-@%>*]+$', '', cod_raw)
                # Strip bracket suffix complet: [1], [1], [1 etc.
                cod_raw = re.sub(r'\s*\[\d*\]?\s*$', '', cod_raw)
                return cod_raw, m.group(2).strip(), ''
        # Cod normativ singur pe linie, cu optional tip UM (ASIM etc.) pe aceeași linie
        m = COD_NORM_STANDALONE_RE.match(s)
        if m:
            cod_raw = m.group(1).strip().upper()
            cod_raw = re.sub(r'[-@%>*]+$', '', cod_raw)
            cod_raw = re.sub(r'\s*\[\d*\]?\s*$', '', cod_raw)
            um_hint_raw = m.group(2).rstrip('.').upper() if m.group(2) else ''
            # Ignora designatori normativi (ASIM, TSCH etc.) — nu sunt UM reale
            um_hint = um_hint_raw if um_hint_raw and um_hint_raw not in UM_SKIP else ''
            return cod_raw, '', um_hint
        # Cod numeric cu spaţiu + descriere + optional |UM (Breviar materiale)
        m = COD_NUMERIC_PIPE_RE.match(s)
        if m:
            cod_raw = '$' + m.group(1)
            den = m.group(2).strip()
            um_hint = m.group(3).rstrip('.').upper() if m.group(3) else ''
            return cod_raw, den, um_hint
        return None, None, ''

    for raw_line in lines:
        line = raw_line.strip()
        if not line or SKIP_RE.search(line):
            continue

        price_count = len(preturi)

        # ── IDLE ─────────────────────────────────────────────────────────────
        if state == _IDLE:
            # Format referinţă deviz: "024 CK26A#" sau "024 2200012" (NR+COD pe linie)
            # sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC." (cu tokeni UM pe aceeași linie)
            m_ai = NR_ALPHA_INLINE_RE.match(line)
            m_ni = NR_NUMERIC_INLINE_RE.match(line)
            if m_ai or m_ni:
                m = m_ai or m_ni
                last_nr_crt = int(m.group(1))
                cod = ('$' + m.group(2)) if m_ni else re.sub(r'[-@%>*]+$|\s*\[\d*\]?\s*$', '', m.group(2).upper())
                denumire_parts = []
                # Extrage primul UM valid din tokenii rămași pe linie (grup 3 din NR_ALPHA_INLINE_RE)
                um = ''
                if m_ai and m_ai.lastindex >= 3 and m_ai.group(3):
                    for tok in m_ai.group(3).strip().split():
                        tok_clean = tok.rstrip('.')
                        if _is_valid_um(tok_clean):
                            um = tok_clean.upper()
                            break
                cantitate = 0.0
                preturi = []
                state = _READING
                waiting_lines = 0
            elif _is_nr_crt(line, _IDLE, price_count):
                last_nr_crt = int(NR_CRT_RE.match(line).group(1))
                state = _WAITING
                waiting_lines = 0
            else:
                # Format cod direct fără NR_CRT (ex: "3270513 - BANDA AVERTIZARE...")
                # Încearcă să parseze ca cod articol direct
                parsed_cod, parsed_den, parsed_um_hint = _try_parse_cod(line)
                if parsed_cod:
                    cod = parsed_cod
                    denumire_parts = [parsed_den] if parsed_den else []
                    um = parsed_um_hint
                    cantitate = 0.0
                    preturi = []
                    state = _READING
                    waiting_lines = 0
                # altfel ignora orice linie în IDLE

        # ── WAITING_ARTICLE ──────────────────────────────────────────────────
        elif state == _WAITING:
            parsed_cod, parsed_den, parsed_um_hint = _try_parse_cod(line)
            if parsed_cod:
                cod = parsed_cod
                denumire_parts = [parsed_den] if parsed_den else []
                um = parsed_um_hint  # setat direct dacă vine din |UM inline
                cantitate = 0.0
                preturi = []
                state = _READING
                waiting_lines = 0
            else:
                # Verifica si format NR_INLINE (038 2222219) in WAITING — acelasi handling ca IDLE
                m_ai = NR_ALPHA_INLINE_RE.match(line)
                m_ni = NR_NUMERIC_INLINE_RE.match(line)
                if m_ai or m_ni:
                    m = m_ai or m_ni
                    last_nr_crt = int(m.group(1))
                    cod = ('$' + m.group(2)) if m_ni else re.sub(r'[-@%>*]+$|\s*\[\d*\]?\s*$', '', m.group(2).upper())
                    denumire_parts = []
                    um = ''
                    if m_ai and m_ai.lastindex >= 3 and m_ai.group(3):
                        for tok in m_ai.group(3).strip().split():
                            tok_clean = tok.rstrip('.')
                            if _is_valid_um(tok_clean):
                                um = tok_clean.upper()
                                break
                    cantitate = 0.0
                    preturi = []
                    state = _READING
                    waiting_lines = 0
                elif _is_nr_crt(line, _IDLE, 0):
                    # NR_CRT nou — actualizează și rămâne în WAITING
                    last_nr_crt = int(NR_CRT_RE.match(line).group(1))
                    waiting_lines = 0
                else:
                    waiting_lines += 1
                    if waiting_lines >= 3:
                        # Nu era articol — numărul era altceva (pagină, preț etc.)
                        state = _IDLE

        # ── READING_ARTICLE ──────────────────────────────────────────────────
        elif state == _READING:
            # Format referinţă deviz: "024 CK26A#" sau "024 2200012" → finalizează + articol nou
            # sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC." (cu tokeni UM pe aceeași linie)
            m_ai = NR_ALPHA_INLINE_RE.match(line)
            m_ni = NR_NUMERIC_INLINE_RE.match(line)
            if m_ai or m_ni:
                _finalize()
                m = m_ai or m_ni
                last_nr_crt = int(m.group(1))
                cod = ('$' + m.group(2)) if m_ni else re.sub(r'[-@%>*]+$|\s*\[\d*\]?\s*$', '', m.group(2).upper())
                denumire_parts = []
                # Extrage primul UM valid din tokenii rămași pe linie (grup 3 din NR_ALPHA_INLINE_RE)
                um = ''
                if m_ai and m_ai.lastindex >= 3 and m_ai.group(3):
                    for tok in m_ai.group(3).strip().split():
                        tok_clean = tok.rstrip('.')
                        if _is_valid_um(tok_clean):
                            um = tok_clean.upper()
                            break
                cantitate = 0.0
                preturi = []
                state = _READING
                waiting_lines = 0
                continue

            # NR_CRT nou (bare) → finalizează articolul curent
            if _is_nr_crt(line, _READING, price_count, cantitate):
                _finalize()
                last_nr_crt = int(NR_CRT_RE.match(line).group(1))
                state = _WAITING
                waiting_lines = 0
                continue

            # Cod nou cu separator – fără NR_CRT explicit (ex: "30172 - Transport")
            # Finalizează articolul curent și pornește unul nou
            parsed_cod, parsed_den, parsed_um_hint = _try_parse_cod(line)
            if parsed_cod and (COD_NUMERIC_RE.match(line) or COD_NORM_RE.match(line)
                               or COD_NORM_EXTENDED_RE.match(line) or COD_BREVIAR_RE.match(line)):
                _finalize()
                cod = parsed_cod
                denumire_parts = [parsed_den] if parsed_den else []
                um = parsed_um_hint
                cantitate = 0.0
                preturi = []
                state = _READING
                continue

            # UM (doar dacă nu e setat) — normalizează M.C. → MC, MP . → MP
            if not um and _is_valid_um(line):
                um = re.sub(r'[\.\s]', '', line.strip()).upper()
                continue

            # Format "100 MC." — indicator normativ pe linie separată
            # Extrage DOAR um-ul; cantitatea reală urmează pe linia următoare
            if um == '':
                m_um_norm = re.match(r'^\d+\s+([A-Z]{1,6})\.?\s*$', line, re.IGNORECASE)
                if m_um_norm:
                    um_candidate = m_um_norm.group(1).upper()
                    if _is_valid_um(um_candidate):
                        um = um_candidate
                        continue

            # Format pipe: "M.C. | 18.144 | BETON MARFA CLASA C8/10" (referinta breviar materiale)
            if um == '' and cantitate == 0.0:
                m_pipe = re.match(
                    r'^([A-Z][A-Z.]{0,5})\s*\|\s*(\d+[.,]\d+|\d+)\s*\|\s*(.+)$',
                    line, re.IGNORECASE
                )
                if m_pipe:
                    um_candidate = m_pipe.group(1).upper().replace('.', '').rstrip()
                    if _is_valid_um(um_candidate):
                        um = um_candidate
                        cantitate = _parse_number(m_pipe.group(2))
                        den = m_pipe.group(3).strip()
                        if den:
                            denumire_parts.append(den)
                        continue

            # Cantitate decimală
            if cantitate == 0.0 and CANT_DECIMAL_RE.match(line):
                cantitate = _parse_number(line)
                continue

            # Cantitate întreagă (doar dacă UM setat și cantitate nu setat)
            if cantitate == 0.0 and um and CANT_INT_RE.match(line):
                val = int(line)
                if not _is_nr_crt(line, _READING, price_count, cantitate):
                    cantitate = float(val)
                    continue

            # Preț/valoare numerică
            if PRET_RE.match(line) and not _is_nr_crt(line, _READING, price_count, cantitate):
                preturi.append(_parse_number(line))
                continue

            # Ignoră linii >>> componenta (procesate separat de _extract_components_from_section)
            if line.startswith('>>>'):
                continue

            # Orice altă linie text → continuare denumire (multi-line)
            # Continue appending text to denomination until UM is found
            # Even after UM detection, append non-price text lines to denomination
            if um == '':
                # Before UM is found, collect all text
                denumire_parts.append(line)
            elif line and not _is_price_line(line):
                # After UM found, still append non-price text lines to denomination
                # This handles cases where denomination spans multiple lines
                denumire_parts.append(line)

    # Finalizează ultimul articol
    if state == _READING:
        _finalize()

    logger.info(f"[PARSER] {deviz_cod}: {len(articole)} articole extrase (regex)")
    return articole
