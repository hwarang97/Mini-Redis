"""Snapshot persistence support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class RDBSnapshotStore:
    """Persist full engine state to a snapshot file."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, payload: dict[str, Any]) -> Path:
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return self._path
