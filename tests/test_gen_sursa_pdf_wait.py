"""Word must finish opening the document before the export script runs."""

import pytest

from gen_sursa_incarcare import _wait_for_word_document


def test_waits_until_word_reports_an_open_document():
    """A cold Word start takes longer than any fixed sleep worth hard-coding."""
    probe_calls = []

    def probe():
        probe_calls.append(1)
        return len(probe_calls) >= 4  # open on the 4th poll

    assert _wait_for_word_document(probe, timeout=5.0, interval=0.0) is True
    assert len(probe_calls) == 4


def test_gives_up_when_no_document_ever_opens():
    assert _wait_for_word_document(lambda: False, timeout=0.0, interval=0.0) is False


def test_returns_immediately_when_already_open():
    calls = []

    def probe():
        calls.append(1)
        return True

    assert _wait_for_word_document(probe, timeout=5.0, interval=0.0) is True
    assert len(calls) == 1


def test_failed_conversion_removes_the_previous_pdf(tmp_path):
    """A stale PDF next to a fresh DOCX reads as current and gets sent out."""
    from gen_sursa_incarcare import _convert_docx_to_pdf

    docx = tmp_path / "missing.docx"          # never created: `open` fails fast
    pdf = tmp_path / "missing.pdf"
    pdf.write_bytes(b"%PDF-1.4 stale content")

    assert _convert_docx_to_pdf(docx, pdf) is False
    assert not pdf.exists()
