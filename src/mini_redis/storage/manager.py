"""Primary in-memory storage."""

from __future__ import annotations


class StorageManager:
    """Store key/value pairs. This is where incremental rehashing could evolve later."""

    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def set(self, key: str, value: str) -> None:
        self._data[key] = value

    def delete(self, key: str) -> bool:
        return self._data.pop(key, None) is not None

    def exists(self, key: str) -> bool:
        return key in self._data

    def keys(self) -> list[str]:
        return sorted(self._data.keys())

    def items(self) -> dict[str, str]:
        return dict(self._data)

    def clear(self) -> int:
        removed = len(self._data)
        self._data.clear()
        return removed
