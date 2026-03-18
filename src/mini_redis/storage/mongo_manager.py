"""MongoDB integration manager."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from mini_redis.storage.mongo_adapter import MongoAdapter


class MongoManager:
    """Own Mongo-related sync policy and delegate persistence to the adapter."""

    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter
        self._last_write_duration_seconds: float | None = None

    @property
    def enabled(self) -> bool:
        return self._adapter.enabled

    def write_value(self, key: str, value: str) -> float | None:
        if not self.enabled:
            self._last_write_duration_seconds = None
            return None
        started_at = perf_counter()
        self._adapter.upsert(key, value)
        elapsed = perf_counter() - started_at
        self._last_write_duration_seconds = elapsed
        return elapsed

    def read_value(self, key: str) -> str | None:
        if not self.enabled:
            return None
        return self._adapter.get(key)

    def sync_value(self, key: str, value: str) -> float | None:
        # Compatibility shim for older code paths that still call the previous sync-oriented API.
        return self.write_value(key, value)

    def maybe_sync(self, key: str, value: str) -> float | None:
        # Compatibility shim for code written before MongoManager replaced direct adapter usage.
        return self.write_value(key, value)

    def delete_key(self, key: str) -> None:
        self._adapter.delete(key)

    def clear(self) -> None:
        self._adapter.clear()

    def info(self) -> dict[str, Any]:
        payload = self._adapter.info()
        payload["last_write_duration_seconds"] = self._last_write_duration_seconds
        payload["last_write_duration_ms"] = (
            None
            if self._last_write_duration_seconds is None
            else round(self._last_write_duration_seconds * 1000, 3)
        )
        return payload
