"""Persistence metadata file support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PersistenceMetadataStore:
    """Persist operational metadata for persistence workflows."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with self._path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save(self, payload: dict[str, Any]) -> Path:
        with self._path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
        return self._path

    @property
    def path(self) -> Path:
        return self._path
