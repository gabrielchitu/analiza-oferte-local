# tests/test_verify_agent.py
import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from verify_agent import (
    load_agent_knowledge, save_agent_knowledge,
    get_client_thresholds, _generate_md_report, _record_run,
)


def test_load_agent_knowledge_missing_file(tmp_path):
    kb_file = tmp_path / "agent_knowledge.json"
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        result = load_agent_knowledge()
    assert result == {}


def test_save_and_load_roundtrip(tmp_path):
    kb_file = tmp_path / "agent_knowledge.json"
    data = {"Test Client": {"thresholds": {"extra": 3}}}
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        save_agent_knowledge(data)
        loaded = load_agent_knowledge()
    assert loaded == data


def test_get_client_thresholds_default():
    knowledge = {}
    result = get_client_thresholds(knowledge, "Nonexistent")
    assert result == {}


def test_get_client_thresholds_custom():
    knowledge = {"CM": {"thresholds": {"extra": 5, "lipsa": 2}}}
    result = get_client_thresholds(knowledge, "CM")
    assert result == {"extra": 5, "lipsa": 2}


def test_record_run_appends(tmp_path):
    kb_file = tmp_path / "ak.json"
    with patch("verify_agent.AGENT_KNOWLEDGE_FILE", kb_file):
        knowledge = {}
        _record_run(knowledge, "CM", iteration=1,
                    nc_before=100, nc_after=80, findings_count=5, actions=[])
        assert "CM" in knowledge
        assert len(knowledge["CM"]["runs"]) == 1
        run = knowledge["CM"]["runs"][0]
        assert run["iteration"] == 1
        assert run["nc_before"] == 100
        assert run["nc_after"] == 80


def test_generate_md_report_contains_client_name():
    from shared.pipeline_verifier import Finding
    findings = [
        Finding("HIGH_EXTRA", "MEDIUM", 1, "DEV1", "Test deviz", 10, 3,
                hypothesis="Subcomponente clasificate gresit")
    ]
    iterations = [
        {"iteration": 1, "nc_before": 100, "nc_after": 80,
         "findings_count": 5, "actions": ["group_match: +1 pereche"]}
    ]
    report = _generate_md_report("Camin Maneciu", iterations, findings,
                                 stopped_reason="convergenta")
    assert "Camin Maneciu" in report
    assert "HIGH_EXTRA" in report
    assert "Test deviz" in report
    assert "convergenta" in report
