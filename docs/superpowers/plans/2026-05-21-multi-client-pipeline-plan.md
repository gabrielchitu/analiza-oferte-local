# Multi-Client Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the offer analysis pipeline from single-hardcoded-client to multi-client mode with interactive selection and per-client output directories.

**Architecture:** Create `ClientConfig` class to encapsulate client-specific paths, refactor `local_run.py` to accept client config instead of global paths, and add `multi_client_run.py` entry point with client detection + interactive menu + CLI override.

**Tech Stack:** Python 3, Anthropic API (Sonnet/Haiku), pathlib, argparse

---

## File Structure

**Files to Create:**
- `shared/client_config.py` — ClientConfig class (detect clients, resolve paths, validate)
- `multi_client_run.py` — Entry point (menu, CLI parsing, orchestration)
- `tests/shared/test_client_config.py` — Unit tests for ClientConfig
- `tests/test_multi_client_run.py` — Integration/CLI tests

**Files to Modify:**
- `local_run.py` — Accept `client_config` parameter, replace global paths with client_config attributes

---

## Task 1: Create ClientConfig Class

**Files:**
- Create: `shared/client_config.py`
- Test: `tests/shared/test_client_config.py`

- [ ] **Step 1: Create test file with all test cases**

```python
# tests/shared/test_client_config.py
import pytest
from pathlib import Path
import tempfile
import json
from shared.client_config import ClientConfig

class TestClientConfigDetectClients:
    """Test client detection from input_AO folder."""
    
    def test_detect_clients_finds_all_folders_with_referinta(self):
        """Detect only folders containing di_referinta.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input_AO"
            input_dir.mkdir()
            
            # Create 2 client folders with di_referinta.json
            (input_dir / "Blocuri Racari").mkdir()
            (input_dir / "Blocuri Racari" / "di_referinta.json").write_text('{}')
            
            (input_dir / "Camin Maneciu").mkdir()
            (input_dir / "Camin Maneciu" / "di_referinta.json").write_text('{}')
            
            # Create folder without di_referinta.json (should be ignored)
            (input_dir / "InvalidClient").mkdir()
            
            clients = ClientConfig.detect_clients(input_dir)
            assert sorted(clients) == ["Blocuri Racari", "Camin Maneciu"]
    
    def test_detect_clients_empty_input_dir(self):
        """Return empty list if no valid clients found."""
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "input_AO"
            input_dir.mkdir()
            
            clients = ClientConfig.detect_clients(input_dir)
            assert clients == []

class TestClientConfigFromFolder:
    """Test ClientConfig creation from client folder."""
    
    def test_from_folder_resolves_paths(self):
        """Verify from_folder resolves all paths correctly."""
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
    """Test offer file discovery."""
    
    def test_list_offer_files_finds_all_di_oferta(self):
        """Find all di_oferta_N.json files in client folder."""
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
    """Test validation of client files."""
    
    def test_validate_success_with_all_files(self):
        """Validation passes with di_referinta.json present."""
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
        """Validation fails if di_referinta.json missing."""
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
```

- [ ] **Step 2: Run test file to verify all fail**

```bash
rtk python3 -m pytest tests/shared/test_client_config.py -v
```

Expected: All tests fail with "ModuleNotFoundError: No module named 'shared.client_config'"

- [ ] **Step 3: Implement ClientConfig class**

```python
# shared/client_config.py
"""
ClientConfig — Client-specific path management for multi-client pipeline.

Encapsulates all paths (input, output, checkpoints) for a single client.
Immutable once created. Provides static methods for client detection.
"""
from pathlib import Path
from typing import List


class ClientConfig:
    """Manages client-specific paths and file discovery."""
    
    def __init__(
        self,
        name: str,
        input_dir: Path,
        output_dir: Path,
        checkpoint_dir: Path,
        reference_file: Path,
        offer_files: List[Path],
    ):
        """Initialize ClientConfig (immutable)."""
        self.name = name
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.reference_file = Path(reference_file)
        self.offer_files = [Path(f) for f in offer_files]
    
    @staticmethod
    def detect_clients(input_base: Path) -> List[str]:
        """
        Detect all clients in input_base.
        
        Returns list of folder names containing di_referinta.json.
        Folders are sorted alphabetically.
        
        Args:
            input_base: Path to input_AO directory
        
        Returns:
            List of client folder names (e.g., ["Blocuri Racari", "Camin Maneciu"])
        """
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
        """
        Create ClientConfig from client folder name.
        
        Resolves all paths based on input_base and output_base directories.
        Does NOT validate file existence (use .validate() for that).
        
        Args:
            client_name: Folder name (e.g., "Blocuri Racari")
            input_base: Path to input_AO directory
            output_base: Path to output_AO directory
        
        Returns:
            ClientConfig instance
        """
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
        """
        Validate that required files exist.
        
        Checks: di_referinta.json exists in input_dir.
        
        Returns:
            True if valid, False otherwise
        """
        return self.reference_file.exists()
    
    def list_offer_files(self) -> List[Path]:
        """
        Return all di_oferta_*.json files for this client.
        
        Returns:
            List of Path objects, sorted by filename
        """
        return self.offer_files
    
    def ensure_output_dirs(self) -> None:
        """Create output and checkpoint directories if they don't exist."""
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: Run tests to verify all pass**

```bash
rtk python3 -m pytest tests/shared/test_client_config.py -v
```

Expected: All tests pass (7 passed)

- [ ] **Step 5: Commit**

```bash
rtk git add shared/client_config.py tests/shared/test_client_config.py
rtk git commit -m "feat: add ClientConfig class with client detection and path management"
```

---

## Task 2: Refactor local_run.py to Use ClientConfig

**Files:**
- Modify: `local_run.py`

- [ ] **Step 1: Identify all global path usages in local_run.py**

Run: `rtk grep -n "INPUT_DIR\|OUTPUT_DIR\|CHECKPOINT_DIR\|ROOT" local_run.py | head -30`

Note the line numbers. These will be refactored to use `client_config` instead.

- [ ] **Step 2: Create new run_pipeline function with client_config parameter**

Add at the top of local_run.py, after imports:

```python
def run_pipeline(client_config: ClientConfig) -> None:
    """
    Run complete analysis pipeline for a single client.
    
    Args:
        client_config: ClientConfig instance with paths and file list
    """
    from shared.client_config import ClientConfig
    
    logger.info(f"Starting pipeline for client: {client_config.name}")
    client_config.ensure_output_dirs()
    
    # Load reference and offers
    logger.info(f"Loading reference: {client_config.reference_file}")
    with open(client_config.reference_file) as f:
        referinta_data = json.load(f)
    
    oferta_data_list = []
    for offer_file in client_config.list_offer_files():
        logger.info(f"Loading offer: {offer_file}")
        with open(offer_file) as f:
            oferta_data_list.append(json.load(f))
    
    # Continue with rest of pipeline (will refactor next)
    logger.info(f"Loaded {len(oferta_data_list)} offer(s)")
```

- [ ] **Step 3: Update _checkpoint_path to accept checkpoint_dir parameter**

Replace the existing `_checkpoint_path` function with:

```python
def _checkpoint_path(di_path: Path, checkpoint_dir: Path) -> Path:
    """Return checkpoint path for a document DI."""
    import shared.f3_page_classifier as _clf_module
    _clf_hash = hashlib.md5(
        inspect.getsource(_clf_module).encode()
    ).hexdigest()[:12]
    return checkpoint_dir / f"{di_path.stem}_page_classes_{_clf_hash}.json"
```

- [ ] **Step 4: Update all helper functions to accept client_config**

For each internal function that uses OUTPUT_DIR or INPUT_DIR:
- Add `client_config: ClientConfig` parameter
- Replace `OUTPUT_DIR` with `client_config.output_dir`
- Replace `INPUT_DIR` with `client_config.input_dir`
- Replace `CHECKPOINT_DIR` with `client_config.checkpoint_dir`
- Update all call sites to pass `client_config`

- [ ] **Step 5: Test backward compatibility (root files)**

```bash
python3 << 'EOF'
from pathlib import Path
from shared.client_config import ClientConfig
from local_run import run_pipeline

root_config = ClientConfig(
    name="root",
    input_dir=Path("input_AO"),
    output_dir=Path("output_AO_test"),
    checkpoint_dir=Path("output_AO_test/checkpoints"),
    reference_file=Path("input_AO/di_referinta.json"),
    offer_files=sorted(Path("input_AO").glob("di_oferta_*.json")),
)

if root_config.validate():
    print("✓ Root config valid")
    run_pipeline(root_config)
    print("✓ Pipeline ran successfully")
else:
    print("✗ Root config invalid")
EOF
```

Expected: Pipeline runs without errors.

- [ ] **Step 6: Commit refactored local_run.py**

```bash
rtk git add local_run.py
rtk git commit -m "refactor(local_run): accept ClientConfig parameter, remove global path dependencies"
```

---

## Task 3: Create multi_client_run.py Entry Point

**Files:**
- Create: `multi_client_run.py`

- [ ] **Step 1: Write multi_client_run.py with full implementation**

```python
#!/usr/bin/env python3
"""
multi_client_run.py — Multi-client orchestrator for offer analysis pipeline.

Usage:
    python3 multi_client_run.py              # Interactive menu
    python3 multi_client_run.py --client "Blocuri Racari"  # Direct client

Detects clients from input_AO/, shows menu or uses --client arg,
runs pipeline via local_run.run_pipeline(client_config).
"""
import argparse
import logging
import sys
from pathlib import Path

from shared.client_config import ClientConfig
from local_run import run_pipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent
INPUT_BASE = ROOT / "input_AO"
OUTPUT_BASE = ROOT / "output_AO"


def show_client_menu(clients: list[str]) -> str:
    """
    Display interactive menu for client selection.
    
    Args:
        clients: List of client names
    
    Returns:
        Selected client name
    """
    if not clients:
        logger.error("No clients found in input_AO/")
        sys.exit(1)
    
    print("\n" + "="*60)
    print("Multi-Client Offer Analysis Pipeline")
    print("="*60)
    print("\nAvailable clients:\n")
    
    for i, client in enumerate(clients, 1):
        print(f"  {i}. {client}")
    
    while True:
        try:
            choice = input(f"\nSelect client (1-{len(clients)}): ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(clients):
                return clients[idx]
            else:
                print(f"Invalid choice. Please enter 1-{len(clients)}")
        except ValueError:
            print("Invalid input. Please enter a number.")
        except KeyboardInterrupt:
            print("\nCancelled.")
            sys.exit(0)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Multi-client offer analysis pipeline"
    )
    parser.add_argument(
        "--client",
        type=str,
        help="Client name (skip menu if provided)",
    )
    return parser.parse_args()


def main():
    """Main orchestrator logic."""
    args = parse_args()
    
    # Detect clients
    logger.info(f"Scanning for clients in {INPUT_BASE}/")
    clients = ClientConfig.detect_clients(INPUT_BASE)
    
    if not clients:
        logger.error(f"No clients found in {INPUT_BASE}/")
        logger.info("Expected folder structure: input_AO/ClientName/di_referinta.json")
        sys.exit(1)
    
    logger.info(f"Found {len(clients)} client(s): {', '.join(clients)}")
    
    # Get client selection
    if args.client:
        if args.client not in clients:
            logger.error(f"Client '{args.client}' not found.")
            logger.info(f"Available clients: {', '.join(clients)}")
            sys.exit(1)
        selected_client = args.client
        logger.info(f"Using client from --client arg: {selected_client}")
    else:
        selected_client = show_client_menu(clients)
    
    # Create client config
    try:
        client_config = ClientConfig.from_folder(
            client_name=selected_client,
            input_base=INPUT_BASE,
            output_base=OUTPUT_BASE,
        )
    except Exception as e:
        logger.error(f"Failed to create client config: {e}")
        sys.exit(1)
    
    # Validate
    if not client_config.validate():
        logger.error(f"Client validation failed: di_referinta.json not found at {client_config.reference_file}")
        sys.exit(1)
    
    # Run pipeline
    try:
        logger.info(f"\n{'='*60}")
        logger.info(f"Starting pipeline for: {client_config.name}")
        logger.info(f"Input:  {client_config.input_dir}")
        logger.info(f"Output: {client_config.output_dir}")
        logger.info(f"{'='*60}\n")
        
        run_pipeline(client_config)
        
        logger.info(f"\n{'='*60}")
        logger.info(f"✓ Pipeline completed successfully for: {client_config.name}")
        logger.info(f"Results saved to: {client_config.output_dir}")
        logger.info(f"{'='*60}\n")
    
    except Exception as e:
        logger.error(f"\n{'='*60}")
        logger.error(f"✗ Pipeline failed for: {client_config.name}")
        logger.error(f"Error: {e}")
        logger.error(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test menu interactive selection**

```bash
rtk python3 multi_client_run.py
```

Expected: Menu appears. Select a client and verify pipeline starts.

- [ ] **Step 3: Test CLI --client arg**

```bash
rtk python3 multi_client_run.py --client "Blocuri Racari"
```

Expected: Skips menu, runs directly.

- [ ] **Step 4: Test error handling**

```bash
rtk python3 multi_client_run.py --client "NonExistent"
```

Expected: Error message listing available clients.

- [ ] **Step 5: Commit**

```bash
rtk git add multi_client_run.py
rtk git chmod +x multi_client_run.py
rtk git commit -m "feat: add multi_client_run.py with menu and CLI parsing"
```

---

## Task 4: Write Integration Tests

**Files:**
- Create: `tests/test_multi_client_run.py`

- [ ] **Step 1: Create integration test file**

```python
# tests/test_multi_client_run.py
import pytest
import json
from pathlib import Path
import tempfile
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
                
                # Minimal referinta
                referinta = {
                    "devizes": [
                        {
                            "cod": "4.1",
                            "articole": [
                                {"cod": "TEST01", "descriere": "Test Article"}
                            ]
                        }
                    ]
                }
                (client_input / "di_referinta.json").write_text(json.dumps(referinta))
                
                # Minimal oferta
                oferta = {
                    "devizes": [
                        {
                            "cod": "4.1",
                            "articole": [
                                {"cod": "TEST01", "cantitate": 1, "um": "buc"}
                            ]
                        }
                    ]
                }
                (client_input / "di_oferta_1.json").write_text(json.dumps(oferta))
            
            yield input_base, output_base
    
    def test_run_pipeline_creates_output_per_client(self, test_clients_dir):
        """Verify pipeline creates output in per-client subfolder."""
        input_base, output_base = test_clients_dir
        
        config = ClientConfig.from_folder(
            client_name="TestClient1",
            input_base=input_base,
            output_base=output_base,
        )
        
        run_pipeline(config)
        
        assert config.output_dir.exists()
        assert config.checkpoint_dir.exists()
    
    def test_multiple_clients_isolated_checkpoints(self, test_clients_dir):
        """Verify each client has isolated checkpoints."""
        input_base, output_base = test_clients_dir
        
        config1 = ClientConfig.from_folder("TestClient1", input_base, output_base)
        run_pipeline(config1)
        
        config2 = ClientConfig.from_folder("TestClient2", input_base, output_base)
        run_pipeline(config2)
        
        assert (config1.checkpoint_dir).exists()
        assert (config2.checkpoint_dir).exists()
        assert config1.checkpoint_dir != config2.checkpoint_dir
```

- [ ] **Step 2: Run integration tests**

```bash
rtk python3 -m pytest tests/test_multi_client_run.py -v
```

Expected: Tests pass or show reasonable failures (implementation-dependent).

- [ ] **Step 3: Commit**

```bash
rtk git add tests/test_multi_client_run.py
rtk git commit -m "test: add integration tests for multi-client pipeline"
```

---

## Task 5: Regression Testing (Backward Compatibility)

**Files:**
- Root input files (existing)

- [ ] **Step 1: Test root files still work**

```bash
python3 << 'EOF'
from pathlib import Path
from shared.client_config import ClientConfig
from local_run import run_pipeline

root_config = ClientConfig(
    name="root_legacy",
    input_dir=Path("input_AO"),
    output_dir=Path("output_AO_regression"),
    checkpoint_dir=Path("output_AO_regression/checkpoints"),
    reference_file=Path("input_AO/di_referinta.json"),
    offer_files=sorted(Path("input_AO").glob("di_oferta_*.json")),
)

if root_config.validate():
    print("✓ Root files accessible")
    run_pipeline(root_config)
    print("✓ Pipeline succeeded on root files")
else:
    print("✗ Root files not found")
EOF
```

Expected: Pipeline runs on root files.

- [ ] **Step 2: Commit**

```bash
rtk git add .
rtk git commit -m "test: verify backward compatibility with root input files"
```

---

## Task 6: Documentation and Polish

**Files:**
- Modify/Create: `README.md`

- [ ] **Step 1: Add usage section to README**

Add this section to README.md:

```markdown
## Multi-Client Pipeline

### Usage

#### Interactive Menu (Default)
\`\`\`bash
python3 multi_client_run.py
\`\`\`

Lists all detected clients and prompts selection by number.

#### Direct Client Selection
\`\`\`bash
python3 multi_client_run.py --client "Blocuri Racari"
\`\`\`

Skips menu, runs directly for specified client.

### Input Structure

Each client must have:
\`\`\`
input_AO/{ClientName}/
  ├── di_referinta.json (required)
  ├── di_oferta_1.json (required)
  └── di_oferta_2.json (optional, any number)
\`\`\`

### Output Structure

Results saved per-client:
\`\`\`
output_AO/{ClientName}/
  ├── referinta.json
  ├── oferta_1.json
  ├── comparatie_oferta_1.json
  ├── Raport_Oferta_1.docx
  └── checkpoints/
\`\`\`

### Backward Compatibility

Old single-client mode still works:
\`\`\`bash
python3 local_run.py  # Uses input_AO/di_referinta.json + di_oferta_*.json
\`\`\`
```

- [ ] **Step 2: Test all error scenarios are clear**

```bash
# No clients
rtk python3 multi_client_run.py  # (with no client folders) → error message

# Invalid client
rtk python3 multi_client_run.py --client "InvalidClient" → lists available

# Menu timeout
rtk python3 multi_client_run.py  # then Ctrl+C → "Cancelled"
```

- [ ] **Step 3: Final smoke test on all 4 real clients**

```bash
rtk python3 multi_client_run.py --client "Blocuri Racari"
rtk python3 multi_client_run.py --client "Camin Maneciu"
rtk python3 multi_client_run.py --client "Scoala Dragomiresti"
rtk python3 multi_client_run.py --client "Scoala Sportiva Racari"
```

Verify all complete successfully, outputs in output_AO/{client_name}/.

- [ ] **Step 4: Commit**

```bash
rtk git add README.md
rtk git commit -m "docs: add multi-client pipeline usage guide"
```

---

## Success Criteria

After all tasks, verify:

- [ ] ClientConfig detects all 4 clients correctly
- [ ] ClientConfig.from_folder resolves paths correctly
- [ ] ClientConfig.validate checks di_referinta.json
- [ ] multi_client_run.py shows menu when no --client
- [ ] multi_client_run.py --client skips menu
- [ ] Invalid --client shows error with list
- [ ] Output goes to output_AO/{client_name}/
- [ ] Checkpoints isolated per-client
- [ ] Root di_oferta files still process (backward compat)
- [ ] All tests pass
- [ ] No placeholder code
- [ ] Documentation complete
