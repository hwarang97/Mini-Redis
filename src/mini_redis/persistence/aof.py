"""Append-only file support."""

from __future__ import annotations

import json
from pathlib import Path


class AOFWriter:
    """Write operation events to an append-only log."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, operation: str, args: list[object]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"op": operation, "args": args}) + "\n")
