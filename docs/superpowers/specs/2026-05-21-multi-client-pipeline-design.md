# Multi-Client Pipeline Design

**Date:** 2026-05-21  
**Status:** Approved  
**Scope:** Refactor single-client offer analysis pipeline to support multiple clients with interactive selection

## Problem Statement

Currently, the pipeline processes hardcoded files at `input_AO/di_referinta.json` + `input_AO/di_oferta_N.json`. The codebase has 4 clients in separate folders (Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari), but the pipeline doesn't use them. Users must manually manage different input/output sets, making it error-prone and inefficient.

## Goal

Transform pipeline into a **client-aware agent** that:
- Auto-detects available clients from `input_AO/` folder structure
- Presents interactive menu for client selection (with CLI arg override)
- Processes selected client's input files
- Outputs results to per-client subfolders in `output_AO/`
- Maintains backward compatibility (root di_oferta files still processable)

## Architecture

### Input Structure
```
input_AO/
  ├── di_referinta.json (shared/legacy)
  ├── di_oferta_N.json (shared/legacy)
  ├── Blocuri Racari/
  │   ├── di_referinta.json
  │   └── di_oferta_N.json (one or more)
  ├── Camin Maneciu/
  │   ├── di_referinta.json
  │   └── di_oferta_N.json
  ... (other clients)
```

### Output Structure
```
output_AO/
  ├── {client_name}/
  │   ├── referinta.json
  │   ├── oferta_N.json (extracted)
  │   ├── comparatie_oferta_N.json (match results)
  │   ├── Raport_Oferta_N.docx (reports)
  │   └── checkpoints/
  │       └── di_X_page_classes_{hash}.json
```

### Execution Flow

1. User runs: `python3 multi_client_run.py [--client CLIENT_NAME]`
2. **Client detection:** Scan `input_AO/` for folders containing `di_referinta.json`
3. **Selection:**
   - If `--client` provided: skip menu, use that client
   - Else: show interactive menu (list clients, user picks by number)
4. **Validation:** Verify selected client has required files
5. **Pipeline execution:** Call refactored `run_pipeline(client_config)`
6. **Output:** Results land in `output_AO/{client_name}/`

## Components

### 1. ClientConfig Class (New)
**File:** `shared/client_config.py`

Encapsulates all client-specific state. Immutable once created.

**Attributes:**
- `name: str` — Client folder name (e.g., "Blocuri Racari")
- `input_dir: Path` — `input_AO/{name}/`
- `output_dir: Path` — `output_AO/{name}/`
- `checkpoint_dir: Path` — `output_AO/{name}/checkpoints/`
- `reference_file: Path` — `input_dir/di_referinta.json`
- `offer_files: List[Path]` — all `di_oferta_*.json` in `input_dir`

**Methods:**
- `from_folder(client_name: str) -> ClientConfig` — Create from client folder
- `detect_clients(input_base: Path) -> List[str]` — Find all clients (static)
- `validate() -> bool` — Check required files exist
- `list_offer_files() -> List[Path]` — Return offer files

### 2. multi_client_run.py (New Entry Point)
**File:** `multi_client_run.py`

**Responsibilities:**
- Detect clients via `ClientConfig.detect_clients(input_AO)`
- Parse CLI args (`--client`, optional flags)
- If no `--client`: show interactive menu (list + number input)
- Create `ClientConfig` for selection
- Call `run_pipeline(client_config)` (from refactored `local_run.py`)
- Handle errors, log per-client summary

**Example usage:**
```bash
# Interactive menu (default)
python3 multi_client_run.py

# Direct client selection (CLI override)
python3 multi_client_run.py --client "Blocuri Racari"
```

### 3. local_run.py (Refactored)
**File:** `local_run.py`

**Changes:**
- Replace global `ROOT`, `INPUT_DIR`, `OUTPUT_DIR`, `CHECKPOINT_DIR` with function parameters
- Main function signature: `run_pipeline(client_config: ClientConfig) -> None`
- All internal functions accept `client_config` parameter
- Checkpoint hashing uses `client_config.checkpoint_dir`
- Load files from `client_config.reference_file`, `client_config.offer_files`
- Output to `client_config.output_dir`

**Backward compatibility:**
- Old global paths remain (unused)
- If called without `client_config`, fallback to root di_oferta files
- Existing imports/API unchanged

### 4. No Changes Required
- `AgentComparator_local.py` — unchanged
- `shared/comparator.py`, `shared/article_matcher.py` — unchanged
- Other utilities — unchanged

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│ multi_client_run.py (entry point)                           │
├─────────────────────────────────────────────────────────────┤
│ 1. ClientConfig.detect_clients(input_AO)                    │
│    └─ List clients: ["Blocuri Racari", "Camin Maneciu", ...] │
│ 2. Parse --client arg or show menu                          │
│    └─ Get: "Blocuri Racari"                                 │
│ 3. ClientConfig.from_folder("Blocuri Racari")               │
│    └─ Resolve paths: input_AO/Blocuri Racari/, etc.        │
│ 4. run_pipeline(client_config)                              │
│    ├─ Load files from client_config paths                   │
│    ├─ Classify pages (checkpoint: client_config.checkpoint) │
│    ├─ Match articles (AgentComparator_local)                │
│    ├─ Generate reports                                      │
│    └─ Write output to client_config.output_dir              │
│ 5. Log summary + success                                    │
└─────────────────────────────────────────────────────────────┘
```

## Error Handling

| Scenario | Behavior |
|----------|----------|
| No clients detected | Error: "No clients found in input_AO/" + exit |
| Missing di_referinta.json for client | Error: "di_referinta.json not found for {client}" + exit |
| Invalid --client arg | Error: list available clients + exit |
| Menu timeout/invalid input | Reprompt user |
| Pipeline error for selected client | Log error + offer retry/abort |
| Output directory exists | Create subfolders, don't delete existing |

## Testing Strategy

**Unit Tests:**
- `ClientConfig.detect_clients()` — mock folder structure
- `ClientConfig.from_folder()` — verify path resolution
- `ClientConfig.validate()` — check file existence logic

**Integration Tests:**
- Run pipeline on 1-2 small test clients (mini di_referinta + di_oferta_1)
- Verify outputs in per-client subfolders
- Check checkpoint isolation (each client has own checkpoints)

**Regression Tests:**
- Run with root di_oferta files (backward compatibility)
- Verify results match previous single-client behavior

## Phases

### Phase 1: Foundation
- Create `shared/client_config.py`
- Refactor `local_run.py` to accept `ClientConfig`
- Create `multi_client_run.py` with menu + CLI parsing
- Manual testing on 1 client

### Phase 2: Validation
- Unit tests for `ClientConfig`
- Integration test (2-3 clients)
- Regression test (root files still work)

### Phase 3: Polish
- Error messages + logging refinement
- Documentation updates
- Commit + tag

## Backward Compatibility

- `local_run.py` can still run standalone: `python3 local_run.py` (uses default root di_oferta)
- Old scripts calling `local_run` functions directly: supported (no signature breaking)
- `.env` config (ANTHROPIC_API_KEY, ANTHROPIC_MODEL): unchanged
- Checkpoints: still work (per-client isolation by default)

## Success Criteria

✓ Multi-client menu detection works (all 4 clients appear)  
✓ CLI arg override works (`--client "Blocuri Racari"` skips menu)  
✓ Output folders created per-client (`output_AO/{client_name}/`)  
✓ Checkpoints isolated per-client (no cross-contamination)  
✓ Root di_oferta files still process (backward compat)  
✓ All tests pass (unit + integration + regression)
