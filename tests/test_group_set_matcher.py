"""Tests for group-level matching using deviz_cod with article-level matching.

Tests the match_groups_by_deviz() function which performs set operations
on deviz_cod to match groups, then uses set-based article matching within
each matched group.
"""

import pytest
from shared.group_set_matcher import match_groups_by_deviz


class TestMatchGroupsByDeviz:
    """Tests for group-level matching by deviz_cod."""

    def test_match_groups_by_deviz_basic(self):
        """Should match groups by deviz_cod and articles within."""
        ref_groups = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Excavation",
                "articole": [
                    {"nr": "1", "descriere": "EXCAVATOR", "um": "buc", "cant": "1"},
                    {"nr": "2", "descriere": "BULDOZER", "um": "buc", "cant": "1"},
                ],
            },
            {
                "deviz_cod": "0002",
                "deviz_den": "Transport",
                "articole": [
                    {"nr": "3", "descriere": "CAMION", "um": "buc", "cant": "2"},
                ],
            },
        ]

        oferta_groups = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Excavation",
                "articole": [
                    {"nr": "1", "descriere": "EXCAVATOR", "um": "buc", "cant": "1"},
                    {"nr": "4", "descriere": "GREDER", "um": "buc", "cant": "1"},
                ],
            },
            {
                "deviz_cod": "0003",
                "deviz_den": "Other",
                "articole": [
                    {"nr": "5", "descriere": "PALA", "um": "buc", "cant": "1"},
                ],
            },
        ]

        result = match_groups_by_deviz(ref_groups, oferta_groups)

        # Matched groups: 0001
        assert len(result["matched_groups"]) == 1
        assert result["matched_groups"][0]["deviz_cod"] == "0001"

        # Articles within matched group: nr=1 matched, nr=2 ref_only (implicit in stats)
        matched_articles = result["matched_groups"][0]["articole"]
        assert len(matched_articles) == 1
        assert matched_articles[0]["ref"]["nr"] == "1"

        # Ref-only groups: 0002
        assert len(result["ref_only_groups"]) == 1
        assert result["ref_only_groups"][0]["deviz_cod"] == "0002"

        # Oferta-only groups: 0003
        assert len(result["oferta_only_groups"]) == 1
        assert result["oferta_only_groups"][0]["deviz_cod"] == "0003"

    def test_no_matched_groups(self):
        """Should handle disjoint deviz_cod sets."""
        ref = [{"deviz_cod": "0001", "deviz_den": "A", "articole": []}]
        oferta = [{"deviz_cod": "0002", "deviz_den": "B", "articole": []}]

        result = match_groups_by_deviz(ref, oferta)

        assert len(result["matched_groups"]) == 0
        assert len(result["ref_only_groups"]) == 1
        assert len(result["oferta_only_groups"]) == 1

    def test_all_matched_groups(self):
        """Should match all groups when deviz_cod sets are identical."""
        groups = [
            {
                "deviz_cod": "0001",
                "deviz_den": "A",
                "articole": [{"nr": "1", "descriere": "Item1"}],
            },
            {
                "deviz_cod": "0002",
                "deviz_den": "B",
                "articole": [{"nr": "2", "descriere": "Item2"}],
            },
        ]

        result = match_groups_by_deviz(groups, groups)

        assert len(result["matched_groups"]) == 2
        assert len(result["ref_only_groups"]) == 0
        assert len(result["oferta_only_groups"]) == 0

    def test_empty_groups(self):
        """Should handle empty group lists."""
        result = match_groups_by_deviz([], [])

        assert len(result["matched_groups"]) == 0
        assert len(result["ref_only_groups"]) == 0
        assert len(result["oferta_only_groups"]) == 0
        assert "matched_groups" in result
        assert "ref_only_groups" in result
        assert "oferta_only_groups" in result

    def test_matched_group_preserves_metadata(self):
        """Matched groups should preserve deviz_cod and deviz_den."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Excavation Works",
                "articole": [{"nr": "1", "descriere": "A"}],
            }
        ]
        oferta = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Excavation Works",
                "articole": [{"nr": "1", "descriere": "A"}],
            }
        ]

        result = match_groups_by_deviz(ref, oferta)

        matched = result["matched_groups"][0]
        assert matched["deviz_cod"] == "0001"
        assert matched["deviz_den"] == "Excavation Works"

    def test_matched_group_includes_article_stats(self):
        """Matched groups should include article-level statistics."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "articole": [
                    {"nr": "1", "descriere": "A"},
                    {"nr": "2", "descriere": "B"},
                ],
            }
        ]
        oferta = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "articole": [{"nr": "1", "descriere": "A"}],
            }
        ]

        result = match_groups_by_deviz(ref, oferta)

        matched = result["matched_groups"][0]
        stats = matched["stats"]

        assert stats["matched_count"] == 1
        assert stats["ref_only_count"] == 1
        assert stats["oferta_only_count"] == 0
        assert stats["ref_total"] == 2
        assert stats["oferta_total"] == 1

    def test_multiple_matched_groups(self):
        """Should handle multiple matched groups."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "A",
                "articole": [{"nr": "1", "descriere": "Item1"}],
            },
            {
                "deviz_cod": "0002",
                "deviz_den": "B",
                "articole": [{"nr": "2", "descriere": "Item2"}],
            },
            {
                "deviz_cod": "0003",
                "deviz_den": "C",
                "articole": [{"nr": "3", "descriere": "Item3"}],
            },
        ]
        oferta = [
            {
                "deviz_cod": "0001",
                "deviz_den": "A",
                "articole": [{"nr": "1", "descriere": "Item1"}],
            },
            {
                "deviz_cod": "0003",
                "deviz_den": "C",
                "articole": [{"nr": "3", "descriere": "Item3"}],
            },
        ]

        result = match_groups_by_deviz(ref, oferta)

        assert len(result["matched_groups"]) == 2
        assert len(result["ref_only_groups"]) == 1
        assert len(result["oferta_only_groups"]) == 0

        # Check matched devizes are sorted
        matched_devizes = [g["deviz_cod"] for g in result["matched_groups"]]
        assert matched_devizes == ["0001", "0003"]

    def test_ref_only_groups_preserve_structure(self):
        """Ref-only groups should preserve complete structure."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "extra_field": "value",
                "articole": [
                    {"nr": "1", "descriere": "Item1"},
                    {"nr": "2", "descriere": "Item2"},
                ],
            }
        ]
        oferta = []

        result = match_groups_by_deviz(ref, oferta)

        ref_only = result["ref_only_groups"][0]
        assert ref_only["deviz_cod"] == "0001"
        assert ref_only["deviz_den"] == "Works"
        assert ref_only["extra_field"] == "value"
        assert len(ref_only["articole"]) == 2

    def test_oferta_only_groups_preserve_structure(self):
        """Oferta-only groups should preserve complete structure."""
        oferta = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "extra_field": "value",
                "articole": [
                    {"nr": "1", "descriere": "Item1"},
                    {"nr": "2", "descriere": "Item2"},
                ],
            }
        ]
        ref = []

        result = match_groups_by_deviz(ref, oferta)

        oferta_only = result["oferta_only_groups"][0]
        assert oferta_only["deviz_cod"] == "0001"
        assert oferta_only["deviz_den"] == "Works"
        assert oferta_only["extra_field"] == "value"
        assert len(oferta_only["articole"]) == 2

    def test_result_structure(self):
        """Result should have expected top-level keys."""
        result = match_groups_by_deviz([], [])

        assert "matched_groups" in result
        assert "ref_only_groups" in result
        assert "oferta_only_groups" in result
        assert isinstance(result["matched_groups"], list)
        assert isinstance(result["ref_only_groups"], list)
        assert isinstance(result["oferta_only_groups"], list)

    def test_matched_group_structure(self):
        """Matched groups should have expected keys."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "articole": [{"nr": "1", "descriere": "Item"}],
            }
        ]

        result = match_groups_by_deviz(ref, ref)
        matched = result["matched_groups"][0]

        assert "deviz_cod" in matched
        assert "deviz_den" in matched
        assert "articole" in matched
        assert "stats" in matched

    def test_matched_group_articole_list(self):
        """Matched groups articole should be list of {ref, oferta} pairs."""
        ref = [
            {
                "deviz_cod": "0001",
                "deviz_den": "Works",
                "articole": [{"nr": "1", "descriere": "Item"}],
            }
        ]

        result = match_groups_by_deviz(ref, ref)
        articole = result["matched_groups"][0]["articole"]

        assert isinstance(articole, list)
        assert len(articole) == 1
        pair = articole[0]
        assert "ref" in pair
        assert "oferta" in pair

    def test_groups_sorted_by_deviz_cod(self):
        """Matched groups should be sorted by deviz_cod (ref side)."""
        ref = [
            {"deviz_cod": "0003", "deviz_den": "C", "articole": [{"cod": "C001", "descriere": "C"}]},
            {"deviz_cod": "0001", "deviz_den": "A", "articole": [{"cod": "A001", "descriere": "A"}]},
            {"deviz_cod": "0002", "deviz_den": "B", "articole": [{"cod": "B001", "descriere": "B"}]},
        ]

        result = match_groups_by_deviz(ref, ref)

        devizes = [g["deviz_cod"] for g in result["matched_groups"]]
        assert devizes == ["0001", "0002", "0003"]

    def test_empty_articole_in_groups(self):
        """Empty groups with same deviz_cod match via fallback; different deviz_cod → unmatched."""
        ref = [{"deviz_cod": "0001", "deviz_den": "Works", "articole": []}]
        oferta = [{"deviz_cod": "0001", "deviz_den": "Works", "articole": []}]

        result = match_groups_by_deviz(ref, oferta)

        # same deviz_cod + no header text → fallback exact match
        assert len(result["matched_groups"]) == 1
        assert result["matched_groups"][0]["stats"]["matched_count"] == 0

    def test_complex_scenario(self):
        """Should handle complex scenario with mixed matches."""
        ref = [
            {
                "deviz_cod": "A001",
                "deviz_den": "Foundation",
                "articole": [
                    {"nr": "1", "descriere": "Concrete"},
                    {"nr": "2", "descriere": "Rebar"},
                ],
            },
            {
                "deviz_cod": "A002",
                "deviz_den": "Walls",
                "articole": [
                    {"nr": "3", "descriere": "Bricks"},
                ],
            },
            {
                "deviz_cod": "A003",
                "deviz_den": "Roof",
                "articole": [
                    {"nr": "4", "descriere": "Tiles"},
                ],
            },
        ]
        oferta = [
            {
                "deviz_cod": "A001",
                "deviz_den": "Foundation",
                "articole": [
                    {"nr": "1", "descriere": "Concrete"},
                    {"nr": "5", "descriere": "Fasteners"},
                ],
            },
            {
                "deviz_cod": "A002",
                "deviz_den": "Walls",
                "articole": [
                    {"nr": "3", "descriere": "Bricks"},
                    {"nr": "6", "descriere": "Mortar"},
                ],
            },
            {
                "deviz_cod": "A004",
                "deviz_den": "Windows",
                "articole": [
                    {"nr": "7", "descriere": "Glass"},
                ],
            },
        ]

        result = match_groups_by_deviz(ref, oferta)

        # Check matched groups
        assert len(result["matched_groups"]) == 2
        assert {g["deviz_cod"] for g in result["matched_groups"]} == {"A001", "A002"}

        # Check ref-only groups
        assert len(result["ref_only_groups"]) == 1
        assert result["ref_only_groups"][0]["deviz_cod"] == "A003"

        # Check oferta-only groups
        assert len(result["oferta_only_groups"]) == 1
        assert result["oferta_only_groups"][0]["deviz_cod"] == "A004"

        # Check article matching within matched groups
        a001_matched = next(
            g for g in result["matched_groups"] if g["deviz_cod"] == "A001"
        )
        assert len(a001_matched["articole"]) == 1  # nr=1 matched
        assert a001_matched["stats"]["ref_only_count"] == 1  # nr=2
        assert a001_matched["stats"]["oferta_only_count"] == 1  # nr=5


class TestResidualN1Matching:
    """Tests for residual N:1 matching — offer group merges multiple ref categories."""

    def test_residual_ref_group_matched_via_oferta_only(self):
        """Offer group merges two ref groups — residual N:1 links second ref to same offer.

        Ref has A (TSG01XA, TSE05XC) and B (bazin, wc).
        Offer has X (all 4 articles). Primary: X→B (categoria text match). Residual: A→X.
        """
        ref = [
            {
                "deviz_cod": "A",
                "deviz_den": "Amenajarea terenului",
                "categoria": "Amenajarea terenului",
                "obiectul": "CAV",
                "articole": [
                    {"nr": "1", "cod": "TSG01XA", "descriere": "Degajarea terenului"},
                    {"nr": "2", "cod": "TSE05XC", "descriere": "Nivelarea"},
                ],
            },
            {
                "deviz_cod": "B",
                "deviz_den": "Organizare santier",
                "categoria": "Lucrari de constructii si instalatii aferente organizarii de santier",
                "obiectul": "CAV",
                "articole": [
                    {"nr": "3", "cod": "$4537027", "descriere": "Bazin"},
                    {"nr": "4", "cod": "$4537028", "descriere": "Wc ecologic"},
                ],
            },
        ]
        oferta = [
            {
                "deviz_cod": "X",
                "deviz_den": "Organizare santier general",
                "categoria": "Lucrari de constructii si instalatii aferente organizarii de santier",
                "obiectul": "CAV",
                "articole": [
                    {"nr": "1", "cod": "TSG01XA", "descriere": "Degajarea terenului"},
                    {"nr": "2", "cod": "TSE05XC", "descriere": "Nivelarea"},
                    {"nr": "3", "cod": "$4537027", "descriere": "Bazin"},
                    {"nr": "4", "cod": "$4537028", "descriere": "Wc ecologic"},
                ],
            }
        ]

        result = match_groups_by_deviz(ref, oferta)

        # Both ref groups matched — no ref_only_groups
        assert len(result["ref_only_groups"]) == 0
        # X used for both primary + residual — not in oferta_only
        assert len(result["oferta_only_groups"]) == 0
        # Two matched_group entries (primary + residual)
        assert len(result["matched_groups"]) == 2

        primary = next(g for g in result["matched_groups"] if g.get("match_type") != "residual_n1")
        residual = next(g for g in result["matched_groups"] if g.get("match_type") == "residual_n1")

        # Primary: B→X (categoria text identity)
        assert primary["deviz_cod"] == "B"
        assert primary["oferta_deviz_cod"] == "X"
        assert len(primary["articole"]) == 2  # nr=3,4 matched
        assert primary["stats"]["oferta_only_count"] == 0  # removed by residual pass

        # Residual: A→X (TSG01XA, TSE05XC from X's oferta_only)
        assert residual["deviz_cod"] == "A"
        assert residual["oferta_deviz_cod"] == "X"
        assert residual["match_type"] == "residual_n1"
        assert len(residual["articole"]) == 2  # nr=1,2 matched
        assert len(residual["ref_only"]) == 0
        assert len(residual["oferta_only"]) == 0

    def test_residual_no_match_when_articles_absent(self):
        """Ref group B whose articles are not in any offer group's oferta_only stays ref_only."""
        ref = [
            {
                "deviz_cod": "A",
                "deviz_den": "Group A",
                "categoria": "Category A",
                "obiectul": "OBJ",
                "articole": [{"nr": "1", "descriere": "Art1"}],
            },
            {
                "deviz_cod": "B",
                "deviz_den": "Group B",
                "categoria": "Category B completely different",
                "obiectul": "OBJ",
                "articole": [{"nr": "99", "descriere": "Completely different article"}],
            },
        ]
        oferta = [
            {
                "deviz_cod": "X",
                "deviz_den": "Group X",
                "categoria": "Category A",
                "obiectul": "OBJ",
                "articole": [{"nr": "1", "descriere": "Art1"}],
            }
        ]

        result = match_groups_by_deviz(ref, oferta)

        # Primary: X→A (1:1). B has nr=99 not in X's oferta_only → stays ref_only.
        assert len(result["matched_groups"]) == 1
        assert len(result["ref_only_groups"]) == 1
        assert result["ref_only_groups"][0]["deviz_cod"] == "B"
        # X oferta_only empty after 1:1 match — primary stats unchanged
        assert result["matched_groups"][0]["stats"]["oferta_only_count"] == 0

    def test_residual_partial_coverage_below_threshold_stays_unmatched(self):
        """Ref group with ≤ 50% (< 60% threshold) articles in offer oferta_only stays unmatched.

        RESIDUAL_THRESHOLD = 0.6. A 2-article ref group with only 1 found (50%) must stay ref_only.
        This prevents OCR artefact groups (e.g. eDevize with 2 articles) from spuriously matching.
        """
        ref = [
            {
                "deviz_cod": "A",
                "deviz_den": "Group A",
                "categoria": "Category A",
                "obiectul": "OBJ",
                "articole": [{"nr": "1", "descriere": "Art1"}],
            },
            {
                "deviz_cod": "B",
                "deviz_den": "OCR artefact group",
                "categoria": "Category B very different text",
                "obiectul": "OBJ",
                # 2 articles; only 1 in offer oferta_only → 50% < 60% threshold
                "articole": [
                    {"nr": "10", "descriere": "Art10"},
                    {"nr": "11", "descriere": "Art11"},
                ],
            },
        ]
        oferta = [
            {
                "deviz_cod": "X",
                "deviz_den": "Group X",
                "categoria": "Category A",
                "obiectul": "OBJ",
                # Only 1 of B's 2 articles present → 50% coverage < 60% threshold
                "articole": [
                    {"nr": "1", "descriere": "Art1"},
                    {"nr": "10", "descriere": "Art10"},
                ],
            }
        ]

        result = match_groups_by_deviz(ref, oferta)

        # Primary: X→A (1:1). X oferta_only has nr=10 (1 of B's 2 articles = 50% < 60%)
        assert len(result["matched_groups"]) == 1
        assert len(result["ref_only_groups"]) == 1
        assert result["ref_only_groups"][0]["deviz_cod"] == "B"
