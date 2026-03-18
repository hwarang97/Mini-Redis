"""Append-only file support."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any


@dataclass(frozen=True)
class AOFReadResult:
    entries: list[dict[str, Any]]
    corruption_detected: bool
    ignored_entries: int
    corrupted_line: int | None


class AOFWriter:
    """Write operation events to an append-only log."""

    def __init__(self, path: Path, fsync_policy: str = "everysec") -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fsync_policy = fsync_policy
        self._last_fsync_at = monotonic()

    def append(self, operation: str, args: list[object]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({"op": operation, "args": args}) + "\n")
            handle.flush()
            if self._fsync_policy == "always":
                os.fsync(handle.fileno())
                self._last_fsync_at = monotonic()
            elif self._fsync_policy == "everysec" and monotonic() - self._last_fsync_at >= 1:
                os.fsync(handle.fileno())
                self._last_fsync_at = monotonic()

    def read_entries(self) -> AOFReadResult:
        if not self._path.exists():
            return AOFReadResult(
                entries=[],
                corruption_detected=False,
                ignored_entries=0,
                corrupted_line=None,
            )

        entries: list[dict[str, Any]] = []
        corruption_detected = False
        ignored_entries = 0
        corrupted_line: int | None = None
        with self._path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    corruption_detected = True
                    corrupted_line = line_number
                    ignored_entries += 1
                    ignored_entries += sum(1 for remaining in handle if remaining.strip())
                    break

                if not isinstance(payload, dict) or "op" not in payload:
                    corruption_detected = True
                    corrupted_line = line_number
                    ignored_entries += 1
                    ignored_entries += sum(1 for remaining in handle if remaining.strip())
                    break

                entries.append(payload)

        return AOFReadResult(
            entries=entries,
            corruption_detected=corruption_detected,
            ignored_entries=ignored_entries,
            corrupted_line=corrupted_line,
        )

    def rewrite(self, entries: list[dict[str, Any]]) -> Path:
        with self._path.open("w", encoding="utf-8") as handle:
            for entry in entries:
                handle.write(json.dumps(entry) + "\n")
        return self._path

    def repair(self) -> dict[str, Any]:
        result = self.read_entries()
        if not self._path.exists():
            return {
                "path": str(self._path),
                "repaired": False,
                "corruption_detected": False,
                "ignored_entries": 0,
                "corrupted_line": None,
            }

        if result.corruption_detected:
            self.rewrite(result.entries)

        return {
            "path": str(self._path),
            "repaired": result.corruption_detected,
            "corruption_detected": result.corruption_detected,
            "ignored_entries": result.ignored_entries,
            "corrupted_line": result.corrupted_line,
        }

    def set_fsync_policy(self, policy: str) -> None:
        self._fsync_policy = policy

    @property
    def fsync_policy(self) -> str:
        return self._fsync_policy

    @property
    def path(self) -> Path:
        return self._path
