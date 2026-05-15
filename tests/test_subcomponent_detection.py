import pytest
from shared.f3_regex_parser import SUBCOMP_EXPLICIT_MARKER_RE, SUBCOMP_SUFFIX_RE, HIERARCHY_CODE_RE

class TestSubcomponentDetection:

    def test_explicit_marker_detection(self):
        """Test detection of >>> componenta markers."""
        line = ">>> componenta 0C1"
        assert SUBCOMP_EXPLICIT_MARKER_RE.search(line)

        line2 = ">>> component 002"
        assert SUBCOMP_EXPLICIT_MARKER_RE.search(line2)

        line3 = "011 PF04A1 ASIN"
        assert not SUBCOMP_EXPLICIT_MARKER_RE.search(line3)

    def test_suffix_detection(self):
        """Test detection of .L suffix (e.g., 17.L)."""
        assert SUBCOMP_SUFFIX_RE.match("17.L")
        assert SUBCOMP_SUFFIX_RE.match("19.L")
        assert not SUBCOMP_SUFFIX_RE.match("17")
        assert not SUBCOMP_SUFFIX_RE.match("17.X")

    def test_hierarchy_detection(self):
        """Test detection of numeric hierarchy (1.1, 2.3)."""
        assert HIERARCHY_CODE_RE.match("1.1")
        assert HIERARCHY_CODE_RE.match("2.3")
        assert HIERARCHY_CODE_RE.match("10.5")
        assert not HIERARCHY_CODE_RE.match("1")
        assert not HIERARCHY_CODE_RE.match("ACD04C1")
