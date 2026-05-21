# Multi-Offer Analysis Pipeline

## Multi-Client Pipeline

### Usage

#### Interactive Menu (Default)
```bash
python3 multi_client_run.py
```

Lists all detected clients and prompts you to select one by number.

#### Direct Client Selection (CLI)
```bash
python3 multi_client_run.py --client "Blocuri Racari"
```

Skips the menu and runs directly for the specified client.

### Input Structure

Each client must have the following folder structure:
```
input_AO/{ClientName}/
  ├── di_referinta.json          (required — reference data)
  ├── di_oferta_1.json           (required — first offer, one or more)
  ├── di_oferta_2.json
  └── di_oferta_N.json           (any number of offers)
```

### Output Structure

Results are saved in per-client subfolders:
```
output_AO/{ClientName}/
  ├── referinta.json             (extracted reference)
  ├── oferta_1.json              (extracted offer 1)
  ├── oferta_2.json
  ├── comparatie_oferta_1.json   (match results for offer 1)
  ├── comparatie_oferta_2.json
  ├── Raport_Oferta_1.docx       (generated report for offer 1)
  ├── Raport_Oferta_2.docx
  └── checkpoints/
      ├── di_referinta_page_classes_<hash>.json
      ├── di_oferta_1_page_classes_<hash>.json
      └── di_oferta_2_page_classes_<hash>.json
```

### Backward Compatibility

The pipeline maintains full backward compatibility with the original single-client mode. Old root-level input files still work:
```bash
python3 local_run.py  # Uses input_AO/di_referinta.json + input_AO/di_oferta_*.json
```

This produces outputs in `output_AO/` (root directory) as before.

### Error Messages

The pipeline provides clear error messages for common issues:

**No clients found:**
```
ERROR: No clients found in input_AO/
INFO: Expected folder structure: input_AO/ClientName/di_referinta.json
```

**Invalid --client argument:**
```
ERROR: Client 'InvalidName' not found.
INFO: Available clients: Blocuri Racari, Camin Maneciu, Scoala Dragomiresti, Scoala Sportiva Racari
```

**Missing di_referinta.json:**
```
ERROR: Client validation failed: di_referinta.json not found at input_AO/ClientName/di_referinta.json
```
