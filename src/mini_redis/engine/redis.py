"""Internal Redis engine orchestration."""

from __future__ import annotations

from mini_redis.persistence.invalidation import InvalidationManager
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
        invalidation: InvalidationManager,
        mongo: MongoAdapter,
    ) -> None:
        self._storage = storage
        self._ttl = ttl
        self._persistence = persistence
        self._invalidation = invalidation
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
        self._invalidation.notify(key)
        self._mongo.maybe_sync(key, value)
        return "OK"

    def delete(self, key: str) -> int:
        self._ttl.clear_expiration(key)
        deleted = 1 if self._storage.delete(key) else 0
        self._persistence.append("DELETE", key)
        if deleted:
            self._invalidation.notify(key)
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
        self._invalidation.notify(key)
        self._mongo.maybe_sync(key, str(next_value))
        return next_value

    def flushdb(self) -> int:
        removed = self._storage.clear()
        self._ttl.clear_all()
        self._persistence.append("FLUSHDB")
        return removed

    def save(self) -> str:
        snapshot = {
            "storage": self._storage.items(),
            "ttl": self._ttl.export(),
            "operation_log": [list(entry) for entry in self._persistence.operation_log],
        }
        path = self._persistence.save_snapshot(snapshot)
        return str(path)

    def quit(self) -> str:
        return "BYE"
