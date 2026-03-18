"""Internal Redis engine orchestration."""

from __future__ import annotations

from typing import Any

from mini_redis.persistence.manager import PersistenceManager
from mini_redis.storage.manager import StorageManager
from mini_redis.storage.mongo_adapter import MongoAdapter
from mini_redis.storage.ttl import TTLManager


class Redis:
    """Orchestrate storage and supporting managers."""

    def __init__(
        self,
        storage: StorageManager,
        ttl: TTLManager,
        persistence: PersistenceManager,
        mongo: MongoAdapter,
    ) -> None:
        self._storage = storage
        self._ttl = ttl
        self._persistence = persistence
        self._mongo = mongo

    def ping(self) -> str:
        return "PONG"

    def get(self, key: str) -> str | None:
        self._ttl.purge_if_expired(key, self._storage)
        return self._storage.get(key)

    def set(self, key: str, value: str, ttl_seconds: int | None = None) -> str:
        self._storage.set(key, value)
        self._ttl.set_expiration(key, ttl_seconds)
        self._persistence.append("SET", key, value, ttl_seconds)
        self._mongo.maybe_sync(key, value)
        return "OK"

    def delete(self, key: str) -> int:
        self._ttl.clear_expiration(key)
        deleted = 1 if self._storage.delete(key) else 0
        self._persistence.append("DELETE", key)
        return deleted

    def exists(self, key: str) -> int:
        self._ttl.purge_if_expired(key, self._storage)
        return 1 if self._storage.exists(key) else 0

    def expire(self, key: str, ttl_seconds: int) -> int:
        self._ttl.purge_if_expired(key, self._storage)
        if not self._storage.exists(key):
            return 0
        self._ttl.set_expiration(key, ttl_seconds)
        self._persistence.append("EXPIRE", key, ttl_seconds)
        return 1

    def ttl(self, key: str) -> int:
        return self._ttl.ttl(key, self._storage)

    def keys(self) -> list[str]:
        self._ttl.purge_expired_keys(self._storage)
        return self._storage.keys()

    def mget(self, keys: list[str]) -> list[str | None]:
        return [self.get(key) for key in keys]

    def incr(self, key: str) -> int | str:
        current = self.get(key)
        if current is None:
            next_value = 1
        else:
            try:
                next_value = int(current) + 1
            except ValueError:
                return "ERR value is not an integer or out of range"

        self._storage.set(key, str(next_value))
        self._persistence.append("INCR", key)
        self._mongo.maybe_sync(key, str(next_value))
        return next_value

    def flushdb(self) -> int:
        removed = self._storage.clear()
        self._ttl.clear_all()
        self._persistence.append("FLUSHDB")
        return removed

    def save(self) -> str:
        # Snapshot payloads carry the AOF offset so restore can replay only newer entries.
        snapshot = {
            "storage": self._storage.items(),
            "ttl": self._ttl.export(),
            "operation_log": [list(entry) for entry in self._persistence.operation_log],
            "aof_offset": len(self._persistence.operation_log),
        }
        path = self._persistence.save_snapshot(snapshot)
        self._persistence.record_snapshot_save()
        return str(path)

    def bgsave(self) -> dict[str, Any]:
        return self._persistence.start_background_save(self.save)

    def load(self) -> str:
        loaded = self._persistence.load_snapshot(self)
        if not loaded:
            return "ERR snapshot file does not exist"
        return "OK"

    def info(self, section: str) -> dict[str, Any] | str:
        normalized = section.upper()
        if normalized == "PERSISTENCE":
            payload = self._persistence.info()
            payload["key_count"] = self.key_count()
            return payload
        return "ERR unsupported INFO section"

    def config_get(self, key: str) -> dict[str, Any] | str:
        return self._persistence.get_config(key)

    def config_set(self, key: str, value: str) -> str:
        return self._persistence.set_config(key, value)

    def rewrite_aof(self) -> str:
        entries: list[dict[str, Any]] = []
        ttl_remaining = self._ttl.export_remaining(self._storage)
        # Rebuild AOF from live state instead of replaying the full historical log.
        for key, value in self._storage.items().items():
            ttl_seconds = ttl_remaining.get(key)
            args: list[Any] = [key, value, ttl_seconds]
            entries.append({"op": "SET", "args": args})
        path = self._persistence.rewrite_aof(entries)
        return str(path)

    def bgrewriteaof(self) -> dict[str, Any]:
        return self._persistence.start_background_rewrite(self.rewrite_aof)

    def repair_aof(self) -> dict[str, Any]:
        return self._persistence.repair_aof()

    def restore_snapshot(self, snapshot: dict[str, Any]) -> None:
        self._storage.load_items(
            {str(key): str(value) for key, value in snapshot.get("storage", {}).items()}
        )
        self._ttl.load_expirations(
            {str(key): str(value) for key, value in snapshot.get("ttl", {}).items()},
            self._storage,
        )

    def replay_operation(self, operation: str, args: list[Any]) -> None:
        # Replay bypasses normal command handlers so restore can rebuild state quickly.
        name = operation.upper()
        if name == "SET" and len(args) >= 2:
            ttl_seconds = None if len(args) < 3 or args[2] is None else int(args[2])
            self._storage.set(str(args[0]), str(args[1]))
            self._ttl.set_expiration(str(args[0]), ttl_seconds)
            return
        if name == "DELETE" and args:
            key = str(args[0])
            self._ttl.clear_expiration(key)
            self._storage.delete(key)
            return
        if name == "EXPIRE" and len(args) == 2:
            key = str(args[0])
            if self._storage.exists(key):
                self._ttl.set_expiration(key, int(args[1]))
            return
        if name == "INCR" and args:
            current = self._storage.get(str(args[0]))
            next_value = 1 if current is None else int(current) + 1
            self._storage.set(str(args[0]), str(next_value))
            return
        if name == "FLUSHDB":
            self._storage.clear()
            self._ttl.clear_all()
            return

    def reset_state(self) -> None:
        self._storage.clear()
        self._ttl.clear_all()

    def key_count(self) -> int:
        self._ttl.purge_expired_keys(self._storage)
        return len(self._storage.items())

    def quit(self) -> str:
        return "BYE"
