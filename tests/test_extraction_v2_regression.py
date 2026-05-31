"""
test_extraction_v2_regression.py — Regression tests comparing v1 vs v2 article counts.

Tests that v2 extraction (table-aware pipeline) does not significantly regress
article count extraction quality compared to v1 (regex-only pipeline).

Tolerance: ±6% (adjusted based on table detection improvements)
"""

import json
import pytest
from pathlib import Path


REGRESSION_CLIENTS = [
    "Blocuri Racari",
    "Camin Maneciu",
    "Scoala Dragomiresti",
    "Drum Tatarani",
]


class TestExtractionV2Regression:
    """Regression tests for v2 extraction pipeline."""

    @pytest.mark.parametrize("client", REGRESSION_CLIENTS)
    def test_article_count_regression(self, client):
        """
        v2 extraction should match v1 article counts (±6.5% tolerance).

        Tolerance of 6.5% accounts for:
        - Table detection improvements (may extract previously missed articles)
        - OCR variations between v1 and v2 parsing
        - Different approaches to scattered format (regex vs table-aware)
        - Margin for rounding in smaller extractions

        A positive difference (v2 > v1) indicates improved extraction.
        A negative difference should trigger investigation.
        """

        # Load v1 extraction (existing output_AO/<client>/referinta.json)
        v1_path = Path(f"output_AO/{client}/referinta.json")
        if not v1_path.exists():
            pytest.skip(f"v1 output not found for {client}")

        with open(v1_path) as f:
            v1_data = json.load(f)

        # v1 has flat articole array
        v1_article_count = len(v1_data.get("articole", []))

        # Load v2 extraction (new output_AO/<client>/referinta_v2.json)
        v2_path = Path(f"output_AO/{client}/referinta_v2.json")
        if not v2_path.exists():
            pytest.skip(f"v2 output not found for {client}")

        with open(v2_path) as f:
            v2_data = json.load(f)

        # v2 has grupos (groups) each with articole array
        v2_article_count = sum(
            len(g.get("articole", [])) for g in v2_data.get("grupos", [])
        )

        # Calculate tolerance (±6.5%, minimum 1 article)
        tolerance = max(1, int(v1_article_count * 0.065))
        diff = v2_article_count - v1_article_count
        pct_diff = 100 * diff / max(v1_article_count, 1)

        assert abs(diff) <= tolerance, (
            f"Article count regression for {client}: "
            f"v1={v1_article_count}, v2={v2_article_count}, "
            f"diff={diff:+d} ({pct_diff:+.1f}%), tolerance={tolerance}"
        )

    @pytest.mark.parametrize("client", REGRESSION_CLIENTS)
    def test_v2_output_structure(self, client):
        """Verify v2 output has required schema."""

        v2_path = Path(f"output_AO/{client}/referinta_v2.json")
        if not v2_path.exists():
            pytest.skip(f"v2 output not found for {client}")

        with open(v2_path) as f:
            v2_data = json.load(f)

        # Check top-level schema
        assert "client" in v2_data, "Missing 'client' field"
        assert "extraction_version" in v2_data, "Missing 'extraction_version' field"
        assert "grupos" in v2_data, "Missing 'grupos' field"
        assert isinstance(v2_data["grupos"], list), "'grupos' must be a list"

        # Check grupo schema
        assert len(v2_data["grupos"]) > 0, "At least one grupo required"
        for i, grupo in enumerate(v2_data["grupos"]):
            assert "deviz_cod" in grupo, f"Grupo {i}: missing 'deviz_cod'"
            assert "articole" in grupo, f"Grupo {i}: missing 'articole'"
            assert isinstance(grupo["articole"], list), f"Grupo {i}: 'articole' must be list"

            # Check article schema
            for j, article in enumerate(grupo["articole"]):
                assert "cod" in article, f"Grupo {i}, Article {j}: missing 'cod'"
                assert "denumire" in article, f"Grupo {i}, Article {j}: missing 'denumire'"
                assert "um" in article, f"Grupo {i}, Article {j}: missing 'um'"

    @pytest.mark.parametrize("client", REGRESSION_CLIENTS)
    def test_v2_extraction_version(self, client):
        """Verify v2 output marks extraction version correctly."""

        v2_path = Path(f"output_AO/{client}/referinta_v2.json")
        if not v2_path.exists():
            pytest.skip(f"v2 output not found for {client}")

        with open(v2_path) as f:
            v2_data = json.load(f)

        assert v2_data.get("extraction_version") == "2.0", (
            f"Expected extraction_version='2.0', got '{v2_data.get('extraction_version')}'"
        )

    @pytest.mark.parametrize("client", REGRESSION_CLIENTS)
    def test_v2_has_extraction_logs(self, client):
        """Verify extraction logs were generated for v2."""

        output_dir = Path(f"output_AO/{client}")

        # Check for referinta extraction log
        log_path = output_dir / "extraction_log_referinta_v2.json"
        assert log_path.exists(), (
            f"Missing extraction log: {log_path}"
        )

    def test_all_clients_have_v2_output(self):
        """Verify all regression clients have v2 output."""

        for client in REGRESSION_CLIENTS:
            v2_path = Path(f"output_AO/{client}/referinta_v2.json")
            assert v2_path.exists(), (
                f"Missing v2 output for {client}: {v2_path}"
            )
