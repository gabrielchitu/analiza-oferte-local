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
# Sufixe acceptate: # > * @ % ^ + și [1] [2] ]1 cu optional - trailing
# Include si sufixe designator normativ: ASIM, TSCH (TCB40B1ASIM, CG08A#ASIM)
# Permite combinatii: '#' urmat opțional de ASIM/TSCH (ex: CG08A#ASIM)
_COD_SUFFIX = r'(?:[#>*@%^+]|\[\d*\]|[\[\]]\d*)?(?:ASIM|TSCH)?[-]?'
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
# Cod cu prefix single-letter + multi-digit: C003A01, C123B45
# Matches: Letter + 2-3 digits + Letter + 2 digits (OCR variants of CO03A01 → C003A01)
COD_SINGLE_MULTIDIGIT_RE = re.compile(
    r'^([A-Z]\d{2,3}[A-Z]\d{2}' + _COD_SUFFIX + r')\s*[-–]\s*(.+)',
    re.IGNORECASE
)
# Cod breviar cu $ prefix
COD_BREVIAR_RE = re.compile(r'^(\$[A-Z0-9]{4,})\s*[-–]\s*(.+)', re.IGNORECASE)
# Cod numeric pur 4-8 cifre cu – şi descriere; acceptă @ suffix şi bracket suffix [1], [2], etc.
# 4 cifre: utilaje breviar (1303, 2506); 8 cifre: materiale extinse (22000561)
# Exemple: "6715504 - Piesa..." sau "6715504[1] - Piesa..." sau "6715504@ - Piesa..."
COD_NUMERIC_RE = re.compile(r'^(\d{4,9}(?:[@]|\[\d+\])?)\s*[-–]\s*(.+)')
# Cod normativ SINGUR pe linie, cu opțional tokeni sufixe (ASIM, BUC. etc.) — max 3
# Ex: "TCB40A1", "TCB40A1 ASIM", "IA37E1 ASIM BUC." (format referinţă deviz)
COD_NORM_STANDALONE_RE = re.compile(
    r'^([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,3})\s*$',
    re.IGNORECASE
)
# Cod extended SINGUR pe linie: TRI1AA08F1, TRI1AA01C2 (format: 2-5L + 1-2D + 1-3L + 2-4D + opt)
COD_NORM_EXTENDED_STANDALONE_RE = re.compile(
    r'^([A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}[A-Z]?\d?' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,3})\s*$',
    re.IGNORECASE
)
# Cod single-letter complex SINGUR pe linie: W1C01A1, H1V06H (format: L + D + 1-3L + 2-4D + opt)
COD_NORM_SINGLE_STANDALONE_RE = re.compile(
    r'^([A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,3})\s*$',
    re.IGNORECASE
)
# Cod single-letter multi-digit SINGUR pe linie: C003A01, C123B45 (format: L + 2-3D + L + 2D + opt)
# Handles OCR errors where O→0: CO03A01 → C003A01
COD_SINGLE_MULTIDIGIT_STANDALONE_RE = re.compile(
    r'^([A-Z]\d{2,3}[A-Z]\d{2}' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,3})\s*$',
    re.IGNORECASE
)
# Cod numeric cu spaţiu + descriere + optional |UM (format Breviar materiale referinţă)
# Ex: "6701362 @COT RACORD WC ORIENTABIL |BUC." sau "6715504[1] PIESA DE CURATIRE |BUC."
# Acceptă @ prefix în descriere şi [N] bracket suffix în cod
COD_NUMERIC_PIPE_RE = re.compile(
    r'^(\d{4,9}(?:\[\d+\])?)\s+(@?[^\|]{3,}?)(?:\s*\|([A-Z]{1,6}\.?))?\s*$'
)
# NR_CRT + COD NORMATIV pe aceeaşi linie, cu optional tokeni UM (ASIM, BUC. etc.)
# Ex: "024 CK26A#" sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC."
NR_ALPHA_INLINE_RE = re.compile(
    r'^(\d{1,3})[\s|]+([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,2})\s*$',
    re.IGNORECASE
)
# NR_CRT + COD NUMERIC pe aceeaşi linie (format referinţă deviz: "024 2200012" or "024|2200012")
NR_NUMERIC_INLINE_RE = re.compile(
    r'^(\d{1,3})[\s|]+(\d{4,9})\s*$'
)
# NR_CRT + COD BREVIAR CU $ pe aceeaşi linie (format articol composite ISDP: "010 $16508" or "010|$16508")
NR_BREVIAR_INLINE_RE = re.compile(
    r'^(\d{1,3})[\s|]+(\$\d{4,9}[@]?)\s*$'
)
# NR_CRT + COD single-letter pe aceeaşi linie (ex: "017 W2F05C01" sau "017|H1V06H BUC.")
NR_SINGLE_INLINE_RE = re.compile(
    r'^(\d{1,3})[\s|]+([A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}' + _COD_SUFFIX + r')((?:\s+[A-Z]{1,8}\.?){0,2})\s*$',
    re.IGNORECASE
)
# NR_CRT: integer 1-999 singur pe linie
NR_CRT_RE = re.compile(r'^(\d{1,3})$')
# NR_SUBITEM: decimal sub-article marker (ex: "34.1", "23.1" in breviar tables)
NR_SUBITEM_RE = re.compile(r'^(\d{1,3}\.\d{1})$')
# NR_LINKED: articol legat ISDP — "N.L" sau "N.M.L" singur pe linie (ex: "6.L", "11.1.L", "11.2.L")
NR_LINKED_RE = re.compile(r'^(\d{1,3})(?:\.\d+)?\.L\s*$', re.IGNORECASE)
# BARE_L: standalone "L" marker pe linie (articole legate ISDP in format multi-line)
BARE_L_RE = re.compile(r'^L\s*$', re.IGNORECASE)
# DOT_L: ".L" marker pe linie (varianta cu punct prefix - articole legate ISDP in format multi-line)
DOT_L_RE = re.compile(r'^\.L\s*$', re.IGNORECASE)
# COD_NUMERIC_BARE: cod numeric pur 5-8 cifre singur pe linie (articole legate ISDP)
COD_NUMERIC_BARE_RE = re.compile(r'^(\d{4,9})\s*$')  # 4+ cifre: NR_CRT e max 3 cifre, deci 4 = breviar
# UM: token scurt alfabetic
UM_RE = re.compile(r'^([A-Z]{1,6})\.?$', re.IGNORECASE)
# Cantitate cu zecimale — include format cu separator mii și valori negative.
# Include si N.DDD (ex: 480.000 = 480.0) — format cu 3 zecimale zero frecvent in devize.
CANT_DECIMAL_RE = re.compile(r'^-?(?:\d{1,10}(?:[.,]\d{3})*[,.]\d{1,6}|\d{1,10}[.,]\d{1,3})$')
# Cantitate întreagă (folosit doar când UM deja setat)
CANT_INT_RE = re.compile(r'^-?\d{1,6}$')
# Preț/valoare numerică (poate conține separator mii)
PRET_RE = re.compile(r'^[\d.,]+$')
# Linii de ignorat (sumar, total, footer eDevize etc.)
# Footer-urile eDevize ('Deviz "X" - Formular F3', 'Formular generat', 'Pagina N din M')
# trebuie skipped in READING state ca sa nu contamineze denominatia articolului curent.
SKIP_RE = re.compile(
    r'(Cheltuieli\s+directe|Total\s+cheltuieli|Cheltuieli\s+indirecte|'
    r'Profit|TOTAL\s+GENERAL|TVA|contributie\s+asiguratorie|'
    r'Formular\s+generat\s+cu\s+programul|'
    r'Pagina\s+\d+\s+din\s+\d+|'
    r'Deviz\s+["\']?\d+(?:\.\d+)?["\']?\s*[-–]?\s*Formular\s+F3|'
    r'^\d+\s+pag|^pag\s|\bpag$|'
    r'Lista\s+cu\s+cantitati|'
    r'Categoria\s+de\s+lucrari|'
    r'Persoana\s+juridica|'
    r'Obiectul\s*:|'
    r'^Deviz\s+oferta|'
    r'^=\s*$|^NR\.\s+SIMBOL|'
    r'^CANTITATE$|^PU\s|^GR\.\s+|^SPOR\s|'
    r'^(MATERIALE|MANOPERA|UTILAJ|TRANSPORT|GREUTATE|TOTAL|ARTICOL)$|'
    r'^\d{4,8}$|'  # Pure numeric CPV/metadata codes (e.g., "0004", "45000000")
    r'Cheltuieli\s+(directe|indirecte)|Din\s+care:|'
    r'Valoare\s+aferenta|'
    r'PROIECTANT|ORIGEN\s+STUDIE|'
    r'SIGN\s+|S\.\s+C\.\s+|Artisan|-\s+proiect|424|'
    r'STE[\-\s]|TARGO|DAMBO|'
    r'\d{3}-?rev[/\s]+\d{4}|'  # Project version codes like "424-rev/2024" or "424 rev 2024"
    r'[A-Z\s]*S\.R\.L\.|[A-Z]{2,}\s+SRL|'  # Company names with SRL/S.R.L.
    r'(?:proiect|project)\s+(?:initial|inițial|integral|actualizat|updated)|'  # Project status phrases
    r'-\s+(?:proiect|project)|'  # "- proiect..." lines from watermarks
    r'(?:design|studio|solutions?)(?:\s+|\.)*s\.?r\.?l\.?)',  # Design/studio company names
    re.IGNORECASE
)
# NR_CRT + COD_NORM/EXTENDED/SINGLE/NUMERIC + separator + descriere pe aceeași linie
# Ex: "6 CA01J1 - TURNARE BETON", "12 CG08A#ASIM - Pardoseli", "10 3274584 - OTEL BETON"
# Supports both space and pipe separators: "6 CA01J1" or "6|CA01J1"
NR_COD_DESC_RE = re.compile(
    r'^(\d{1,3})[\s|]+'
    r'([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?'
    r'|[A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}[A-Z]?\d?'
    r'|[A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}'
    r'|\d{4,9}(?:[@]|\[\d+\])?)'
    r'(?:[#>*@%^+]|\[\d*\]|ASIM|TSCH){0,2}[-]?\s*[-–]\s*(.+)$',
    re.IGNORECASE
)
# NR_CRT directly concatenated with CODE (no separator): "3CF41B01* - Tencuiala..."
# Handles cases where OCR didn't preserve whitespace between NR_CRT and code
NR_COD_CONCAT_RE = re.compile(
    r'^(\d{1,3})'
    r'([A-Z]{1,5}\d{1,4}[A-Z]?\d{0,2}[A-Z]?'
    r'|[A-Z]{2,5}\d{1,2}[A-Z]{1,3}\d{2,4}[A-Z]?\d?'
    r'|[A-Z]\d[A-Z]{1,3}\d{2,4}[A-Z]?\d{0,2}'
    r'|\d{4,9})'
    r'([#>*@%^]?)\s*[-–]\s*(.+)$',
    re.IGNORECASE
)
# Etichete de sectiune pret in format eDevize — NU sunt denumire articol
_PRICE_LABEL_RE = re.compile(r'^(material|manopera|utilaj|transport)\s*:', re.IGNORECASE)

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


def _is_model_reference(line: str) -> bool:
    """
    Check if a line is a model/reference number (like 'ni522', 'MF100', etc.)
    that should be skipped — it's not a denomination, UM, or quantity.

    Pattern: 2-3 letters followed by 2-4 digits, no spaces.
    Examples: ni522, MF100, TX50, etc.
    """
    return bool(re.match(r'^[A-Z]{2,3}\d{2,4}$', line.strip(), re.IGNORECASE))


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
    3. Handle OCR corruption: specific known patterns (B?C → BUC, etc.)
    4. Acceptă NUMAI dacă token-ul e în UM_KNOWN (whitelist explicit)
       — elimină catch-all-ul anterior (len≤4, isalpha) care accepta
         'tare', 'mata', 'toli', 'cod' etc. din denumiri multi-linie
    5. Fallback: try ton→tona normalization if direct match fails
    """
    t = re.sub(r'[\.\s]', '', token.strip()).upper()
    if not t:
        return False
    if t in UM_SKIP:
        return False
    # Regula anti-digit: o linie cu cifre nu este o coloana UM
    if re.search(r'\d', token):
        return False

    if t in UM_KNOWN:
        return True

    # Only attempt fuzzy match if token contains non-letter OCR noise: ?, !, |, ~, ^
    # This avoids false matches like TOL→TON
    if any(c in t for c in '?!|~^'):
        t_clean = re.sub(r'[?!|~^]', '', t)
        if t_clean and t_clean in UM_KNOWN:
            return True

    # ton → tona normalization
    if t == 'TON' and 'TONA' in UM_KNOWN:
        return True

    return False


def _normalize_um_value(token: str) -> str:
    """Return the canonical UM value, handling OCR corruption and normalization."""
    t = re.sub(r'[\.\s]', '', token.strip()).upper()
    if not t:
        return ''

    if t in UM_KNOWN:
        return t

    # Only attempt fuzzy match if token contains non-letter OCR noise: ?, !, |, ~, ^
    if any(c in t for c in '?!|~^'):
        t_clean = re.sub(r'[?!|~^]', '', t)
        if t_clean and t_clean in UM_KNOWN:
            return t_clean

    # ton → tona normalization
    if t == 'TON':
        return 'TONA'

    return t


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


def _preprocess_compound_um(lines: List[str]) -> List[str]:
    """
    Combină un număr bare + UM bare de pe linii consecutive într-o singură linie.

    Rezolvă formatul ofertelor unde '100' și 'mp' apar pe linii separate:
        ['100', 'mp'] → ['100 mp']
    Referințele au de obicei '100 MP.' pe o singură linie — rămân neschimbate.

    Heuristică sigură: un număr de 1-4 cifre urmat imediat de o linie cu doar
    litere UM (mp, mc, buc, etc.) nu poate fi NR_CRT — NR_CRT e urmat de un COD,
    nu de un token UM standalone.
    """
    result = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            if (re.match(r'^\d{1,4}$', line) and
                    re.match(r'^[A-Za-z]{1,6}\.?$', next_line)):
                # Verifica ca next_line e un UM valid (nu un cuvant din denumire)
                um_candidate = re.sub(r'\.', '', next_line).upper()
                if um_candidate in UM_KNOWN and um_candidate != 'KM':
                    result.append(f"{line} {next_line}")
                    i += 2
                    continue
        result.append(lines[i])
        i += 1
    return result


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
    lines = _preprocess_compound_um(lines)
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
    _after_linked = False  # True imediat dupa un N.L — asteptam cod numeric bare

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
            # Skip coduri de specificatii tehnice: DN32, PN10, S7064, N1080 etc.
            # Acestea sunt fragmente din denominatia articolului precedent splituite de OCR.
            # Pattern restrâns: 1-2 litere + EXACT 2 cifre (DN32, PN10) SAU 1 litera + 4-5 cifre (S7064).
            # VC1011, SD13A1, SA131 (2+ cifre dupa 2 litere) sunt coduri reale — NU se skipuiesc.
            elif re.match(r'^(?:[A-Z]{1,2}\d{2}|[A-Z]\d{4,5})$', cod):
                logger.debug(f"[PARSER] Skip spec tehnica (DN/PN/tip material): {cod}")
            # Skip coduri marcatori capitol ISDP: $0001-$0009 (CPV section headers)
            # Apar la inceputul fiecarui deviz in format ISDP, nu sunt articole reale.
            elif re.match(r'^\$0{2,}\d$', cod):
                logger.debug(f"[PARSER] Skip capitol ISDP: {cod}")
            # Skip coduri deviz-sumar: cod numeric pur ($226XXX) cu denominatie care
            # contine markeri de antet de capitol (pag, formular f3, e devize).
            # Aceste coduri sunt numere de capitol extrase gresit, nu articole reale.
            elif re.match(r'^\$\d{4,7}$', cod) and (
                den_joined.lower().startswith('pag')
                or re.search(r'formular\s+f3|e\s+devize', den_joined, re.IGNORECASE)
            ):
                logger.debug(f"[PARSER] Skip deviz-sumar numeric: {cod}")
            # Skip orice cod cu footer eDevize in denominatie (ex: S7064 cu den="deviz '226408' - formular f3")
            # Footer-ul eDevize contine "deviz 'XXXXXX' - Formular F3" care nu este o denumire articol.
            elif re.search(r"deviz\s+['\"]?\d{5,8}['\"]?\s*[-–]?\s*formular\s+f3", den_joined, re.IGNORECASE):
                logger.debug(f"[PARSER] Skip cod cu footer eDevize in denominatie: {cod}")
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

        PLUS: În IDLE state, reject 2-digit numbers > 5 (probable sub-article markers)
        Exemple: "21" sau "11" sunt probabil numere de secțiune, nu NR_CRT.
        Numerele reale de articol sunt 3+ cifre (001-999) sau 1-5 (reset).
        """
        m = NR_CRT_RE.match(line.strip())
        if not m:
            return False
        val = int(m.group(1))
        if not (1 <= val <= 999):
            return False
        if current_state == _IDLE:
            # În IDLE, accept numai:
            # - 3+ cifre (001, 027, etc) care sunt >= last_nr_crt
            # - 1-5 cifre (reset la secțiune nouă)
            # Reject 2-digit numbers > 5 (21, 27 etc.) ca suspecte (secțiuni, nu articole)
            num_digits = len(m.group(1))
            if num_digits == 2 and val > 5:
                # "21", "27" etc. sunt probabil numere de secțiune, nu NR_CRT
                return False
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
        # Formate cu separator –: breviar $COD, normativ (2+ litere), single-letter, single-multi-digit, numeric
        for pattern in (COD_BREVIAR_RE, COD_NORM_EXTENDED_RE, COD_NORM_RE, COD_NORM_SINGLE_RE, COD_SINGLE_MULTIDIGIT_RE, COD_NUMERIC_RE):
            m = pattern.match(s)
            if m:
                cod_raw = m.group(1).strip().upper()
                # Strip trailing artifacts: -, >, *, @, %, #, ^
                cod_raw = re.sub(r'[-@%>#*^+]+$', '', cod_raw)
                # Strip bracket suffix complet: [1], [1], [1 etc.
                cod_raw = re.sub(r'\s*\[\d*\]?\s*$', '', cod_raw)
                # Strip designatori normativi lipiti (ASIM, TSCH): TCB40B1ASIM → TCB40B1
                cod_raw = re.sub(r'(?:ASIM|TSCH)$', '', cod_raw).strip()
                cod_raw = re.sub(r'[-@%>#*^+]+$', '', cod_raw)  # al 2-lea pass: CG08A#ASIM → CG08A
                return cod_raw, m.group(2).strip(), ''
        # Cod normativ singur pe linie (simple, extended, single-letter) — cu sufixe opționale
        def _parse_standalone(m):
            cod_raw = m.group(1).strip().upper()
            cod_raw = re.sub(r'[-@%>#*^]+$', '', cod_raw)
            cod_raw = re.sub(r'\s*\[\d*\]?\s*$', '', cod_raw)
            cod_raw = re.sub(r'(?:ASIM|TSCH)$', '', cod_raw).strip()
            # Extrage UM din tokenii sufixe (grup 2 = " ASIM BUC." etc.)
            um_hint = ''
            suffix = (m.group(2) or '').strip()
            for tok in suffix.split():
                t = re.sub(r'\.', '', tok).upper()
                if t in UM_KNOWN and t not in UM_SKIP:
                    um_hint = t
                    break
            return cod_raw, '', um_hint

        for standalone_re in (COD_NORM_STANDALONE_RE,
                              COD_NORM_EXTENDED_STANDALONE_RE,
                              COD_NORM_SINGLE_STANDALONE_RE,
                              COD_SINGLE_MULTIDIGIT_STANDALONE_RE):
            m = standalone_re.match(s)
            if m:
                return _parse_standalone(m)
        # Cod numeric cu spaţiu + descriere + optional |UM (Breviar materiale)
        m = COD_NUMERIC_PIPE_RE.match(s)
        if m:
            cod_raw = '$' + m.group(1)
            den = m.group(2).strip()
            um_hint = m.group(3).rstrip('.').upper() if m.group(3) else ''
            return cod_raw, den, um_hint
        # Cod breviar cu $ prefix deja in sursa, singur pe linie (ex: "$16508", "$05021")
        # Apare in oferte care scriu explicit codul cu $ (fara separator si descriere)
        m = re.match(r'^(\$\d{4,9}[@]?)\s*$', s)
        if m:
            return m.group(1), '', ''
        # Cod numeric bare (4-8 cifre) singur pe linie — articole care apar standalone
        # (e.g., 7206121 pe o linie, urmata de UM si cantitate pe liniile urmatoare)
        m = COD_NUMERIC_BARE_RE.match(s)
        if m:
            return '$' + m.group(1), '', ''
        return None, None, ''

    for line_idx, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or SKIP_RE.search(line) or _PRICE_LABEL_RE.match(line):
            continue

        # N.L handler: articol legat ISDP — funcționează în orice stare
        m_linked = NR_LINKED_RE.match(line)
        if m_linked:
            if state == _READING:
                _finalize()
            last_nr_crt = int(m_linked.group(1))
            cod = ''; denumire_parts = []; um = ''; cantitate = 0.0; preturi = []
            state = _WAITING
            waiting_lines = 0
            _after_linked = True
            continue
        # Bare "L" handler: linked marker on separate line (multi-line format in offer 2)
        m_bare_l = BARE_L_RE.match(line)
        if m_bare_l:
            if state == _READING:
                _finalize()
            # Keep last_nr_crt if already set, otherwise use placeholder
            if not last_nr_crt:
                last_nr_crt = 1
            cod = ''; denumire_parts = []; um = ''; cantitate = 0.0; preturi = []
            state = _WAITING
            waiting_lines = 0
            _after_linked = True
            continue
        # Dot "L" handler: ".L" marker on separate line (variant with dot prefix)
        m_dot_l = DOT_L_RE.match(line)
        if m_dot_l:
            if state == _READING:
                _finalize()
            # Keep last_nr_crt if already set, otherwise use placeholder
            if not last_nr_crt:
                last_nr_crt = 1
            cod = ''; denumire_parts = []; um = ''; cantitate = 0.0; preturi = []
            state = _WAITING
            waiting_lines = 0
            _after_linked = True
            continue

        # NR_SUBITEM handler: decimal sub-article marker like "34.1", "23.1"
        # These appear in breviar tables as sub-items under a main article
        m_subitem = NR_SUBITEM_RE.match(line)
        if m_subitem:
            if state == _READING:
                _finalize()
            # Extract base article number from "34.1" → 34
            subitem_str = m_subitem.group(1)
            base_nr = int(subitem_str.split('.')[0])
            last_nr_crt = base_nr
            cod = ''; denumire_parts = []; um = ''; cantitate = 0.0; preturi = []
            state = _WAITING
            waiting_lines = 0
            continue

        price_count = len(preturi)

        # ── IDLE ─────────────────────────────────────────────────────────────
        if state == _IDLE:
            # Format referinţă deviz: "024 CK26A#" sau "024 2200012" (NR+COD pe linie)
            # sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC." (cu tokeni UM pe aceeași linie)
            # sau "017 W2F05C01 BUC." (NR + single-letter cod)
            m_ai = NR_ALPHA_INLINE_RE.match(line)
            m_ni = NR_NUMERIC_INLINE_RE.match(line)
            m_si = NR_SINGLE_INLINE_RE.match(line)
            m_bi = NR_BREVIAR_INLINE_RE.match(line)
            if m_ai or m_ni or m_si or m_bi:
                m = m_ai or m_ni or m_si or m_bi
                last_nr_crt = int(m.group(1))
                if m_bi:
                    cod = m.group(2)
                elif m_ni:
                    cod = '$' + m.group(2)
                else:
                    raw_cod = m.group(2).upper()
                    raw_cod = re.sub(r'[-@%>#*]+$|\s*\[\d*\]?\s*$', '', raw_cod)
                    raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                    cod = raw_cod
                denumire_parts = []
                # Extrage primul UM valid din tokenii rămași pe linie (grup 3 din NR_ALPHA_INLINE_RE și NR_SINGLE_INLINE_RE)
                um = ''
                if (m_ai or m_si) and m.lastindex >= 3 and m.group(3):
                    for tok in m.group(3).strip().split():
                        tok_clean = tok.rstrip('.')
                        if _is_valid_um(tok_clean):
                            um = _normalize_um_value(tok_clean)
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
                # Format "NR COD - DESCRIERE" pe aceeasi linie (ex: "6 CA01J1 - TURNARE BETON")
                m_ncd = NR_COD_DESC_RE.match(line)
                if m_ncd:
                    last_nr_crt = int(m_ncd.group(1))
                    raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', m_ncd.group(2).upper())
                    raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                    cod = raw_cod
                    denumire_parts = [m_ncd.group(3).strip()] if m_ncd.group(3) else []
                    um = ''
                    cantitate = 0.0
                    preturi = []
                    state = _READING
                    waiting_lines = 0
                else:
                    # Format "NRCOD* - DESCRIERE" (concatenated, no separator)
                    m_concat = NR_COD_CONCAT_RE.match(line)
                    if m_concat:
                        last_nr_crt = int(m_concat.group(1))
                        raw_cod = (m_concat.group(2) + (m_concat.group(3) or '')).upper()
                        raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', raw_cod)
                        raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                        cod = raw_cod
                        denumire_parts = [m_concat.group(4).strip()] if m_concat.group(4) else []
                        um = ''
                        cantitate = 0.0
                        preturi = []
                        state = _READING
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
            # Cod numeric bare (5-8 cifre) dupa N.L — articol legat ISDP
            if _after_linked:
                m_bare = COD_NUMERIC_BARE_RE.match(line)
                if m_bare:
                    cod = '$' + m_bare.group(1)
                    denumire_parts = []; um = ''; cantitate = 0.0; preturi = []
                    state = _READING
                    waiting_lines = 0
                    _after_linked = False
                    continue
            parsed_cod, parsed_den, parsed_um_hint = _try_parse_cod(line)
            if parsed_cod:
                cod = parsed_cod
                denumire_parts = [parsed_den] if parsed_den else []
                um = parsed_um_hint  # setat direct dacă vine din |UM inline
                cantitate = 0.0
                preturi = []
                state = _READING
                waiting_lines = 0
                _after_linked = False
            else:
                # Verifica si format NR_INLINE (038 2222219) sau single-letter (017 W2F05C01) in WAITING — acelasi handling ca IDLE
                m_ai = NR_ALPHA_INLINE_RE.match(line)
                m_ni = NR_NUMERIC_INLINE_RE.match(line)
                m_si = NR_SINGLE_INLINE_RE.match(line)
                m_bi = NR_BREVIAR_INLINE_RE.match(line)
                if m_ai or m_ni or m_si or m_bi:
                    m = m_ai or m_ni or m_si or m_bi
                    last_nr_crt = int(m.group(1))
                    if m_bi:
                        cod = m.group(2)
                    elif m_ni:
                        cod = '$' + m.group(2)
                    else:
                        raw_cod = m.group(2).upper()
                        raw_cod = re.sub(r'[-@%>#*]+$|\s*\[\d*\]?\s*$', '', raw_cod)
                        raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                        cod = raw_cod
                    denumire_parts = []
                    um = ''
                    if (m_ai or m_si) and m.lastindex >= 3 and m.group(3):
                        for tok in m.group(3).strip().split():
                            tok_clean = tok.rstrip('.')
                            if _is_valid_um(tok_clean):
                                um = _normalize_um_value(tok_clean)
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
                    # Format "NR COD - DESCRIERE" pe aceeasi linie in WAITING
                    m_ncd = NR_COD_DESC_RE.match(line)
                    if m_ncd:
                        last_nr_crt = int(m_ncd.group(1))
                        raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', m_ncd.group(2).upper())
                        raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                        cod = raw_cod
                        denumire_parts = [m_ncd.group(3).strip()] if m_ncd.group(3) else []
                        um = ''; cantitate = 0.0; preturi = []
                        state = _READING; waiting_lines = 0; _after_linked = False
                    else:
                        # Format "NRCOD* - DESC" (concatenated NR+CODE, no separator) in WAITING
                        # Handles OCR artifacts where whitespace was lost: "3CF41B01* - Tencuiala..."
                        m_concat = NR_COD_CONCAT_RE.match(line)
                        if m_concat:
                            last_nr_crt = int(m_concat.group(1))
                            raw_cod = (m_concat.group(2) + (m_concat.group(3) or '')).upper()
                            raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', raw_cod)
                            raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                            cod = raw_cod
                            denumire_parts = [m_concat.group(4).strip()] if m_concat.group(4) else []
                            um = ''; cantitate = 0.0; preturi = []
                            state = _READING; waiting_lines = 0; _after_linked = False
                        else:
                            waiting_lines += 1
                            if waiting_lines >= 3:
                                # Nu era articol — numărul era altceva (pagină, preț etc.)
                                state = _IDLE

        # ── READING_ARTICLE ──────────────────────────────────────────────────
        elif state == _READING:
            # Format referinţă deviz: "024 CK26A#" sau "024 2200012" → finalizează + articol nou
            # sau "002 TCB40A1 ASIM" sau "004 ATA01B ASIM BUC." (cu tokeni UM pe aceeași linie)
            # sau "017 W2F05C01 BUC." (NR + single-letter cod)
            m_ai = NR_ALPHA_INLINE_RE.match(line)
            m_ni = NR_NUMERIC_INLINE_RE.match(line)
            m_si = NR_SINGLE_INLINE_RE.match(line)
            m_bi = NR_BREVIAR_INLINE_RE.match(line)
            if m_ai or m_ni or m_si or m_bi:
                _finalize()
                m = m_ai or m_ni or m_si or m_bi
                last_nr_crt = int(m.group(1))
                cod = (m.group(2) if m_bi else ('$' + m.group(2)) if m_ni else re.sub(r'[-@%>#*]+$|\s*\[\d*\]?\s*$', '', m.group(2).upper()))
                denumire_parts = []
                # Extrage primul UM valid din tokenii rămași pe linie (grup 3 din NR_ALPHA_INLINE_RE sau NR_SINGLE_INLINE_RE)
                um = ''
                if (m_ai or m_si) and m.lastindex >= 3 and m.group(3):
                    for tok in m.group(3).strip().split():
                        tok_clean = tok.rstrip('.')
                        if _is_valid_um(tok_clean):
                            um = _normalize_um_value(tok_clean)
                            break
                cantitate = 0.0
                preturi = []
                state = _READING
                waiting_lines = 0
                continue

            # Skip model/reference numbers (like "ni522", "MF100") that appear between
            # article description and actual UM — they're not denomination text
            if _is_model_reference(line):
                continue

            # NR_CRT nou (bare) → finalizează articolul curent
            # Only treat bare integer as NR_CRT if we have NO CODE yet.
            # If we have a code, let quantity/other checks handle the integer first.
            m_bare_nr = NR_CRT_RE.match(line)
            if m_bare_nr and not cod:
                # If we have NO code yet, treat bare NR as the start of a split-format article
                _finalize()
                last_nr_crt = int(m_bare_nr.group(1))
                state = _WAITING
                waiting_lines = 0
                continue
            elif _is_nr_crt(line, _READING, price_count, cantitate):
                _finalize()
                last_nr_crt = int(NR_CRT_RE.match(line).group(1))
                state = _WAITING
                waiting_lines = 0
                continue

            # Cod nou cu separator – fără NR_CRT explicit (ex: "30172 - Transport" sau "TRA01A20")
            # BUT: if current article is incomplete (no UM/Qty), usually treat as denomination continuation
            # EXCEPT: if code matches a STRONG pattern (standalone), it's likely a new article
            parsed_cod, parsed_den, parsed_um_hint = _try_parse_cod(line)
            line_norm = re.sub(r'(?<=[A-Z0-9])\s+(\[\d)', r'\1', line, flags=re.IGNORECASE)
            is_strong_code = (COD_NORM_STANDALONE_RE.match(line_norm) or
                             COD_NORM_EXTENDED_STANDALONE_RE.match(line_norm) or
                             COD_NORM_SINGLE_STANDALONE_RE.match(line_norm) or
                             COD_NUMERIC_BARE_RE.match(line))
            if parsed_cod and um == '' and cantitate == 0.0 and not is_strong_code:
                # Current article is incomplete AND code is weak pattern → treat as denomination continuation
                # But strong patterns (standalone codes) start new articles
                parsed_cod = None
            # Check both code patterns WITH separators and standalone code patterns.
            # (line_norm already computed above)
            # Respinge COD_NUMERIC_RE când descrierea e pur numerică:
            # ex. '4741-71' → cod=$4741, den='71' — e continuare de denumire, nu articol nou
            _numeric_den = (COD_NUMERIC_RE.match(line) and
                            not re.search(r'[A-Za-z]', parsed_den or ''))
            # Format "NR COD - DESC" in READING → finalizeaza curent + incepe nou articol
            m_ncd = NR_COD_DESC_RE.match(line)
            if m_ncd:
                _finalize()
                last_nr_crt = int(m_ncd.group(1))
                raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', m_ncd.group(2).upper())
                raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                cod = raw_cod
                denumire_parts = [m_ncd.group(3).strip()] if m_ncd.group(3) else []
                um = ''; cantitate = 0.0; preturi = []
                state = _READING
                continue

            # Format "NRCOD* - DESC" (concatenated NR+CODE, no separator) in READING
            # Handles OCR artifacts where whitespace was lost: "3CF41B01* - Tencuiala..."
            m_concat = NR_COD_CONCAT_RE.match(line)
            if m_concat:
                _finalize()
                last_nr_crt = int(m_concat.group(1))
                raw_cod = (m_concat.group(2) + (m_concat.group(3) or '')).upper()
                raw_cod = re.sub(r'[-@%>#*^+]+$|\s*\[\d*\]?\s*$', '', raw_cod)
                raw_cod = re.sub(r'(?:ASIM|TSCH)$', '', raw_cod).strip()
                cod = raw_cod
                denumire_parts = [m_concat.group(4).strip()] if m_concat.group(4) else []
                um = ''; cantitate = 0.0; preturi = []
                state = _READING
                continue

            if parsed_cod and not _numeric_den and (
                    COD_NUMERIC_RE.match(line) or COD_NORM_RE.match(line)
                    or COD_NORM_EXTENDED_RE.match(line) or COD_BREVIAR_RE.match(line)
                    or COD_NUMERIC_PIPE_RE.match(line) or COD_NORM_STANDALONE_RE.match(line_norm)
                    or COD_NORM_EXTENDED_STANDALONE_RE.match(line_norm)
                    or COD_NORM_SINGLE_STANDALONE_RE.match(line_norm)):
                _finalize()
                cod = parsed_cod
                denumire_parts = [parsed_den] if parsed_den else []
                um = parsed_um_hint
                cantitate = 0.0
                preturi = []
                state = _READING
                continue

            # UM (doar dacă nu e setat) — normalizează M.C. → MC, MP . → MP
            # BUT: skip "KM" — it's ALWAYS a distance spec (e.g., "DIST .= 10 KM"), never a work unit
            if not um and _is_valid_um(line):
                um_candidate = re.sub(r'[\.\s]', '', line.strip()).upper()
                if um_candidate == 'KM':
                    continue  # Skip distance specifications
                um = _normalize_um_value(line)
                continue

            # Format "100 MC." — indicator normativ pe linie separată
            # Extrage UM-ul COMPLET inclusiv prefixul numeric (ex: "100 MP", "1000 BUC")
            # Cantitatea reală urmează pe linia următoare.
            # BUT: skip "NUMBER KM" (always distance spec like "20 KM", never work unit)
            if um == '':
                m_um_norm = re.match(r'^(\d+)\s+([A-Z]{1,6})\.?\s*$', line, re.IGNORECASE)
                if m_um_norm:
                    um_candidate = m_um_norm.group(2).upper()
                    # KM e ÎNTOTDEAUNA specificație de distanță (20 KM, 50 KM), nu unitate de lucru
                    if um_candidate == 'KM':
                        continue
                    if _is_valid_um(um_candidate):
                        um = f"{m_um_norm.group(1)} {um_candidate}"  # "100 MP" nu doar "MP"
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
                        um = _normalize_um_value(um_candidate)
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

            # Trailing decimal zeros on separate line (e.g., "306" then "000" → 306.000)
            # Format split: cantidad integer on one line, decimals on next (page breaks, watermarks)
            if cantitate > 0.0 and um and line == '000':
                # Concatenate trailing zeros to form decimal: 306 + "000" → 306.000
                cantitate = float(f"{int(cantitate)}.000")
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
