"""MongoDB adapter seam."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class MongoAdapter:
    """Optional external database sync point."""

    def __init__(
        self,
        enabled: bool = False,
        *,
        uri: str = "mongodb://127.0.0.1:27017",
        database: str = "mini_redis",
        collection: str = "kv_store",
        server_selection_timeout_ms: int = 2000,
        client_factory: Callable[..., Any] | None = None,
    ) -> None:
        self.enabled = enabled
        self.uri = uri
        self.database = database
        self.collection = collection
        self.server_selection_timeout_ms = server_selection_timeout_ms
        self._client_factory = client_factory
        self._client: Any | None = None
        self._collection_handle: Any | None = None
        self._connected = False
        self.operations: list[dict[str, Any]] = []
        if self.enabled:
            self._connect()

    def upsert(self, key: str, value: str) -> None:
        if not self.enabled:
            return
        self._require_collection().update_one(
            {"_id": key},
            {"$set": {"value": value}},
            upsert=True,
        )
        self.operations.append({"action": "upsert", "key": key, "value": value})

    def delete(self, key: str) -> None:
        if not self.enabled:
            return
        self._require_collection().delete_one({"_id": key})
        self.operations.append({"action": "delete", "key": key})

    def clear(self) -> None:
        if not self.enabled:
            return
        self._require_collection().delete_many({})
        self.operations.append({"action": "clear"})

    def maybe_sync(self, key: str, value: str) -> None:
        # Compatibility shim for older engine code that still calls the original adapter hook name.
        self.upsert(key, value)

    def info(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "connected": self._connected,
            "uri": self.uri,
            "database": self.database,
            "collection": self.collection,
            "operation_count": len(self.operations),
            # Keep the old field name too so earlier tests/callers do not break on rename.
            "queued_operations": len(self.operations),
            "last_operation": self.operations[-1] if self.operations else None,
        }

    def _connect(self) -> None:
        client_factory = self._resolve_client_factory()
        try:
            client = client_factory(
                self.uri,
                serverSelectionTimeoutMS=self.server_selection_timeout_ms,
            )
            collection = client[self.database][self.collection]
            client.admin.command("ping")
        except Exception as exc:
            raise RuntimeError(
                f"Failed to connect to MongoDB at {self.uri}: {exc}"
            ) from exc

        self._client = client
        self._collection_handle = collection
        self._connected = True

    def _resolve_client_factory(self) -> Callable[..., Any]:
        if self._client_factory is not None:
            return self._client_factory
        try:
            from pymongo import MongoClient
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "MongoDB sync is enabled but pymongo is not installed."
            ) from exc
        return MongoClient

    def _require_collection(self) -> Any:
        if self._collection_handle is None:
            raise RuntimeError("MongoDB collection is not initialized.")
        return self._collection_handle
