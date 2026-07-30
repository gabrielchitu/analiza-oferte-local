import pytest
from shared.f3_price_extractor import _parse_number, _is_capitol_header, _is_cod_name, _is_um, _is_breakdown_key, _is_skip
from shared.f3_price_extractor import _parse_f3_page_lines, _assemble_deviz

def test_parse_number_simple():
    assert _parse_number("33.22") == pytest.approx(33.22)

def test_parse_number_with_thousands():
    assert _parse_number("7,473.71") == pytest.approx(7473.71)

def test_parse_number_eu_format():
    """EU format: dot=thousands separator, comma=decimal."""
    assert _parse_number("1.234,56") == pytest.approx(1234.56)

def test_parse_number_zero():
    assert _parse_number("0.00") == pytest.approx(0.0)

def test_parse_number_invalid():
    assert _parse_number("material:") is None
    assert _parse_number("INFRASTRUCTURA") is None
    assert _parse_number("") is None

def test_is_capitol_header_yes():
    assert _is_capitol_header("INFRASTRUCTURA") is True
    assert _is_capitol_header("COMPARTIMENTARI") is True
    assert _is_capitol_header("FINISAJE EXTERIOARE") is True

def test_is_capitol_header_no():
    assert _is_capitol_header("TOTAL INFRASTRUCTURA") is False
    assert _is_capitol_header("1") is False
    assert _is_capitol_header("CF38A* - Tencuiala") is False
    assert _is_capitol_header("Nr.") is False

def test_is_cod_name_standard():
    assert _is_cod_name("CF38A* - Tencuiala pe baza de ciment") is True
    assert _is_cod_name("RPCE27A+ - Mastic bituminos") is True

def test_is_cod_name_numeric():
    assert _is_cod_name("2101121 - Mortar de zidarie M 10 nisip S1030") is True

def test_is_cod_name_no():
    assert _is_cod_name("mp") is False
    assert _is_cod_name("225.000") is False
    assert _is_cod_name("armatura din poliester") is False  # continuation line

def test_is_um():
    assert _is_um("mp") is True
    assert _is_um("MP") is True
    assert _is_um("mc") is True
    assert _is_um("buc") is True
    assert _is_um("ml") is True
    assert _is_um("kg") is True
    assert _is_um("33.22") is False
    assert _is_um("CF38A*") is False

def test_is_breakdown_key():
    assert _is_breakdown_key("material:") is True
    assert _is_breakdown_key("manopera:") is True
    assert _is_breakdown_key("utilaj:") is True
    assert _is_breakdown_key("transport:") is True
    assert _is_breakdown_key("material") is False
    assert _is_breakdown_key("TOTAL") is False

def test_is_skip_exact():
    """Lines in _SKIP_EXACT must be skipped."""
    assert _is_skip("eDevize") is True

def test_is_skip_regex():
    """Lines matching _SKIP_RE must be skipped."""
    assert _is_skip("Pagina 3 din 14") is True

def test_is_skip_no():
    """Normal cod-name lines must not be skipped."""
    assert _is_skip("CF38A* - Tencuiala") is False


_SAMPLE_LINES = [
    'Antet stanga', 'eDevize', 'SECTIUNEA TEHNICA', 'Nr.', 'Capitol de lucrari',
    'U.M.', 'Cantitatea', 'Pretul unitar', '(fara TVA)', '- Lei -',
    'TOTALUL', '(fara TVA)', '- Lei -', '0', '1', '2', '3', '4', '5 = 3 x 4',
    'INFRASTRUCTURA',
    '1',
    'CF38A* - Tencuiala pe baza de ciment',
    'mp',
    '225.000',
    '33.22',
    '7,473.71',
    'material:',
    '13.22',
    '2,973.71',
    'manopera:',
    '20.00',
    '4,500.00',
    'utilaj:',
    '0.00',
    '0.00',
    'transport:',
    '0.00',
    '0.00',
    '1.1',
    '2101121 - Mortar de zidarie M 10 nisip S1030',
    'mc',
    '1.939',
    '385.00',
    '746.62',
    'TOTAL INFRASTRUCTURA',
    '24,220.05',
    'Deviz "3.1" - Formular F3',
    'Pagina 1 din 14',
]

_MULTILINE_LINES = [
    '5 = 3 x 4',
    '5',
    'RPCE31B+ - Hidroizolatie membrana bituminoasa cu',
    'armatura din poliester netesut - la contactul zidariei cu',
    'placa de la cota +/- 0,00',
    'MP',
    '34.000',
    '63.16',
    '2,147.57',
    'material:',
    '50.94',
    '1,731.82',
    'manopera:',
    '12.22',
    '415.61',
    'utilaj:',
    '0.00',
    '0.00',
    'transport:',
    '0.00',
    '0.00',
]


def test_parse_f3_page_lines_basic():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    types = [e[0] for e in events]
    assert 'CAPITOL' in types
    assert 'ART_NR' in types
    assert 'COD_NAME' in types
    assert 'UM' in types
    assert 'BREAKDOWN' in types
    assert 'SUB_NR' in types
    assert 'TOTAL_CAPITOL' in types


def test_parse_f3_ignores_header_zone():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    texts = [e[1].get('text', '') for e in events if e[0] == 'TEXT']
    assert 'Antet stanga' not in texts
    assert 'eDevize' not in texts


def test_parse_f3_breakdown_event():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    breakdowns = [e[1] for e in events if e[0] == 'BREAKDOWN']
    assert len(breakdowns) == 4  # material, manopera, utilaj, transport
    material = next(b for b in breakdowns if b['key'] == 'material')
    assert material['pret'] == pytest.approx(13.22)
    assert material['total'] == pytest.approx(2973.71)


def test_parse_f3_total_capitol_event():
    events = _parse_f3_page_lines(_SAMPLE_LINES)
    totals = [e[1] for e in events if e[0] == 'TOTAL_CAPITOL']
    assert len(totals) == 1
    assert totals[0]['titlu'] == 'INFRASTRUCTURA'
    assert totals[0]['total'] == pytest.approx(24220.05)


def test_parse_f3_multiline_denumire():
    events = _parse_f3_page_lines(_MULTILINE_LINES)
    cod_events = [e[1] for e in events if e[0] == 'COD_NAME']
    assert len(cod_events) == 1
    assert 'armatura din poliester' in cod_events[0]['denumire']


def test_assemble_deviz_article_count():
    class MockHeader:
        obiectivul = "CONSTRUIRE UNITATE DE CAZARE - TARGOVISTE"
        obiectul = "3 ARHITECTURA"
        categoria = "3.1 ARHITECTURA"
        deviz_key = "abc123"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    assert deviz['obiectivul'] == MockHeader.obiectivul
    assert len(deviz['capitole']) == 1
    capitol = deviz['capitole'][0]
    assert capitol['titlu'] == 'INFRASTRUCTURA'
    assert capitol['total_capitol'] == pytest.approx(24220.05)
    assert len(capitol['articole']) == 1
    art = capitol['articole'][0]
    assert art['nr_crt'] == '1'
    assert art['cod'] == 'CF38A*'
    assert art['cantitate'] == pytest.approx(225.0)
    assert art['pret_unitar'] == pytest.approx(33.22)
    assert art['total'] == pytest.approx(7473.71)


def test_assemble_deviz_breakdown():
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert art['breakdown'] is not None
    assert art['breakdown']['material']['pret'] == pytest.approx(13.22)
    assert art['breakdown']['control_ok'] is True


def test_assemble_deviz_sub_item():
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert len(art['sub_items']) == 1
    sub = art['sub_items'][0]
    assert sub['nr_crt'] == '1.1'
    assert sub['total'] == pytest.approx(746.62)


def test_assemble_deviz_suspect_flag_on_control_ok():
    """Article with matching breakdown → control_ok=True, suspect=False."""
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    events = _parse_f3_page_lines(_SAMPLE_LINES)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert art['breakdown']['control_ok'] is True
    assert art.get('suspect') is False


def test_assemble_deviz_breakdown_control_fail():
    """Article with mismatched breakdown → control_ok=False, suspect=True."""
    class MockHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test"

    # Manually craft lines where material pret != pret_unitar
    lines_bad = [
        '5 = 3 x 4',
        'CAPITOL',
        '1',
        'CF38A* - Tencuiala pe baza de ciment',
        'mp',
        '100.000',
        '50.00',    # pret_unitar
        '5,000.00',
        'material:',
        '10.00',   # material.pret (sum = 10.00, but pret_unitar = 50.00 → mismatch)
        '1,000.00',
        'manopera:',
        '0.00',
        '0.00',
        'utilaj:',
        '0.00',
        '0.00',
        'transport:',
        '0.00',
        '0.00',
        'TOTAL CAPITOL',
        '5,000.00',
    ]
    events = _parse_f3_page_lines(lines_bad)
    deviz = _assemble_deviz(events, MockHeader())
    art = deviz['capitole'][0]['articole'][0]
    assert art['breakdown']['control_ok'] is False
    assert art.get('suspect') is True


def test_extract_prices_checkpoint_roundtrip(tmp_path):
    """extract_prices saves to checkpoint and loads on second call without re-extracting."""
    from shared.f3_price_extractor import extract_prices

    # Build minimal page_classes and deviz_headers
    class FakeHeader:
        obiectivul = "TEST"
        obiectul = "TEST"
        categoria = "TEST"
        deviz_key = "test123"
        deviz_cod = "3.1"
        is_valid = True

    page_classes = [{
        'is_f3': True,
        'header_only': False,
        'deviz_cod': '3.1',
        'page_number': 1,
        'lines': ['5 = 3 x 4', 'CAPITOL', '1', 'TEST - Article', 'buc', '1.000', '10.00', '10.00', 'TOTAL CAPITOL', '10.00'],
    }]
    deviz_headers = {'test123': FakeHeader()}
    ckpt = tmp_path / 'sursa_extracted_test.json'

    # First call — extracts and saves
    result1 = extract_prices(page_classes, deviz_headers, checkpoint_path=ckpt)
    assert ckpt.exists()
    assert len(result1) == 1

    # Second call — loads from checkpoint (pass empty page_classes to prove no re-extraction)
    result2 = extract_prices([], {}, checkpoint_path=ckpt)
    assert result2 == result1

    # force=True — re-extracts even with checkpoint
    result3 = extract_prices(page_classes, deviz_headers, checkpoint_path=ckpt, force=True)
    assert len(result3) == 1


# --- Regression: all-caps line mistaken for a CAPITOL header (EuroProject) ---

def _capitole(lines):
    events = _parse_f3_page_lines(['5 = 3 x 4'] + lines)
    return [e[1]['titlu'] for e in events if e[0] == 'CAPITOL']


def _first(events, etype):
    return next(e[1] for e in events if e[0] == etype)


def test_wrapped_denumire_fragment_is_not_a_capitol():
    """'CATV' wraps off the denumire above it — the UM right after proves it."""
    lines = [
        '25.1',
        '100014356 - Cablu coaxial 2275 tip RG6 pt. instalatie',
        'CATV',
        'm', '61.800', '3.80', '234.53',
    ]
    assert _capitole(lines) == []
    events = _parse_f3_page_lines(['5 = 3 x 4'] + lines)
    assert _first(events, 'COD_NAME')['denumire'].endswith('instalatie CATV')
    assert _first(events, 'UM')['um'] == 'M'


def test_line_split_um_bucata_is_not_a_capitol():
    """eDevize splits the UM 'BUCATA' across two lines as 'BUCAT' + 'A'."""
    lines = [
        '115',
        'RPSE21A# - Apometru Dn25',
        'BUCAT', 'A',
        '8.000', '2,572.27', '20,578.19',
    ]
    assert _capitole(lines) == []
    events = _parse_f3_page_lines(['5 = 3 x 4'] + lines)
    assert _first(events, 'COD_NAME')['denumire'] == 'Apometru Dn25'
    assert _first(events, 'UM')['um'] == 'BUC'
    assert [e[1]['value'] for e in events if e[0] == 'NUMBER'] == [8.0, 2572.27, 20578.19]


def test_um_ans_is_recognised():
    """'ans' (ansamblu) is a UM, not a trailing word of the denumire."""
    lines = [
        '22',
        'IE01A02> - Efectuarea probei de etanseitate la presiune a',
        'instalatiei de incalzire',
        'ans', '2.000', '149.32', '298.63',
    ]
    events = _parse_f3_page_lines(['5 = 3 x 4'] + lines)
    assert _first(events, 'COD_NAME')['denumire'].endswith('instalatiei de incalzire')
    assert _first(events, 'UM')['um'] == 'ANS'


def test_real_capitol_header_still_detected():
    """A header followed by an article number is still a CAPITOL."""
    lines = ['TOTAL CURENTI TARI', '54,018.05', 'CURENTI SLABI', '21',
             'ED04B01> - Priza dubla RJ45, montaj ST', 'buc', '6.000', '59.88', '359.28']
    assert _capitole(lines) == ['CURENTI SLABI']
