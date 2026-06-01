"""Tests for holistic JSON generator from v2 extraction + matching results.

Tests the generate_holistic_v2() function which converts v2 extracted data
(reference + offer with groups and articles) into v1-compatible holistic JSON
with matched_groups, ref_only_groups, oferta_only_groups, and aggregated stats.
"""

import pytest
from shared.holistic_generator import generate_holistic_v2


class TestGenerateHolisticV2:
    """Tests for holistic JSON generation from v2 matching results."""

    def test_generate_holistic_v2_basic(self):
        """Should generate holistic JSON with matched groups."""
        ref_extracted = {
            "client": "Drum Tatarani",
            "di_file": "di_referinta.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "Excavation",
                    "articole": [
                        {"nr": "1", "descriere": "EXCAVATOR"},
                        {"nr": "2", "descriere": "BULDOZER"},
                    ],
                }
            ],
        }

        oferta_extracted = {
            "client": "Drum Tatarani",
            "di_file": "di_oferta_1.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "Excavation",
                    "articole": [
                        {"nr": "1", "descriere": "EXCAVATOR"},
                    ],
                }
            ],
        }

        holistic = generate_holistic_v2(ref_extracted, oferta_extracted)

        # Check structure
        assert "client" in holistic
        assert "di_file" in holistic
        assert "extraction_version" in holistic
        assert "matched_groups" in holistic
        assert "ref_only_groups" in holistic
        assert "oferta_only_groups" in holistic
        assert "stats" in holistic

        # Check basic properties
        assert holistic["client"] == "Drum Tatarani"
        assert holistic["extraction_version"] == "2.0"
        assert holistic["di_file"] == "di_oferta_1.json"

    def test_holistic_matched_groups_preserved(self):
        """Matched groups should preserve deviz_cod and deviz_den."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "Works",
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
                    "deviz_den": "Works",
                    "articole": [{"nr": "1"}],
                }
            ],
        }

        holistic = generate_holistic_v2(ref, oferta)

        assert len(holistic["matched_groups"]) == 1
        matched = holistic["matched_groups"][0]
        assert matched["deviz_cod"] == "0001"
        assert matched["deviz_den"] == "Works"

    def test_holistic_stats_article_counts(self):
        """Stats should have correct article counts."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [
                        {"nr": "1"},
                        {"nr": "2"},
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
                        {"nr": "1"},
                    ],
                }
            ],
        }

        holistic = generate_holistic_v2(ref, oferta)

        stats = holistic["stats"]
        assert stats["matched_articles_count"] == 1
        assert stats["ref_only_articles_count"] == 1
        assert stats["oferta_only_articles_count"] == 0

    def test_holistic_empty_grupos(self):
        """Should handle empty groups lists."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [],
        }
        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        holistic = generate_holistic_v2(ref, oferta)

        assert len(holistic["matched_groups"]) == 0
        assert len(holistic["ref_only_groups"]) == 0
        assert len(holistic["oferta_only_groups"]) == 0
        assert holistic["stats"]["matched_articles_count"] == 0

    def test_holistic_ref_only_groups(self):
        """Should populate ref_only_groups correctly."""
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
            "grupos": [],
        }

        holistic = generate_holistic_v2(ref, oferta)

        assert len(holistic["ref_only_groups"]) == 1
        assert holistic["ref_only_groups"][0]["deviz_cod"] == "0001"
        assert holistic["stats"]["ref_only_articles_count"] == 1

    def test_holistic_oferta_only_groups(self):
        """Should populate oferta_only_groups correctly."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [],
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

        holistic = generate_holistic_v2(ref, oferta)

        assert len(holistic["oferta_only_groups"]) == 1
        assert holistic["oferta_only_groups"][0]["deviz_cod"] == "0001"
        assert holistic["stats"]["oferta_only_articles_count"] == 1

    def test_holistic_multiple_groups_mixed(self):
        """Should handle mixed scenario with matched, ref_only, oferta_only."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"cod": "SA001"}, {"cod": "SA002"}],
                },
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [{"cod": "SA003"}],
                },
                {
                    "deviz_cod": "0003",
                    "deviz_den": "C",
                    "articole": [{"cod": "SA004"}],
                },
            ],
        }
        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "X001",
                    "deviz_den": "A",
                    "articole": [{"cod": "SA001"}],  # SA001 matches ref 0001
                },
                {
                    "deviz_cod": "X002",
                    "deviz_den": "B",
                    "articole": [{"cod": "SA003"}],  # SA003 matches ref 0002
                },
                {
                    "deviz_cod": "X004",
                    "deviz_den": "D",
                    "articole": [{"cod": "SA999"}],  # no match
                },
            ],
        }

        holistic = generate_holistic_v2(ref, oferta)

        # Check group counts
        assert len(holistic["matched_groups"]) == 2  # 0001↔X001, 0002↔X002
        assert len(holistic["ref_only_groups"]) == 1  # 0003
        assert len(holistic["oferta_only_groups"]) == 1  # X004

        # Check article counts
        assert holistic["stats"]["matched_articles_count"] == 2  # 1 + 1
        assert holistic["stats"]["ref_only_articles_count"] == 2  # SA002 + SA004
        assert holistic["stats"]["oferta_only_articles_count"] == 1  # SA999

    def test_holistic_stats_group_counts(self):
        """Stats should have correct group counts (content-based matching)."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "articole": [{"cod": "SA001"}],
                },
                {
                    "deviz_cod": "0002",
                    "deviz_den": "B",
                    "articole": [{"cod": "SA002"}],
                },
            ],
        }
        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "X001",
                    "deviz_den": "A",
                    "articole": [{"cod": "SA001"}],  # SA001 matches ref 0001
                },
            ],
        }

        holistic = generate_holistic_v2(ref, oferta)

        assert holistic["stats"]["matched_groups_count"] == 1
        assert holistic["stats"]["ref_only_groups_count"] == 1
        assert holistic["stats"]["oferta_only_groups_count"] == 0

    def test_holistic_preserves_group_metadata(self):
        """Groups should preserve all metadata fields (content-based matching)."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "0001",
                    "deviz_den": "A",
                    "source_pages": [1, 2],
                    "extra_field": "value",
                    "articole": [{"cod": "SA001"}],
                }
            ],
        }
        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [
                {
                    "deviz_cod": "X001",
                    "deviz_den": "A",
                    "source_pages": [3],
                    "articole": [{"cod": "SA001"}],  # SA001 matches ref 0001
                }
            ],
        }

        holistic = generate_holistic_v2(ref, oferta)

        ref_only = holistic["ref_only_groups"]
        assert len(ref_only) == 0  # Should not have ref_only in this case

        # Check matched group structure
        matched = holistic["matched_groups"][0]
        assert "deviz_cod" in matched
        assert "deviz_den" in matched
        assert "articole" in matched

    def test_holistic_stats_structure(self):
        """Stats should have all required fields."""
        ref = {
            "client": "Test",
            "di_file": "ref.json",
            "extraction_version": "2.0",
            "grupos": [],
        }
        oferta = {
            "client": "Test",
            "di_file": "off.json",
            "extraction_version": "2.0",
            "grupos": [],
        }

        holistic = generate_holistic_v2(ref, oferta)

        stats = holistic["stats"]
        assert "matched_articles_count" in stats
        assert "ref_only_articles_count" in stats
        assert "oferta_only_articles_count" in stats
        assert "matched_groups_count" in stats
        assert "ref_only_groups_count" in stats
        assert "oferta_only_groups_count" in stats

    def test_holistic_matched_groups_contain_articole(self):
        """Matched groups should contain articole field."""
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

        holistic = generate_holistic_v2(ref, oferta)

        matched = holistic["matched_groups"][0]
        assert "articole" in matched
        assert isinstance(matched["articole"], list)
