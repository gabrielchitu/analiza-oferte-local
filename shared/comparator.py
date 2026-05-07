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
    neconf = []
    if _normalize_um(ref.get("um", "")) != _normalize_um(oferta.get("um", "")):
        neconf.append({
            "tip": "UM_DIFERIT",
            "camp": "um",
            "ref": ref.get("um"),
            "oferta": oferta.get("um"),
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
