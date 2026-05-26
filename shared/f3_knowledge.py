from __future__ import annotations

import json
import re
from pathlib import Path
from datetime import datetime, timezone

KNOWLEDGE_PATH = Path(__file__).parent / "f3_markers_knowledge.json"


class F3Knowledge:
    def __init__(self, path: Path = KNOWLEDGE_PATH):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            return json.loads(self.path.read_text(encoding="utf-8"))
        return {"version": 1, "start_markers": [], "end_markers": []}

    def save(self):
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def find_start_marker(self, lines: list) -> str | None:
        """Return first matching line or None."""
        for line in lines:
            for m in self._data.get("start_markers", []):
                if self._matches(line, m):
                    return line
        return None

    def find_end_marker(self, lines: list, skip_header_lines: int = 20) -> tuple | None:
        """Return (line_index, matched_line) or None.

        Skips first skip_header_lines lines — page headers (PROIECTANT:, OBIECTIV:, etc.)
        appear in the first ~10 lines and must not trigger as false end-markers.
        """
        for i, line in enumerate(lines):
            if i < skip_header_lines:
                continue
            for m in self._data.get("end_markers", []):
                if self._matches(line, m):
                    return (i, line)
        return None

    def learn(self, pattern: str, marker_type: str, source_type: str = "start",
              source: str = "llm", format_hint: str = "generic"):
        """Add new marker pattern. Ignores duplicates and short patterns."""
        if len(pattern.strip()) < 5:
            return
        key = "start_markers" if source_type == "start" else "end_markers"
        existing = [m for m in self._data[key] if m["pattern"] == pattern]
        if existing:
            existing[0]["seen_count"] = existing[0].get("seen_count", 0) + 1
            self.save()
            return
        self._data[key].append({
            "pattern": pattern,
            "type": marker_type,
            "format": format_hint,
            "source": source,
            "seen_count": 1,
            "learned_at": datetime.now(tz=timezone.utc).isoformat(),
        })
        self.save()

    def _matches(self, line: str, marker: dict) -> bool:
        p = marker["pattern"]
        t = marker.get("type", "exact")
        if t == "exact":
            return p in line
        if t == "prefix":
            return line.strip().startswith(p)
        if t == "regex":
            try:
                return bool(re.search(p, line))
            except re.error:
                return False
        return False
