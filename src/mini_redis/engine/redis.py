"""Internal Redis engine orchestration."""

from __future__ import annotations

from typing import Any

from mini_redis.invalidation.manager import InvalidationManager
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
            # TAGS 옵션이 들어온 경우에만 태그 인덱스를 갱신한다.
            # 즉, 일반 SET은 기존 태그 관계를 유지해서 캐시 그룹 연결이 조용히 사라지지 않게 한다.
            self._invalidation.set_tags(key, tags)
        # AOF에도 태그 정보를 함께 남겨야 재시작 후 invalidate 동작이 그대로 복구된다.
        self._persistence.append("SET", key, value, ttl_seconds, tags)
        self._mongo.maybe_sync(key, value)
        return "OK"

    def delete(self, key: str) -> int:
        self._ttl.clear_expiration(key)
        # key 삭제 시 value만 지우면 tag_map에 stale key가 남기 때문에
        # invalidation 인덱스도 먼저 정리한다.
        self._invalidation.clear_key(key)
        deleted = 1 if self._storage.delete(key) else 0
        self._persistence.append("DELETE", key)
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
        self._mongo.maybe_sync(key, str(next_value))
        return next_value

    def flushdb(self) -> int:
        removed = self._storage.clear()
        self._ttl.clear_all()
        # store 전체 삭제와 함께 보조 인덱스도 비워야 이후 invalidate가 잘못된 key를 반환하지 않는다.
        self._invalidation.clear_all()
        self._persistence.append("FLUSHDB")
        return removed

    def invalidate(self, tag: str) -> int:
        # InvalidationManager는 "이 태그에 연결된 key 목록"만 돌려주고,
        # 실제 데이터 삭제와 TTL 정리는 Redis가 책임진다.
        removed = 0
        for key in self._invalidation.invalidate(tag):
            self._ttl.clear_expiration(key)
            if self._storage.delete(key):
                removed += 1
        # INVALIDATE 자체도 AOF에 남겨야 snapshot 이후 tail replay 시
        # 이미 무효화된 캐시가 다시 살아나지 않는다.
        self._persistence.append("INVALIDATE", tag)
        return removed

    def save(self) -> str:
        # Snapshot payloads carry the AOF offset so restore can replay only newer entries.
        snapshot = {
            "storage": self._storage.items(),
            "ttl": self._ttl.export(),
            # invalidation index도 snapshot에 포함해야 복구 직후 바로 INVALIDATE가 동작한다.
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
        return "ERR unsupported INFO section"

    def config_get(self, key: str) -> dict[str, Any] | str:
        return self._persistence.get_config(key)

    def config_set(self, key: str, value: str) -> str:
        return self._persistence.set_config(key, value)

    def rewrite_aof(self) -> str:
        entries: list[dict[str, Any]] = []
        # AOF 재작성 전에 만료 key를 먼저 걷어내야 이미 죽은 캐시가
        # 새 AOF에 다시 살아있는 상태로 기록되지 않는다.
        self._purge_expired_keys()
        ttl_remaining = self._ttl.export_remaining(self._storage)
        # Rebuild AOF from live state instead of replaying the full historical log.
        for key, value in self._storage.items().items():
            ttl_seconds = ttl_remaining.get(key)
            # compaction 이후에도 태그 기반 invalidation이 유지되도록
            # 현재 key에 연결된 tags를 SET 엔트리에 같이 기록한다.
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
        # snapshot에는 실제 데이터(store)와 보조 인덱스(invalidation)가 함께 들어 있으므로
        # 복구 시에도 같은 순서로 다시 세팅한다.
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
        # snapshot 저장 시점에는 살아 있었지만 복구 시점에는 이미 만료된 key가 있을 수 있다.
        # 이런 key는 storage에서 제거된 뒤 invalidation 인덱스에서도 반드시 같이 정리한다.
        for key in expired_keys:
            self._invalidation.clear_key(key)

    def replay_operation(self, operation: str, args: list[Any]) -> None:
        # Replay bypasses normal command handlers so restore can rebuild state quickly.
        name = operation.upper()
        if name == "SET" and len(args) >= 2:
            ttl_seconds = None if len(args) < 3 or args[2] is None else int(args[2])
            tags = self._coerce_tags(args[3]) if len(args) >= 4 else None
            key = str(args[0])
            self._storage.set(key, str(args[1]))
            self._ttl.set_expiration(key, ttl_seconds)
            if tags is not None:
                # AOF replay로도 동일한 tag_map이 재구성돼야 invalidate 결과가 재시작 전과 동일하다.
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
            # 과거에 실행된 INVALIDATE도 재시작 후 그대로 반영되도록 AOF replay에서 다시 수행한다.
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
        # TTLManager는 storage 삭제까지만 알고 있으므로,
        # 만료가 실제로 발생했을 때 invalidation 보조 인덱스는 Redis가 이어서 정리한다.
        if self._ttl.purge_if_expired(key, self._storage):
            self._invalidation.clear_key(key)

    def _purge_expired_keys(self) -> None:
        # bulk purge에서도 동일하게 만료된 key 목록을 받아 tag_map을 함께 청소한다.
        for key in self._ttl.purge_expired_keys(self._storage):
            self._invalidation.clear_key(key)

    def _coerce_tags(self, raw_tags: Any) -> list[str] | None:
        # AOF/snapshot에서 들어오는 다양한 직렬화 형태를 list[str]로 통일한다.
        if raw_tags is None:
            return None
        if isinstance(raw_tags, list):
            return [str(tag) for tag in raw_tags]
        return [str(raw_tags)]
