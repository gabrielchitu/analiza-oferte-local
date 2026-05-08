"""
Tests pentru parsarea robusta a JSON returnat de LLM.

Problema: Haiku si GPT-mini uneori impacheteaza JSON in markdown fences
(```json\n...\n```) in loc de JSON pur. json.loads() crapa,
deviz normalization si fuzzy matching sunt disablate silentios.

Fix: _safe_json_parse() incearca json direct, apoi stripuieste fences.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic_adapter import _safe_json_parse


def test_plain_json_parsed():
    raw = '{"matches": [{"ref_cod": "CA02A1", "oferta_cod": "CA02A1"}]}'
    result = _safe_json_parse(raw)
    assert result == {"matches": [{"ref_cod": "CA02A1", "oferta_cod": "CA02A1"}]}


def test_markdown_json_fence_stripped():
    raw = '```json\n{"matches": [{"ref_cod": "CA02A1", "oferta_cod": "CA02A1"}]}\n```'
    result = _safe_json_parse(raw)
    assert result == {"matches": [{"ref_cod": "CA02A1", "oferta_cod": "CA02A1"}]}


def test_markdown_fence_without_language_stripped():
    raw = '```\n{"key": "value"}\n```'
    result = _safe_json_parse(raw)
    assert result == {"key": "value"}


def test_json_with_preamble_extracted():
    """LLM pune text inainte de JSON block."""
    raw = 'Iata raspunsul:\n```json\n{"result": true}\n```\nSper ca ajuta.'
    result = _safe_json_parse(raw)
    assert result == {"result": True}


def test_json_embedded_in_text_extracted():
    """JSON valabil undeva in mijlocul textului."""
    raw = 'Matches found: {"matches": []} - done'
    result = _safe_json_parse(raw)
    assert result == {"matches": []}


def test_invalid_json_returns_empty_dict():
    raw = "Nu am putut genera un raspuns valid."
    result = _safe_json_parse(raw)
    assert result == {}


def test_empty_string_returns_empty_dict():
    result = _safe_json_parse("")
    assert result == {}


def test_truncated_json_in_fence_returns_empty():
    """JSON trunchiat in fence — nu trebuie sa crape."""
    raw = '```json\n{"matches": [{"ref_cod": "CA02A1"'
    result = _safe_json_parse(raw)
    assert result == {}
