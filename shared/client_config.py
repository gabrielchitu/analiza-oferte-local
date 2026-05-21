from pathlib import Path
from typing import List


class ClientConfig:
    def __init__(
        self,
        name: str,
        input_dir: Path,
        output_dir: Path,
        checkpoint_dir: Path,
        reference_file: Path,
        offer_files: List[Path],
    ):
        self.name = name
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.reference_file = Path(reference_file)
        self.offer_files = [Path(f) for f in offer_files]

    @staticmethod
    def detect_clients(input_base: Path) -> List[str]:
        input_base = Path(input_base)
        if not input_base.exists():
            return []
        clients = []
        for item in input_base.iterdir():
            if item.is_dir():
                referinta = item / "di_referinta.json"
                if referinta.exists():
                    clients.append(item.name)
        return sorted(clients)

    @staticmethod
    def from_folder(
        client_name: str,
        input_base: Path,
        output_base: Path,
    ) -> "ClientConfig":
        input_base = Path(input_base)
        output_base = Path(output_base)
        input_dir = input_base / client_name
        output_dir = output_base / client_name
        checkpoint_dir = output_dir / "checkpoints"
        reference_file = input_dir / "di_referinta.json"
        offer_files = sorted(input_dir.glob("di_oferta_*.json"))
        return ClientConfig(
            name=client_name,
            input_dir=input_dir,
            output_dir=output_dir,
            checkpoint_dir=checkpoint_dir,
            reference_file=reference_file,
            offer_files=offer_files,
        )

    def validate(self) -> bool:
        return self.reference_file.exists()

    def list_offer_files(self) -> List[Path]:
        return self.offer_files

    def ensure_output_dirs(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
