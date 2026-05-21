import pytest
from pathlib import Path
import tempfile
import json
from shared.client_config import ClientConfig

class TestClientConfigDetectClients:
    def test_detect_clients_finds_all_folders_with_referinta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input_AO"
            input_dir.mkdir()
            (input_dir / "Blocuri Racari").mkdir()
            (input_dir / "Blocuri Racari" / "di_referinta.json").write_text('{}')
            (input_dir / "Camin Maneciu").mkdir()
            (input_dir / "Camin Maneciu" / "di_referinta.json").write_text('{}')
            (input_dir / "InvalidClient").mkdir()
            clients = ClientConfig.detect_clients(input_dir)
            assert sorted(clients) == ["Blocuri Racari", "Camin Maneciu"]

    def test_detect_clients_empty_input_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input_AO"
            input_dir.mkdir()
            clients = ClientConfig.detect_clients(input_dir)
            assert clients == []

class TestClientConfigFromFolder:
    def test_from_folder_resolves_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input_AO" / "Test Client"
            output_dir = root / "output_AO" / "Test Client"
            input_dir.mkdir(parents=True)
            (input_dir / "di_referinta.json").write_text('{}')
            (input_dir / "di_oferta_1.json").write_text('{}')
            (input_dir / "di_oferta_2.json").write_text('{}')
            config = ClientConfig.from_folder(
                client_name="Test Client",
                input_base=root / "input_AO",
                output_base=root / "output_AO"
            )
            assert config.name == "Test Client"
            assert config.input_dir == input_dir
            assert config.output_dir == output_dir
            assert config.checkpoint_dir == output_dir / "checkpoints"
            assert config.reference_file == input_dir / "di_referinta.json"

class TestClientConfigListOffers:
    def test_list_offer_files_finds_all_di_oferta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input_AO" / "Test"
            input_dir.mkdir(parents=True)
            (input_dir / "di_referinta.json").write_text('{}')
            (input_dir / "di_oferta_1.json").write_text('{}')
            (input_dir / "di_oferta_2.json").write_text('{}')
            (input_dir / "other_file.json").write_text('{}')
            config = ClientConfig.from_folder(
                client_name="Test",
                input_base=root / "input_AO",
                output_base=root / "output_AO"
            )
            offers = config.list_offer_files()
            assert len(offers) == 2
            assert all(f.name.startswith("di_oferta_") for f in offers)

class TestClientConfigValidate:
    def test_validate_success_with_all_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input_AO" / "Test"
            input_dir.mkdir(parents=True)
            (input_dir / "di_referinta.json").write_text('{}')
            config = ClientConfig.from_folder(
                client_name="Test",
                input_base=root / "input_AO",
                output_base=root / "output_AO"
            )
            assert config.validate() is True

    def test_validate_fails_without_referinta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            input_dir = root / "input_AO" / "Test"
            input_dir.mkdir(parents=True)
            config = ClientConfig.from_folder(
                client_name="Test",
                input_base=root / "input_AO",
                output_base=root / "output_AO"
            )
            assert config.validate() is False
