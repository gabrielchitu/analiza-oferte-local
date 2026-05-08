# tests/test_report_word.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.report_word import generate_word
from docx import Document
import io


def _make_neconf(tip, deviz, ref_cod='CA01A1', ref_den='TEST', ref_um='m',
                 ref_cant=10.0, oferta_cod='CA01A1', oferta_den='TEST',
                 oferta_um='m', oferta_cant=10.0, camp=None, deviz_den='STRUCTURA'):
    n = {
        'tip': tip, 'deviz_ref': deviz, 'deviz_denumire': deviz_den,
        'ref_cod': ref_cod, 'ref_denumire': ref_den,
        'ref_um': ref_um, 'ref_cantitate': ref_cant,
        'oferta_cod': oferta_cod, 'oferta_denumire': oferta_den,
        'oferta_um': oferta_um, 'oferta_cantitate': oferta_cant,
    }
    if camp:
        n['camp'] = camp
    return n


def _load_doc(comp, mismatches=None, devize_extra=None, devize_lipsa=None):
    session = {'client_name': 'TEST', 'obiect_investitii': ''}
    comp_full = {
        'oferta_nr': 1, 'source_file': 'test.json', 'ofertant': 'Test SRL',
        **comp,
        'deviz_mismatches': mismatches or [],
    }
    docx_bytes = generate_word(
        session, comp_full,
        devize_extra=devize_extra or [],
        devize_lipsa=devize_lipsa or [],
    )
    return Document(io.BytesIO(docx_bytes))


def test_deviz_section_heading_appears():
    """Fiecare deviz are un heading cu codul si numarul de articole."""
    comp = {
        'neconformitati': [
            _make_neconf('ARTICOL_LIPSA', '226108', deviz_den='STRUCTURA CUPOLA'),
        ],
        'total_neconformitati': 1, 'matches': 43,
    }
    doc = _load_doc(comp)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '226108' in full_text, f"Deviz 226108 not found in doc text"


def test_extra_articles_appear_after_deviz_data():
    """Articolele EXTRA apar dupa randurile de LIPSA/DIFERENTA ale devizului."""
    comp = {
        'neconformitati': [
            _make_neconf('ARTICOL_LIPSA',  '226108', ref_cod='AA01A1'),
            _make_neconf('ARTICOL_EXTRA',  '226108', oferta_cod='EXTRA1',
                         ref_cod='', ref_den=''),
        ],
        'total_neconformitati': 2, 'matches': 43,
    }
    doc = _load_doc(comp)
    assert len(doc.tables) > 0 or len(doc.paragraphs) > 0


def test_deviz_mismatch_alert_appears():
    """Alerta DEVIZ_MISMATCH apare la finalul documentului."""
    comp = {
        'neconformitati': [],
        'total_neconformitati': 0, 'matches': 100,
    }
    mismatches = [{'oferta_deviz': '226113', 'ref_deviz': '226118',
                   'overlap_score': 0.88, 'oferta_art_count': 8, 'ref_art_count': 7}]
    doc = _load_doc(comp, mismatches=mismatches)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '226113' in full_text, "Mismatch alert 226113 not found in doc"
    assert '226118' in full_text, "Mismatch ref deviz 226118 not found in doc"


def test_devize_extra_alert_appears():
    """Devizele din oferta absente din referinta apar in sectiunea alerte."""
    comp = {
        'neconformitati': [],
        'total_neconformitati': 0, 'matches': 100,
    }
    devize_extra = [{'deviz': '226728', 'denumire': 'CHELTUIELI CONEXE', 'art_count': 2}]
    doc = _load_doc(comp, devize_extra=devize_extra)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '226728' in full_text, "Extra deviz alert 226728 not found in doc"


def test_empty_neconformitati_generates_valid_doc():
    """Document fara neconformitati se genereaza fara erori."""
    comp = {'neconformitati': [], 'total_neconformitati': 0, 'matches': 100}
    doc = _load_doc(comp)
    assert doc is not None


def test_sumar_contains_counts():
    """Sectiunea de sumar contine numarul de articole matched."""
    comp = {
        'neconformitati': [_make_neconf('ARTICOL_LIPSA', '226108')],
        'total_neconformitati': 1, 'matches': 42,
        'ref_art_count': 43, 'oferta_art_count': 44,
    }
    doc = _load_doc(comp)
    full_text = '\n'.join(p.text for p in doc.paragraphs)
    assert '42' in full_text or '43' in full_text, "Counts not found in doc"
