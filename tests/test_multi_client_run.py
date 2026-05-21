import pytest
import json
from pathlib import Path
import tempfile
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.client_config import ClientConfig
from local_run import run_pipeline


class TestMultiClientRun:
    """Integration tests for multi-client pipeline."""

    @pytest.fixture
    def test_clients_dir(self):
        """Create temporary test clients with minimal data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_base = root / "input_AO"
            output_base = root / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            # Create 2 test clients
            for client_name in ["TestClient1", "TestClient2"]:
                client_input = input_base / client_name
                client_input.mkdir()

                # Minimal referinta with required structure
                referinta = {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {"content": "4.1 - Test Deviz"},
                                {"content": "TEST01 - Test Article"},
                                {"content": "1 buc"}
                            ]
                        }
                    ],
                    "tables": []
                }
                (client_input / "di_referinta.json").write_text(json.dumps(referinta))

                # Minimal oferta with same structure
                oferta = {
                    "pages": [
                        {
                            "page_number": 1,
                            "lines": [
                                {"content": "4.1 - Test Deviz"},
                                {"content": "TEST01 - Test Article"},
                                {"content": "1 buc"}
                            ]
                        }
                    ],
                    "tables": []
                }
                (client_input / "di_oferta_1.json").write_text(json.dumps(oferta))

            yield input_base, output_base

    def test_client_config_creation(self):
        """Test ClientConfig can be created and paths are correct."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir) / "input_AO"
            output_base = Path(tmpdir) / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            # Create test client structure
            client_input = input_base / "TestClient"
            client_input.mkdir()
            (client_input / "di_referinta.json").write_text(json.dumps({"pages": []}))

            config = ClientConfig.from_folder("TestClient", input_base, output_base)

            assert config.name == "TestClient"
            assert config.input_dir == client_input
            assert config.output_dir == output_base / "TestClient"
            assert config.checkpoint_dir == output_base / "TestClient" / "checkpoints"
            assert config.reference_file == client_input / "di_referinta.json"

    def test_client_config_ensure_output_dirs(self):
        """Test ClientConfig creates output directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir) / "input_AO"
            output_base = Path(tmpdir) / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            client_input = input_base / "TestClient"
            client_input.mkdir()
            (client_input / "di_referinta.json").write_text(json.dumps({"pages": []}))

            config = ClientConfig.from_folder("TestClient", input_base, output_base)

            assert not config.output_dir.exists()
            assert not config.checkpoint_dir.exists()

            config.ensure_output_dirs()

            assert config.output_dir.exists()
            assert config.checkpoint_dir.exists()

    def test_multiple_clients_isolated_checkpoints(self, test_clients_dir):
        """Verify each client has isolated checkpoints."""
        input_base, output_base = test_clients_dir

        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)

        config1.ensure_output_dirs()
        config2.ensure_output_dirs()

        assert config1.checkpoint_dir.exists()
        assert config2.checkpoint_dir.exists()
        assert config1.checkpoint_dir != config2.checkpoint_dir
        assert "TestClient1" in str(config1.checkpoint_dir)
        assert "TestClient2" in str(config2.checkpoint_dir)

    def test_multiple_clients_isolated_output_dirs(self, test_clients_dir):
        """Verify each client has isolated output directories."""
        input_base, output_base = test_clients_dir

        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)

        config1.ensure_output_dirs()
        config2.ensure_output_dirs()

        assert config1.output_dir != config2.output_dir
        assert "TestClient1" in str(config1.output_dir)
        assert "TestClient2" in str(config2.output_dir)

    def test_offer_files_detection(self, test_clients_dir):
        """Test ClientConfig correctly detects offer files."""
        input_base, output_base = test_clients_dir

        config = ClientConfig.from_folder("TestClient1", input_base, output_base)
        offer_files = config.list_offer_files()

        assert len(offer_files) == 1
        assert offer_files[0].name == "di_oferta_1.json"

    def test_detect_clients(self, test_clients_dir):
        """Test ClientConfig.detect_clients finds all clients."""
        input_base, output_base = test_clients_dir

        clients = ClientConfig.detect_clients(input_base)

        assert len(clients) == 2
        assert "TestClient1" in clients
        assert "TestClient2" in clients
        assert clients == sorted(clients)  # Should be sorted

    def test_validate_client_config(self, test_clients_dir):
        """Test ClientConfig.validate checks for reference file."""
        input_base, output_base = test_clients_dir

        # Valid client with reference
        config = ClientConfig.from_folder("TestClient1", input_base, output_base)
        assert config.validate() is True

        # Invalid client without reference
        invalid_input = input_base / "InvalidClient"
        invalid_input.mkdir()
        invalid_config = ClientConfig.from_folder("InvalidClient", input_base, output_base)
        assert invalid_config.validate() is False

    def test_per_client_reference_files(self, test_clients_dir):
        """Test each client has separate reference files."""
        input_base, output_base = test_clients_dir

        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)

        ref1 = json.loads(config1.reference_file.read_text())
        ref2 = json.loads(config2.reference_file.read_text())

        # Both should have same structure (they're created identically in fixture)
        assert "pages" in ref1
        assert "pages" in ref2

    def test_client_config_list_offer_files(self, test_clients_dir):
        """Test ClientConfig.list_offer_files returns correct files."""
        input_base, output_base = test_clients_dir

        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)

        files1 = config1.list_offer_files()
        files2 = config2.list_offer_files()

        assert len(files1) == 1
        assert len(files2) == 1
        assert files1[0].parent.name == "TestClient1"
        assert files2[0].parent.name == "TestClient2"

    def test_multiple_offers_per_client(self):
        """Test ClientConfig handles multiple offers per client."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir) / "input_AO"
            output_base = Path(tmpdir) / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            client_input = input_base / "TestClient"
            client_input.mkdir()

            # Create reference and multiple offers
            (client_input / "di_referinta.json").write_text(json.dumps({"pages": []}))
            (client_input / "di_oferta_1.json").write_text(json.dumps({"pages": []}))
            (client_input / "di_oferta_2.json").write_text(json.dumps({"pages": []}))
            (client_input / "di_oferta_3.json").write_text(json.dumps({"pages": []}))

            config = ClientConfig.from_folder("TestClient", input_base, output_base)
            offer_files = config.list_offer_files()

            assert len(offer_files) == 3
            assert all(f.name.startswith("di_oferta_") for f in offer_files)

    def test_client_isolation_no_cross_contamination(self, test_clients_dir):
        """Test that creating/reading one client doesn't affect another."""
        input_base, output_base = test_clients_dir

        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)

        # Ensure output dirs
        config1.ensure_output_dirs()

        # Verify config2's dirs don't exist yet
        assert not config2.output_dir.exists()
        assert not config2.checkpoint_dir.exists()

        # Ensure config2's dirs
        config2.ensure_output_dirs()

        # Verify they're different
        assert config1.output_dir.exists()
        assert config2.output_dir.exists()
        assert not config1.checkpoint_dir == config2.checkpoint_dir


class TestMultiClientDetection:
    """Tests for multi-client detection and discovery."""

    def test_detect_clients_empty_directory(self):
        """Test detect_clients with empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir)
            clients = ClientConfig.detect_clients(input_base)
            assert clients == []

    def test_detect_clients_nonexistent_directory(self):
        """Test detect_clients with nonexistent directory."""
        nonexistent = Path("/nonexistent/path/to/input_AO")
        clients = ClientConfig.detect_clients(nonexistent)
        assert clients == []

    def test_detect_clients_with_files_but_no_reference(self):
        """Test detect_clients ignores directories without di_referinta.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir)

            # Create dir with offers but no reference
            client_dir = input_base / "NoRefClient"
            client_dir.mkdir()
            (client_dir / "di_oferta_1.json").write_text(json.dumps({"pages": []}))

            clients = ClientConfig.detect_clients(input_base)
            assert clients == []

    def test_detect_clients_sorted_output(self):
        """Test detect_clients returns sorted list."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir)

            # Create clients in non-alphabetical order
            for name in ["Zebra", "Apple", "Banana"]:
                client_dir = input_base / name
                client_dir.mkdir()
                (client_dir / "di_referinta.json").write_text(json.dumps({"pages": []}))

            clients = ClientConfig.detect_clients(input_base)
            assert clients == ["Apple", "Banana", "Zebra"]


class TestClientConfigPathValidation:
    """Tests for ClientConfig path validation and sanitization."""

    def test_client_paths_with_special_characters(self):
        """Test ClientConfig handles client names with special characters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir) / "input_AO"
            output_base = Path(tmpdir) / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            client_name = "Client-Special_123"
            client_input = input_base / client_name
            client_input.mkdir()
            (client_input / "di_referinta.json").write_text(json.dumps({"pages": []}))

            config = ClientConfig.from_folder(client_name, input_base, output_base)
            assert config.name == client_name
            assert client_name in str(config.output_dir)

    def test_client_paths_are_absolute(self):
        """Test that ClientConfig paths are absolute."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_base = Path(tmpdir) / "input_AO"
            output_base = Path(tmpdir) / "output_AO"
            input_base.mkdir()
            output_base.mkdir()

            client_input = input_base / "TestClient"
            client_input.mkdir()
            (client_input / "di_referinta.json").write_text(json.dumps({"pages": []}))

            config = ClientConfig.from_folder("TestClient", input_base, output_base)

            assert config.input_dir.is_absolute()
            assert config.output_dir.is_absolute()
            assert config.checkpoint_dir.is_absolute()
            assert config.reference_file.is_absolute()
