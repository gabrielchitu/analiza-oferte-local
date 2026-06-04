"""Fingerprint learning mechanism for document type detection.

Analyzes successful extraction runs to identify and learn new document types,
updating extraction_fingerprints.json with new templates and their features.
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

FINGERPRINTS_PATH = Path(__file__).parent / "extraction_fingerprints.json"


class FingerprintLearner:
    """Learn and update fingerprints from extraction runs."""

    def __init__(self):
        """Initialize with current fingerprints."""
        self.fingerprints = self._load_fingerprints()

    def _load_fingerprints(self) -> Dict:
        """Load current fingerprints from JSON."""
        if not FINGERPRINTS_PATH.exists():
            return {
                "UNKNOWN": {
                    "description": "Fallback template for unknown documents",
                    "features": {},
                    "accuracy": 0.0,
                }
            }

        try:
            with open(FINGERPRINTS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load fingerprints: {e}")
            return {
                "UNKNOWN": {
                    "description": "Fallback template for unknown documents",
                    "features": {},
                    "accuracy": 0.0,
                }
            }

    def learn_from_extraction(
        self,
        di_json: Dict,
        extracted_result: Dict,
        client_name: str,
        document_type: str = None,
    ) -> bool:
        """Learn a new fingerprint from a successful extraction.

        Args:
            di_json: Original document info dict
            extracted_result: Extraction output with template_id and groups
            client_name: Name of client
            document_type: Override document type (template_id) if provided

        Returns:
            True if fingerprint was learned/updated
        """
        template_id = document_type or extracted_result.get("template_id", "UNKNOWN")

        # Don't learn from UNKNOWN (fallback template)
        if template_id == "UNKNOWN":
            return False

        # Extract fingerprint features
        fingerprint = self._extract_fingerprint(di_json)

        # Check if template already exists
        if template_id in self.fingerprints:
            # Update existing template with weighted average of features
            self._update_template(template_id, fingerprint, client_name)
        else:
            # Create new template
            self._create_template(template_id, fingerprint, client_name)

        return True

    def _extract_fingerprint(self, di_json: Dict) -> Dict:
        """Extract structural features from document."""
        pages = di_json.get("pages", [])
        tables = di_json.get("tables", [])

        # Count total pages
        num_pages = len(pages)

        # Count tables
        num_tables = len(tables)

        # Find primary (largest) table
        primary_table_cols = 0
        primary_table_rows = 0
        if tables:
            largest_table = max(
                tables,
                key=lambda t: t.get("row_count", 0) * t.get("column_count", 0),
            )
            primary_table_cols = largest_table.get("column_count", 0)
            primary_table_rows = largest_table.get("row_count", 0)

        # Calculate text density (lines per page on first 5 pages)
        first_5_pages = pages[:5]
        total_lines = 0
        for page in first_5_pages:
            lines = page.get("lines", [])
            total_lines += len([l for l in lines if isinstance(l, str) and l.strip()])

        text_density = total_lines / len(first_5_pages) if first_5_pages else 0.0

        has_multicolumn_primary = primary_table_cols >= 4

        return {
            "num_pages": num_pages,
            "num_tables": num_tables,
            "primary_table_cols": primary_table_cols,
            "primary_table_rows": primary_table_rows,
            "text_density": round(text_density, 2),
            "has_multicolumn_primary": has_multicolumn_primary,
        }

    def _create_template(
        self, template_id: str, fingerprint: Dict, client_name: str
    ) -> None:
        """Create a new template entry."""
        self.fingerprints[template_id] = {
            "description": f"Template learned from {client_name}",
            "features": fingerprint,
            "accuracy": 0.85,  # Initial confidence
            "last_seen": datetime.now(tz=timezone.utc).isoformat(),
            "learned_from": [client_name],
        }
        logger.info(f"Created new template: {template_id} from {client_name}")

    def _update_template(
        self, template_id: str, fingerprint: Dict, client_name: str
    ) -> None:
        """Update existing template with new observation."""
        template = self.fingerprints[template_id]

        # Record observation
        if "learned_from" not in template:
            template["learned_from"] = []

        if client_name not in template["learned_from"]:
            template["learned_from"].append(client_name)

        # Update features (weighted average towards new observation)
        # Weight new observation less than existing (more stable learning)
        old_features = template.get("features", {})
        weight_old = 0.7
        weight_new = 0.3

        updated_features = {}
        all_keys = set(old_features.keys()) | set(fingerprint.keys())

        for key in all_keys:
            old_val = old_features.get(key, 0)
            new_val = fingerprint.get(key, 0)

            if isinstance(old_val, (int, float)) and isinstance(new_val, (int, float)):
                updated_features[key] = round(
                    old_val * weight_old + new_val * weight_new, 2
                )
            elif isinstance(old_val, bool) or isinstance(new_val, bool):
                # For boolean, use OR logic (if either is true)
                updated_features[key] = bool(old_val or new_val)
            else:
                # Keep old value for other types
                updated_features[key] = old_val

        template["features"] = updated_features
        template["last_seen"] = datetime.now(tz=timezone.utc).isoformat()

        # Slightly increase accuracy (up to 0.95)
        template["accuracy"] = min(0.95, template.get("accuracy", 0.85) + 0.02)

        logger.info(
            f"Updated template: {template_id} with observation from {client_name}"
        )

    def save_fingerprints(self) -> bool:
        """Save updated fingerprints to JSON file."""
        try:
            FINGERPRINTS_PATH.parent.mkdir(parents=True, exist_ok=True)
            with open(FINGERPRINTS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.fingerprints, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved fingerprints to {FINGERPRINTS_PATH}")
            return True
        except Exception as e:
            logger.error(f"Failed to save fingerprints: {e}")
            return False

    def get_template_stats(self) -> Dict:
        """Return statistics about learned templates."""
        stats = {
            "total_templates": len(self.fingerprints),
            "templates": {},
        }

        for template_id, template_def in self.fingerprints.items():
            if template_id != "UNKNOWN":
                stats["templates"][template_id] = {
                    "accuracy": template_def.get("accuracy", 0.0),
                    "learned_from": template_def.get("learned_from", []),
                    "last_seen": template_def.get("last_seen", "unknown"),
                }

        return stats


def learn_from_all_extractions(dry_run: bool = False, force_create: bool = False) -> Dict:
    """Process all v2 extractions and learn new templates.

    Args:
        dry_run: If True, don't save fingerprints
        force_create: If True, create new templates for UNKNOWN clients (based on client name)

    Returns:
        Stats dict with learning results
    """
    from shared.client_config import ClientConfig

    learner = FingerprintLearner()
    stats = {"clients_processed": 0, "templates_created": 0, "templates_updated": 0}

    root = Path(__file__).parent.parent
    input_base = root / "input_AO"
    output_base = root / "output_AO"

    # Detect all clients
    clients = ClientConfig.detect_clients(input_base)

    for client in clients:
        try:
            client_config = ClientConfig.from_folder(
                client_name=client, input_base=input_base, output_base=output_base
            )

            # Load reference DI
            with open(client_config.reference_file) as f:
                ref_di = json.load(f)

            # Load v2 extraction
            ref_v2_path = client_config.output_dir / "referinta_v2.json"
            if ref_v2_path.exists():
                with open(ref_v2_path) as f:
                    ref_extracted = json.load(f)

                # Count templates before
                before = len(
                    [t for t in learner.fingerprints if t != "UNKNOWN"]
                )

                # Determine template_id to use
                template_id = ref_extracted.get("template_id", "UNKNOWN")

                # If force_create and UNKNOWN, generate template name from client
                if force_create and template_id == "UNKNOWN":
                    # Generate template from client name (e.g., "Blocuri Racari" -> "BR_CONSOLIDATED")
                    template_id = _generate_template_id(client)
                    logger.info(f"Force-creating template {template_id} for {client}")

                # Learn from extraction
                learner.learn_from_extraction(
                    ref_di, ref_extracted, client, document_type=template_id
                )

                # Count templates after
                after = len([t for t in learner.fingerprints if t != "UNKNOWN"])

                if after > before:
                    stats["templates_created"] += 1
                else:
                    stats["templates_updated"] += 1

                stats["clients_processed"] += 1

        except Exception as e:
            logger.warning(f"Failed to process client {client}: {e}")

    # Save if not dry run
    if not dry_run:
        learner.save_fingerprints()

    # Get final stats
    stats.update(learner.get_template_stats())

    return stats


def _generate_template_id(client_name: str) -> str:
    """Generate a template ID from client name.

    Examples:
        "Blocuri Racari" -> "BR_CONSOLIDATED"
        "BR BLOC A" -> "BR_BLOC_A"
        "Camin Maneciu" -> "CM_HIERARCHICAL"
        "Drum Tatarani" -> "DT_STREETS"
        "Scoala Dragomiresti" -> "SDR_TABLES"
        "Scoala Sportiva Racari" -> "SSR_MIXED"
    """
    if "Blocuri" in client_name and "Racari" in client_name:
        return "BR_CONSOLIDATED"
    elif client_name.startswith("BR BLOC"):
        suffix = client_name.replace("BR BLOC ", "").replace(" ", "_")
        return f"BR_BLOC_{suffix}"
    elif "Camin" in client_name:
        return "CM_HIERARCHICAL"
    elif "Drum" in client_name:
        return "DT_STREETS"
    elif "Dragomiresti" in client_name:
        return "SDR_TABLES"
    elif "Sportiva" in client_name:
        return "SSR_MIXED"
    else:
        # Generic fallback
        words = client_name.split()
        return "_".join(w[:2].upper() for w in words[:2])


if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s"
    )

    if len(sys.argv) > 1 and sys.argv[1] == "--dry-run":
        print("DRY RUN - fingerprints will NOT be saved")
        results = learn_from_all_extractions(dry_run=True)
    else:
        results = learn_from_all_extractions(dry_run=False)

    print("\nFingerprint Learning Results:")
    print(json.dumps(results, indent=2, default=str))
