"""Internal Redis engine orchestration."""

from __future__ import annotations

from time import perf_counter_ns
from typing import Any

from mini_redis.invalidation.manager import InvalidationManager
from mini_redis.persistence.manager import PersistenceManager
from mini_redis.storage.benchmark import BenchmarkResult
from mini_redis.storage.benchmark import StorageBenchmarkSuite
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
        self._benchmark_suite = StorageBenchmarkSuite()

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
        mongo_write_elapsed = self._mongo.write_value(key, value)
        return self._format_set_response(mongo_write_elapsed)

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

    def dumpall(self) -> list[str]:
        # 전체 데이터 조회 전에도 만료 key를 먼저 정리해서 발표/디버깅 화면에 stale entry가 보이지 않게 한다.
        self._purge_expired_keys()
        items = self._storage.items()
        ttl_remaining = self._ttl.export_remaining(self._storage)
        lines: list[str] = []
        for key in sorted(items):
            ttl_seconds = ttl_remaining.get(key)
            ttl_display = "persistent" if ttl_seconds is None else f"{ttl_seconds}s"
            tags = self._invalidation.tags_for_key(key)
            tags_display = ",".join(tags) if tags else "-"
            lines.append(
                f"key={key} value={items[key]} ttl={ttl_display} tags={tags_display}"
            )
        return lines

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
        self._mongo.write_value(key, str(next_value))
        return next_value

    def flushdb(self) -> int:
        removed = self._storage.clear()
        self._ttl.clear_all()
        # FLUSHDB must wipe secondary indexes too or later INVALIDATE calls can see stale keys.
        self._invalidation.clear_all()
        self._persistence.append("FLUSHDB")
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
            return self._format_info_payload("Persistence", payload)
        if normalized == "MONGO":
            payload = self._mongo.info()
            payload["key_count"] = self.key_count()
            # INFO 응답은 RESP에서 안전하게 직렬화될 수 있도록 섹션별 문자열 포맷으로 통일한다.
            return self._format_info_payload("Mongo", payload)
        return "ERR unsupported INFO section"

    def inspect_storage(self, include_table: bool = False) -> str:
        payload = self._storage.inspect(include_table=include_table)
        payload["key_count"] = self.key_count()
        if not include_table:
            latest_storage_op = self._storage.latest_operation()
            last_request = (
                "n/a"
                if latest_storage_op is None
                else f"{latest_storage_op['elapsed_us'] / 1_000:.3f} ms"
            )
            return (
                "# Storage\r\n"
                f"[table size: {payload['active_capacity']}] "
                f"[resizing: {payload['is_rehashing']}] "
                f"[keys: {payload['key_count']}] "
                f"[rehash table size: {payload['rehash_capacity']}] "
                f"[progress: {payload['rehash_progress']}] "
                f"[last request: {last_request}]"
            )
        return self._format_info_payload("Storage", payload)

    def reset_storage_diagnostics(self) -> str:
        self._storage.reset_diagnostics()
        return "OK"

    def run_storage_probe(
        self,
        operations: int,
        *,
        mode: str = "insert",
    ) -> str:
        if operations <= 0:
            return "ERR operations must be a positive integer"

        self._storage.reset_diagnostics()
        prefix = "inspect:run:"
        normalized_mode = mode.lower()
        if normalized_mode not in {"insert", "update"}:
            return "ERR unsupported storage probe mode"

        lines = [f"# Storage {normalized_mode.title()} Run"]
        for index in range(operations):
            key = f"{prefix}{index}"
            value = str(index) if normalized_mode == "insert" else f"updated:{index}"
            if normalized_mode == "insert":
                lines.append(self.probe_set(key, value))
                continue
            lines.append(self.probe_update(key, value))
        return "\r\n".join(lines)

    def benchmark(
        self,
        target: str,
        operations: int,
        *,
        keep_data: bool = False,
    ) -> str:
        normalized = target.upper()
        if operations <= 0:
            return "ERR operations must be a positive integer"

        if normalized == "REDIS":
            result = self._benchmark_suite.benchmark_redis_set(
                self._storage,
                operations,
                key_prefix="bench:redis:",
                keep_data=keep_data,
            )
            return self._format_benchmark_result(result)

        if normalized == "MONGO":
            if not self._mongo.enabled:
                return "ERR MongoDB benchmark requires mongo integration to be enabled"
            result = self._benchmark_suite.benchmark_mongo_write(
                self._mongo,
                operations,
                key_prefix="bench:mongo:",
                keep_data=keep_data,
            )
            return self._format_benchmark_result(result)

        if normalized == "HYBRID":
            if not self._mongo.enabled:
                return "ERR hybrid benchmark requires mongo integration to be enabled"
            result = self._benchmark_suite.benchmark_hybrid_write(
                self._storage,
                self._mongo,
                operations,
                key_prefix="bench:hybrid:",
                keep_data=keep_data,
            )
            return self._format_benchmark_result(result)

        return "ERR unsupported benchmark target"

    def probe_set(
        self,
        key: str,
        value: str,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
    ) -> str:
        started_at_ns = perf_counter_ns()
        result = self.set(key, value, ttl_seconds=ttl_seconds, tags=tags)
        elapsed_us = (perf_counter_ns() - started_at_ns) / 1_000
        if isinstance(result, str) and result.startswith("ERR "):
            return result

        snapshot = self._storage.inspect(include_table=False)
        latest_storage_op = self._storage.latest_operation()
        return (
            f"[request: {elapsed_us / 1_000:.3f} ms ({elapsed_us:.3f} us)] "
            f"[table size: {snapshot['active_capacity']}] "
            f"[resizing: {snapshot['is_rehashing']}] "
            f"size={snapshot['size']} "
            f"rehash_capacity={snapshot['rehash_capacity']} "
            f"progress={snapshot['rehash_progress']}"
            + (
                ""
                if latest_storage_op is None
                else (
                    f" storage_{latest_storage_op['operation']}: "
                    f"{latest_storage_op['elapsed_us'] / 1_000:.3f} ms"
                    f" ({latest_storage_op['elapsed_us']:.3f} us)"
                )
            )
        )

    def probe_update(self, key: str, value: str) -> str:
        if self._storage.get(key) is None:
            return f"ERR key '{key}' does not exist for update probe"

        started_at_ns = perf_counter_ns()
        result = self.set(key, value)
        elapsed_us = (perf_counter_ns() - started_at_ns) / 1_000
        if isinstance(result, str) and result.startswith("ERR "):
            return result

        snapshot = self._storage.inspect(include_table=False)
        latest_storage_op = self._storage.latest_operation()
        return (
            f"[request: {elapsed_us / 1_000:.3f} ms ({elapsed_us:.3f} us)] "
            f"[table size: {snapshot['active_capacity']}] "
            f"[resizing: {snapshot['is_rehashing']}] "
            f"size={snapshot['size']} "
            f"rehash_capacity={snapshot['rehash_capacity']} "
            f"progress={snapshot['rehash_progress']}"
            + (
                ""
                if latest_storage_op is None
                else (
                    f" storage_{latest_storage_op['operation']}: "
                    f"{latest_storage_op['elapsed_us'] / 1_000:.3f} ms"
                    f" ({latest_storage_op['elapsed_us']:.3f} us)"
                )
            )
        )

    def config_get(self, key: str) -> list[str] | str:
        config = self._persistence.get_config(key)
        if isinstance(config, str):
            return config
        result: list[str] = []
        for config_key, config_value in config.items():
            result.extend([config_key, str(config_value)])
        return result

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

    def _format_info_payload(self, title: str, payload: dict[str, Any]) -> str:
        lines: list[str] = [f"# {title}"]

        def append_lines(prefix: str, value: Any) -> None:
            if isinstance(value, dict):
                for nested_key, nested_value in value.items():
                    next_prefix = f"{prefix}.{nested_key}" if prefix else str(nested_key)
                    append_lines(next_prefix, nested_value)
                return
            if isinstance(value, list):
                for index, nested_value in enumerate(value):
                    next_prefix = f"{prefix}.{index}" if prefix else str(index)
                    append_lines(next_prefix, nested_value)
                if not value:
                    lines.append(f"{prefix}:[]")
                return
            lines.append(f"{prefix}:{value}")

        for key, value in payload.items():
            append_lines(str(key), value)
        return "\r\n".join(lines)

    def _format_set_response(self, mongo_write_elapsed: float | None) -> str:
        if mongo_write_elapsed is None:
            return "OK"
        return f"OK mongo_write={mongo_write_elapsed:.6f}s"

    def _format_benchmark_result(self, result: BenchmarkResult) -> str:
        payload: dict[str, Any] = {
            "target": result.target,
            "operation": result.operation,
            "operations": result.operations,
            "elapsed_seconds": round(result.elapsed_seconds, 6),
            "ops_per_second": round(result.ops_per_second, 3),
        }
        payload.update(result.details)
        return self._format_info_payload("Benchmark", payload)
