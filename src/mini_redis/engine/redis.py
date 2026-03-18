"""Internal Redis engine orchestration."""

from __future__ import annotations

from typing import Any

from mini_redis.invalidation.manager import InvalidationManager
from mini_redis.persistence.manager import PersistenceManager
from mini_redis.storage.manager import StorageManager
from mini_redis.storage.mongo_manager import MongoManager
from mini_redis.storage.ttl import TTLManager


class Redis:
    """Orchestrate storage and supporting managers."""

    def __init__(
        self,
        storage: StorageManager,
        ttl: TTLManager,
        persistence: PersistenceManager,
        invalidation: InvalidationManager,
        mongo: MongoManager,
    ) -> None:
        self._storage = storage
        self._ttl = ttl
        self._persistence = persistence
        self._invalidation = invalidation
        self._mongo = mongo

    def ping(self) -> str:
        return "PONG"

    def get(self, key: str) -> str | None:
        self._purge_if_expired(key)
        return self._storage.get(key)

    def set(
        self,
        key: str,
        value: str,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        self._storage.set(key, value)
        self._ttl.set_expiration(key, ttl_seconds)
        if tags is not None:
            # Keep tag invalidation behavior from the other branch while merging Mongo support.
            # Without this, SET ... TAGS would silently stop participating in INVALIDATE.
            self._invalidation.set_tags(key, tags)
        # Persist tags together with the value so snapshot/AOF replay keeps invalidation semantics.
        self._persistence.append("SET", key, value, ttl_seconds, tags)
        self._mongo.sync_value(key, value)
        return "OK"

    def delete(self, key: str) -> int:
        self._ttl.clear_expiration(key)
        # Clear the secondary invalidation index before deleting the value so tag lookups stay in sync.
        self._invalidation.clear_key(key)
        deleted = 1 if self._storage.delete(key) else 0
        self._persistence.append("DELETE", key)
        if deleted:
            self._mongo.delete_key(key)
        return deleted

    def exists(self, key: str) -> int:
        self._purge_if_expired(key)
        return 1 if self._storage.exists(key) else 0

    def expire(self, key: str, ttl_seconds: int) -> int:
        self._purge_if_expired(key)
        if not self._storage.exists(key):
            return 0
        self._ttl.set_expiration(key, ttl_seconds)
        self._persistence.append("EXPIRE", key, ttl_seconds)
        return 1

    def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        return self._ttl.ttl(key, self._storage)

    def keys(self) -> list[str]:
        self._purge_expired_keys()
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
        self._mongo.sync_value(key, str(next_value))
        return next_value

    def flushdb(self) -> int:
        removed = self._storage.clear()
        self._ttl.clear_all()
        # FLUSHDB must wipe secondary indexes too or later INVALIDATE calls can see stale keys.
        self._invalidation.clear_all()
        self._persistence.append("FLUSHDB")
        if removed:
            self._mongo.clear()
        return removed

    def invalidate(self, tag: str) -> int:
        removed = 0
        for key in self._invalidation.invalidate(tag):
            self._ttl.clear_expiration(key)
            if self._storage.delete(key):
                removed += 1
        # Keep INVALIDATE in AOF so replay does not resurrect cache entries that were already evicted.
        self._persistence.append("INVALIDATE", tag)
        return removed

    def save(self) -> str:
        snapshot = {
            "storage": self._storage.items(),
            "ttl": self._ttl.export(),
            # Snapshot must include invalidation state so INVALIDATE keeps working after restore.
            "invalidation": self._invalidation.export(),
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
        if normalized == "MONGO":
            payload = self._mongo.info()
            payload["key_count"] = self.key_count()
            return payload
        return "ERR unsupported INFO section"

    def config_get(self, key: str) -> dict[str, Any] | str:
        return self._persistence.get_config(key)

    def config_set(self, key: str, value: str) -> str:
        return self._persistence.set_config(key, value)

    def rewrite_aof(self) -> str:
        entries: list[dict[str, Any]] = []
        # Expire first so compaction only captures live data and live tag relationships.
        self._purge_expired_keys()
        ttl_remaining = self._ttl.export_remaining(self._storage)
        for key, value in self._storage.items().items():
            ttl_seconds = ttl_remaining.get(key)
            args: list[Any] = [key, value, ttl_seconds, self._invalidation.tags_for_key(key)]
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
        # Restore invalidation metadata alongside values so cache-tag behavior survives restart.
        self._invalidation.load_tag_map(
            {
                str(tag): list(keys)
                for tag, keys in snapshot.get("invalidation", {}).items()
                if isinstance(keys, list)
            }
        )
        expired_keys = self._ttl.load_expirations(
            {str(key): str(value) for key, value in snapshot.get("ttl", {}).items()},
            self._storage,
        )
        for key in expired_keys:
            self._invalidation.clear_key(key)

    def replay_operation(self, operation: str, args: list[Any]) -> None:
        name = operation.upper()
        if name == "SET" and len(args) >= 2:
            ttl_seconds = None if len(args) < 3 or args[2] is None else int(args[2])
            tags = self._coerce_tags(args[3]) if len(args) >= 4 else None
            key = str(args[0])
            self._storage.set(key, str(args[1]))
            self._ttl.set_expiration(key, ttl_seconds)
            if tags is not None:
                self._invalidation.set_tags(key, tags)
            return
        if name == "DELETE" and args:
            key = str(args[0])
            self._ttl.clear_expiration(key)
            self._invalidation.clear_key(key)
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
        if name == "INVALIDATE" and args:
            for key in self._invalidation.invalidate(str(args[0])):
                self._ttl.clear_expiration(key)
                self._storage.delete(key)
            return
        if name == "FLUSHDB":
            self._storage.clear()
            self._ttl.clear_all()
            self._invalidation.clear_all()
            return

    def reset_state(self) -> None:
        self._storage.clear()
        self._ttl.clear_all()
        self._invalidation.clear_all()

    def key_count(self) -> int:
        self._purge_expired_keys()
        return len(self._storage.items())

    def quit(self) -> str:
        return "BYE"

    def _purge_if_expired(self, key: str) -> None:
        # TTLManager only knows about expirations and storage; Redis cleans sibling indexes afterward.
        if self._ttl.purge_if_expired(key, self._storage):
            self._invalidation.clear_key(key)

    def _purge_expired_keys(self) -> None:
        for key in self._ttl.purge_expired_keys(self._storage):
            self._invalidation.clear_key(key)

    def _coerce_tags(self, raw_tags: Any) -> list[str] | None:
        if raw_tags is None:
            return None
        if isinstance(raw_tags, list):
            return [str(tag) for tag in raw_tags]
        return [str(raw_tags)]
