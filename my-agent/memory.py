from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MemoryStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []

    def _write_all(self, items: list[dict[str, Any]]) -> None:
        self.path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def append(self, role: str, content: str) -> None:
        items = self._read_all()
        items.append(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "role": role,
                "content": content,
            }
        )
        self._write_all(items)

    def recent(self, count: int = 8) -> list[dict[str, Any]]:
        items = self._read_all()
        return items[-count:]
