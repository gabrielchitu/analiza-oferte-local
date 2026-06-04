"""Integration tests for extraction_v2 with matching pipeline.

Tests the integration of ExtractionOrchestrator with MatchingOrchestratorV2,
verifying that extracted reference and offer data can be matched into
v1-compatible holistic JSON with proper structure and statistics.
"""

import pytest
from shared.extraction_v2 import ExtractionOrchestrator
from shared.matching_orchestrator_v2 import MatchingOrchestratorV2


class TestMatchingOrchestratorV2:
    """Tests for MatchingOrchestratorV2 class."""

    def test_matching_orchestrator_v2_init(self):
        """Should initialize with empty statistics."""
        matcher = MatchingOrchestratorV2()
        assert matcher.stats == {
            "matched_groups": 0,
            "ref_only_groups": 0,
            "oferta_only_groups": 0,
            "matched_articles": 0,
            "ref_only_articles": 0,
            "oferta_only_articles": 0,
        }

    def test_matching_orchestrator_v2_match_full_match(self):
        """Should match all groups when all deviz_cod match."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [
                        {"nr": "1", "descriere": "EXCAVATOR"},
                        {"nr": "2", "descriere": "BULDOZER"},
                    ],
                }
            ],
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [
                        {"nr": "1", "descriere": "EXCAVATOR"},
                        {"nr": "2", "descriere": "BULDOZER"},
                    ],
                }
            ],
        }

        holistic = matcher.match(ref, oferta)

        # Check structure
        assert "matched_groups" in holistic
        assert "ref_only_groups" in holistic
        assert "oferta_only_groups" in holistic
        assert "stats" in holistic

        # Check stats
        assert holistic["stats"]["matched_groups_count"] == 1
        assert holistic["stats"]["ref_only_groups_count"] == 0
        assert holistic["stats"]["oferta_only_groups_count"] == 0

        # Check cached stats
        assert matcher.stats["matched_groups"] == 1
        assert matcher.stats["ref_only_groups"] == 0
        assert matcher.stats["oferta_only_groups"] == 0

    def test_matching_orchestrator_v2_match_partial_match(self):
        """Should handle partial group matching."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1", "descriere": "EXCAVATOR"}],
                },
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [{"nr": "2", "descriere": "BULDOZER"}],
                },
            ],
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1", "descriere": "EXCAVATOR"}],
                }
            ],
        }

        holistic = matcher.match(ref, oferta)

        assert holistic["stats"]["matched_groups_count"] == 1
        assert holistic["stats"]["ref_only_groups_count"] == 1
        assert holistic["stats"]["oferta_only_groups_count"] == 0

    def test_matching_orchestrator_v2_match_no_overlap(self):
        """Should handle groups with no deviz_cod overlap."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1"}],
                }
            ],
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [{"nr": "2"}],
                }
            ],
        }

        holistic = matcher.match(ref, oferta)

        assert holistic["stats"]["matched_groups_count"] == 0
        assert holistic["stats"]["ref_only_groups_count"] == 1
        assert holistic["stats"]["oferta_only_groups_count"] == 1

    def test_matching_orchestrator_v2_get_stats(self):
        """Should return copy of cached statistics."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1"}],
                }
            ],
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1"}],
                }
            ],
        }

        matcher.match(ref, oferta)

        stats = matcher.get_stats()
        assert stats["matched_groups"] == 1
        assert stats["matched_articles"] >= 0

        # Modifying returned stats should not affect internal state
        stats["matched_groups"] = 999
        assert matcher.stats["matched_groups"] == 1


class TestExtractionOrchestratorMatching:
    """Tests for ExtractionOrchestrator.match_reference_with_offer() method."""

    def test_orchestrator_has_matching_method(self):
        """Should have match_reference_with_offer method."""
        orchestrator = ExtractionOrchestrator()
        assert hasattr(orchestrator, "match_reference_with_offer")
        assert callable(orchestrator.match_reference_with_offer)

    def test_orchestrator_match_reference_with_offer_basic(self):
        """Should match reference with offer using orchestrator."""
        orchestrator = ExtractionOrchestrator()

        ref_extracted = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1", "descriere": "TEST"}],
                }
            ],
        }

        oferta_extracted = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1", "descriere": "TEST"}],
                }
            ],
        }

        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        # Check structure
        assert "matched_groups" in holistic
        assert "ref_only_groups" in holistic
        assert "oferta_only_groups" in holistic
        assert "stats" in holistic

        # Check content
        assert holistic["client"] == "Test"
        assert holistic["extraction_version"] == "2.0"

    def test_orchestrator_match_empty_grupos(self):
        """Should handle empty grupos gracefully."""
        orchestrator = ExtractionOrchestrator()

        ref_extracted = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        oferta_extracted = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        assert holistic["stats"]["matched_groups_count"] == 0
        assert holistic["stats"]["ref_only_groups_count"] == 0
        assert holistic["stats"]["oferta_only_groups_count"] == 0

    def test_orchestrator_match_multiple_groups(self):
        """Should match multiple groups correctly."""
        orchestrator = ExtractionOrchestrator()

        ref_extracted = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [
                        {"nr": "1", "descriere": "A1"},
                        {"nr": "2", "descriere": "A2"},
                    ],
                },
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [{"nr": "3", "descriere": "B1"}],
                },
                {
                    "deviz_cod": "0003",
                    "deviz_den": "C",
                    "articole": [{"nr": "4", "descriere": "C1"}],
                },
            ],
        }

        oferta_extracted = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"nr": "1", "descriere": "A1"}],
                },
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [
                        {"nr": "3", "descriere": "B1"},
                        {"nr": "5", "descriere": "B2"},
                    ],
                },
            ],
        }

        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        # 2 matched (0001, 0002), 1 ref-only (0003), 0 oferta-only
        assert holistic["stats"]["matched_groups_count"] == 2
        assert holistic["stats"]["ref_only_groups_count"] == 1
        assert holistic["stats"]["oferta_only_groups_count"] == 0

    def test_orchestrator_match_preserves_metadata(self):
        """Should preserve client and di_file metadata in holistic."""
        orchestrator = ExtractionOrchestrator()

        ref_extracted = {
            "client": "ClientName",
            "di_file": "di_referinta.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        oferta_extracted = {
            "client": "ClientName",
            "di_file": "di_oferta_1.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        assert holistic["client"] == "ClientName"
        assert holistic["di_file"] == "di_oferta_1.json"
        assert holistic["extraction_version"] == "2.0"


class TestExtractionV2WithMatchingIntegration:
    """Integration tests combining extraction and matching."""

    def test_full_extraction_and_matching_pipeline(self):
        """Should extract and match successfully in sequence."""
        # Create minimal DI JSON structures
        ref_di = {
            "pages": [
                {
                    "content": "Deviz 0001\nArticol 1\nArticol 2",
                    "lines": [
                        {"content": "Deviz 0001"},
                        {"content": "Articol 1"},
                        {"content": "Articol 2"},
                    ],
                    "deviz_cod": "0001",
                    "deviz_den": "Category A",
                }
            ]
        }

        oferta_di = {
            "pages": [
                {
                    "content": "Deviz 0001\nArticol 1",
                    "lines": [
                        {"content": "Deviz 0001"},
                        {"content": "Articol 1"},
                    ],
                    "deviz_cod": "0001",
                    "deviz_den": "Category A",
                }
            ]
        }

        orchestrator = ExtractionOrchestrator()

        # Extract
        ref_extracted = orchestrator.extract_from_di(ref_di, "TestClient")
        oferta_extracted = orchestrator.extract_from_di(oferta_di, "TestClient")

        # Verify extraction produced valid output
        assert "grupos" in ref_extracted
        assert "grupos" in oferta_extracted
        assert ref_extracted["client"] == "TestClient"

        # Match
        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        # Verify holistic structure
        assert "matched_groups" in holistic
        assert "stats" in holistic
        assert isinstance(holistic["stats"]["matched_groups_count"], int)

    def test_extraction_matching_with_empty_pages(self):
        """Should handle extraction and matching with empty pages."""
        ref_di = {"pages": []}
        oferta_di = {"pages": []}

        orchestrator = ExtractionOrchestrator()

        ref_extracted = orchestrator.extract_from_di(ref_di, "TestClient")
        oferta_extracted = orchestrator.extract_from_di(oferta_di, "TestClient")

        holistic = orchestrator.match_reference_with_offer(
            ref_extracted, oferta_extracted
        )

        # Should produce valid structure even with empty extraction
        assert holistic["stats"]["matched_groups_count"] == 0
        assert holistic["stats"]["ref_only_groups_count"] == 0
        assert holistic["stats"]["oferta_only_groups_count"] == 0


class TestMatchingOrchestratorV2EdgeCases:
    """Tests for edge cases in MatchingOrchestratorV2."""

    def test_matching_with_missing_articole(self):
        """Should handle groups with missing articole key."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A"}],  # No articole
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }

        holistic = matcher.match(ref, oferta)
        assert holistic["stats"]["matched_groups_count"] == 1

    def test_matching_with_empty_articole(self):
        """Should handle groups with empty articole list."""
        matcher = MatchingOrchestratorV2()

        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }

        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }

        holistic = matcher.match(ref, oferta)
        assert holistic["stats"]["matched_groups_count"] == 1
        assert holistic["stats"]["matched_articles_count"] == 0

    def test_matching_stats_update_on_each_call(self):
        """Should update stats on each match() call."""
        matcher = MatchingOrchestratorV2()

        # First match
        ref1 = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }
        oferta1 = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }

        matcher.match(ref1, oferta1)
        assert matcher.stats["matched_groups"] == 1

        # Second match with different data
        ref2 = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {"deviz_cod": "0001", "deviz_den": "A", "articole": []},
                {"deviz_cod": "0002", "deviz_den": "B", "articole": []},
            ],
        }
        oferta2 = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}],
        }

        matcher.match(ref2, oferta2)
        assert matcher.stats["matched_groups"] == 1  # Only 0001 matches
        assert matcher.stats["ref_only_groups"] == 1  # 0002 is ref-only
