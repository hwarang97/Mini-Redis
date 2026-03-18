"""MongoDB integration manager."""

from __future__ import annotations

from typing import Any

from mini_redis.storage.mongo_adapter import MongoAdapter


class MongoManager:
    """Own Mongo-related sync policy and delegate persistence to the adapter."""

    def __init__(self, adapter: MongoAdapter) -> None:
        self._adapter = adapter

    @property
    def enabled(self) -> bool:
        return self._adapter.enabled

    def sync_value(self, key: str, value: str) -> None:
        self._adapter.upsert(key, value)

    def maybe_sync(self, key: str, value: str) -> None:
        # Compatibility shim for code written before MongoManager replaced direct adapter usage.
        self.sync_value(key, value)

    def delete_key(self, key: str) -> None:
        self._adapter.delete(key)

    def clear(self) -> None:
        self._adapter.clear()

    def info(self) -> dict[str, Any]:
        return self._adapter.info()
