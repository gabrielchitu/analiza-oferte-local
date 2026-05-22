CANTITATE_FIELDS = ["cantitate"]
PRICE_FIELDS = [
    "pret_material", "pret_manopera", "pret_utilaj", "pret_transport",
    "val_material", "val_manopera", "val_utilaj", "val_transport",
]
# Păstrează NUMERIC_FIELDS pentru backwards-compat cu cod existent
NUMERIC_FIELDS = CANTITATE_FIELDS + PRICE_FIELDS

PRET_VAL_PAIRS = [
    ("pret_material", "val_material"),
    ("pret_manopera", "val_manopera"),
    ("pret_utilaj", "val_utilaj"),
    ("pret_transport", "val_transport"),
]

# Toleranta absoluta pentru campuri numerice mici
ARITHMETIC_TOLERANCE = 0.05
# Toleranta relativa (%) pentru valori mari — evita false pozitive din rotunjiri
RELATIVE_TOLERANCE_PCT = 0.5  # 0.5%


# Unitati de masura echivalente in constructii romanesti:
# ml (metri liniari) = m — aceeasi unitate fizica, variatie de notatie
_UM_EQUIV: dict = {"ML": "M"}


def _normalize_um(um: str) -> str:
    """Normalizeaza UM: uppercase, elimina spatii si puncte (BUC. -> BUC, M. C. -> MC, MP . -> MP).
    Aplica echivalente cunoscute: ml -> m."""
    import re
    normalized = re.sub(r'[\s.]+', '', (um or "").upper())
    return _UM_EQUIV.get(normalized, normalized)


def compare_articles(ref: dict, oferta: dict, include_prices: bool = True) -> list:
    from difflib import SequenceMatcher
    neconf = []
    if _normalize_um(ref.get("um", "")) != _normalize_um(oferta.get("um", "")):
        neconf.append({
            "tip": "UM_DIFERIT",
            "camp": "um",
            "ref": ref.get("um"),
            "oferta": oferta.get("um"),
        })
    # Check denomination similarity (detect genuinely different descriptions)
    # Strip known OCR artifacts from eDevize headers before comparing
    import re as _re
    _OCR_ARTIFACTS = _re.compile(
        r'\bantet\s+stanga\b|\bedevize\b|\bsectiunea\s+tehnica\b|\bformular\s+f3\b'
        r'|\bsectiunea\s+financiara\b|\bpag\.?\s*\d+\b|\bsistem\s+informatic\b'
        # Adnotari specifice devize constructii romanesti
        r'|\bdotare\s+constructor\b|\basim\b'
        # Notatie subcomponente/materiale legate: "l: IZL4F -m : 7801893 -" sau "l:lc52a -0059: 6716352 -"
        # Strip de la l: pana la sfarsitul notatiei (tot ce urmeaza dupa codul l: e metadata)
        r'|l\s*:\s*[a-z0-9]+(?:\s*-\s*[a-z0-9]*\s*:\s*[a-z0-9]*\s*-.*)?'
        # Garbage financiar din tabele de totalizare (diferite formate)
        r'|%\s*\)\s*vo\s*=|%\s*x\s*\(?to|\+po\b|\bio\s*=\s*%|\bpo\s*=\s*%|\bto\s*\+\s*io\b'
        r'|\bcontrib\s+asig\s+munca\b|\btotal\s+chelt\s+directe\b'
        r'|\bcheltuieli\s+(directe|indirecte)\b'
        # Garbage din alte randuri ale tabelului (executant, obiectiv, etc.)
        r'|\bexecutant\s+\d+|\bobiecti[vu]\s+\d+|\bcomercial[a]\b',
        _re.IGNORECASE
    )
    def _clean_den(s: str) -> str:
        s = _OCR_ARTIFACTS.sub('', s)
        # Strip trailing " a" OCR artifact si cratime standalone
        s = _re.sub(r'(\s+-)+\s*$', '', s)
        s = _re.sub(r'\s+a\s*$', '', s)
        return _re.sub(r'\s+', ' ', s).strip()

    ref_den = _clean_den((ref.get("denumire") or "").lower())
    oferta_den = _clean_den((oferta.get("denumire") or "").lower())
    if ref_den and oferta_den and len(ref_den) > 10 and len(oferta_den) > 10:
        # Jaccard pe cuvinte — robust la zgomot OCR (cratime, spatii, split cuvinte)
        def _word_tokens(s):
            return set(_re.sub(r'[^a-z0-9]', ' ', s).split()) - {'', '-'}
        r_tok = _word_tokens(ref_den)
        o_tok = _word_tokens(oferta_den)
        if r_tok and o_tok:
            inter = len(r_tok & o_tok)
            union = len(r_tok | o_tok)
            sim = inter / union  # Jaccard pur — robust la OCR, sensibil la diferente reale
            if sim < 0.50:
                neconf.append({
                    "tip": "DESCRIERE_DIFERITA",
                    "camp": "denumire",
                    "ref": ref_den[:150],
                    "oferta": oferta_den[:150],
                    "similaritate": round(sim, 2),
                })
    fields_to_check = CANTITATE_FIELDS + (PRICE_FIELDS if include_prices else [])
    for field in fields_to_check:
        r_val = ref.get(field, 0.0) or 0.0
        o_val = oferta.get(field, 0.0) or 0.0
        diff = abs(r_val - o_val)
        # Ignora diferente minore (rotunjiri OCR): absolut < 0.05 SAU relativ < 0.5%
        max_val = max(abs(r_val), abs(o_val))
        if diff <= ARITHMETIC_TOLERANCE:
            continue
        if max_val > 0 and (diff / max_val * 100) < RELATIVE_TOLERANCE_PCT:
            continue
        neconf.append({
            "tip": "DIFERENTA_CAMP",
            "camp": field,
            "ref": r_val,
            "oferta": o_val,
        })
    return neconf


def check_arithmetic(art: dict) -> list:
    """Verifica daca val = cantitate * pret (cu toleranta 1% pentru spor/rotunjiri)."""
    neconf = []
    cantitate = art.get("cantitate", 0.0) or 0.0
    for pret_field, val_field in PRET_VAL_PAIRS:
        pret = art.get(pret_field, 0.0) or 0.0
        val = art.get(val_field, 0.0) or 0.0
        if pret <= 0 or val <= 0:
            continue
        expected = round(cantitate * pret, 2)
        if expected <= 0:
            continue
        diff = abs(val - expected)
        # Toleranta relativa 1% (sporul de dificultate poate modifica valoarea)
        if diff > 0.05 and (diff / max(val, expected) * 100) > 1.0:
            neconf.append({
                "tip": "EROARE_ARITMETICA",
                "camp": val_field,
                "calculat": expected,
                "declarat": val,
            })
    return neconf
