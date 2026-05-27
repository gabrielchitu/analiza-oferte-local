"""
test_verify_agent_llm.py — Tests for LLM diagnosis and auto-fix in verify_agent.py.
"""
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from shared.pipeline_verifier import Finding
from verify_agent import _diagnose_and_fix


def _finding(check, severity="MEDIUM", oferta_n=1,
             group_key="DEV1", group_den="Test grup", value=10, threshold=3):
    return Finding(check, severity, oferta_n, group_key, group_den, value, threshold)


def _mock_llm_client(response_text: str):
    """Create a mock LLM client that returns the given response text."""
    mock = MagicMock()
    mock.chat.completions.create.return_value.choices = [
        MagicMock(message=MagicMock(content=response_text))
    ]
    return mock


def test_high_extra_gets_hypothesis(tmp_path):
    """HIGH_EXTRA finding gets a hypothesis string from LLM."""
    findings = [_finding("HIGH_EXTRA")]
    knowledge = {}

    llm_response = "Articolele sunt subcomponente clasificate ca principale in oferta."
    mock_client = _mock_llm_client(llm_response)

    with patch("verify_agent._get_llm_client", return_value=(mock_client, "claude-sonnet-4-6")):
        _diagnose_and_fix(findings, "TestClient", knowledge)

    assert findings[0].hypothesis is not None
    assert len(findings[0].hypothesis) > 10


def test_oferta_only_adds_to_group_knowledge(tmp_path):
    """OFERTA_ONLY_GROUP: LLM match → written to group_match_knowledge.json."""
    findings = [_finding("OFERTA_ONLY_GROUP", severity="HIGH",
                         group_den="BLOC 1 | Arhitectura | Finisaje")]
    knowledge = {}

    llm_json = json.dumps([{
        "ref_den": "BLOC 1 | Arhitectura | Finisaje interioare",
        "oferta_den": "BLOC 1 | Arhitectura | Finisaje",
        "confidence": 0.9
    }])
    mock_client = _mock_llm_client(llm_json)

    gm_file = tmp_path / "group_match_knowledge.json"
    gm_file.write_text(json.dumps({}))

    with patch("verify_agent._get_llm_client", return_value=(mock_client, "model")), \
         patch("verify_agent.GROUP_MATCH_KNOWLEDGE_FILE", gm_file):
        actions = _diagnose_and_fix(findings, "TestClient", knowledge)

    data = json.loads(gm_file.read_text())
    assert "TestClient" in data
    assert len(data["TestClient"]) == 1
    assert len(actions) == 1


def test_no_llm_skips_diagnosis():
    """When LLM client unavailable, _diagnose_and_fix returns empty actions."""
    findings = [_finding("HIGH_EXTRA")]
    with patch("verify_agent._get_llm_client", return_value=(None, "")):
        actions = _diagnose_and_fix(findings, "TestClient", {})
    assert actions == []
    assert findings[0].hypothesis is None
