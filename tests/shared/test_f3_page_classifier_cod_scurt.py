"""Cod de deviz SCURT (sub 5 caractere) urmat de denumire pe linia urmatoare.

Format real (client Gura Foii, oferta VACOMAN): fiecare deviz al ofertei e
identificat de "Deviz oferta GF06" + denumirea pe linia de dedesubt, in timp ce
"Categoria de lucrari: 0150" e IDENTICA pe toate devizele obiectului.

Clasificatorul cerea coduri de 5-8 caractere, deci "GF06" nu se potrivea; cadea
pe cheia compusa Obiect-Categorie ("0001-0150") — aceeasi pentru toate devizele
obiectului. Rezultat: 11 devize de referinta colapsau intr-un singur grup de
oferta, restul deveneau "extra", iar imperecherea era arbitrara (articole de
instalatii sanitare comparate cu montaj utilaje).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.f3_page_classifier import classify_page_local


def _make_page(lines, page_number=1):
    return {"page_number": page_number, "lines": [{"content": l} for l in lines]}


def _pagina_vacoman(cod: str, denumire: str):
    """Antetul real: cod si denumire pe linii SEPARATE, categoria numerica comuna."""
    return _make_page([
        "Persoana juridica achizitoare",
        "COMUNA GURA FOII",
        "Formularul F3",
        "Obiectivul:",
        "0150 000000150",
        "REABILITARE SCOALA GURA FOII PRIN EFICIENTIZARE ENERGETICA",
        "Obiectul:",
        "0001 1",
        "OB. 01. CONSTRUCTII SI INSTALATII CHELTUIELI ELIGIBILE",
        "Lista cu cantitatile de lucrari",
        f"Deviz oferta {cod}",
        denumire,
        "Categoria de lucrari: 0150",
        "Nr. Capitol de lucr.",
        "UM",
        "CANTITATEA",
        "001 SC13B1",
        "BUC.",
        "6.000",
    ])


def test_cod_scurt_cu_cifra_e_recunoscut_ca_explicit():
    r = classify_page_local(_pagina_vacoman("GF06", "INSTALATII SANITARE INTERIOARE"))
    assert r["extraction_method"] == "explicit", r
    assert r["deviz_cod"] == "GF06", r


def test_denumirea_de_dupa_cod_devine_categoria_nu_antetul_de_tabel():
    """Fara denumire, grupurile ofertei n-ar avea text de comparat cu referinta
    si s-ar potrivi doar prin egalitate de cod — imposibil intre 'GF06' si
    'INSTALATII SANITARE INTERIOARE'."""
    r = classify_page_local(_pagina_vacoman("GF06", "INSTALATII SANITARE INTERIOARE"))
    assert r["categoria"]["text"] == "INSTALATII SANITARE INTERIOARE", r
    assert r["deviz_den"] == "INSTALATII SANITARE INTERIOARE", r


def test_devize_diferite_ale_aceluiasi_obiect_primesc_chei_diferite():
    """Miezul regresiei: 'Categoria de lucrari: 0150' e comuna, deci cheia compusa
    Obiect-Categorie colapsa toate devizele obiectului intr-unul singur."""
    coduri = {
        classify_page_local(_pagina_vacoman(cod, den))["deviz_cod"]
        for cod, den in [
            ("GF02", "INFRASTRUCTURA ELIGIBIL"),
            ("GF06", "INSTALATII SANITARE INTERIOARE"),
            ("GF13", "MONTAJ UTILAJE"),
            ("GF16", "RETEA APA"),
        ]
    }
    assert coduri == {"GF02", "GF06", "GF13", "GF16"}, coduri


def test_denumire_pura_fara_cod_ramane_pe_calea_veche():
    """Formatul referintei ('Deviz oferta INSTALATII SANITARE INTERIOARE', fara
    cod) nu trebuie sa fie confundat cu un cod scurt: primele 8 litere ale
    denumirii NU sunt un cod, fiindca n-au nicio cifra."""
    r = classify_page_local(_make_page([
        "Formularul F3",
        "Obiectul :1 CONSTRUCTII SI INSTALATII",
        "Lista cu cantitatile de lucrari",
        "Deviz oferta INSTALATII SANITARE INTERIOARE",
        "Categoria de lucrari :",
        "= NR. SIMBOL ART.",
        "001 RPCT09H1",
    ]))
    assert r["deviz_cod"] == "INSTALATII SANITARE INTERIOARE", r


def test_cod_lung_clasic_neschimbat():
    """Formatul SSR/DT (cod de 6 cifre) ramane exact cum era."""
    r = classify_page_local(_make_page([
        "Formularul F3",
        "Obiectul: 0002 VESTIAR",
        "Deviz oferta 226238 STRUCTURA DE REZISTENTA",
        "Categoria de lucrari: 0120",
        "001 CA01A1",
    ]))
    assert r["extraction_method"] == "explicit", r
    assert r["deviz_cod"] == "226238", r


# ── Pagini de continuare: codul devizului doar in antetul curent ────────────
# "pag 2 GF06" — fara "Deviz oferta", fara Obiectul/Categoria. Pagina ramanea
# fara cod, deci articolele ei nu intrau in grupul devizului: 17 grupuri-fantoma
# de oferta, toate raportate ca articole "extra".


def _pagina_continuare(pag: int, cod: str):
    """Forma reala a paginii 2+ dintr-un deviz: antet curent 'pag N COD', apoi
    direct articole — niciun 'Deviz oferta', niciun Obiectul/Categoria."""
    return _make_page([
        "pag", str(pag), cod,
        "016", "SA12D1#", "BUC.", "6.060",
        "VAS CLOSET COL2-A PORTELAN ALB C. 1 S",
    ])


def test_pagina_de_continuare_preia_codul_din_antetul_curent():
    r = classify_page_local(_pagina_continuare(2, "GF06"))
    assert r["deviz_cod"] == "GF06", r


def test_pagina_de_continuare_nu_inventeaza_categoria():
    """Doar codul se propaga; denumirea vine de pe pagina de antet a devizului."""
    r = classify_page_local(_pagina_continuare(3, "GF06"))
    assert r["categoria"] is None, r


def test_numarul_de_articol_nu_e_confundat_cu_un_cod_de_deviz():
    """'007' de pe prima linie de articol nu trebuie sa devina cod de deviz —
    exact asa apareau grupurile-fantoma 005/007/012/..."""
    r = classify_page_local(_make_page([
        "007", "SA12D1#", "BUC.", "6.060", "VAS CLOSET COL2-A PORTELAN ALB",
    ]))
    assert r["deviz_cod"] != "007", r
